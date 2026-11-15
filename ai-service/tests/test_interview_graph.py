"""면접 그래프·내부 API 테스트 (실시간 면접 1단계). TTS는 가짜, 체크포인터는 메모리다."""

import base64

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from app.api import interview
from app.core.config import get_settings
from app.graphs.interview import builder
from app.main import app
from app.schemas.internal import AnswerRequest, StartInterviewRequest

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


def _answer(qkey, question_id, end_reason="button"):
    return AnswerRequest(qkey=qkey, question_id=question_id, end_reason=end_reason)


@pytest.fixture
def setup():
    tts, saver = FakeTts(), InMemorySaver()
    return builder.build_interview_graph(saver, tts), tts, saver


def test_start_presents_first_question_with_audio(setup):
    graph, tts, _ = setup
    actions = builder.start_or_resume(graph, StartInterviewRequest(**BODY), tts)
    assert [a["type"] for a in actions] == ["present"]
    assert actions[0]["question"]["qkey"] == "q11"
    assert base64.b64decode(actions[0]["audio_b64"]) == "wav:캐시를 왜 썼나요?".encode()


def test_answers_go_through_all_questions_then_end(setup):
    graph, tts, _ = setup
    builder.start_or_resume(graph, StartInterviewRequest(**BODY), tts)
    second = builder.submit_answer(graph, 5, _answer("q11", 11))
    assert [(a["type"], a["question"]["qkey"]) for a in second] == [("present", "q12")]  # 이전 요청의 행동은 다시 오지 않는다
    third = builder.submit_answer(graph, 5, _answer("q12", 12, "timeout"))
    assert third[0]["question"]["qkey"] == "q13"
    assert builder.submit_answer(graph, 5, _answer("q13", 13)) == [{"type": "end"}]
    state = graph.get_state(builder.graph_config(5)).values
    assert state["answered"] == ["q11", "q12", "q13"] and state["queue"] == []


def test_reconnect_presents_the_waiting_question_again_without_advancing(setup):
    graph, tts, saver = setup
    builder.start_or_resume(graph, StartInterviewRequest(**BODY), tts)
    builder.submit_answer(graph, 5, _answer("q11", 11))
    # 서버가 다시 떠도(같은 체크포인터로 그래프를 새로 만듦) 같은 응시를 이어간다
    graph2 = builder.build_interview_graph(saver, tts)
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
    assert r.json()["evaluation"] is None and r.json()["actions"][0]["question"]["qkey"] == "q12"


def test_api_errors(api):
    assert api.post("/internal/interview/5/start", json=BODY | {"resume": True}, headers=H).status_code == 409
    assert api.post("/internal/interview/6/start", json=BODY, headers=H).status_code == 422  # 경로와 본문이 다름
    api.post("/internal/interview/5/start", json=BODY, headers=H)
    r = api.post("/internal/interview/5/answer", json={"qkey": "q13", "question_id": 13, "end_reason": "button"}, headers=H)
    assert r.status_code == 409
