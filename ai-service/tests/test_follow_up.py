"""꼬리질문 서브그래프 테스트 (AI Agent 설계서 5장). LLM은 정해 둔 출력을 차례로 내는 가짜다."""

import json

from langchain_core.messages import AIMessage

from app.graphs.interview.follow_up_nodes import make_follow_up

INPUTS = {
    "prev_question": "캐시를 왜 썼나요?",
    "prev_answer": "주문 API 응답이 느려서 Redis 캐시를 넣었습니다.",
    "parent_question": "캐시를 왜 썼나요?",
    "contexts": ["주문 API는 Redis로 응답을 캐시한다."],
    "compare_questions": ["모른다고 말한 경험은?"],
}
GOOD = {"question": "Redis 캐시가 오래된 값을 주지 않게 하려고 어떻게 했나요?"}
VALID = {"is_valid": True, "feedback": ""}
INVALID = {"is_valid": False, "feedback": "직전 질문을 다시 묻는다."}


class FakeModel:
    """출력을 차례로 낸다. 'ERROR'면 연결 오류처럼 예외를 던진다. 받은 프롬프트를 기록한다."""

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.prompts = []

    def invoke(self, messages):
        self.prompts.append(messages[-1].content)
        out = self.outputs.pop(0)
        if out == "ERROR":
            raise ConnectionError("LLM down")
        return AIMessage(content=json.dumps(out, ensure_ascii=False))


def _kinds(model):
    return ["검증" if "꼬리질문이 아래를 모두" in p else "fallback" if "왜 그렇게 했는지" in p
            else "고르기" if "더 물을 답변 문장" in p else "생성" for p in model.prompts]


TWO_SENTENCES = INPUTS | {"prev_answer": "음 먼저 인사드립니다. 주문 API 응답이 느려서 Redis 캐시를 넣었습니다."}


def test_answer_sentence_is_picked_without_documents_then_written_with_it():
    model = FakeModel({"based_on": "2"}, GOOD, VALID)
    assert make_follow_up(model, TWO_SENTENCES) == GOOD["question"]
    pick, write, _ = model.prompts
    assert "[2] 주문 API 응답이 느려서" in pick and "Redis로 응답을 캐시한다" not in pick  # 고르기는 회사 문서 없이
    assert "주문 API 응답이 느려서 Redis 캐시를 넣었습니다." in write and "먼저 인사드립니다" not in write
    assert "Redis로 응답을 캐시한다" in write  # 쓰기는 고른 문장과 회사 문서를 본다


def test_wrong_sentence_number_counts_as_error_and_skips_writing():
    model = FakeModel({"based_on": "9"}, {"based_on": "2"}, GOOD, VALID)
    assert make_follow_up(model, TWO_SENTENCES) == GOOD["question"]
    assert _kinds(model) == ["고르기", "고르기", "생성", "검증"]


def test_single_sentence_answer_needs_no_pick_call():
    model = FakeModel(GOOD, VALID)
    make_follow_up(model, INPUTS)
    assert _kinds(model) == ["생성", "검증"]


def test_valid_follow_up_is_confirmed():
    model = FakeModel(GOOD, VALID)
    assert make_follow_up(model, INPUTS) == GOOD["question"]
    generate, validate = model.prompts
    # 생성은 회사 문서·직전 답변·비교 질문을 본다. 검증은 생성 대화 기록 없이 꼬리질문과 답변만 본다
    assert "Redis로 응답을 캐시한다" in generate and "모른다고 말한 경험은?" in generate
    assert GOOD["question"] in validate and "Redis로 응답을 캐시한다" not in validate


def test_feedback_goes_to_the_next_generation():
    model = FakeModel(GOOD, INVALID, GOOD, VALID)
    assert make_follow_up(model, INPUTS) == GOOD["question"]
    assert INVALID["feedback"] in model.prompts[2]


def test_bad_form_is_retried_without_asking_the_validator():
    two_questions = {"question": "왜 Redis를 골랐나요? 다른 방법은 없었나요?"}
    model = FakeModel(two_questions, GOOD, VALID)
    assert make_follow_up(model, INPUTS) == GOOD["question"]
    assert _kinds(model) == ["생성", "생성", "검증"]
    assert "물음표가 하나인 질문" in model.prompts[1]  # 형식 문제를 피드백으로 넘긴다


def test_three_failed_validations_go_to_fallback():
    fallback = {"question": "Redis 캐시를 넣은 이유는 무엇인가요?"}
    model = FakeModel(GOOD, INVALID, GOOD, INVALID, GOOD, INVALID, fallback)
    assert make_follow_up(model, INPUTS) == fallback["question"]
    assert _kinds(model) == ["생성", "검증"] * 3 + ["fallback"]


def test_validation_error_retries_validation_only():
    model = FakeModel(GOOD, "ERROR", VALID)
    assert make_follow_up(model, INPUTS) == GOOD["question"]
    assert _kinds(model) == ["생성", "검증", "검증"]


def test_three_errors_go_to_fallback_and_its_failure_means_no_follow_up():
    # 연결 오류는 invoke_structured가 다시 묻지 않고 바로 올린다. 생성 에러 3번 → fallback도 에러
    model = FakeModel(*["ERROR"] * 4)
    assert make_follow_up(model, INPUTS) is None
    assert _kinds(model) == ["생성"] * 3 + ["fallback"]
