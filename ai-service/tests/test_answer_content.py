"""면접 답변 내용 점수 테스트. LLM은 정해 둔 JSON을 돌려주는 가짜로 바꾼다.

기대 점수는 루브릭 설계서 3.5 예시와 같다 (적합성 90, 구체성 80).
"""

import json
from decimal import Decimal

import pytest
from langchain_core.messages import AIMessage

from app.chains.answer_content import (
    NO_ANSWER_DOC_NOTE,
    NO_QUESTION_DOC_NOTE,
    EvidenceStatus,
    score_content,
)
from app.chains.structured import StructuredOutputError, invoke_structured
from app.rag.evidence import merge_contexts, number_sentences, split_sentences
from app.rag.retriever import Chunk
from app.schemas.llm_outputs import AnswerContentOutput

QUESTION = "결제 승인이 늦을 때 중복 결제를 어떻게 막나요?"
ANSWER = "타임아웃 후 확인 중으로 두고 배치로 PG에 조회해 확정합니다."
JOB = "주문·결제 백엔드를 개발한다."


class FakeModel:
    """돌려줄 출력을 차례로 내준다. 받은 메시지를 기록한다."""

    def __init__(self, *outputs):
        self.outputs = [o if isinstance(o, str) else json.dumps(o, ensure_ascii=False) for o in outputs]
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content=self.outputs.pop(0))


def _chunk(chunk_id, content, similarity=0.7):
    return Chunk(chunk_id, "프로젝트 문서", 100 + chunk_id, 0, content, similarity)


PG = _chunk(1, "PG 승인 응답이 5초 안에 오지 않으면 결제 상태를 확인 중으로 둔다. 보정 배치가 1분마다 조회한다.")
DEPLOY = _chunk(2, "배포는 Docker로 한다.", similarity=0.6)


def _output(ids, question_in_docs=True, doc_match=95):
    return {
        "question_in_docs": question_in_docs,
        "evidence_ids": ids,
        "relevance": 90,
        "specificity": 80,
        "doc_match": doc_match,
        "reason": "질문에 맞게 순서대로 답했다.",
    }


def _score(model, question_context=(PG, DEPLOY), answer_context=()):
    return score_content(QUESTION, ANSWER, list(question_context), list(answer_context), JOB, model=model)


# ---------- 문장 번호 ----------


def test_sentences_split_at_sentence_end_and_newline_but_not_decimals():
    assert split_sentences("버전은 v1.2다. 충실도는 0.93이다!\n목록 항목") == ["버전은 v1.2다.", "충실도는 0.93이다!", "목록 항목"]


def test_contexts_merge_by_chunk_keeping_highest_similarity():
    merged = merge_contexts([_chunk(1, "a", 0.6), _chunk(2, "b", 0.7)], [_chunk(1, "a", 0.9)])
    assert [(c.chunk_id, c.similarity) for c in merged] == [(1, 0.9), (2, 0.7)]


def test_numbers_are_candidate_then_sentence_and_overlap_is_not_repeated():
    first = _chunk(1, "가는 1이다. 나는 2이다.")
    second = _chunk(2, "나는 2이다. 다는 3이다.")  # 청크 겹침으로 앞 문장이 다시 나온다
    assert [(s.id, s.text) for s in number_sentences([first, second])] == [
        ("1-1", "가는 1이다."),
        ("1-2", "나는 2이다."),
        ("2-2", "다는 3이다."),
    ]


# ---------- 근거 상태와 점수 ----------


def test_found_evidence_uses_three_axes_and_copies_sentence():
    result = _score(FakeModel(_output(["1-1"])))
    assert result.status == EvidenceStatus.FOUND
    assert result.score == Decimal("88.50")  # 36 + 24 + 28.5
    assert result.reason == "질문에 맞게 순서대로 답했다."
    [evidence] = result.evidence
    assert evidence.sentence == "PG 승인 응답이 5초 안에 오지 않으면 결제 상태를 확인 중으로 둔다."
    assert (evidence.source_type, evidence.source_id, evidence.chunk_id) == ("프로젝트 문서", 101, 1)


def test_unknown_ids_are_dropped_and_duplicates_kept_once():
    result = _score(FakeModel(_output(["9-9", "1-2", "1-2"])))
    assert [e.sentence for e in result.evidence] == ["보정 배치가 1분마다 조회한다."]


def test_no_valid_id_with_topic_in_docs_is_no_answer_doc():
    result = _score(FakeModel(_output(["9-9"], question_in_docs=True, doc_match=95)))
    assert result.status == EvidenceStatus.NO_ANSWER_DOC
    # LLM의 일치 점수 95 대신 50을 넣는다: 36 + 24 + 15
    assert result.score == Decimal("75.00")
    assert result.reason.endswith(NO_ANSWER_DOC_NOTE)
    assert result.evidence == []


def test_no_valid_id_with_topic_not_in_docs_is_no_question_doc():
    result = _score(FakeModel(_output([], question_in_docs=False)))
    assert result.status == EvidenceStatus.NO_QUESTION_DOC
    assert result.score == Decimal("85.71")  # 90 × 4/7 + 80 × 3/7
    assert result.reason.endswith(NO_QUESTION_DOC_NOTE)


def test_valid_evidence_wins_over_topic_judgment():
    result = _score(FakeModel(_output(["1-1"], question_in_docs=False)))
    assert result.status == EvidenceStatus.FOUND
    assert result.score == Decimal("88.50")


def test_empty_question_context_scores_without_documents():
    model = FakeModel({"relevance": 90, "specificity": 80, "reason": "답변이 구체적이다."})
    # 답변 검색 결과가 있어도 채점에는 쓰지 않는다 (루브릭 설계서 3.3)
    result = _score(model, question_context=(), answer_context=(PG,))
    assert result.status == EvidenceStatus.NO_QUESTION_DOC
    assert result.score == Decimal("85.71")
    prompt = model.calls[0][-1].content
    assert "회사 문서 문장" not in prompt and PG.content not in prompt


def test_prompt_numbers_sentences_from_both_contexts():
    model = FakeModel(_output(["1-1"]))
    _score(model, question_context=(DEPLOY,), answer_context=(PG,))
    prompt = model.calls[0][-1].content
    # 유사도가 높은 PG가 1번 후보다
    assert "[1-1] PG 승인 응답이" in prompt and "[2-1] 배포는 Docker로 한다." in prompt


# ---------- 출력 형식 검증 ----------


def test_invalid_output_is_retried_with_the_error():
    model = FakeModel("점수는 90점입니다", {**_output(["1-1"]), "relevance": 150}, _output(["1-1"]))
    out = invoke_structured(model, [], AnswerContentOutput, max_retries=2)
    assert out.relevance == 90
    # 두 번째·세 번째 요청에는 앞의 틀린 출력과 오류가 붙어 있다
    assert len(model.calls) == 3 and "형식에 맞지 않습니다" in model.calls[2][-1].content


def test_gives_up_after_max_retries():
    with pytest.raises(StructuredOutputError):
        invoke_structured(FakeModel("x", "y"), [], AnswerContentOutput, max_retries=1)
