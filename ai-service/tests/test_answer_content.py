"""면접 답변 내용 점수 테스트. LLM은 정해 둔 JSON을 차례로 돌려주는 가짜로 바꾼다.

호출 순서: 답변 읽기 → 질문 주제 판정 → 주장마다 비교.
기대 점수는 루브릭 설계서 3.5 예시와 같다 (적합성 90, 구체성 80).
"""

import json
from decimal import Decimal

import pytest
from langchain_core.messages import AIMessage

from app.chains.answer_content import (
    NO_ANSWER_DOC_NOTE,
    NO_CLAIM_NOTE,
    NO_QUESTION_DOC_NOTE,
    EvidenceStatus,
    judge_question_topic,
    score_content,
)
from app.chains.structured import StructuredOutputError, invoke_structured
from app.prompts.answer_content import EMPTY_CLAIMS_RETRY
from app.rag.evidence import merge_contexts, number_sentences, split_sentences
from app.rag.retriever import Chunk
from app.schemas.llm_outputs import AnswerReadOutput

QUESTION = "결제 승인이 늦을 때 중복 결제를 어떻게 막나요?"
ANSWER = "음 타임아웃 후 확인 중으로 두고 배치로 PG에 조회해 확정합니다."
JOB = "주문·결제 백엔드를 개발한다."
CLAIMS = ["타임아웃 후 확인 중으로 둔다", "배치로 PG에 조회해 확정한다"]


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


def _read(claims=tuple(CLAIMS)):
    return {"claims": list(claims), "relevance": 90, "specificity": 80, "reason": "질문에 맞게 순서대로 답했다."}


def _topic(in_docs=True):
    return {"question_in_docs": in_docs}


def _claim(level, ids):
    return {"level": level, "evidence_ids": ids}


def _model(*judgments, claims=tuple(CLAIMS), in_docs=True):
    return FakeModel(_read(claims), _topic(in_docs), *[_claim(lv, ids) for lv, ids in judgments])


class FakeEmbed:
    """글마다 정해 둔 방향의 단위 벡터를 준다. 정하지 않은 글은 모두 같은 방향이라 유사도 1이다."""

    def __init__(self, directions=None):
        self.directions = directions or {}

    def embed(self, texts):
        return [[1.0, 0.0] if self.directions.get(t, 0) == 0 else [0.0, 1.0] for t in texts]


def _score(model, question_context=(PG, DEPLOY), answer_context=(), embed=None):
    return score_content(
        QUESTION, ANSWER, list(question_context), list(answer_context), JOB, model=model, embed=embed or FakeEmbed()
    )


# ---------- 문장 번호 ----------


def test_sentences_split_at_sentence_end_and_newline_but_not_decimals():
    assert split_sentences("버전은 v1.2다. 충실도는 0.93이다!\n목록 항목") == ["버전은 v1.2다.", "충실도는 0.93이다!", "목록 항목"]


def test_list_numbers_stay_with_their_sentence():
    # P9에서 '10.', '13.'만 남은 조각이 근거 문장으로 뽑혔다
    text = "엣지는 다음과 같다. 10. generate → check_grounded\n11.\n\ncheck_grounded → END"
    assert split_sentences(text) == ["엣지는 다음과 같다.", "10. generate → check_grounded", "11. check_grounded → END"]


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


# ---------- 호출 구성 ----------


def test_read_call_sees_no_documents_and_comparison_calls_see_no_raw_answer():
    model = _model(("같음", ["1-1"]), ("같음", ["1-2"]))
    _score(model)
    read, topic, claim1, claim2 = (call[-1].content for call in model.calls)
    # 답변 읽기는 회사 문서 없이 답변만 본다
    assert ANSWER in read and PG.content not in read and "[1-1]" not in read
    # 비교 호출은 원래 답변 대신 주장 하나만 본다
    assert all(ANSWER not in c for c in (topic, claim1, claim2))
    assert CLAIMS[0] in claim1 and CLAIMS[1] not in claim1 and CLAIMS[1] in claim2


def test_comparison_calls_share_the_same_front_part():
    model = _model(("같음", ["1-1"]), ("같음", ["1-2"]))
    _score(model, question_context=(PG, DEPLOY))
    systems = [call[0].content for call in model.calls[1:]]
    # 앞부분이 글자 하나까지 같아야 Ollama가 계산을 다시 쓴다
    assert len(set(systems)) == 1
    # 회사 문서와 질문은 앞부분에 있다. 유사도가 높은 PG가 1번 후보다
    assert "[1-1] PG 승인 응답이" in systems[0] and "[2-1] 배포는 Docker로 한다." in systems[0] and QUESTION in systems[0]


def test_front_part_has_only_question_search_and_answer_only_chunks_follow():
    # 질문 검색은 DEPLOY만, 답변 검색은 PG와 DEPLOY를 찾았다
    model = _model(("같음", ["2-1"]), ("같음", ["1-1"]))
    result = _score(model, question_context=(DEPLOY,), answer_context=(PG, DEPLOY))
    system = model.calls[1][0].content
    claim = model.calls[2][-1].content
    # 앞부분은 질문 검색 문장만이다. 답변으로만 찾은 PG는 번호를 이어 2번 후보로 주장 요청에 붙는다
    assert "[1-1] 배포는 Docker로 한다." in system and PG.content not in system
    assert "[2-1] PG 승인 응답이" in claim and "[1-1] 배포는" not in claim
    # 이어 붙인 번호도 근거로 쓸 수 있다
    assert "PG 승인 응답이 5초 안에 오지 않으면 결제 상태를 확인 중으로 둔다." in [e.sentence for e in result.evidence]


def test_topic_judged_at_question_time_is_reused():
    question_context = [PG, DEPLOY]
    early = FakeModel(_topic(True))
    topic = judge_question_topic(QUESTION, question_context, model=early)
    # 답변 뒤에는 질문 주제를 다시 묻지 않는다: 읽기 → 주장 1 → 주장 2
    model = FakeModel(_read(), _claim("같음", ["1-1"]), _claim("같음", ["1-2"]))
    result = score_content(QUESTION, ANSWER, question_context, [], JOB, model=model, embed=FakeEmbed(), topic=topic)
    assert len(model.calls) == 3 and result.status == EvidenceStatus.FOUND
    # 질문을 낼 때의 앞부분과 답변 뒤 주장 비교의 앞부분이 같다 (캐시를 다시 쓰는 조건)
    assert early.calls[0][0].content == model.calls[1][0].content


def test_no_question_search_needs_no_topic_at_question_time():
    assert judge_question_topic(QUESTION, [], model=FakeModel()) is None


# ---------- 근거 상태와 점수 ----------


def test_all_claims_same_uses_three_axes_and_copies_sentences():
    result = _score(_model(("같음", ["1-1"]), ("같음", ["1-2"])))
    assert result.status == EvidenceStatus.FOUND
    assert result.score == Decimal("90.00")  # 36 + 24 + 30 (같음 = 100)
    assert [e.sentence for e in result.evidence] == [
        "PG 승인 응답이 5초 안에 오지 않으면 결제 상태를 확인 중으로 둔다.",
        "보정 배치가 1분마다 조회한다.",
    ]
    assert (result.evidence[0].source_type, result.evidence[0].source_id, result.evidence[0].chunk_id) == ("프로젝트 문서", 101, 1)
    assert result.reason.startswith("질문에 맞게 순서대로 답했다.")
    assert result.llm_output["topic"] == {"question_in_docs": True} and len(result.llm_output["claims"]) == 2


@pytest.mark.parametrize(
    ("levels", "expected", "gathered"),
    [
        (["같음", "같음"], "90.00", "같음"),
        (["같음", "반대"], "82.50", "대부분 같음"),  # 절반 이상 같음 (75)
        (["같음", "반대", "반대"], "67.50", "일부만 같음"),  # 절반 미만 (25)
        (["반대"], "60.00", "반대"),  # (0)
    ],
)
def test_claim_levels_are_gathered_into_doc_match_level(levels, expected, gathered):
    claims = [f"주장 {i}" for i in range(1, len(levels) + 1)]
    result = _score(_model(*[(lv, ["1-1"]) for lv in levels], claims=claims))
    assert result.score == Decimal(expected) and result.doc_match_level == gathered


def test_claims_not_in_docs_are_not_counted():
    # 문서에 없는 다른 방법은 점수를 올리지도 내리지도 않는다
    result = _score(_model(("같음", ["1-1"]), ("문서에 없음", [])))
    assert result.status == EvidenceStatus.FOUND and result.score == Decimal("90.00")


def test_claim_without_valid_ids_counts_as_not_in_docs():
    result = _score(_model(("같음", ["9-9"]), ("반대", [])))
    assert result.status == EvidenceStatus.NO_ANSWER_DOC and result.doc_match_level == "문서에 없음"
    assert result.score == Decimal("75.00")  # 36 + 24 + 15
    assert result.reason.endswith(NO_ANSWER_DOC_NOTE) and result.evidence == []


def test_sentence_after_evidence_id_is_accepted():
    # P8에서 EXAONE이 실제로 쓴 형식: '[1-1] 문장'
    result = _score(_model(("같음", ["[1-1] PG 승인 응답이 5초 안에…"]), ("같음", ["1-2"])))
    assert result.status == EvidenceStatus.FOUND and len(result.evidence) == 2


FIRST = "PG 승인 응답이 5초 안에 오지 않으면 결제 상태를 확인 중으로 둔다."
SECOND = "보정 배치가 1분마다 조회한다."


def test_evidence_unlike_the_claim_is_not_kept_but_verdict_stays():
    # 1번 주장의 근거 중 SECOND는 주장과 직교(유사도 0)라 빠진다
    embed = FakeEmbed({SECOND: 1})
    result = _score(_model(("같음", ["1-1", "1-2"]), ("문서에 없음", [])), embed=embed)
    assert result.status == EvidenceStatus.FOUND and result.score == Decimal("90.00")
    assert [e.sentence for e in result.evidence] == [FIRST]


def test_best_evidence_is_kept_even_when_all_are_unlike():
    # 근거가 모두 기준 아래여도 주장마다 가장 비슷한 1개는 남긴다. 판정은 바꾸지 않는다
    embed = FakeEmbed({FIRST: 1, SECOND: 1})
    result = _score(_model(("같음", ["1-1"]), ("반대", ["1-2"])), embed=embed)
    assert result.score == Decimal("82.50")  # 같음·반대 → 대부분 같음
    assert [e.sentence for e in result.evidence] == [FIRST, SECOND]


def test_nothing_compared_and_topic_not_in_docs_is_no_question_doc():
    result = _score(_model(("문서에 없음", []), ("문서에 없음", []), in_docs=False))
    assert result.status == EvidenceStatus.NO_QUESTION_DOC
    assert result.score == Decimal("85.71")  # 90 × 4/7 + 80 × 3/7
    assert result.reason.endswith(NO_QUESTION_DOC_NOTE)


def test_compared_claim_wins_over_topic_judgment():
    result = _score(_model(("같음", ["1-1"]), ("문서에 없음", []), in_docs=False))
    assert result.status == EvidenceStatus.FOUND and result.score == Decimal("90.00")


def test_empty_question_context_needs_only_the_read_call():
    model = FakeModel(_read())
    # 답변 검색 결과가 있어도 채점에는 쓰지 않는다 (루브릭 설계서 3.3)
    result = _score(model, question_context=(), answer_context=(PG,))
    assert result.status == EvidenceStatus.NO_QUESTION_DOC and result.score == Decimal("85.71")
    assert len(model.calls) == 1
    assert result.llm_output["topic"] is None and result.llm_output["read"]["relevance"] == 90


def test_empty_claims_are_asked_once_more():
    model = FakeModel(_read(claims=()), _read(claims=["타임아웃 후 확인 중으로 둔다"]), _topic(), _claim("같음", ["1-1"]))
    result = _score(model)
    assert result.status == EvidenceStatus.FOUND
    # 두 번째 읽기 요청에는 앞 출력과 다시 묻는 말이 붙는다
    assert model.calls[1][-1].content == EMPTY_CLAIMS_RETRY


def test_still_empty_claims_score_zero_without_comparing():
    model = FakeModel(_read(claims=()), _read(claims=()))
    result = _score(model)
    # 다시 물어도 주장이 없으면 무응답이다. 0점이고 회사 문서와 비교하지 않는다 (읽기 2번뿐)
    assert result.status == EvidenceStatus.NO_CLAIM and result.score == Decimal("0.00")
    assert result.reason.endswith(NO_CLAIM_NOTE) and len(model.calls) == 2


def test_empty_claims_score_zero_even_without_question_search():
    # ㉠보다 먼저 본다. 질문이 문서에 없어도 아무 말도 안 했으면 0점이다
    result = _score(FakeModel(_read(claims=()), _read(claims=())), question_context=())
    assert result.status == EvidenceStatus.NO_CLAIM and result.score == Decimal("0.00")


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
