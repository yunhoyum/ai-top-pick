"""면접 답변 내용 점수 테스트. LLM은 정해 둔 JSON을 차례로 돌려주는 가짜로 바꾼다.

첫 출력은 1번 호출(답변 읽기), 둘째 출력은 2번 호출(회사 문서 비교)의 답이다.
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
from app.schemas.llm_outputs import AnswerReadOutput

QUESTION = "결제 승인이 늦을 때 중복 결제를 어떻게 막나요?"
ANSWER = "음 타임아웃 후 확인 중으로 두고 배치로 PG에 조회해 확정합니다."
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


def _read(claims=("타임아웃 후 확인 중으로 둔다", "배치로 PG에 조회해 확정한다")):
    return {"claims": list(claims), "relevance": 90, "specificity": 80, "reason": "질문에 맞게 순서대로 답했다."}


def _match(*matches, question_in_docs=True):
    """matches: (주장 번호, 단계, 근거 번호 목록)."""
    return {
        "question_in_docs": question_in_docs,
        "matches": [{"claim": c, "level": lv, "evidence_ids": ids} for c, lv, ids in matches],
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


# ---------- 두 번 호출 ----------


def test_first_call_sees_no_documents_and_second_call_sees_no_raw_answer():
    model = FakeModel(_read(), _match((1, "같음", ["1-1"])))
    _score(model)
    first, second = model.calls[0][-1].content, model.calls[1][-1].content
    # 1번은 회사 문서 없이 답변만 읽는다
    assert ANSWER in first and PG.content not in first and "[1-1]" not in first
    # 2번은 원래 답변 대신 1번이 뽑은 주장을 문서와 비교한다
    assert ANSWER not in second
    assert "1. 타임아웃 후 확인 중으로 둔다" in second and "[1-1] PG 승인 응답이" in second


def test_documents_are_numbered_from_both_contexts():
    model = FakeModel(_read(), _match((1, "같음", ["1-1"])))
    _score(model, question_context=(DEPLOY,), answer_context=(PG,))
    second = model.calls[1][-1].content
    # 유사도가 높은 PG가 1번 후보다
    assert "[1-1] PG 승인 응답이" in second and "[2-1] 배포는 Docker로 한다." in second


# ---------- 근거 상태와 점수 ----------


def test_all_claims_same_uses_three_axes_and_copies_sentences():
    result = _score(FakeModel(_read(), _match((1, "같음", ["1-1"]), (2, "같음", ["1-2"]))))
    assert result.status == EvidenceStatus.FOUND
    assert result.score == Decimal("90.00")  # 36 + 24 + 30 (같음 = 100)
    assert [e.sentence for e in result.evidence] == [
        "PG 승인 응답이 5초 안에 오지 않으면 결제 상태를 확인 중으로 둔다.",
        "보정 배치가 1분마다 조회한다.",
    ]
    assert (result.evidence[0].source_type, result.evidence[0].source_id, result.evidence[0].chunk_id) == ("프로젝트 문서", 101, 1)
    assert result.reason.startswith("질문에 맞게 순서대로 답했다.")


@pytest.mark.parametrize(
    ("levels", "expected"),
    [
        (["같음", "같음"], "90.00"),  # 같음
        (["같음", "반대"], "82.50"),  # 절반 이상 같음 → 대부분 같음(75)
        (["같음", "반대", "반대"], "67.50"),  # 절반 미만 → 일부만 같음(25)
        (["반대"], "60.00"),  # 반대(0)
    ],
)
def test_claim_levels_are_gathered_into_doc_match_level(levels, expected):
    claims = [f"주장 {i}" for i in range(1, len(levels) + 1)]
    matches = [(i, lv, ["1-1"]) for i, lv in enumerate(levels, start=1)]
    assert _score(FakeModel(_read(claims), _match(*matches))).score == Decimal(expected)


def test_claims_not_in_docs_are_not_counted():
    # 문서에 없는 다른 방법은 점수를 올리지도 내리지도 않는다
    result = _score(FakeModel(_read(), _match((1, "같음", ["1-1"]), (2, "문서에 없음", []))))
    assert result.status == EvidenceStatus.FOUND and result.score == Decimal("90.00")


def test_claim_without_valid_ids_counts_as_not_in_docs():
    result = _score(FakeModel(_read(), _match((1, "같음", ["9-9"]), (2, "반대", []))))
    assert result.status == EvidenceStatus.NO_ANSWER_DOC
    assert result.score == Decimal("75.00")  # 36 + 24 + 15
    assert result.reason.endswith(NO_ANSWER_DOC_NOTE) and result.evidence == []


def test_unknown_and_repeated_claim_numbers_are_ignored():
    matches = _match((7, "반대", ["1-1"]), (1, "같음", ["1-1"]), (1, "반대", ["1-2"]))
    result = _score(FakeModel(_read(), matches))
    # 7번 주장은 없고, 1번의 두 번째 판정은 무시한다
    assert result.score == Decimal("90.00") and [e.sentence for e in result.evidence] == [
        "PG 승인 응답이 5초 안에 오지 않으면 결제 상태를 확인 중으로 둔다."
    ]


def test_nothing_compared_and_topic_not_in_docs_is_no_question_doc():
    result = _score(FakeModel(_read(), _match((1, "문서에 없음", []), question_in_docs=False)))
    assert result.status == EvidenceStatus.NO_QUESTION_DOC
    assert result.score == Decimal("85.71")  # 90 × 4/7 + 80 × 3/7
    assert result.reason.endswith(NO_QUESTION_DOC_NOTE)


def test_compared_claim_wins_over_topic_judgment():
    result = _score(FakeModel(_read(), _match((1, "같음", ["1-1"]), question_in_docs=False)))
    assert result.status == EvidenceStatus.FOUND and result.score == Decimal("90.00")


def test_empty_question_context_needs_only_the_first_call():
    model = FakeModel(_read())
    # 답변 검색 결과가 있어도 채점에는 쓰지 않는다 (루브릭 설계서 3.3)
    result = _score(model, question_context=(), answer_context=(PG,))
    assert result.status == EvidenceStatus.NO_QUESTION_DOC and result.score == Decimal("85.71")
    assert len(model.calls) == 1
    assert result.llm_output["match"] is None and result.llm_output["read"]["relevance"] == 90


# ---------- 출력 형식 검증 ----------


def test_invalid_output_is_retried_with_the_error():
    model = FakeModel("점수는 90점입니다", {**_read(), "relevance": 150}, _read())
    out = invoke_structured(model, [], AnswerReadOutput, max_retries=2)
    assert out.relevance == 90
    # 두 번째·세 번째 요청에는 앞의 틀린 출력과 오류가 붙어 있다
    assert len(model.calls) == 3 and "형식에 맞지 않습니다" in model.calls[2][-1].content


def test_gives_up_after_max_retries():
    with pytest.raises(StructuredOutputError):
        invoke_structured(FakeModel("x", "y"), [], AnswerReadOutput, max_retries=1)
