"""면접 답변 내용 점수 (루브릭 설계서 3장, 벡터 DB 설계서 8.4).

LLM을 여러 번 부른다.
1. 답변 읽기: 회사 문서 없이 지원자가 말한 것(주장), 질문 적합성, 구체성을 받는다.
2. 질문 주제 판정: 질문 주제가 회사 문서에 있는지 받는다.
3. 주장 비교: 주장마다 따로 회사 문서와 비교해 같음·반대·문서에 없음과 근거 번호를 받는다.
일치 단계, 근거 상태, 점수 계산은 코드가 한다.

1에 문서를 넣지 않는 이유: 문서를 같이 보면 답변에 없는 문서 내용을 답변에 섞어 읽었다 (RAG 설계서 5.5 P7).
3을 주장마다 나누는 이유: 한 번에 비교하게 하면 주장을 합치거나 빠뜨리고 번호를 틀렸다 (P8).
2·3은 앞부분(지시, 회사 문서, 질문)을 같게 둬서 Ollama가 그 계산을 다시 쓰게 한다.
"""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable

from app.chains.structured import invoke_structured
from app.clients.embed import EmbedClient
from app.core.config import get_settings
from app.core.llm import get_chat_model
from app.prompts import answer_content as prompts
from app.rag.evidence import NumberedSentence, merge_contexts, number_sentences
from app.rag.retriever import Chunk
from app.schemas.llm_outputs import AnswerReadOutput, ClaimJudgment, TopicOutput

# 일치 단계별 점수 (루브릭 설계서 3.2). '문서에 없음'은 ㉡이고 50을 넣는다
DOC_MATCH_SCORES = {"같음": 100, "대부분 같음": 75, "일부만 같음": 25, "반대": 0}
NO_ANSWER_DOC_MATCH = 50

# 근거 상태를 저장하지 않으므로 점수 이유 끝에 처리 사실을 붙인다 (루브릭 설계서 3.3)
NO_QUESTION_DOC_NOTE = "회사 문서에 관련 내용이 없는 질문이라 회사 문서 일치 축을 빼고 채점했다."
NO_ANSWER_DOC_NOTE = "답변과 비교할 내용이 회사 문서에 없어 회사 문서 일치 축을 50점으로 채점했다."
NO_CLAIM_NOTE = "답변에서 방법이나 사실을 찾지 못해 내용 점수를 0점으로 채점했다."

_SENTENCE_ID = re.compile(r"\d+-\d+")


class EvidenceStatus(StrEnum):
    FOUND = "근거 있음"
    NO_QUESTION_DOC = "질문 근거 없음"  # ㉠
    NO_ANSWER_DOC = "답변 근거 없음"  # ㉡
    NO_CLAIM = "답변 내용 없음"  # 주장이 하나도 없다. 내용 점수 0점 (루브릭 설계서 3.3)


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
    # 검증을 통과한 LLM 출력 그대로 {"read", "topic", "claims"}. 평가·디버깅용이다.
    # 축 점수는 DB에 저장하지 않는다 (루브릭 설계서 3.6)
    llm_output: dict


def judge_question_topic(
    question: str, question_context: list[Chunk], model: Runnable | None = None
) -> TopicOutput | None:
    """질문을 낼 때 부른다. 질문 주제 판정과 함께, 답변 뒤 주장 비교가 다시 쓸 앞부분 계산을 Ollama에 남긴다.
    질문 검색 결과가 비면(㉠) 회사 문서와 비교하지 않으므로 부르지 않는다."""
    if not question_context:
        return None
    system = prompts.comparison_system(question, _question_sentences(question_context))
    return invoke_structured(model or get_chat_model(), prompts.judge_topic(system), TopicOutput)


def score_content(
    question: str,
    answer: str,
    question_context: list[Chunk],
    answer_context: list[Chunk],
    job_description: str,
    model: Runnable | None = None,
    embed: EmbedClient | None = None,
    topic: TopicOutput | None = None,
) -> ContentScore:
    """topic: 질문을 낼 때 judge_question_topic으로 받아 둔 결과. 없으면 여기서 부른다."""
    model = model or get_chat_model()
    read = _read_answer(model, question, answer, job_description)

    # 다시 물어도 주장이 없으면 무응답으로 보고 0점이다. ㉡(50점)으로 두면 아무 말도 안 한 답변이
    # 문서와 반대인 답변보다 높은 점수를 받는다 (루브릭 설계서 3.3)
    if not read.claims:
        llm_output = {"read": read.model_dump(), "topic": None, "claims": []}
        return ContentScore(Decimal("0.00"), f"{read.reason} {NO_CLAIM_NOTE}", EvidenceStatus.NO_CLAIM, [], llm_output)

    # ㉠: 질문으로 찾은 문서가 없다. 회사 문서와 비교하지 않는다
    if not question_context:
        return _without_doc_axis(read, {"read": read.model_dump(), "topic": None, "claims": []})

    # 앞부분(시스템 메시지)은 질문 검색 문장만으로 만든다. 질문을 낼 때와 글자 하나 다르지 않아야 캐시를 다시 쓴다.
    # 답변으로만 찾은 문장은 번호를 이어 매겨 주장마다 뒤에 붙인다
    question_sentences = _question_sentences(question_context)
    answer_sentences = number_sentences(
        _answer_only(question_context, answer_context), start=len(question_context) + 1, already=question_sentences
    )
    sentences = question_sentences + answer_sentences
    system = prompts.comparison_system(question, question_sentences)
    topic = topic or invoke_structured(model, prompts.judge_topic(system), TopicOutput)
    judgments = [
        invoke_structured(model, prompts.judge_claim(system, c, answer_sentences), ClaimJudgment) for c in read.claims
    ]
    llm_output = {
        "read": read.model_dump(),
        "topic": topic.model_dump(),
        "claims": [j.model_dump() for j in judgments],
    }

    compared = _compared_claims(read.claims, judgments, sentences)

    # 판정 순서 (루브릭 설계서 3.3): 근거 번호가 검증된 같음·반대 주장이 있으면 질문 주제 판정과 상관없이 근거 있음
    if compared:
        same = sum(level == "같음" for _, level, _ in compared)
        level = _level(same, len(compared))
        picked = _filter_evidence(compared, embed or EmbedClient())
        evidence = [EvidenceSentence(s.chunk.source_type, s.chunk.source_id, s.chunk.chunk_id, s.text) for s in picked]
        score = _weighted(read.relevance, read.specificity, DOC_MATCH_SCORES[level])
        reason = f"{read.reason} 회사 문서와 비교한 주장 {len(compared)}개 중 {same}개가 문서와 같다 (일치 단계: {level})."
        return ContentScore(score, reason, EvidenceStatus.FOUND, evidence, llm_output)
    if not topic.question_in_docs:
        return _without_doc_axis(read, llm_output)
    # ㉡: 비교할 내용이 문서에 없다
    score = _weighted(read.relevance, read.specificity, NO_ANSWER_DOC_MATCH)
    return ContentScore(score, f"{read.reason} {NO_ANSWER_DOC_NOTE}", EvidenceStatus.NO_ANSWER_DOC, [], llm_output)


def _question_sentences(question_context: list[Chunk]) -> list[NumberedSentence]:
    return number_sentences(merge_contexts(question_context))


def _answer_only(question_context: list[Chunk], answer_context: list[Chunk]) -> list[Chunk]:
    """답변 검색 결과 중 질문 검색에 없던 청크 (유사도 순)."""
    seen = {c.chunk_id for c in question_context}
    return [c for c in merge_contexts(answer_context) if c.chunk_id not in seen]


def _read_answer(model: Runnable, question: str, answer: str, job_description: str) -> AnswerReadOutput:
    """주장을 하나도 뽑지 않으면 한 번 더 묻는다. temperature가 0이라 같은 질문은 같은 답을 내므로 앞 출력과 요청을 붙인다."""
    messages = prompts.read_answer(question, answer, job_description)
    read = invoke_structured(model, messages, AnswerReadOutput)
    if read.claims:
        return read
    retry = messages + [AIMessage(content=read.model_dump_json()), HumanMessage(content=prompts.EMPTY_CLAIMS_RETRY)]
    return invoke_structured(model, retry, AnswerReadOutput)


def _compared_claims(
    claims: list[str], judgments: list[ClaimJudgment], sentences: list[NumberedSentence]
) -> list[tuple[str, str, list[NumberedSentence]]]:
    """일치 단계에 세는 주장 (주장, 같음·반대, 근거 문장). 목록에 없는 문장 번호는 버린다.
    같음·반대인데 남은 문장 번호가 없으면 근거를 확인할 수 없으므로 '문서에 없음'과 같이 빼고 센다."""
    by_id = {s.id: s for s in sentences}
    compared = []
    for claim, j in zip(claims, judgments):
        ids = list(dict.fromkeys(i for i in _evidence_ids(j.evidence_ids) if i in by_id))
        if j.level != "문서에 없음" and ids:
            compared.append((claim, j.level, [by_id[i] for i in ids]))
    return compared


def _filter_evidence(
    compared: list[tuple[str, str, list[NumberedSentence]]], embed: EmbedClient
) -> list[NumberedSentence]:
    """주장과 유사도가 낮은 근거 문장은 저장하지 않는다. 주장마다 가장 비슷한 1개는 남긴다.
    판정은 바꾸지 않는다. 유사도로 판정을 바꾸면 맞는 판정도 잃었다 (RAG 설계서 5.5 P11)."""
    threshold = get_settings().EVIDENCE_MIN_SIMILARITY
    texts = list(dict.fromkeys([claim for claim, _, _ in compared] + [s.text for _, _, ss in compared for s in ss]))
    # embed-server는 길이 1로 정규화한 벡터를 준다. 내적이 코사인 유사도다
    vectors = dict(zip(texts, embed.embed(texts)))
    picked: dict[str, NumberedSentence] = {}
    for claim, _, candidates in compared:
        scored = [(sum(a * b for a, b in zip(vectors[claim], vectors[s.text])), s) for s in candidates]
        kept = [s for similarity, s in scored if similarity >= threshold] or [max(scored, key=lambda x: x[0])[1]]
        for s in kept:
            picked.setdefault(s.id, s)
    return list(picked.values())


def _evidence_ids(raw: list[str]) -> list[str]:
    """근거 번호를 뽑는다. EXAONE은 '[1-7] 문장'처럼 번호와 문장을 함께 쓰기도 한다 (P8)."""
    return [found for item in raw for found in _SENTENCE_ID.findall(item)]


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
