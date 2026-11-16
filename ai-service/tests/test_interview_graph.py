"""면접 그래프·내부 API 테스트 (실시간 면접 1~4단계). TTS·LLM·검색·vision·내용 채점은 가짜, 체크포인터는 메모리다."""

import base64
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.api import interview
from app.chains.answer_content import NO_CLAIM_NOTE, ContentScore, EvidenceSentence, EvidenceStatus
from app.core.config import get_settings
from app.graphs.interview import builder, nodes
from app.graphs.interview.nodes import Deps
from app.main import app
from app.rag.retriever import Chunk
from app.schemas.internal import AnswerRequest, ExpressionRequest, StartInterviewRequest

QUESTIONS = [
    {"qkey": "q11", "question_id": 11, "kind": "AI", "question_type": "직무", "text": "캐시를 왜 썼나요?"},
    {"qkey": "q12", "question_id": 12, "kind": "AI", "question_type": "인성", "text": "모른다고 말한 경험은?"},
    {"qkey": "q13", "question_id": 13, "kind": "기업", "question_type": None, "text": "지원 동기는?"},
]
BODY = {
    "session_id": 5,
    "posting_id": 1,
    "resume": False,
    "settings": {"follow_up_enabled": True, "think_time_sec": 30, "answer_time_sec": 90,
                 "ratios": {"내용": 50, "언어": 30, "비언어": 20}},
    "questions": QUESTIONS,
    "posting": {"posting_id": 1, "position_name": "백엔드", "job_description": "주문 API",
                "functional_talent": "-", "nonfunctional_talent": "-"},
    "documents": {"personal": {}, "skills": [], "educations": [], "careers": [], "projects": [],
                  "skill_cases": [], "essays": [], "portfolio_text": None},
}


class FakeTts:
    def __init__(self):
        self.texts = []

    def __call__(self, text):
        self.texts.append(text)
        return f"wav:{text}".encode()


class FakeLlm:
    """STT 보정 가짜. 'AP '를 'API '로 고친다. 받은 프롬프트를 기록한다."""

    def __init__(self):
        self.prompts = []

    def invoke(self, messages):
        text = messages[-1].content
        self.prompts.append(text)
        block = text.split("[음성 인식 구간]\n")[1].split("\n\n")[0]
        raws = [line.split("] ", 1)[1] for line in block.splitlines()]
        return AIMessage(content=json.dumps({"corrected": [r.replace("AP ", "API ") for r in raws]}, ensure_ascii=False))


FILLERS = ["음", "어"]
CHUNK = Chunk(chunk_id=7, source_type="프로젝트 문서", source_id=3, seq=0, content="캐시로 응답을 줄였다.", similarity=0.8)


class Fakes:
    """검색·vision·내용 채점·질문 주제 판정 가짜. 받은 인자를 기록한다."""

    def __init__(self, frames=None, vision_error=False, score_error=False, answer_search_error=False,
                 content="70.00", follow_ups=()):
        self.searches, self.scored, self.topics, self.follow_up_inputs = [], [], [], []
        self.content, self.follow_ups = content, list(follow_ups)
        self.score_error, self.answer_search_error = score_error, answer_search_error
        self.frames = frames if frames is not None else [{"emotion": "neutral"}] * 8 + [{"emotion": "fear"}] * 2
        self.vision_error = vision_error

    def search(self, posting_id, texts):
        self.searches.append((posting_id, texts))
        if self.answer_search_error and len(self.searches) > 1:  # 질문 검색은 되고 답변 검색만 실패
            raise RuntimeError("embed down")
        return [CHUNK]

    def analyze(self, video_path):
        if self.vision_error:
            raise RuntimeError("vision down")
        return self.frames

    def judge_topic(self, question, context, model):
        self.topics.append((question, context))
        return "topic-result"

    def score_content(self, question, answer, question_context, answer_context, job, model=None, topic=None):
        self.scored.append({"answer": answer, "qc": question_context, "ac": answer_context, "job": job, "topic": topic})
        if self.score_error:
            raise RuntimeError("LLM 형식 오류")
        evidence = [EvidenceSentence("프로젝트 문서", 3, 7, "캐시로 응답을 줄였다.")]
        return ContentScore(Decimal(self.content), "캐시 이유가 분명하다.", EvidenceStatus.FOUND, evidence, {})

    def follow_up(self, inputs):
        """정해 둔 꼬리질문을 차례로 낸다. None이면 만들지 못한 것이다."""
        self.follow_up_inputs.append(inputs)
        return self.follow_ups.pop(0) if self.follow_ups else None


def _answer(qkey, question_id, end_reason="button", **over):
    return AnswerRequest(qkey=qkey, question_id=question_id, end_reason=end_reason, **over)


def _build(saver, tts, llm=None, fakes=None):
    f = fakes or Fakes()
    deps = Deps(tts=tts, model=llm or FakeLlm(), fillers=FILLERS, search=f.search, analyze=f.analyze,
                follow_up=f.follow_up, score_content=f.score_content, judge_topic=f.judge_topic)
    return builder.build_interview_graph(saver, deps)


@pytest.fixture
def setup():
    tts, saver = FakeTts(), InMemorySaver()
    return _build(saver, tts), tts, saver


def test_start_presents_first_question_with_audio(setup):
    graph, tts, _ = setup
    actions = builder.start_or_resume(graph, StartInterviewRequest(**BODY), tts)
    assert [a["type"] for a in actions] == ["present"]
    assert actions[0]["question"]["qkey"] == "q11"
    assert base64.b64decode(actions[0]["audio_b64"]) == "wav:캐시를 왜 썼나요?".encode()


def test_answers_go_through_all_questions_then_end(setup):
    graph, tts, _ = setup
    builder.start_or_resume(graph, StartInterviewRequest(**BODY), tts)
    _, second = builder.submit_answer(graph, 5, _answer("q11", 11))
    assert [(a["type"], a["question"]["qkey"]) for a in second] == [("present", "q12")]  # 이전 요청의 행동은 다시 오지 않는다
    _, third = builder.submit_answer(graph, 5, _answer("q12", 12, "timeout"))
    assert third[0]["question"]["qkey"] == "q13"
    assert builder.submit_answer(graph, 5, _answer("q13", 13))[1] == [{"type": "end"}]
    state = graph.get_state(builder.graph_config(5)).values
    assert state["answered"] == ["q11", "q12", "q13"] and state["queue"] == []


def test_reconnect_presents_the_waiting_question_again_without_advancing(setup):
    graph, tts, saver = setup
    builder.start_or_resume(graph, StartInterviewRequest(**BODY), tts)
    builder.submit_answer(graph, 5, _answer("q11", 11))
    # 서버가 다시 떠도(같은 체크포인터로 그래프를 새로 만듦) 같은 응시를 이어간다
    graph2 = _build(saver, tts)
    actions = builder.start_or_resume(graph2, StartInterviewRequest(**(BODY | {"resume": True})), tts)
    assert [(a["type"], a["question"]["qkey"]) for a in actions] == [("present", "q12")]
    assert tts.texts.count("모른다고 말한 경험은?") == 2  # 다시 제시한 질문도 다시 읽어준다 (SYS-011)
    assert graph2.get_state(builder.graph_config(5)).values["answered"] == ["q11"]


def test_resume_without_checkpoint_is_an_error(setup):
    graph, tts, _ = setup
    with pytest.raises(builder.NoCheckpointError):
        builder.start_or_resume(graph, StartInterviewRequest(**(BODY | {"resume": True})), tts)


def test_answer_for_other_question_is_rejected(setup):
    graph, tts, _ = setup
    builder.start_or_resume(graph, StartInterviewRequest(**BODY), tts)
    with pytest.raises(builder.NotWaitingError):
        builder.submit_answer(graph, 5, _answer("q12", 12))
    with pytest.raises(builder.NotWaitingError):
        builder.submit_answer(graph, 99, _answer("q11", 11))  # 시작하지 않은 응시


def test_no_questions_ends_right_away(setup):
    graph, tts, _ = setup
    assert builder.start_or_resume(graph, StartInterviewRequest(**(BODY | {"questions": []})), tts) == [{"type": "end"}]


def test_finished_interview_returns_end_on_start(setup):
    graph, tts, _ = setup
    builder.start_or_resume(graph, StartInterviewRequest(**(BODY | {"questions": QUESTIONS[:1]})), tts)
    builder.submit_answer(graph, 5, _answer("q11", 11))
    assert builder.start_or_resume(graph, StartInterviewRequest(**(BODY | {"resume": True})), tts) == [{"type": "end"}]


# ---------- 내부 API ----------


@pytest.fixture
def api(monkeypatch, setup):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("EMBED_URL", "http://embed")
    monkeypatch.setenv("INTERNAL_TOKEN", "secret")
    get_settings.cache_clear()
    graph, tts, _ = setup
    app.dependency_overrides[interview.get_interview_graph] = lambda: graph
    app.dependency_overrides[interview.get_tts] = lambda: tts
    yield TestClient(app)
    app.dependency_overrides.clear()
    get_settings.cache_clear()


H = {"X-Internal-Token": "secret"}


def test_api_requires_internal_token(api):
    assert api.post("/internal/interview/5/start", json=BODY).status_code == 401


def test_api_start_and_answer(api):
    r = api.post("/internal/interview/5/start", json=BODY, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["actions"][0]["question"]["qkey"] == "q11"
    r = api.post("/internal/interview/5/answer", json={"qkey": "q11", "question_id": 11, "end_reason": "silence"}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["evaluation"]["segments"] == [] and r.json()["actions"][0]["question"]["qkey"] == "q12"


def test_api_errors(api):
    assert api.post("/internal/interview/5/start", json=BODY | {"resume": True}, headers=H).status_code == 409
    assert api.post("/internal/interview/6/start", json=BODY, headers=H).status_code == 422  # 경로와 본문이 다름
    api.post("/internal/interview/5/start", json=BODY, headers=H)
    r = api.post("/internal/interview/5/answer", json={"qkey": "q13", "question_id": 13, "end_reason": "button"}, headers=H)
    assert r.status_code == 409


# ---------- 답변 평가 (2단계: STT 보정·발화 수치) ----------


WORDS = [  # 답변 시간 시작 2.0초. 첫 단어 2.5초 → 응답 지연 0.5초. '캐시를'과 '그' 사이 4초 침묵
    {"word": "음,", "start": 2.5, "end": 2.9}, {"word": "AP", "start": 3.0, "end": 3.4},
    {"word": "응답을", "start": 3.5, "end": 4.0}, {"word": "캐시로", "start": 4.1, "end": 4.6},
    {"word": "줄였습니다.", "start": 4.7, "end": 5.5}, {"word": "그", "start": 9.5, "end": 9.7},
    {"word": "결과", "start": 9.8, "end": 10.2}, {"word": "빨라졌습니다.", "start": 10.3, "end": 11.0},
]


def test_answer_is_corrected_by_segment_and_measured(setup):
    graph, tts, _ = setup
    llm = FakeLlm()
    graph = _build(InMemorySaver(), tts, llm)
    builder.start_or_resume(graph, StartInterviewRequest(**BODY), tts)
    raw = "음, AP 응답을 캐시로 줄였습니다. 그 결과 빨라졌습니다."
    evaluation, _ = builder.submit_answer(graph, 5, _answer("q11", 11, raw_text=raw, words=WORDS, answer_start_sec=2.0))
    assert evaluation["segments"] == [
        {"time_offset_sec": 0, "raw_text": "음, AP 응답을 캐시로 줄였습니다.", "corrected_text": "음, API 응답을 캐시로 줄였습니다."},
        {"time_offset_sec": 7, "raw_text": "그 결과 빨라졌습니다.", "corrected_text": "그 결과 빨라졌습니다."},
    ]
    assert (evaluation["filler_count"], evaluation["silence_sec"], evaluation["response_delay_sec"], evaluation["duration_sec"]) == (1, 4.0, 0.5, 9)
    assert "캐시를 왜 썼나요?" in llm.prompts[0]  # 질문을 문맥으로 준다


def test_no_words_skips_llm(setup):
    graph, tts, _ = setup
    llm = FakeLlm()
    graph = _build(InMemorySaver(), tts, llm)
    builder.start_or_resume(graph, StartInterviewRequest(**BODY), tts)
    evaluation, _ = builder.submit_answer(graph, 5, _answer("q11", 11, end_reason="timeout"))
    keys = ("segments", "duration_sec", "filler_count", "silence_sec", "response_delay_sec")
    assert {k: evaluation[k] for k in keys} == {
        "segments": [], "duration_sec": 0, "filler_count": 0, "silence_sec": 0, "response_delay_sec": 0.0}
    # 답변이 없으면 답변 내용 없음 0점, 발화 0점 (루브릭 설계서 3.3, 4.2)
    assert (evaluation["content_score"], evaluation["content_reason"], evaluation["speech_score"]) == (
        Decimal("0.00"), NO_CLAIM_NOTE, Decimal("0.00"))
    assert llm.prompts == []


class BrokenLlm:
    def invoke(self, messages):
        return AIMessage(content="형식이 아닌 출력")


def test_correction_failure_keeps_raw_text(setup):
    graph, tts, _ = setup
    graph = _build(InMemorySaver(), tts, BrokenLlm())
    builder.start_or_resume(graph, StartInterviewRequest(**BODY), tts)
    evaluation, actions = builder.submit_answer(graph, 5, _answer("q11", 11, raw_text="AP 응답", words=WORDS[1:3]))
    assert [s["corrected_text"] for s in evaluation["segments"]] == ["AP 응답을"]
    assert actions[0]["question"]["qkey"] == "q12"  # 보정이 실패해도 면접은 이어진다


# ---------- 채점 (3단계) ----------


VIDEO = "interviews/5/11.webm"
RAW = "음, AP 응답을 캐시로 줄였습니다. 그 결과 빨라졌습니다."


def _scored_setup(**fake_args):
    fakes = Fakes(**fake_args)
    tts = FakeTts()
    graph = _build(InMemorySaver(), tts, fakes=fakes)
    builder.start_or_resume(graph, StartInterviewRequest(**BODY), tts)
    nodes._topic_pool.submit(lambda: None).result()  # 뒤에서 돈 질문 주제 판정이 끝나기를 기다린다
    return graph, fakes


def _scored_answer(**over):
    return _answer("q11", 11, raw_text=RAW, words=WORDS, answer_start_sec=2.0, **over)


def test_question_is_searched_when_presented_and_topic_is_judged_in_background():
    graph, fakes = _scored_setup()
    assert fakes.searches == [(1, ["캐시를 왜 썼나요?"])]
    assert fakes.topics == [("캐시를 왜 썼나요?", [CHUNK])]
    assert graph.get_state(builder.graph_config(5)).values["question_context"] == [CHUNK.__dict__]


def test_answer_is_scored_with_content_speech_and_expression():
    graph, fakes = _scored_setup()
    evaluation, actions = builder.submit_answer(graph, 5, _scored_answer(video_path=VIDEO))
    scored = fakes.scored[0]
    # 보정된 답변으로 검색하고, 질문 검색 결과·답변 검색 결과·미리 받은 질문 주제를 채점에 넘긴다
    assert scored["answer"] == "음, API 응답을 캐시로 줄였습니다. 그 결과 빨라졌습니다."
    assert fakes.searches[1] == (1, [scored["answer"]])
    assert (scored["qc"], scored["ac"], scored["job"], scored["topic"]) == ([CHUNK], [CHUNK], "주문 API", "topic-result")
    # 발화: 간투사 1(−3), 침묵 4초(−5) → 92. 표정: neutral 0.8, fear 0.2 → 80
    assert (evaluation["speech_score"], evaluation["main_expression"], evaluation["expression_ratio"]["fear"]) == (
        Decimal("92.00"), "neutral", 0.2)
    assert evaluation["expression_score"] == Decimal("80.00")
    # 답변 점수 = (70 × 50 + 92 × 30 + 80 × 20) ÷ 100
    assert evaluation["answer_score"] == Decimal("78.60")
    assert evaluation["evidence"] == [
        {"source_type": "프로젝트 문서", "source_id": 3, "chunk_id": 7, "sentence": "캐시로 응답을 줄였다."}]
    assert actions[0]["question"]["qkey"] == "q12"


def test_without_video_expression_is_left_out_of_answer_score():
    graph, _ = _scored_setup()
    evaluation, actions = builder.submit_answer(graph, 5, _scored_answer())
    assert (evaluation["main_expression"], evaluation["expression_score"]) == (None, None)
    # 표정이 없으면 내용·언어 비율을 늘린다: (70 × 50 + 92 × 30) ÷ 80
    assert evaluation["answer_score"] == Decimal("78.25")
    assert actions[0]["type"] == "present"  # 다시 분석할 영상이 없으니 기다리지 않는다


def test_failed_expression_waits_for_reanalysis_then_scores():
    graph, _ = _scored_setup(vision_error=True)
    evaluation, actions = builder.submit_answer(graph, 5, _scored_answer(video_path=VIDEO))
    assert [a["type"] for a in actions] == ["await_expression"] and actions[0]["question"]["qkey"] == "q11"
    assert (evaluation["content_score"], evaluation["answer_score"]) == (Decimal("70.00"), None)
    with pytest.raises(builder.NotWaitingError):
        builder.submit_answer(graph, 5, _answer("q12", 12))  # 표정을 기다리는 동안 다음 답변은 받지 않는다
    evaluation, actions = builder.submit_expression(graph, 5, ExpressionRequest(
        qkey="q11", answer_id=1, main_expression="happy", expression_ratio={"happy": 1.0}))
    assert (evaluation["expression_score"], evaluation["answer_score"]) == (Decimal("100.00"), Decimal("82.60"))
    assert actions[0]["question"]["qkey"] == "q12"


def test_reanalysis_failure_scores_without_expression():
    graph, _ = _scored_setup(vision_error=True)
    builder.submit_answer(graph, 5, _scored_answer(video_path=VIDEO))
    evaluation, _ = builder.submit_expression(graph, 5, ExpressionRequest(qkey="q11", answer_id=1))
    assert (evaluation["expression_score"], evaluation["answer_score"]) == (None, Decimal("78.25"))


def test_reconnect_while_waiting_for_expression_asks_again():
    graph, _ = _scored_setup(vision_error=True)
    builder.submit_answer(graph, 5, _scored_answer(video_path=VIDEO))
    actions = builder.start_or_resume(graph, StartInterviewRequest(**(BODY | {"resume": True})), FakeTts())
    assert [a["type"] for a in actions] == ["await_expression"] and actions[0]["question"]["qkey"] == "q11"
    with pytest.raises(builder.NotWaitingError):
        builder.submit_expression(graph, 5, ExpressionRequest(qkey="q12", answer_id=1))


def test_no_face_frames_counts_as_failure():
    graph, _ = _scored_setup(frames=[])
    _, actions = builder.submit_answer(graph, 5, _scored_answer(video_path=VIDEO))
    assert [a["type"] for a in actions] == ["await_expression"] and actions[0]["question"]["qkey"] == "q11"


def test_api_expression(api):
    api.post("/internal/interview/5/start", json=BODY, headers=H)
    r = api.post("/internal/interview/5/expression", json={"qkey": "q11", "answer_id": 1}, headers=H)
    assert r.status_code == 409


@pytest.mark.parametrize("failure", ["score_error", "answer_search_error"])
def test_content_scoring_failure_keeps_interview_going_without_answer_score(failure):
    """내용 채점이 끝까지 실패하면 답변 점수 없이 다음 질문으로 간다 (AI Agent 설계서 2.4)."""
    graph, _ = _scored_setup(**{failure: True})
    evaluation, actions = builder.submit_answer(graph, 5, _scored_answer(video_path=VIDEO))
    assert (evaluation["content_score"], evaluation["content_reason"], evaluation["answer_score"]) == (None, None, None)
    assert (evaluation["speech_score"], evaluation["expression_score"]) == (Decimal("92.00"), Decimal("80.00"))
    assert actions[0]["question"]["qkey"] == "q12"


# ---------- 꼬리질문 (4단계, SYS-008) ----------


JOB_QUESTIONS = [
    {"qkey": "q21", "question_id": 21, "kind": "AI", "question_type": "직무", "text": "캐시를 왜 썼나요?"},
    {"qkey": "q22", "question_id": 22, "kind": "AI", "question_type": "직무", "text": "장애를 어떻게 막았나요?"},
    {"qkey": "q23", "question_id": 23, "kind": "AI", "question_type": "직무", "text": "배포는 어떻게 했나요?"},
    {"qkey": "q24", "question_id": 24, "kind": "AI", "question_type": "인성", "text": "모른다고 말한 경험은?"},
]
FOLLOW_BODY = BODY | {"questions": JOB_QUESTIONS}


def _follow_setup(enabled=True, **fake_args):
    """내용 90점이면 답변 점수 (90 × 50 + 92 × 30 + 80 × 20) ÷ 100 = 88.6 → 꼬리질문 조건 ③ 참."""
    fakes = Fakes(**({"content": "90.00"} | fake_args))
    tts = FakeTts()
    graph = _build(InMemorySaver(), tts, fakes=fakes)
    settings = FOLLOW_BODY["settings"] | {"follow_up_enabled": enabled}
    builder.start_or_resume(graph, StartInterviewRequest(**(FOLLOW_BODY | {"settings": settings})), tts)
    nodes._topic_pool.submit(lambda: None).result()
    return graph, fakes, tts


def _job_answer(qkey, question_id, **over):
    return _answer(qkey, question_id, raw_text=RAW, words=WORDS, answer_start_sec=2.0, video_path=VIDEO, **over)


def _state(graph):
    return graph.get_state(builder.graph_config(5)).values


def test_high_score_job_answer_gets_a_follow_up_and_next_job_question_is_removed():
    graph, fakes, tts = _follow_setup(follow_ups=["Redis 캐시가 오래된 값을 주지 않게 어떻게 했나요?"])
    evaluation, actions = builder.submit_answer(graph, 5, _job_answer("q21", 21))
    assert evaluation["answer_score"] == Decimal("88.60")
    remove, present = actions
    assert (remove["type"], remove["question"]["qkey"]) == ("remove", "q22")  # 바로 다음 직무 질문
    follow = present["question"]
    assert present["type"] == "present" and follow["kind"] == "꼬리" and follow["parent_qkey"] == "q21"
    assert follow["question_id"] is None and follow["qkey"].startswith("f")
    assert base64.b64decode(present["audio_b64"]) == f"wav:{follow['text']}".encode()  # 꼬리질문도 읽어준다
    # 꼬리질문 입력: 직전 답변은 보정문, 비교 대상에서 부모와 바로 다음 직무 질문은 뺀다
    inputs = fakes.follow_up_inputs[0]
    assert inputs["prev_answer"] == "음, API 응답을 캐시로 줄였습니다. 그 결과 빨라졌습니다."
    assert inputs["parent_question"] == "캐시를 왜 썼나요?" and inputs["contexts"] == [CHUNK.content]
    assert inputs["compare_questions"] == ["배포는 어떻게 했나요?", "모른다고 말한 경험은?"]
    state = _state(graph)
    assert [q["qkey"] for q in state["queue"]] == ["q23", "q24"] and state["follow_up_counts"] == {"q21": 1}
    # 꼬리질문으로도 회사 문서를 미리 검색한다 (AI Agent 설계서 4.1)
    assert fakes.searches[-1] == (1, [follow["text"]])


def test_binding_sets_question_id_and_follow_up_of_follow_up_keeps_the_same_parent():
    graph, fakes, _ = _follow_setup(follow_ups=["꼬리 1?", "꼬리 2?"])
    _, actions = builder.submit_answer(graph, 5, _job_answer("q21", 21))
    first = actions[1]["question"]
    binding = {"qkey": first["qkey"], "question_id": 901}
    _, actions = builder.submit_answer(graph, 5, _job_answer(first["qkey"], 901, bindings=[binding]))
    assert _state(graph)["history"][-1]["question"]["question_id"] == 901  # 짝을 반영한 뒤 답변을 기록했다
    remove, present = actions
    assert remove["question"]["qkey"] == "q23" and present["question"]["parent_qkey"] == "q21"
    assert _state(graph)["follow_up_counts"] == {"q21": 2}
    # 비교 대상: 부모(q21)와 그 꼬리질문은 빼고, 다음 직무 질문(q23)도 뺀다
    assert fakes.follow_up_inputs[1]["compare_questions"] == ["모른다고 말한 경험은?"]


def test_third_follow_up_is_not_made_for_the_same_parent():
    jobs = JOB_QUESTIONS[:3] + [{"qkey": "q25", "question_id": 25, "kind": "AI", "question_type": "직무",
                                  "text": "테스트는 어떻게 했나요?"}]
    fakes = Fakes(content="90.00", follow_ups=["꼬리 1?", "꼬리 2?", "꼬리 3?"])
    tts = FakeTts()
    graph = _build(InMemorySaver(), tts, fakes=fakes)
    builder.start_or_resume(graph, StartInterviewRequest(**(BODY | {"questions": jobs})), tts)
    _, a = builder.submit_answer(graph, 5, _job_answer("q21", 21))
    _, a = builder.submit_answer(graph, 5, _job_answer(a[1]["question"]["qkey"], 0))
    _, a = builder.submit_answer(graph, 5, _job_answer(a[1]["question"]["qkey"], 0))
    assert [x["type"] for x in a] == ["present"] and a[0]["question"]["qkey"] == "q25"  # 부모당 2개까지
    assert len(fakes.follow_up_inputs) == 2


def test_no_follow_up_when_disabled_or_low_score_or_not_job_or_no_job_left():
    graph, fakes, _ = _follow_setup(enabled=False, follow_ups=["꼬리?"])
    assert builder.submit_answer(graph, 5, _job_answer("q21", 21))[1][0]["question"]["qkey"] == "q22"
    graph, fakes, _ = _follow_setup(content="60.00", follow_ups=["꼬리?"])  # 답변 점수 68.6
    assert builder.submit_answer(graph, 5, _job_answer("q21", 21))[1][0]["question"]["qkey"] == "q22"
    assert fakes.follow_up_inputs == []
    # 기본 질문 목록: q11 직무 다음이 인성 질문이라 남은 직무 질문이 없다
    fakes = Fakes(content="90.00", follow_ups=["꼬리?"])
    tts = FakeTts()
    graph = _build(InMemorySaver(), tts, fakes=fakes)
    builder.start_or_resume(graph, StartInterviewRequest(**BODY), tts)
    assert builder.submit_answer(graph, 5, _job_answer("q11", 11))[1][0]["question"]["qkey"] == "q12"
    assert fakes.follow_up_inputs == []


def test_failed_follow_up_keeps_the_next_job_question():
    graph, fakes, _ = _follow_setup(follow_ups=[None])
    _, actions = builder.submit_answer(graph, 5, _job_answer("q21", 21))
    assert [(a["type"], a["question"]["qkey"]) for a in actions] == [("present", "q22")]
    assert len(fakes.follow_up_inputs) == 1 and _state(graph)["follow_up_counts"] == {}


def test_follow_up_is_judged_after_expression_reanalysis_too():
    graph, fakes, _ = _follow_setup(vision_error=True, follow_ups=["꼬리?"])
    _, actions = builder.submit_answer(graph, 5, _job_answer("q21", 21))
    assert [a["type"] for a in actions] == ["await_expression"] and fakes.follow_up_inputs == []
    _, actions = builder.submit_expression(graph, 5, ExpressionRequest(
        qkey="q21", answer_id=1, main_expression="neutral", expression_ratio={"neutral": 1.0}))
    assert [a["type"] for a in actions] == ["remove", "present"]
