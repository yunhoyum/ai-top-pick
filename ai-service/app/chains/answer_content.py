"""면접 답변 내용 점수 (루브릭 설계서 3장, 벡터 DB 설계서 8.4).

LLM을 한 번 불러 질문 주제 판정, 근거 문장 번호, 세 축 점수를 받는다.
번호 검증, 근거 상태 결정, 점수 계산은 코드가 한다.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from langchain_core.runnables import Runnable

from app.chains.structured import invoke_structured
from app.core.llm import get_chat_model
from app.prompts import answer_content as prompts
from app.rag.evidence import merge_contexts, number_sentences
from app.rag.retriever import Chunk
from app.schemas.llm_outputs import AnswerContentNoDocOutput, AnswerContentOutput

# 일치 단계별 점수 (루브릭 설계서 3.2). '문서에 없음'은 ㉡이고 50을 넣는다
DOC_MATCH_SCORES = {"같음": 100, "대부분 같음": 75, "일부만 같음": 25, "반대": 0}
NO_ANSWER_DOC_LEVEL = "문서에 없음"
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
    # 검증을 통과한 LLM 출력 그대로. 평가·디버깅용이다. 축 점수는 DB에 저장하지 않는다 (루브릭 설계서 3.6)
    llm_output: AnswerContentOutput | AnswerContentNoDocOutput


def score_content(
    question: str,
    answer: str,
    question_context: list[Chunk],
    answer_context: list[Chunk],
    job_description: str,
    model: Runnable | None = None,
) -> ContentScore:
    model = model or get_chat_model()

    # ㉠: 질문으로 찾은 문서가 없다. 회사 문서 없이 두 축만 채점한다
    if not question_context:
        out = invoke_structured(
            model, prompts.without_documents(question, answer, job_description), AnswerContentNoDocOutput
        )
        return _without_doc_axis(out)

    sentences = number_sentences(merge_contexts(question_context, answer_context))
    out = invoke_structured(
        model, prompts.with_documents(question, answer, job_description, sentences), AnswerContentOutput
    )

    # 목록에 없는 번호는 버린다. 같은 번호가 여러 번 나오면 한 번만 쓴다
    by_id = {s.id: s for s in sentences}
    picked = [by_id[i] for i in dict.fromkeys(out.evidence_ids) if i in by_id]

    # 판정 순서 (루브릭 설계서 3.3): 통과한 번호가 있고 일치 단계가 '문서에 없음'이 아니면
    # 질문 주제 판정과 상관없이 근거 있음
    if picked and out.doc_match_level != NO_ANSWER_DOC_LEVEL:
        evidence = [EvidenceSentence(s.chunk.source_type, s.chunk.source_id, s.chunk.chunk_id, s.text) for s in picked]
        score = _weighted(out.relevance, out.specificity, DOC_MATCH_SCORES[out.doc_match_level])
        return ContentScore(score, out.reason, EvidenceStatus.FOUND, evidence, out)
    if not out.question_in_docs:
        return _without_doc_axis(out)
    # ㉡: LLM이 낸 일치 점수는 쓰지 않는다
    score = _weighted(out.relevance, out.specificity, NO_ANSWER_DOC_MATCH)
    return ContentScore(score, f"{out.reason} {NO_ANSWER_DOC_NOTE}", EvidenceStatus.NO_ANSWER_DOC, [], out)


def _weighted(relevance: int, specificity: int, doc_match: int) -> Decimal:
    """적합성 40 + 구체성 30 + 일치 30 (루브릭 설계서 3.1)."""
    return _round((Decimal(relevance) * 4 + Decimal(specificity) * 3 + Decimal(doc_match) * 3) / 10)


def _without_doc_axis(out: AnswerContentOutput | AnswerContentNoDocOutput) -> ContentScore:
    """㉠: 일치 축을 빼고 40:30 비율을 유지한다 (4/7, 3/7)."""
    score = _round((Decimal(out.relevance) * 4 + Decimal(out.specificity) * 3) / 7)
    return ContentScore(score, f"{out.reason} {NO_QUESTION_DOC_NOTE}", EvidenceStatus.NO_QUESTION_DOC, [], out)


def _round(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
