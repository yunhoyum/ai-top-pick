"""서류 보고서 항목 점수 (루브릭 설계서 7장, RAG 설계서 4.1).

항목(이력서, 기술 적용 사례, 포트폴리오, 자기소개)마다 LLM을 여러 번 부른다.
1. 항목 읽기: 회사 자료 없이 지원자가 쓴 것(주장)과 회사와 상관없는 축 점수를 받는다.
2. 주장 비교: 주장마다 따로 회사 자료와 비교해 같음·반대·문서에 없음과 근거 번호를 받는다.
회사 일치 축 점수와 항목 점수는 코드가 계산한다.

회사 일치 축 = 근거 번호가 검증된 '같음' 주장의 비율 × 100 (2026-11-11 결정).
면접(㉡ 50점)과 달리 '문서에 없음'도 0점으로 센다. 서류의 일치 축은 지원자가 한 일이 회사 업무와
얼마나 겹치는지를 보므로, 관계없는 경험이 많을수록 낮아야 한다.
"""

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel

from app.chains.structured import invoke_structured
from app.clients.embed import EmbedClient
from app.core.config import get_settings
from app.core.llm import get_chat_model
from app.prompts import document_report as prompts
from app.rag.evidence import merge_contexts, number_sentences, split_sentences
from app.rag.retriever import Chunk, search_company_docs
from app.schemas.internal import ApplicantDocuments, PostingBrief
from app.schemas.llm_outputs import (
    ClaimJudgment,
    EssayReadOutput,
    FitOutput,
    PointsOutput,
    PortfolioReadOutput,
    ResumeReadOutput,
    SkillCaseReadOutput,
    SummaryOutput,
)

RESUME, SKILL_CASE, PORTFOLIO, ESSAY = "이력서", "기술 적용 사례", "포트폴리오", "자기소개"

# 인재상·직무 설명 문장 번호의 앞글자. 프로젝트 문서 문장은 '후보 순번-문장 순번'이다
JOB, FUNCTIONAL, NONFUNCTIONAL = ("직", "직무 설명"), ("기", "기능적 인재상"), ("비", "비기능적 인재상")
_SENTENCE_ID = re.compile(r"(?:\d+|[직기비])-\d+")
_BULLET = re.compile(r"^[-•*]\s*")

NO_TEXT_NOTE = "서류에 이 항목의 내용이 없어 0점으로 채점했다."
SKILL_ONLY_NOTE = "공고가 학력·경력·프로젝트를 고르지 않아 필수 기술 점수만으로 채점했다."
NO_CLAIM_NOTE = "서류에서 지원자가 한 일을 찾지 못해 회사 일치 축을 0점으로 채점했다."
NO_FIT_NOTE = "서류에서 이 인재상과 맞는 경험을 찾지 못했다."

# 루브릭 설계서 7.3의 축 이름. 강점·확인 필요 프롬프트에 쓴다
AXIS_NAMES = {
    "experience": "직무 관련 경험", "skill": "필수 기술 수준", "talent_match": "기능적 인재상 일치",
    "problem": "문제 정의", "process": "해결 과정·기술 선택 근거", "result": "결과·성과", "doc_match": "회사 업무 일치",
    "decision": "의사결정 방식", "depth": "기술 깊이",
    "format": "형식(주장-근거 명확도)", "logic": "논리성", "company_match": "회사 일치도",
}


@dataclass(frozen=True)
class SourceSentence:
    """번호를 붙인 회사 자료 문장. 근거로 쓰이면 evidence_sentence에 사본으로 저장한다."""

    id: str
    text: str
    source_type: str  # 기능적 인재상, 비기능적 인재상, 직무 설명, 프로젝트 문서
    source_id: int | None = None  # 프로젝트 문서만 document_id
    chunk_id: int | None = None  # 프로젝트 문서만


@dataclass(frozen=True)
class Match:
    """회사 일치 축 하나의 결과."""

    score: Decimal
    counts: dict[str, int]  # 같음, 반대, 문서에 없음. 근거 번호가 모두 빠진 같음·반대는 문서에 없음으로 센다
    evidence: list[SourceSentence]
    judgments: list[dict]
    # 주장마다 (주장, 코드가 정한 판정, 번호가 검증된 회사 자료 문장). 거르기 전이다.
    # 강점·확인 필요가 쓴다
    claims: list[tuple[str, str, list[SourceSentence]]] = field(default_factory=list)


@dataclass(frozen=True)
class ItemScore:
    name: str
    score: Decimal  # 0~100, 소수 둘째 자리 (report_score.score)
    reason: str  # report_score.evidence
    evidence: list[SourceSentence]  # → evidence_sentence(report_id, criteria_id)
    axes: dict[str, Decimal]  # 축 점수. 저장하지 않는다. 평가·디버깅용이다
    llm_output: dict
    matches: dict[str, Match] = field(default_factory=dict)  # 회사 일치 축 key → 결과


@dataclass(frozen=True)
class Fit:
    """report_fit 한 줄. 인재상 문장 하나와 그에 맞는 서류 내용."""

    talent_content: str
    evidence: str


@dataclass(frozen=True)
class Point:
    """report_point 한 줄."""

    point_type: str  # 강점, 확인 필요
    item: str  # 관련 평가 항목 이름. API가 criteria_id로 바꾼다
    content: str


@dataclass(frozen=True)
class DocumentReport:
    items: list[ItemScore]
    fits: list[Fit]
    points: list[Point]
    summary: str  # stage_report.ai_summary
    llm_output: dict  # {"fits": [...], "points": {항목: 출력}, "summary": 출력}. 평가·디버깅용이다


def score_document_items(
    posting: PostingBrief,
    documents: ApplicantDocuments,
    model: Runnable | None = None,
    search: Callable[[list[str]], list[Chunk]] | None = None,
    embed: EmbedClient | None = None,
) -> list[ItemScore]:
    """search: 항목 텍스트로 그 공고의 프로젝트 문서를 찾는다. 없으면 search_company_docs를 쓴다.
    embed: 근거 문장 거르기에 쓴다."""
    model = model or get_chat_model()
    embed = embed or EmbedClient()
    search = search or (lambda texts: search_company_docs(posting.posting_id, texts))
    job = _talent(JOB, posting.job_description)
    functional = _talent(FUNCTIONAL, posting.functional_talent)
    nonfunctional = _talent(NONFUNCTIONAL, posting.nonfunctional_talent)

    texts = _item_texts(documents)
    resume_text, skill_cases, portfolio, essays = (texts[n] for n in (RESUME, SKILL_CASE, PORTFOLIO, ESSAY))
    skill = _skill_score(documents.skills)

    resume = _resume(model, embed, search, resume_text, skill, job, functional)
    others = [
        # 회사 일치 축: 프로젝트 문서 + 기능적 인재상 (루브릭 설계서 7.3)
        _item(model, embed, SKILL_CASE, skill_cases, SkillCaseReadOutput, {"problem": 20, "process": 30, "result": 20},
              "doc_match", 30, lambda: functional + _project(search, skill_cases)),
        _item(model, embed, PORTFOLIO, portfolio, PortfolioReadOutput, {"decision": 40, "depth": 30},
              "doc_match", 30, lambda: functional + _project(search, portfolio)),
        # 회사 일치도: 비기능적 인재상만. 프로젝트 문서는 검색하지 않는다
        _item(model, embed, ESSAY, essays, EssayReadOutput, {"format": 30, "logic": 40},
              "company_match", 30, lambda: nonfunctional),
    ]
    return [resume, *others]


def build_document_report(
    posting: PostingBrief,
    documents: ApplicantDocuments,
    model: Runnable | None = None,
    search: Callable[[list[str]], list[Chunk]] | None = None,
    embed: EmbedClient | None = None,
) -> DocumentReport:
    """서류 보고서 전체 (RAG 설계서 4.1): ① 항목 점수 → ② 인재상 적합도 → ③ 강점·확인 필요 → ④ 요약.
    ②는 인재상 문장마다 LLM이 서류에서 근거 문장을 그대로 옮기고, 코드가 서류에 있는 문장인지 확인한다.
    ③은 항목 원문과 ①의 결과를, ④는 ①②③의 결과와 항목 점수를 받는다."""
    model = model or get_chat_model()
    items = score_document_items(posting, documents, model=model, search=search, embed=embed)
    texts = {name: text for name, text in _item_texts(documents).items() if text}
    talents = _talent(FUNCTIONAL, posting.functional_talent) + _talent(NONFUNCTIONAL, posting.nonfunctional_talent)
    fits, fits_output = _fits(model, talents, texts)

    points: list[Point] = []
    points_output: dict[str, dict] = {}
    for item in items:
        if not item.llm_output:  # 내용이 없거나 필수 기술만 본 항목은 쓸 자료가 없다
            continue
        out = invoke_structured(model, prompts.points(item.name, texts[item.name], _item_brief(item)), PointsOutput)
        points_output[item.name] = out.model_dump()
        points += [Point(t, item.name, c.strip()) for t, c in (("강점", out.strength), ("확인 필요", out.check)) if c.strip()]

    summary = invoke_structured(model, prompts.summary(_report_brief(items, fits, points)), SummaryOutput)
    llm_output = {"fits": fits_output, "points": points_output, "summary": summary.model_dump()}
    return DocumentReport(items, fits, points, summary.summary, llm_output)


def _fits(model, talents: list[SourceSentence], texts: dict[str, str]) -> tuple[list[Fit], list[dict]]:
    """인재상 문장마다 서류에서 근거 문장을 옮겨 받는다 (루브릭 설계서 10).
    ①의 주장으로 만들면 결과 수치·태도처럼 주장에서 뺀 내용이 근거가 될 수 없어, 지표·정직함 같은
    인재상이 늘 '확인되지 않음'이었다 (D3-v3). 옮긴 문장이 서류에 없으면 버린다. 지어낸 근거를 막는다."""
    if not texts:
        return [Fit(t.text, NO_FIT_NOTE) for t in talents], []
    system = prompts.fit_system(texts)  # 서류를 앞부분에 둬 인재상마다 같은 앞부분 계산을 다시 쓴다
    fits, outputs = [], []
    for t in talents:
        out = invoke_structured(model, prompts.judge_fit(system, t.text), FitOutput)
        kept = [(name, q) for q in out.quotes if (name := _quoted_item(q, texts))]
        outputs.append({"talent": t.text, "quotes": out.quotes, "kept": len(kept)})
        evidence = " / ".join(f'{name}: "{_strip_quote(q)}"' for name, q in kept)
        fits.append(Fit(t.text, evidence or NO_FIT_NOTE))
    return fits, outputs


_QUOTE_CHARS = "\"'“”‘’「」"


def _strip_quote(q: str) -> str:
    return q.strip().strip(_QUOTE_CHARS).strip()


def _quoted_item(quote: str, texts: dict[str, str]) -> str | None:
    """옮긴 문장이 들어 있는 항목 이름. 공백과 따옴표 차이는 무시한다. 너무 짧은 조각은 근거로 보지 않는다."""
    q = re.sub(r"\s+", "", _strip_quote(quote))
    if len(q) < 10:
        return None
    return next((name for name, text in texts.items() if q in re.sub(r"\s+", "", text)), None)


def _item_brief(item: ItemScore) -> str:
    """강점·확인 필요를 쓸 자료: 축 점수, 채점 이유, 주장별 판정. 반대면 회사 자료 문장을 함께 보인다."""
    axes = "\n".join(f"- {AXIS_NAMES[k]}: {v:.0f}" for k, v in item.axes.items())
    lines = []
    for match in item.matches.values():
        for claim, level, sources in match.claims:
            line = f"- ({level}) {claim}"
            if level == "반대" and sources:
                line += f' ← 회사 자료: "{sources[0].text}"'
            if line not in lines:
                lines.append(line)
    return f"[축 점수 (0~100)]\n{axes}\n\n[채점 이유]\n{item.reason}\n\n[서류에서 읽은 일과 회사 자료 비교]\n" + "\n".join(lines)


def _report_brief(items: list[ItemScore], fits: list[Fit], points: list[Point]) -> str:
    """요약을 쓸 자료. 항목 점수와 회사 일치 축 점수를 넣는다. 점수 없이 쓰게 했더니 회사와 관계없는
    지원자도 '직무와 잘 부합한다'고 썼다 (D3-v3). 숫자를 문장에 쓰지 말라는 지시는 프롬프트에 있다."""
    parts = []
    for i in items:
        match = ", ".join(f"{AXIS_NAMES[k]} {i.axes[k]:.0f}" for k in i.matches)
        parts.append(f"[{i.name}] 항목 점수 {i.score:.0f}" + (f" (회사 일치: {match})" if match else "") + f"\n{i.reason}")
    found = sum(f.evidence != NO_FIT_NOTE for f in fits)
    parts.append(f"[인재상 적합도] {len(fits)}개 중 {found}개 확인\n" + "\n".join(
        f"- {f.talent_content}: {'확인됨' if f.evidence != NO_FIT_NOTE else '서류에서 확인되지 않음'}" for f in fits
    ))
    parts.append("[강점·확인 필요]\n" + ("\n".join(f"- ({p.point_type}, {p.item}) {p.content}" for p in points) or "- 없음"))
    return "\n\n".join(parts)


def _item_texts(documents: ApplicantDocuments) -> dict[str, str]:
    """항목별 서류 텍스트. 인적사항과 필수 기술 자기평가는 넣지 않는다."""
    return {
        RESUME: _resume_text(documents),
        SKILL_CASE: "\n\n".join(c for c in documents.skill_cases if c.strip()),
        PORTFOLIO: (documents.portfolio_text or "").strip(),
        ESSAY: "\n\n".join(f"[{e.get('topic', '')}]\n{e.get('content', '')}" for e in documents.essays if e.get("content")),
    }


def _resume(model, embed, search, text: str, skill: Decimal, job, functional) -> ItemScore:
    """직무 관련 경험 40 (직무 설명 + 프로젝트 문서) + 필수 기술 20 (코드) + 기능적 인재상 일치 40."""
    if not text:
        # 공고가 학력·경력·프로젝트를 모두 고르지 않았다. LLM을 부르지 않는다 (루브릭 설계서 7.3)
        return ItemScore(RESUME, skill, SKILL_ONLY_NOTE, [], {"skill": skill}, {})
    read = _read(model, RESUME, text, ResumeReadOutput)
    experience = _match(model, embed, read.claims, job + _project(search, text))
    talent = _match(model, embed, read.claims, functional)
    score = _round((experience.score * 40 + skill * 20 + talent.score * 40) / 100)
    reason = " ".join([read.reason, _match_note("직무 관련 경험", experience), _match_note("기능적 인재상 일치", talent)])
    return ItemScore(
        RESUME, score, reason, _merge(experience.evidence, talent.evidence),
        {"experience": experience.score, "skill": skill, "talent_match": talent.score},
        {"read": read.model_dump(), "experience": experience.judgments, "talent_match": talent.judgments},
        {"experience": experience, "talent_match": talent},
    )


def _item(
    model, embed, name: str, text: str, schema: type[BaseModel], ratios: dict[str, int],
    match_key: str, match_ratio: int, sources: Callable[[], list[SourceSentence]],
) -> ItemScore:
    if not text:
        return ItemScore(name, Decimal("0.00"), NO_TEXT_NOTE, [], {}, {})
    read = _read(model, name, text, schema)
    match = _match(model, embed, read.claims, sources())
    axes = {key: Decimal(getattr(read, key)) for key in ratios} | {match_key: match.score}
    score = _round(sum(axes[k] * r for k, r in (ratios | {match_key: match_ratio}).items()) / 100)
    reason = f"{read.reason} {_match_note(_MATCH_NAMES[match_key], match)}"
    return ItemScore(
        name, score, reason, match.evidence, axes, {"read": read.model_dump(), match_key: match.judgments},
        {match_key: match},
    )


_MATCH_NAMES = {"doc_match": "회사 업무 일치", "company_match": "회사 일치도"}


def _read(model, item: str, text: str, schema: type[BaseModel]):
    """주장을 하나도 뽑지 않으면 한 번 더 묻는다 (면접 답변 읽기와 같다)."""
    messages = prompts.read_item(item, text)
    read = invoke_structured(model, messages, schema)
    if read.claims:
        return read
    retry = messages + [AIMessage(content=read.model_dump_json()), HumanMessage(content=prompts.EMPTY_CLAIMS_RETRY)]
    return invoke_structured(model, retry, schema)


def _match(model, embed: EmbedClient, claims: list[str], sources: list[SourceSentence]) -> Match:
    """주장마다 회사 자료와 비교한다. 근거 번호가 검증된 '같음' 주장의 비율이 점수다."""
    counts = {"같음": 0, "반대": 0, "문서에 없음": 0}
    if not claims:
        return Match(Decimal("0.00"), counts, [], [])
    system = prompts.comparison_system([(s.id, s.text) for s in sources])
    by_id = {s.id: s for s in sources}
    judged: list[tuple[str, str, list[SourceSentence]]] = []
    judgments = []
    for claim in claims:
        j = invoke_structured(model, prompts.judge_claim(system, claim), ClaimJudgment)
        judgments.append(j.model_dump())
        ids = list(dict.fromkeys(i for raw in j.evidence_ids for i in _SENTENCE_ID.findall(raw) if i in by_id))
        # 같음·반대인데 남은 번호가 없으면 근거를 확인할 수 없다. 문서에 없음으로 센다 (루브릭 설계서 3.3과 같다)
        level = j.level if ids else "문서에 없음"
        counts[level] += 1
        judged.append((claim, level, [by_id[i] for i in ids] if level != "문서에 없음" else []))
    score = _round(Decimal(counts["같음"] * 100) / len(claims))
    compared = [(claim, ss) for claim, level, ss in judged if level != "문서에 없음"]
    return Match(score, counts, _filter_evidence(compared, embed), judgments, judged)


def _filter_evidence(compared: list[tuple[str, list[SourceSentence]]], embed: EmbedClient) -> list[SourceSentence]:
    """주장과 유사도가 낮은 근거 문장은 저장하지 않는다. 주장마다 가장 비슷한 1개는 남긴다.
    판정과 점수는 바꾸지 않는다 (면접과 같은 규칙, RAG 설계서 5.5 P11).
    EXAONE이 번호 칸에 목록 전체를 붙여 써 근거가 수십 개가 되기도 했다 (D2-v2)."""
    if not compared:
        return []
    threshold = get_settings().EVIDENCE_MIN_SIMILARITY
    texts = list(dict.fromkeys([claim for claim, _ in compared] + [s.text for _, ss in compared for s in ss]))
    # embed-server는 길이 1로 정규화한 벡터를 준다. 내적이 코사인 유사도다
    vectors = dict(zip(texts, embed.embed(texts)))
    picked: dict[str, SourceSentence] = {}
    for claim, candidates in compared:
        scored = [(sum(a * b for a, b in zip(vectors[claim], vectors[s.text])), s) for s in candidates]
        kept = [s for similarity, s in scored if similarity >= threshold] or [max(scored, key=lambda x: x[0])[1]]
        for s in kept:
            picked.setdefault(s.id, s)
    return list(picked.values())


def _match_note(axis: str, match: Match) -> str:
    total = sum(match.counts.values())
    if not total:
        return NO_CLAIM_NOTE
    counts = ", ".join(f"{k} {n}" for k, n in match.counts.items() if n)
    return f"{axis}: 서류에서 읽은 내용 {total}개를 회사 자료와 비교했다 ({counts})."


def _talent(kind: tuple[str, str], text: str) -> list[SourceSentence]:
    """인재상·직무 설명 전문에 번호를 붙인다. 목록 기호는 뗀다 (벡터 DB 설계서 2.3)."""
    prefix, source_type = kind
    sentences = [_BULLET.sub("", s) for s in split_sentences(text)]
    return [SourceSentence(f"{prefix}-{i}", s, source_type) for i, s in enumerate((s for s in sentences if s), start=1)]


def _project(search, text: str) -> list[SourceSentence]:
    """항목 텍스트로 프로젝트 문서를 찾아 문장 번호를 붙인다. 긴 텍스트는 검색이 나눠서 찾는다."""
    return [
        SourceSentence(s.id, s.text, s.chunk.source_type, s.chunk.source_id, s.chunk.chunk_id)
        for s in number_sentences(merge_contexts(search([text])))
    ]


def _resume_text(documents: ApplicantDocuments) -> str:
    """공고가 고른 학력·경력·프로젝트. 키 이름에 기대지 않고 값만 잇는다. 인적사항과 필수 기술은 넣지 않는다."""
    lines = []
    for label, rows in (("학력", documents.educations), ("경력", documents.careers), ("프로젝트", documents.projects)):
        lines += [f"[{label}] " + ", ".join(str(v) for v in row.values() if v) for row in rows]
    return "\n".join(lines)


def _skill_score(skills: list[dict]) -> Decimal:
    """필수 기술 자기평가 평균 ÷ 5 × 100 (루브릭 설계서 7.3). 점수가 빈 기술은 뺀다."""
    scores = [s["self_score"] for s in skills if s.get("self_score") is not None]
    if not scores:
        return Decimal("0.00")
    return _round(Decimal(sum(scores)) / len(scores) / 5 * 100)


def _merge(*groups: list[SourceSentence]) -> list[SourceSentence]:
    return list({s.id: s for group in groups for s in group}.values())


def _round(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
