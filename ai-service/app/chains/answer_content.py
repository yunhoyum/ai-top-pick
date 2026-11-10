"""면접 답변 내용 점수 (루브릭 설계서 3장, 벡터 DB 설계서 8.4).

LLM을 두 번 부른다.
1. 회사 문서 없이 답변을 읽어 지원자가 말한 것(주장), 질문 적합성, 구체성을 받는다.
2. 그 주장만 회사 문서와 비교해 질문 주제 판정과 주장별 같음·반대·문서에 없음을 받는다.
번호 검증, 일치 단계, 근거 상태, 점수 계산은 코드가 한다.
1번에 문서를 넣지 않는 이유: 문서를 같이 보면 답변에 없는 문서 내용을 답변에 섞어 읽었다 (RAG 설계서 5.5 P7).
"""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from langchain_core.runnables import Runnable

from app.chains.structured import invoke_structured
from app.core.llm import get_chat_model
from app.prompts import answer_content as prompts
from app.rag.evidence import NumberedSentence, merge_contexts, number_sentences
from app.rag.retriever import Chunk
from app.schemas.llm_outputs import AnswerReadOutput, DocMatchOutput

# 일치 단계별 점수 (루브릭 설계서 3.2). '문서에 없음'은 ㉡이고 50을 넣는다
DOC_MATCH_SCORES = {"같음": 100, "대부분 같음": 75, "일부만 같음": 25, "반대": 0}
NO_ANSWER_DOC_MATCH = 50

# 근거 상태를 저장하지 않으므로 점수 이유 끝에 처리 사실을 붙인다 (루브릭 설계서 3.3)
NO_QUESTION_DOC_NOTE = "회사 문서에 관련 내용이 없는 질문이라 회사 문서 일치 축을 빼고 채점했다."
NO_ANSWER_DOC_NOTE = "답변과 비교할 내용이 회사 문서에 없어 회사 문서 일치 축을 50점으로 채점했다."


class EvidenceStatus(StrEnum):
    FOUND = "근거 있음"
    NO_QUESTION_DOC = "질문 근거 없음"  # ㉠
    NO_ANSWER_DOC = "답변 근거 없음"  # ㉡


@dataclass(frozen=True)
class EvidenceSentence:
    """evidence_sentence 테이블에 사본으로 저장할 근거 문장."""

    source_type: str
    source_id: int
    chunk_id: int
    sentence: str


@dataclass(frozen=True)
class ContentScore:
    score: Decimal  # 0~100, 소수 둘째 자리 (interview_answer.content_score)
    reason: str  # interview_answer.content_reason
    status: EvidenceStatus
    evidence: list[EvidenceSentence]
    # 검증을 통과한 LLM 출력 그대로 {"read": 1번, "match": 2번 또는 None}. 평가·디버깅용이다.
    # 축 점수는 DB에 저장하지 않는다 (루브릭 설계서 3.6)
    llm_output: dict


def score_content(
    question: str,
    answer: str,
    question_context: list[Chunk],
    answer_context: list[Chunk],
    job_description: str,
    model: Runnable | None = None,
) -> ContentScore:
    model = model or get_chat_model()
    read = invoke_structured(model, prompts.read_answer(question, answer, job_description), AnswerReadOutput)

    # ㉠: 질문으로 찾은 문서가 없다. 회사 문서와 비교하지 않는다
    if not question_context:
        return _without_doc_axis(read, {"read": read.model_dump(), "match": None})

    sentences = number_sentences(merge_contexts(question_context, answer_context))
    match = invoke_structured(model, prompts.match_documents(question, read.claims, sentences), DocMatchOutput)
    llm_output = {"read": read.model_dump(), "match": match.model_dump()}

    same, compared, picked = _compare(read.claims, match, sentences)

    # 판정 순서 (루브릭 설계서 3.3): 근거 번호가 검증된 같음·반대 주장이 있으면 질문 주제 판정과 상관없이 근거 있음
    if compared:
        level = _level(same, compared)
        evidence = [EvidenceSentence(s.chunk.source_type, s.chunk.source_id, s.chunk.chunk_id, s.text) for s in picked]
        score = _weighted(read.relevance, read.specificity, DOC_MATCH_SCORES[level])
        reason = f"{read.reason} 회사 문서와 비교한 주장 {compared}개 중 {same}개가 문서와 같다 (일치 단계: {level})."
        return ContentScore(score, reason, EvidenceStatus.FOUND, evidence, llm_output)
    if not match.question_in_docs:
        return _without_doc_axis(read, llm_output)
    # ㉡: 비교할 내용이 문서에 없다
    score = _weighted(read.relevance, read.specificity, NO_ANSWER_DOC_MATCH)
    return ContentScore(score, f"{read.reason} {NO_ANSWER_DOC_NOTE}", EvidenceStatus.NO_ANSWER_DOC, [], llm_output)


def _compare(
    claims: list[str], match: DocMatchOutput, sentences: list[NumberedSentence]
) -> tuple[int, int, list[NumberedSentence]]:
    """(같음 수, 비교된 주장 수, 근거 문장). 목록에 없는 주장 번호와 문장 번호는 버린다.
    같음·반대인데 남은 문장 번호가 없으면 근거를 확인할 수 없으므로 '문서에 없음'과 같이 센다."""
    by_id = {s.id: s for s in sentences}
    seen_claims: set[int] = set()
    same = compared = 0
    picked: dict[str, NumberedSentence] = {}
    for m in match.matches:
        index = _claim_index(m.claim, claims)
        if index is None or index in seen_claims:
            continue
        seen_claims.add(index)
        ids = [i for i in m.evidence_ids if i in by_id]
        if m.level == "문서에 없음" or not ids:
            continue
        compared += 1
        same += m.level == "같음"
        for i in ids:
            picked.setdefault(i, by_id[i])
    return same, compared, list(picked.values())


def _claim_index(claim: int | str, claims: list[str]) -> int | None:
    """주장 번호(1부터)를 돌려준다. 번호 대신 문장이 오면 띄어쓰기를 무시하고 같은 주장을 찾는다. 없으면 None."""
    if isinstance(claim, str):
        if claim.strip().isdigit():
            claim = int(claim)
        else:
            key = re.sub(r"\s+", "", claim)
            found = [i for i, c in enumerate(claims, start=1) if re.sub(r"\s+", "", c) == key]
            return found[0] if found else None
    return claim if 1 <= claim <= len(claims) else None


def _level(same: int, compared: int) -> str:
    """주장별 결과를 루브릭 설계서 3.2의 일치 단계로 모은다. '문서에 없음' 주장은 세지 않는다."""
    if same == compared:
        return "같음"
    if same * 2 >= compared:
        return "대부분 같음"
    if same > 0:
        return "일부만 같음"
    return "반대"


def _weighted(relevance: int, specificity: int, doc_match: int) -> Decimal:
    """적합성 40 + 구체성 30 + 일치 30 (루브릭 설계서 3.1)."""
    return _round((Decimal(relevance) * 4 + Decimal(specificity) * 3 + Decimal(doc_match) * 3) / 10)


def _without_doc_axis(read: AnswerReadOutput, llm_output: dict) -> ContentScore:
    """㉠: 일치 축을 빼고 40:30 비율을 유지한다 (4/7, 3/7)."""
    score = _round((Decimal(read.relevance) * 4 + Decimal(read.specificity) * 3) / 7)
    return ContentScore(score, f"{read.reason} {NO_QUESTION_DOC_NOTE}", EvidenceStatus.NO_QUESTION_DOC, [], llm_output)


def _round(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
