"""면접 그래프·내부 API 테스트 (실시간 면접 1~3단계). TTS·LLM·검색·vision·내용 채점은 가짜, 체크포인터는 메모리다."""

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

    def __init__(self, frames=None, vision_error=False):
        self.searches, self.scored, self.topics = [], [], []
        self.frames = frames if frames is not None else [{"emotion": "neutral"}] * 8 + [{"emotion": "fear"}] * 2
        self.vision_error = vision_error

    def search(self, posting_id, texts):
        self.searches.append((posting_id, texts))
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
        evidence = [EvidenceSentence("프로젝트 문서", 3, 7, "캐시로 응답을 줄였다.")]
        return ContentScore(Decimal("70.00"), "캐시 이유가 분명하다.", EvidenceStatus.FOUND, evidence, {})


def _answer(qkey, question_id, end_reason="button", **over):
    return AnswerRequest(qkey=qkey, question_id=question_id, end_reason=end_reason, **over)


def _build(saver, tts, llm=None, fakes=None):
    f = fakes or Fakes()
    deps = Deps(tts=tts, model=llm or FakeLlm(), fillers=FILLERS, search=f.search, analyze=f.analyze,
                score_content=f.score_content, judge_topic=f.judge_topic)
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
    assert actions == [{"type": "await_expression"}]
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
    assert actions == [{"type": "await_expression"}]
    with pytest.raises(builder.NotWaitingError):
        builder.submit_expression(graph, 5, ExpressionRequest(qkey="q12", answer_id=1))


def test_no_face_frames_counts_as_failure():
    graph, _ = _scored_setup(frames=[])
    _, actions = builder.submit_answer(graph, 5, _scored_answer(video_path=VIDEO))
    assert actions == [{"type": "await_expression"}]


def test_api_expression(api):
    api.post("/internal/interview/5/start", json=BODY, headers=H)
    r = api.post("/internal/interview/5/expression", json={"qkey": "q11", "answer_id": 1}, headers=H)
    assert r.status_code == 409
