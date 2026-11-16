"""면접 보고서 (루브릭 설계서 8·10.2, 아키텍처 9.4). worker가 응시를 마친 지원자 1명씩 부른다.

항목 점수는 실시간으로 낸 답변별 점수의 평균이다. 면접이 끝난 뒤 다시 채점하지 않는다 (8.2).
- 내용: content_score 평균, 근거는 답변별 채점 이유를 질문 순서대로 모은 것
- 언어: speech_score 평균, 근거는 측정값(간투사·침묵·응답 지연)
- 비언어: expression_score 평균(None은 뺌), 근거는 주요 표정 횟수. 모두 None이면 이 항목은 내지 않는다
강점·확인 필요도 답변별 점수와 이유로 코드가 만든다. LLM은 인재상 적합도(번호 고르기)와 요약에만 쓴다.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from langchain_core.runnables import Runnable

from app.chains.answer_content import RELEVANCE_CAP_NOTES
from app.chains.structured import invoke_structured
from app.core.llm import get_chat_model
from app.prompts import interview_report as prompts
from app.rag.evidence import split_sentences
from app.schemas.internal import AnswerRecord, PostingBrief
from app.schemas.llm_outputs import SummaryOutput, TalentFitOutput

CONTENT, SPEECH, EXPRESSION = "내용", "언어", "비언어"
ITEMS = (CONTENT, SPEECH, EXPRESSION)  # eval_criteria의 면접 항목 이름과 같아야 한다

STRENGTH_FROM = 80  # 서류 보고서와 같은 기준 (루브릭 설계서 10.1, 제안)
CHECK_BELOW = 60
MAX_STRENGTHS = 2
MAX_FIT_SENTENCES = 2
DELAY_SEC = 10  # 응답 지연 감점 기준 (루브릭 설계서 4.2)
NOT_ANSWERED = RELEVANCE_CAP_NOTES["안 함"]  # 내용 채점이 '질문에 답하지 않음'으로 판정한 답변의 이유 끝 문구
NO_FIT_NOTE = "면접 답변에서 이 인재상을 보여 주는 내용을 찾지 못했다."
NO_CONTENT_NOTE = "내용 점수가 있는 답변이 없다."
LOW_CONTENT_NOTE = "내용 점수가 낮다."
_BULLET = re.compile(r"^[-•*]\s*")
# 확인 필요에 보일 채점 이유 문장: 모자란 점을 말하는 문장. 첫 문장은 대개 칭찬이라 쓰면 '확인 필요'와 어긋난다 (실험 R1)
_WEAK = re.compile(r"부족|않|없|낮|반대|다르|빗나|모호|아쉽")
# 답변 채점 이유에 남은 영어 축 이름. 요약에 그대로 옮겨 쓴다 (R1)
_AXIS_WORDS = {"specificity": "구체성", "relevance": "질문 적합성"}


@dataclass(frozen=True)
class ItemResult:
    name: str
    score: Decimal
    evidence: str


@dataclass(frozen=True)
class Fit:
    talent_content: str
    evidence: str


@dataclass(frozen=True)
class Point:
    point_type: str  # 강점, 확인 필요
    item: str
    content: str


@dataclass
class InterviewReport:
    items: list[ItemResult]
    fits: list[Fit]
    points: list[Point]
    summary: str
    llm_outputs: dict = field(default_factory=dict)  # 평가 스크립트가 원래 출력을 남긴다


def build_interview_report(posting: PostingBrief, answers: list[AnswerRecord], model: Runnable | None = None) -> InterviewReport:
    """① 항목 점수(코드) → ② 인재상 적합도(LLM 번호 고르기) → ③ 강점·확인 필요(코드) → ④ 요약(LLM)."""
    model = model or get_chat_model()
    items = score_items(answers)
    fit_out, fits = _fits(model, posting, answers)
    points = _points(answers, items)
    summary = invoke_structured(model, prompts.summary(_report_brief(answers, items, fits, points)), SummaryOutput)
    return InterviewReport(items, fits, points, summary.summary,
                           {"talent_fit": fit_out.model_dump() if fit_out else None, "summary": summary.model_dump()})


def score_items(answers: list[AnswerRecord]) -> list[ItemResult]:
    """항목 점수와 근거 텍스트 (루브릭 설계서 8.2). 질문 유형별 가중치는 두지 않는다."""
    items = []
    contents = [a for a in answers if a.content_score is not None]
    if contents:
        reasons = [f"Q{i}. {a.content_reason or ''}".strip() for i, a in enumerate(answers, start=1) if a.content_score is not None]
        items.append(ItemResult(CONTENT, _avg(a.content_score for a in contents), "\n".join(reasons)))
    if answers:
        delayed = sum(a.response_delay_sec >= DELAY_SEC for a in answers)
        evidence = (f"평균 간투사 {_one(sum(a.filler_count for a in answers) / len(answers))}회, "
                    f"평균 침묵 {_one(sum(a.silence_sec for a in answers) / len(answers))}초, "
                    f"응답 지연 {DELAY_SEC}초 이상 {delayed}회 (답변 {len(answers)}개)")
        items.append(ItemResult(SPEECH, _avg(a.speech_score for a in answers), evidence))
    faces = [a for a in answers if a.expression_score is not None]
    if faces:
        counts = Counter(a.main_expression for a in faces if a.main_expression)
        evidence = "주요 표정 " + ", ".join(f"{e} {n}회" for e, n in counts.most_common()) + f" (표정을 분석한 답변 {len(faces)}개)"
        items.append(ItemResult(EXPRESSION, _avg(a.expression_score for a in faces), evidence))
    return items


def _fits(model: Runnable, posting: PostingBrief, answers: list[AnswerRecord]) -> tuple[TalentFitOutput | None, list[Fit]]:
    """인재상 문장마다 LLM이 고른 답변 문장 번호를 검증해 답변 원문을 근거로 넣는다. 지원자 말을 바꿔 쓰지 않는다.
    서류 보고서에서 LLM이 근거를 직접 쓰게 했더니 원문과 다른 문장을 지어냈다 (RAG 설계서 5.8 D4-v4)."""
    talents = _talents(posting)
    sentences = _answer_sentences(answers)
    if not talents:
        return None, []
    if not sentences:
        return None, [Fit(text, NO_FIT_NOTE) for _, text in talents]
    talent_lines = "\n".join(f"[{tid}] {text}" for tid, text in talents)
    out = invoke_structured(model, prompts.talent_fit(talent_lines, _numbered_answers(answers, sentences)), TalentFitOutput)
    picked = {f.talent_id: f.sentence_ids for f in out.fits}
    low = {f"Q{n}" for n, a in enumerate(answers, start=1) if a.content_score is not None and a.content_score < CHECK_BELOW}
    fits = []
    for tid, text in talents:
        ids = [sid for sid in dict.fromkeys(picked.get(tid, [])) if sid in sentences]  # 없는 번호는 버린다
        if tid.startswith("기"):
            # 기능적(직무) 인재상은 내용 점수가 낮은 답변으로 확인하지 않는다. 문서가 채택하지 않은 방법을
            # 근거로 골랐다 (R1 R3 '청크를 2천 토큰으로'). 비기능적(태도)은 점수와 상관없다 ('잘 모르겠습니다'의 정직함)
            ids = [sid for sid in ids if sid.split("-")[0] not in low]
        ids = ids[:MAX_FIT_SENTENCES]
        evidence = " / ".join(f"{sid.split('-')[0]} 답변: \"{sentences[sid]}\"" for sid in ids)
        fits.append(Fit(text, evidence or NO_FIT_NOTE))
    return out, fits


def _points(answers: list[AnswerRecord], items: list[ItemResult]) -> list[Point]:
    """강점·확인 필요 (루브릭 설계서 10.2). 답변별 점수와 채점 이유로 만든다.
    - 강점: 내용 점수가 STRENGTH_FROM 이상인 답변(높은 순 최대 MAX_STRENGTHS개)의 채점 이유
    - 확인 필요(내용): 질문에 답하지 않았다고 채점된 답변, 그 밖에 내용 점수가 CHECK_BELOW 미만인 답변
    - 확인 필요(언어·비언어): 항목 점수가 CHECK_BELOW 미만이면 측정값"""
    points = []
    numbered = list(enumerate(answers, start=1))
    strong = sorted(((n, a) for n, a in numbered if a.content_score is not None and a.content_score >= STRENGTH_FROM),
                    key=lambda x: -x[1].content_score)[:MAX_STRENGTHS]
    for n, a in strong:
        points.append(Point("강점", CONTENT, f"Q{n} '{a.question_text}': {_first_sentence(_korean(a.content_reason or ''))}"))
    for n, a in numbered:
        if a.content_reason and NOT_ANSWERED in a.content_reason:
            points.append(Point("확인 필요", CONTENT, f"Q{n} '{a.question_text}': 질문이 묻는 것에 답하지 않았다. 같은 내용을 다시 확인한다."))
        elif a.content_score is not None and a.content_score < CHECK_BELOW:
            points.append(Point("확인 필요", CONTENT, f"Q{n} '{a.question_text}': {_weak_sentence(a.content_reason)}"))
    for item in items:
        if item.name != CONTENT and item.score < CHECK_BELOW:
            points.append(Point("확인 필요", item.name, f"{item.name} 점수가 낮다: {item.evidence}"))
    return points


def _report_brief(answers: list[AnswerRecord], items: list[ItemResult], fits: list[Fit], points: list[Point]) -> str:
    """요약을 쓸 자료. 점수는 높음·보통·낮음으로 넣는다. 숫자를 넣으면 요약에 옮겨 쓴다 (서류 D6-v6)."""
    parts = [f"[{i.name}] 항목 점수 {_band(i.score)}" for i in items]
    for a in answers:
        level = _band(a.content_score) if a.content_score is not None else "채점 안 됨"
        parts.append(f"[질문] {a.question_text}\n내용 점수 {level}. {_korean(a.content_reason or '')}".strip())
    # 확인된 것과 안 된 것을 나눠 준다. 한 목록으로 주면 확인된 인재상을 확인되지 않았다고 썼다 (R1)
    found = [f.talent_content for f in fits if f.evidence != NO_FIT_NOTE]
    missing = [f.talent_content for f in fits if f.evidence == NO_FIT_NOTE]
    parts.append("[면접에서 확인된 인재상]\n" + ("\n".join(f"- {t}" for t in found) or "- 없음"))
    parts.append("[면접에서 확인되지 않은 인재상]\n" + ("\n".join(f"- {t}" for t in missing) or "- 없음"))
    parts.append("[강점·확인 필요]\n" + ("\n".join(
        f"- ({p.point_type}, {p.item}) {_korean(_QNUM.sub('', p.content))}" for p in points) or "- 없음"))
    return "\n\n".join(parts)


def _talents(posting: PostingBrief) -> list[tuple[str, str]]:
    """인재상 문장에 번호를 붙인다. 기능적은 '기-n', 비기능적은 '비-n' (서류 보고서와 같은 번호)."""
    out = []
    for prefix, text in (("기", posting.functional_talent), ("비", posting.nonfunctional_talent)):
        sentences = [s for s in (_BULLET.sub("", s) for s in split_sentences(text or "")) if s]
        out += [(f"{prefix}-{i}", s) for i, s in enumerate(sentences, start=1)]
    return out


def _answer_sentences(answers: list[AnswerRecord]) -> dict[str, str]:
    return {f"Q{n}-{i}": s for n, a in enumerate(answers, start=1)
            for i, s in enumerate(split_sentences(a.corrected_text or ""), start=1)}


def _numbered_answers(answers: list[AnswerRecord], sentences: dict[str, str]) -> str:
    blocks = []
    for n, a in enumerate(answers, start=1):
        lines = [f"[{sid}] {text}" for sid, text in sentences.items() if sid.startswith(f"Q{n}-")]
        blocks.append(f"Q{n}. {a.question_text}\n" + ("\n".join(lines) or "(답변 없음)"))
    return "\n\n".join(blocks)


_QNUM = re.compile(r"^Q\d+ ")


def _korean(text: str) -> str:
    for word, korean in _AXIS_WORDS.items():
        text = text.replace(word, korean)
    return text


def _weak_sentence(reason: str | None) -> str:
    """채점 이유에서 모자란 점을 말하는 문장. 없으면 일치 단계 문장, 그것도 없으면 '내용 점수가 낮다.'"""
    sentences = split_sentences(_korean(reason or ""))
    weak = next((s for s in sentences if _WEAK.search(s)), None)
    match = next((s for s in sentences if "일치 단계" in s), None)
    return weak or match or LOW_CONTENT_NOTE


def _first_sentence(reason: str | None) -> str:
    sentences = split_sentences(reason or "")
    return sentences[0] if sentences else "채점 이유가 없다."


def _band(score: Decimal) -> str:
    return "높음" if score >= STRENGTH_FROM else "낮음" if score < CHECK_BELOW else "보통"


def _avg(values) -> Decimal:
    values = [Decimal(v) for v in values]
    return (sum(values) / len(values)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _one(value) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
