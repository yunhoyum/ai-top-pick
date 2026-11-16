"""AI 화상 면접 응시 (실시간 면접 1~3단계: APP-014·015·016·018, SYS-004·005·007·011). ai-service·Deepgram·vision은 가짜다."""

import base64
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import ws_interview
from app.core.config import get_settings
from app.realtime import upload_registry
from app.services import expression_batch, job_queue
from test_applications import _open_posting, applicant, pid  # noqa: F401  (fixture)
from test_my_applications import _stage, _submitted, _timeline
from test_postings import _login, _sql, admin  # noqa: F401  (fixture)


def _questions(aid):
    """직무 → 인성 → 기업 순서로 질문 3개. 기업 질문 내용은 company_question에 있다."""
    pid = _sql("select posting_id from application where application_id = :a", a=aid)[0][0]
    cq = _sql("insert into company_question (posting_id, seq, content) values (:p, 99, '지원 동기는?') "
              "returning company_question_id", p=pid)[0][0]
    for seq, (qtype, content, company) in enumerate(
        [("직무", "캐시를 왜 썼나요?", None), ("인성", "모른다고 말한 경험은?", None), (None, None, cq)], start=1
    ):
        _sql("insert into interview_question (application_id, company_question_id, question_type, seq, content, is_revealed) "
             "values (:a, :c, :t, :s, :q, false)", a=aid, c=company, t=qtype, s=seq, q=content)
    return [r[0] for r in _sql("select question_id from interview_question where application_id = :a order by seq", a=aid)]


def _ready(pid, questions=True, job="완료"):
    """서류 합격, 면접 기간 중, 생각 0초·답변 1초 (테스트를 빨리 끝내려고)."""
    _timeline(pid, doc_result=-2, interview_start=-1, interview_end=1, interview_result=2)
    _sql("update job_posting set think_time_sec = 0, answer_time_sec = 1, follow_up_enabled = false where posting_id = :p", p=pid)
    aid = _stage(pid, "서류", "합격")
    qids = _questions(aid) if questions else []
    if job:
        _sql("insert into batch_job (job_type, posting_id, application_id, status) values ('면접 질문 생성', :p, :a, :s)",
             p=pid, a=aid, s=job)
    return aid, qids


@pytest.fixture
def ready(applicant, pid):
    _submitted(applicant, pid)
    return _ready(pid)


def _guide(c, aid):
    return c.get(f"/api/applications/{aid}/interview/guide")


def _enter(c, aid, camera=True, mic=True):
    return c.post(f"/api/applications/{aid}/interview/sessions", json={"camera_ok": camera, "mic_ok": mic})


# ---------- 안내 (화면 22) ----------
def test_guide_shows_counts_and_times(applicant, ready):
    aid, _ = ready
    r = _guide(applicant, aid)
    assert r.status_code == 200, r.text
    g = r.json()
    assert (g["question_count"], g["think_time_sec"], g["answer_time_sec"], g["can_enter"]) == (3, 0, 1, True)


@pytest.mark.parametrize("case, reason", [
    ("fail", "서류 전형 합격자만"), ("closed", "면접 기간이 아닙니다"), ("not_ready", "면접 질문을 준비하고"),
])
def test_guide_and_enter_reject_with_reason(applicant, pid, case, reason):
    _submitted(applicant, pid)
    if case == "fail":
        _timeline(pid, doc_result=-2, interview_start=-1, interview_end=1, interview_result=2)
        aid = _stage(pid, "서류", "불합격")
    else:
        aid, _ = _ready(pid, job="실행 중" if case == "not_ready" else "완료")
        if case == "closed":
            _sql("update job_posting set interview_end_at = now() - interval '1 minute' where posting_id = :p", p=pid)
    g = _guide(applicant, aid).json()
    assert g["can_enter"] is False and reason in g["reason"]
    r = _enter(applicant, aid)
    assert r.status_code == 409 and r.json()["code"] == "INTERVIEW_NOT_AVAILABLE" and reason in r.json()["message"]


def test_guide_is_own_application_only(client, admin, ready):
    aid, _ = ready
    other = _login(TestClient(client.app), "지원자")
    assert _guide(other, aid).status_code == 404
    assert _guide(admin, aid).status_code == 403


# ---------- 응시 입구 (화면 23) ----------
def test_enter_requires_camera_and_mic(applicant, ready):
    aid, _ = ready
    r = _enter(applicant, aid, camera=True, mic=False)
    assert r.status_code == 409 and "카메라와 마이크" in r.json()["message"]
    assert _sql("select count(*) from interview_session where application_id = :a", a=aid)[0][0] == 0


def test_enter_creates_session_once_and_returns_it_again(applicant, ready):
    aid, _ = ready
    first = _enter(applicant, aid).json()
    assert first["status"] == "진행 중" and first["resumed"] is False
    again = _enter(applicant, aid).json()
    assert again == first | {"resumed": True}  # 재접속은 같은 응시
    assert _sql("select camera_checked, mic_checked, attempt_no from interview_session where session_id = :s",
                s=first["session_id"])[0] == (True, True, 1)


def test_completed_session_cannot_be_entered(applicant, ready):
    aid, _ = ready
    sid = _enter(applicant, aid).json()["session_id"]
    _sql("update interview_session set status = '완료' where session_id = :s", s=sid)
    r = _enter(applicant, aid)
    assert r.status_code == 409 and "이미 면접을 마쳤습니다" in r.json()["message"]


def test_my_applications_gives_application_id(applicant, ready):
    aid, _ = ready
    assert aid in [i["application_id"] for i in applicant.get("/api/applications").json()]


# ---------- 면접 WebSocket (화면 24) ----------
EVALUATION = {
    "segments": [{"time_offset_sec": 0, "raw_text": "AP 캐시를 썼습니다.", "corrected_text": "API 캐시를 썼습니다."},
                 {"time_offset_sec": 4, "raw_text": "빨라졌습니다.", "corrected_text": "빨라졌습니다."}],
    "duration_sec": 6, "filler_count": 1, "silence_sec": 3.5, "response_delay_sec": 0.5,
    # ai-service는 Decimal을 JSON 문자열로 보낸다
    "main_expression": "neutral", "expression_ratio": {"neutral": 0.8, "fear": 0.2},
    "content_score": "70.00", "content_reason": "캐시 이유가 분명하다.", "speech_score": "92.00",
    "expression_score": "80.00", "answer_score": "78.60",
    "evidence": [{"source_type": "프로젝트 문서", "source_id": 3, "chunk_id": 7, "sentence": "캐시로 응답을 줄였다."}],
}
# 표정 분석이 실패한 답변: 표정·표정 점수·답변 점수가 비어 있다
FAILED_EXPRESSION = EVALUATION | {"main_expression": None, "expression_ratio": None, "expression_score": None,
                                  "answer_score": None}
WORDS = [{"word": "AP", "start": 0.5, "end": 0.9}]


class FakeRelay:
    """Deepgram 가짜. 음성 조각마다 중간 자막을 내고, 닫으면 확정 원문을 준다."""

    made: list["FakeRelay"] = []

    def __init__(self, on_result):
        self.on_result, self.chunks, self.closed = on_result, [], False
        FakeRelay.made.append(self)

    async def connect(self):
        pass

    async def send_audio(self, chunk):
        self.chunks.append(chunk)
        await self.on_result(f"자막{len(self.chunks)}", False)

    async def close(self):
        self.closed = True
        return ("AP 캐시를 썼습니다." if self.chunks else ""), (WORDS if self.chunks else [])


@pytest.fixture(autouse=True)
def fake_relay(monkeypatch):
    """실제 Deepgram에 붙지 않게 한다. 영상을 올리지 않는 테스트는 기다리지 않고 넘어간다."""
    FakeRelay.made = []
    monkeypatch.setattr(ws_interview, "get_relay_factory", lambda: FakeRelay)
    monkeypatch.setattr(get_settings(), "VIDEO_UPLOAD_WAIT_SEC", 0.1)


class FakeAi:
    """ai-service 가짜. 질문을 차례로 제시하고, 마지막 답변 뒤에 종료한다."""

    def __init__(self, qids, fail_expression=False, evaluation=None):
        self.qids, self.starts, self.answers, self.expressions = qids, [], [], []
        self.fail_expression, self.evaluation = fail_expression, evaluation or EVALUATION

    def _present(self, i):
        q = self.qids[i]
        return {"type": "present", "question": {"qkey": f"q{q}", "question_id": q, "kind": "AI", "text": f"질문 {i + 1}"},
                "audio_b64": base64.b64encode(f"wav{i + 1}".encode()).decode()}

    async def start_interview(self, session_id, payload):
        self.starts.append(payload)
        return {"actions": [self._present(0)]}

    async def submit_answer(self, session_id, payload):
        self.answers.append(payload)
        i = len(self.answers)
        if self.fail_expression:
            return {"evaluation": FAILED_EXPRESSION,
                    "actions": [{"type": "await_expression", "question": self._present(i - 1)["question"]}]}
        return {"evaluation": self.evaluation, "actions": self._next(i)}

    def _next(self, i):
        return [self._present(i) if i < len(self.qids) else {"type": "end"}]

    async def submit_expression(self, session_id, payload):
        self.expressions.append(payload)
        score = "90.00" if payload["main_expression"] else None
        return {"expression_score": score, "answer_score": "81.00" if score else "78.25",
                "actions": self._next(len(self.answers))}

    async def aclose(self):
        pass


def _socket(c, sid):
    return c.websocket_connect(f"/ws/interview/{sid}")


def _answer_one(ws, qid, press):
    q = ws.receive_json()
    assert q["type"] == "question" and q["question_id"] == qid and (q["think_sec"], q["answer_sec"]) == (0, 1)
    audio = ws.receive_bytes()
    ws.send_json({"type": "question_audio_ended", "question_id": qid})
    assert ws.receive_json()["phase"] == "think"
    assert ws.receive_json()["phase"] == "answer"
    if press:
        ws.send_json({"type": "answer_done", "question_id": qid})
    end = ws.receive_json()
    assert end == {"type": "answer_end", "question_id": qid, "reason": "button" if press else "timeout"}
    assert ws.receive_json() == {"type": "evaluating", "question_id": qid}
    return q, audio


def test_socket_runs_whole_interview_and_completes_session(monkeypatch, applicant, ready):
    aid, qids = ready
    sid = _enter(applicant, aid).json()["session_id"]
    fake = FakeAi(qids)
    monkeypatch.setattr(ws_interview, "get_ai_client", lambda: fake)
    with _socket(applicant, sid) as ws:
        assert ws.receive_json() == {"type": "connected", "session_id": sid}
        q1, audio = _answer_one(ws, qids[0], press=True)
        assert (q1["seq"], q1["total"], audio) == (1, 3, b"wav1")
        _answer_one(ws, qids[1], press=False)  # 답변 시간이 끝나 자동으로 넘어간다
        _answer_one(ws, qids[2], press=True)
        end = ws.receive_json()
        assert end["type"] == "interview_end" and end["answered_count"] == 3
    # 시작 요청 본문 (규약 2.2): 유효 질문 3개를 직무 → 인성 → 기업 순서로, 기업 질문 내용은 company_question에서
    start = fake.starts[0]
    assert start["resume"] is False and start["session_id"] == sid
    assert [(q["kind"], q["question_type"], q["text"]) for q in start["questions"]] == [
        ("AI", "직무", "캐시를 왜 썼나요?"), ("AI", "인성", "모른다고 말한 경험은?"), ("기업", None, "지원 동기는?")]
    assert start["settings"] == {"follow_up_enabled": False, "think_time_sec": 0, "answer_time_sec": 1,
                                 "ratios": start["settings"]["ratios"]}
    assert [a["end_reason"] for a in fake.answers] == ["button", "timeout", "button"]
    assert _sql("select status, ended_at is not null from interview_session where session_id = :s", s=sid)[0] == ("완료", True)
    assert [r[0] for r in _sql("select is_revealed from interview_question where application_id = :a order by seq", a=aid)] == [True] * 3


def test_answer_button_during_think_time_is_ignored(monkeypatch, applicant, ready):
    aid, qids = ready
    _sql("update job_posting set think_time_sec = 1 where posting_id = (select posting_id from application where application_id = :a)", a=aid)
    sid = _enter(applicant, aid).json()["session_id"]
    monkeypatch.setattr(ws_interview, "get_ai_client", lambda: FakeAi(qids))
    with _socket(applicant, sid) as ws:
        ws.receive_json(), ws.receive_json(), ws.receive_bytes()
        ws.send_json({"type": "question_audio_ended", "question_id": qids[0]})
        assert ws.receive_json()["phase"] == "think"
        ws.send_json({"type": "answer_done", "question_id": qids[0]})  # 생각 시간 중 → 버린다
        assert ws.receive_json()["phase"] == "answer"
        assert ws.receive_json()["reason"] == "timeout"


def test_reconnect_sends_resume_after_a_question_was_presented(monkeypatch, applicant, ready):
    aid, qids = ready
    sid = _enter(applicant, aid).json()["session_id"]
    fake = FakeAi(qids)
    monkeypatch.setattr(ws_interview, "get_ai_client", lambda: fake)
    with _socket(applicant, sid) as ws:
        ws.receive_json(), ws.receive_json(), ws.receive_bytes()  # 첫 질문을 받고 끊는다
    with _socket(applicant, sid) as ws:
        assert ws.receive_json()["type"] == "connected"
    assert [s["resume"] for s in fake.starts] == [False, True]
    assert _sql("select status from interview_session where session_id = :s", s=sid)[0][0] == "진행 중"  # 끊겨도 진행 중


def test_socket_rejects_without_login_or_others_session(monkeypatch, client, applicant, ready):
    aid, qids = ready
    sid = _enter(applicant, aid).json()["session_id"]
    monkeypatch.setattr(ws_interview, "get_ai_client", lambda: FakeAi(qids))
    for c in (TestClient(client.app), _login(TestClient(client.app), "지원자")):
        with pytest.raises(WebSocketDisconnect):
            with _socket(c, sid) as ws:
                ws.receive_json()


def test_socket_starts_even_if_portfolio_file_is_missing(monkeypatch, applicant, ready):
    """포트폴리오 글은 대체 질문(5단계)에만 쓴다. 파일이 없어도 면접은 시작한다 (실제 시연에서 500으로 막혔다)."""
    import os
    from app.services import file_service

    aid, qids = ready
    path = _sql("select file_path from portfolio where application_id = :a", a=aid)[0][0]
    os.remove(file_service.resolve(path))
    sid = _enter(applicant, aid).json()["session_id"]
    fake = FakeAi(qids)
    monkeypatch.setattr(ws_interview, "get_ai_client", lambda: fake)
    with _socket(applicant, sid) as ws:
        assert ws.receive_json()["type"] == "connected"
    assert fake.starts[0]["documents"]["portfolio_text"] is None


# ---------- 답변 저장 (2단계: 음성 중계·영상·STT) ----------
def _video(c, sid, qid, data=b"webm-data", ctype="video/webm"):
    return c.post(f"/api/interview/sessions/{sid}/questions/{qid}/video", files={"file": ("a.webm", data, ctype)})


def test_answer_audio_is_relayed_and_answer_is_saved_with_video(monkeypatch, applicant, ready):
    aid, qids = ready
    monkeypatch.setattr(get_settings(), "VIDEO_UPLOAD_WAIT_SEC", 5.0)
    sid = _enter(applicant, aid).json()["session_id"]
    fake = FakeAi(qids[:1])
    monkeypatch.setattr(ws_interview, "get_ai_client", lambda: fake)
    with _socket(applicant, sid) as ws:
        ws.receive_json(), ws.receive_json(), ws.receive_bytes()
        ws.send_bytes(b"before-answer")  # 답변 시간 전 음성은 보내지 않는다
        ws.send_json({"type": "question_audio_ended", "question_id": qids[0]})
        assert ws.receive_json()["phase"] == "think"
        assert ws.receive_json()["phase"] == "answer"
        ws.send_bytes(b"opus1")
        assert ws.receive_json() == {"type": "transcript", "text": "자막1", "is_final": False}
        ws.send_json({"type": "answer_done", "question_id": qids[0]})
        assert ws.receive_json()["reason"] == "button"
        assert ws.receive_json()["type"] == "evaluating"
        assert _video(applicant, sid, qids[0]).status_code == 204
        assert ws.receive_json()["type"] == "interview_end"
    assert FakeRelay.made[0].chunks == [b"opus1"] and FakeRelay.made[0].closed
    sent = fake.answers[0]
    assert (sent["raw_text"], sent["words"], sent["answer_start_sec"], sent["video_path"]) == (
        "AP 캐시를 썼습니다.", WORDS, 0.0, f"interviews/{sid}/{qids[0]}.webm")
    answer = _sql("select answer_id, video_path, duration_sec, filler_count, silence_sec, response_delay_sec, answer_status "
                  "from interview_answer where session_id = :s", s=sid)
    assert [tuple(r[1:]) for r in answer] == [(f"interviews/{sid}/{qids[0]}.webm", 6, 1, 3.5, 0.5, "유효")]
    assert _sql("select time_offset_sec, raw_text, corrected_text from stt_record where answer_id = :a order by stt_id",
                a=answer[0][0]) == [(0, "AP 캐시를 썼습니다.", "API 캐시를 썼습니다."), (4, "빨라졌습니다.", "빨라졌습니다.")]


def test_answer_ends_after_silence_following_speech(monkeypatch, applicant, ready):
    aid, qids = ready
    _sql("update job_posting set answer_time_sec = 5 where posting_id = (select posting_id from application where application_id = :a)", a=aid)
    monkeypatch.setattr(get_settings(), "SILENCE_END_SEC", 0.3)
    sid = _enter(applicant, aid).json()["session_id"]
    fake = FakeAi(qids[:1])
    monkeypatch.setattr(ws_interview, "get_ai_client", lambda: fake)
    with _socket(applicant, sid) as ws:
        ws.receive_json(), ws.receive_json(), ws.receive_bytes()
        ws.send_json({"type": "question_audio_ended", "question_id": qids[0]})
        ws.receive_json(), ws.receive_json()
        ws.send_bytes(b"opus1")
        assert ws.receive_json()["type"] == "transcript"
        assert ws.receive_json()["reason"] == "silence"  # 답변 시간 5초보다 먼저 끝난다
        ws.receive_json()  # evaluating
        assert ws.receive_json()["type"] == "interview_end"
    assert fake.answers[0]["end_reason"] == "silence" and fake.answers[0]["video_path"] is None


def test_video_upload_is_own_in_progress_session_and_webm_only(client, applicant, ready):
    aid, qids = ready
    sid = _enter(applicant, aid).json()["session_id"]
    other = _login(TestClient(client.app), "지원자")
    assert _video(other, sid, qids[0]).status_code == 404
    assert _video(applicant, sid, 999999999).status_code == 404  # 이 응시의 질문이 아니다
    assert _video(applicant, sid, qids[0], ctype="video/mp4").status_code == 422
    assert _video(applicant, sid, qids[0]).status_code == 204
    _sql("update interview_session set status = '완료' where session_id = :s", s=sid)
    assert _video(applicant, sid, qids[0]).status_code == 404



# ---------- 채점 (3단계: 점수·표정·근거 문장, 표정 재분석) ----------
def _one_answer(ws, qid):
    ws.receive_json(), ws.receive_json(), ws.receive_bytes()
    ws.send_json({"type": "question_audio_ended", "question_id": qid})
    ws.receive_json(), ws.receive_json()
    ws.send_json({"type": "answer_done", "question_id": qid})
    ws.receive_json(), ws.receive_json()  # answer_end, evaluating
    assert ws.receive_json()["type"] == "interview_end"


def _answer_row(sid):
    return _sql("select answer_id, main_expression, content_score, content_reason, speech_score, expression_score, "
                "answer_score from interview_answer where session_id = :s and answer_status = '유효'", s=sid)[0]


def test_scores_and_evidence_are_saved(monkeypatch, applicant, ready):
    aid, qids = ready
    sid = _enter(applicant, aid).json()["session_id"]
    monkeypatch.setattr(ws_interview, "get_ai_client", lambda: FakeAi(qids[:1]))
    with _socket(applicant, sid) as ws:
        _one_answer(ws, qids[0])
    row = _answer_row(sid)
    assert tuple(row[1:]) == ("neutral", 70, "캐시 이유가 분명하다.", 92, 80, Decimal("78.6"))
    assert _sql("select seq, source_type, source_id, chunk_id, sentence from evidence_sentence where answer_id = :a",
                a=row[0]) == [(1, "프로젝트 문서", 3, 7, "캐시로 응답을 줄였다.")]


class FakeVision:
    def __init__(self, frames):
        self.frames, self.paths = frames, []

    def analyze(self, video_path):
        self.paths.append(video_path)
        if self.frames is None:
            raise RuntimeError("vision down")
        return self.frames


def _run_worker_inline(monkeypatch, vision):
    """job_queue.send 대신 worker 작업을 바로 돌린다."""
    def send(job_type, job_id):
        assert job_type == "표정 분석 재처리"
        expression_batch.reprocess_expressions(job_id, client=vision)
    monkeypatch.setattr(job_queue, "send", send)


def _with_video(sid, qid):
    """영상이 올라온 것처럼 둔다. 업로드 대기를 건너뛰려고 registry에 바로 알린다."""
    upload_registry.notify(sid, qid, f"interviews/{sid}/{qid}.webm")


def test_failed_expression_is_reanalysed_by_worker_then_scored(monkeypatch, applicant, ready):
    aid, qids = ready
    sid = _enter(applicant, aid).json()["session_id"]
    fake = FakeAi(qids[:1], fail_expression=True)
    monkeypatch.setattr(ws_interview, "get_ai_client", lambda: fake)
    vision = FakeVision([{"emotion": "happy"}] * 3 + [{"emotion": "neutral"}])
    _run_worker_inline(monkeypatch, vision)
    monkeypatch.setattr(upload_registry, "forget", lambda *a: None)  # 미리 알린 업로드를 지우지 않게
    _with_video(sid, qids[0])
    with _socket(applicant, sid) as ws:
        _one_answer(ws, qids[0])
    assert vision.paths == [f"interviews/{sid}/{qids[0]}.webm"]
    sent = fake.expressions[0]
    assert (sent["qkey"], sent["main_expression"], sent["expression_ratio"]["happy"]) == (f"q{qids[0]}", "happy", 0.75)
    row = _answer_row(sid)
    assert (row[1], row[5], row[6]) == ("happy", 90, 81)
    assert _sql("select status from batch_job where job_type = '표정 분석 재처리' and application_id = :a", a=aid) == [("완료",)]


def test_reanalysis_failure_scores_without_expression(monkeypatch, applicant, ready):
    aid, qids = ready
    sid = _enter(applicant, aid).json()["session_id"]
    fake = FakeAi(qids[:1], fail_expression=True)
    monkeypatch.setattr(ws_interview, "get_ai_client", lambda: fake)
    _run_worker_inline(monkeypatch, FakeVision(None))
    monkeypatch.setattr(upload_registry, "forget", lambda *a: None)
    _with_video(sid, qids[0])
    with _socket(applicant, sid) as ws:
        _one_answer(ws, qids[0])
    assert (fake.expressions[0]["main_expression"], fake.expressions[0]["expression_ratio"]) == (None, None)
    row = _answer_row(sid)
    assert (row[1], row[5], row[6]) == (None, None, 78.25)


def test_expression_wait_times_out(monkeypatch, applicant, ready):
    """worker가 끝내지 못해도 EXPRESSION_WAIT_SEC 뒤에는 표정 없이 채점한다."""
    aid, qids = ready
    sid = _enter(applicant, aid).json()["session_id"]
    fake = FakeAi(qids[:1], fail_expression=True)
    monkeypatch.setattr(ws_interview, "get_ai_client", lambda: fake)
    monkeypatch.setattr(job_queue, "send", lambda *a: None)
    monkeypatch.setattr(get_settings(), "EXPRESSION_WAIT_SEC", 0.3)
    with _socket(applicant, sid) as ws:
        _one_answer(ws, qids[0])
    assert fake.expressions[0]["main_expression"] is None


def test_answer_without_content_score_is_saved(monkeypatch, applicant, ready):
    """ai-service의 내용 채점이 끝까지 실패하면 내용 점수·답변 점수가 비어 온다. 그대로 저장하고 면접을 이어간다."""
    aid, qids = ready
    sid = _enter(applicant, aid).json()["session_id"]
    failed = EVALUATION | {"content_score": None, "content_reason": None, "answer_score": None, "evidence": []}
    monkeypatch.setattr(ws_interview, "get_ai_client", lambda: FakeAi(qids[:1], evaluation=failed))
    with _socket(applicant, sid) as ws:
        _one_answer(ws, qids[0])
    row = _answer_row(sid)
    assert (row[2], row[3], row[4], row[6]) == (None, None, 92, None)


# ---------- 꼬리질문 (4단계, SYS-008) ----------
class FollowUpAi(FakeAi):
    """첫 답변 뒤에 바로 다음 질문(qids[1])을 빼고 꼬리질문을 낸다. 꼬리질문 답변 뒤에는 qids[2], 그다음 종료."""

    FOLLOW = "Redis 캐시가 오래된 값을 주지 않게 어떻게 했나요?"

    async def submit_answer(self, session_id, payload):
        self.answers.append(payload)
        q1, q2, q3 = self.qids
        if len(self.answers) == 1:
            follow = {"qkey": "fabc", "question_id": None, "kind": "꼬리", "question_type": "직무",
                      "parent_qkey": f"q{q1}", "text": self.FOLLOW}
            actions = [{"type": "remove", "question": self._present(1)["question"]},
                       {"type": "present", "question": follow, "audio_b64": base64.b64encode(b"wavF").decode()}]
        elif len(self.answers) == 2:
            actions = [self._present(2)]
        else:
            actions = [{"type": "end"}]
        return {"evaluation": EVALUATION, "actions": actions}


def test_follow_up_replaces_the_next_question_and_its_id_is_sent_back(monkeypatch, applicant, ready):
    aid, qids = ready
    sid = _enter(applicant, aid).json()["session_id"]
    fake = FollowUpAi(qids)
    monkeypatch.setattr(ws_interview, "get_ai_client", lambda: fake)
    with _socket(applicant, sid) as ws:
        assert ws.receive_json()["type"] == "connected"
        _answer_one(ws, qids[0], press=True)
        follow = ws.receive_json()
        assert ws.receive_bytes() == b"wavF"
        # 꼬리질문은 빠진 질문의 순번(2)을 이어받는다. 전체 질문 수는 그대로다
        assert (follow["text"], follow["seq"], follow["total"]) == (FollowUpAi.FOLLOW, 2, 3)
        new_id = follow["question_id"]
        ws.send_json({"type": "question_audio_ended", "question_id": new_id})
        ws.receive_json(), ws.receive_json()
        ws.send_json({"type": "answer_done", "question_id": new_id})
        ws.receive_json(), ws.receive_json()
        _answer_one(ws, qids[2], press=True)
        assert ws.receive_json()["type"] == "interview_end"
    # 새 질문의 짝은 꼬리질문 답변 요청에 한 번만 실린다 (규약 2.1 Binding)
    assert [a["bindings"] for a in fake.answers] == [[], [{"qkey": "fabc", "question_id": new_id}], []]
    assert fake.answers[1]["question_id"] == new_id
    rows = _sql("select question_id, parent_question_id, question_type, seq, content, is_revealed, question_status "
                "from interview_question where application_id = :a order by question_id", a=aid)
    by_id = {r[0]: r for r in rows}
    assert by_id[qids[1]][6] == "무효"  # 빠진 질문
    assert tuple(by_id[new_id][1:]) == (qids[0], "직무", 2, FollowUpAi.FOLLOW, True, "유효")
    assert _sql("select count(*) from interview_answer where question_id = :q", q=new_id)[0][0] == 1


def test_same_follow_up_coming_again_reuses_the_row(applicant, ready):
    """짝을 보내기 전에 끊겨 재접속하면 같은 꼬리질문이 question_id 없이 다시 온다. 행을 하나만 둔다."""
    import asyncio

    from app.db.session import AsyncSessionLocal
    from app.services.interview_service import InterviewService

    aid, qids = ready
    sid = _enter(applicant, aid).json()["session_id"]
    follow = {"qkey": "fabc", "question_type": "직무", "parent_qkey": f"q{qids[0]}", "text": "꼬리질문?"}

    async def save_twice():
        async with AsyncSessionLocal() as db:
            first = await InterviewService(db).save_new_question(sid, follow, 2)
        async with AsyncSessionLocal() as db:
            second = await InterviewService(db).save_new_question(sid, follow, None)
        return first, second

    first, second = asyncio.run(save_twice())
    assert first == second
    assert _sql("select count(*) from interview_question where parent_question_id = :p", p=qids[0])[0][0] == 1


# ---------- 문의·예외 처리 (5단계, SYS-003·APP-013·014·018, ADM-026·041) ----------
class InquiryAi(FakeAi):
    """문의 가짜. 메시지에는 안내를 주고, 해결 확인은 resolved_on번째 시도에서 해결된다(None이면 끝내 미해결).
    해결 + 시스템 측이면 지금 질문을 무효로 하고 대체 질문을 낸다. 3회 미해결이면 중단."""

    def __init__(self, qids, cause="지원자 측", resolved_on=1):
        super().__init__(qids)
        self.cause, self.resolved_on, self.inquiries, self.attempts = cause, resolved_on, [], 0

    async def send_inquiry(self, session_id, payload):
        self.inquiries.append(payload)
        if payload["event"] == "open":
            return {"reply": "어떤 문제가 있으신가요?", "check": None, "judgment": None, "actions": []}
        if payload["event"] == "message":
            return {"reply": "마이크를 다시 연결해 보세요.", "check": "system", "judgment": None, "actions": []}
        self.attempts += 1
        resolved = payload["resolved"]
        if not resolved and self.attempts < 3:
            return {"reply": f"다른 방법 {self.attempts}", "check": "applicant", "judgment": None, "actions": []}
        judgment = {"resolved": resolved, "cause": self.cause, "judgment_basis": "마이크 입력 없음",
                    "ai_action": "다시 연결 안내", "handling_detail": "처리 내용", "ai_attempt_count": self.attempts - resolved}
        if not resolved:
            return {"reply": None, "check": None, "judgment": judgment, "actions": [{"type": "suspend"}]}
        actions = []
        if self.cause != "지원자 측":
            q = self._present(0)["question"]
            actions = [{"type": "invalidate", "question": q, "keep_question": False},
                       {"type": "present", "audio_b64": base64.b64encode(b"wavR").decode(),
                        "question": {"qkey": "rnew", "question_id": None, "kind": "AI", "question_type": "직무",
                                     "parent_qkey": None, "text": "대체 질문?"}}]
        return {"reply": None, "check": None, "judgment": judgment, "actions": actions}


def _recv(ws, kind):
    """kind 메시지가 올 때까지 받는다. 그 사이의 다른 메시지와 질문 음성(바이너리)은 넘긴다."""
    while True:
        msg = ws.receive()
        if msg.get("text") and json.loads(msg["text"])["type"] == kind:
            return json.loads(msg["text"])


def _to_answer_phase(ws, qid):
    _recv(ws, "question")
    ws.send_json({"type": "question_audio_ended", "question_id": qid})
    assert _recv(ws, "phase")["phase"] == "think"
    assert _recv(ws, "phase")["phase"] == "answer"


def _inquire(ws, qid):
    ws.send_json({"type": "inquiry_open", "question_id": qid})
    inquiry_id = _recv(ws, "inquiry_opened")["inquiry_id"]
    assert _recv(ws, "inquiry_reply")["text"] == "어떤 문제가 있으신가요?"
    ws.send_json({"type": "inquiry_message", "inquiry_id": inquiry_id, "text": "마이크가 안 돼요"})
    reply = _recv(ws, "inquiry_reply")
    assert (reply["text"], reply["check"]) == ("마이크를 다시 연결해 보세요.", "system")
    return inquiry_id


def _long_answer_time(aid):
    _sql("update job_posting set answer_time_sec = 30 where posting_id = "
         "(select posting_id from application where application_id = :a)", a=aid)


def _inquiry_row(inquiry_id):
    return _sql("select handling_status, judgment_code, ai_attempt_count, question_id from inquiry where inquiry_id = :i",
                i=inquiry_id)[0]


def test_inquiry_resolved_on_applicant_side_continues_the_question(monkeypatch, applicant, ready):
    aid, qids = ready
    _long_answer_time(aid)
    sid = _enter(applicant, aid).json()["session_id"]
    fake = InquiryAi(qids[:1], cause="지원자 측")
    monkeypatch.setattr(ws_interview, "get_ai_client", lambda: fake)
    with _socket(applicant, sid) as ws:
        _to_answer_phase(ws, qids[0])
        inquiry_id = _inquire(ws, qids[0])
        ws.send_json({"type": "inquiry_check", "inquiry_id": inquiry_id, "resolved": True})
        result = _recv(ws, "inquiry_result")
        assert (result["resolved"], result["cause"], result["follow_up"]) == (True, "지원자 측", "기존 질문 그대로 진행")
        ws.send_json({"type": "answer_done", "question_id": qids[0]})  # 같은 질문의 답변을 이어서 낸다
        assert _recv(ws, "answer_end")["reason"] == "button"
        _recv(ws, "interview_end")
    assert _inquiry_row(inquiry_id) == ("AI 처리", "RESOLVED_APPLICANT", 0, qids[0])
    assert _sql("select speaker, content from chat_message where inquiry_id = :i order by seq", i=inquiry_id) == [
        ("챗봇", "어떤 문제가 있으신가요?"), ("지원자", "마이크가 안 돼요"), ("챗봇", "마이크를 다시 연결해 보세요.")]
    # 진행 중인 질문이 시작된 때부터의 이벤트가 시스템 로그로 남는다
    logs = [r[0] for r in _sql("select content from system_log where inquiry_id = :i order by log_id", i=inquiry_id)]
    assert logs[0].startswith("질문 제시") and "답변 시간 시작" in logs
    assert len(fake.answers) == 1  # 답변은 한 번만 보냈다


def test_inquiry_resolved_on_system_side_represents_a_new_question(monkeypatch, applicant, ready):
    aid, qids = ready
    _long_answer_time(aid)
    sid = _enter(applicant, aid).json()["session_id"]
    fake = InquiryAi(qids[:1], cause="시스템 측")
    monkeypatch.setattr(ws_interview, "get_ai_client", lambda: fake)
    with _socket(applicant, sid) as ws:
        _to_answer_phase(ws, qids[0])
        inquiry_id = _inquire(ws, qids[0])
        ws.send_json({"type": "inquiry_check", "inquiry_id": inquiry_id, "resolved": True})
        assert _recv(ws, "inquiry_result")["follow_up"] == "질문 다시 제시 후 재개"
        # 진행 중이던 질문 대신 새 질문이 같은 순번으로 나온다. 생각·답변 시간은 처음부터
        new = _recv(ws, "question")
        assert (new["text"], new["seq"], new["total"]) == ("대체 질문?", 1, 3)
        ws.send_json({"type": "question_audio_ended", "question_id": new["question_id"]})
        _recv(ws, "phase"), _recv(ws, "phase")
        ws.send_json({"type": "answer_done", "question_id": new["question_id"]})
        _recv(ws, "interview_end")
    assert _sql("select question_status from interview_question where question_id = :q", q=qids[0])[0][0] == "무효"
    assert _sql("select seq, parent_question_id, content from interview_question where question_id = :q",
                q=new["question_id"])[0] == (1, None, "대체 질문?")
    # 앞 질문의 답변은 보내지 않았고, 새 질문의 짝을 답변 요청에 실었다
    assert [a["question_id"] for a in fake.answers] == [new["question_id"]]
    assert fake.answers[0]["bindings"] == [{"qkey": "rnew", "question_id": new["question_id"]}]
    assert _inquiry_row(inquiry_id)[:2] == ("AI 처리", "RESOLVED_SYSTEM")


def test_unresolved_system_side_suspends_waits_for_admin_then_retake(monkeypatch, client, admin, applicant, ready):
    aid, qids = ready
    _long_answer_time(aid)
    sid = _enter(applicant, aid).json()["session_id"]
    fake = InquiryAi(qids[:1], cause="시스템 측", resolved_on=None)
    monkeypatch.setattr(ws_interview, "get_ai_client", lambda: fake)
    with _socket(applicant, sid) as ws:
        _to_answer_phase(ws, qids[0])
        inquiry_id = _inquire(ws, qids[0])
        for n in (1, 2):
            ws.send_json({"type": "inquiry_check", "inquiry_id": inquiry_id, "resolved": False})
            assert _recv(ws, "inquiry_reply")["text"] == f"다른 방법 {n}"  # 다른 방법으로 다시 안내
        ws.send_json({"type": "inquiry_check", "inquiry_id": inquiry_id, "resolved": False})
        assert _recv(ws, "inquiry_result")["follow_up"] == "중단 후 관리자 처리, 재시험"
        suspended = _recv(ws, "suspended")
        assert suspended["needs_admin"] is True and "담당자가 확인한 뒤" in suspended["message"]
    assert fake.answers == []
    assert _sql("select status from interview_session where session_id = :s", s=sid)[0][0] == "중단"
    assert _inquiry_row(inquiry_id)[:3] == ("관리자 대기", "UNRESOLVED_SYSTEM", 3)
    # 관리자 처리 전: 처리 중, 응시 버튼 막힘, 입장 거부 (APP-018)
    mine = next(i for i in applicant.get("/api/applications").json() if i["application_id"] == aid)
    assert (mine["status"], mine["can_view_interview_guide"]) == ("처리 중", False)
    r = _enter(applicant, aid)
    assert r.status_code == 409 and "처리하고 있습니다" in r.json()["message"]
    # 관리자 화면 26: 목록·상세·재개 (ADM-026·041)
    listed = admin.get("/api/admin/inquiries", params={"handling_status": "관리자 대기"}).json()
    assert inquiry_id in [i["inquiry_id"] for i in listed]
    detail = admin.get(f"/api/admin/inquiries/{inquiry_id}").json()
    assert (detail["cause"], detail["follow_up"], detail["ai_attempt_count"]) == ("시스템 측", "중단 후 관리자 처리, 재시험", 3)
    assert [m["speaker"] for m in detail["messages"]][:3] == ["챗봇", "지원자", "챗봇"] and detail["logs"]
    pid = _sql("select posting_id from application where application_id = :a", a=aid)[0][0]
    stats = admin.get(f"/api/admin/postings/{pid}/stats").json()
    assert stats["ai_unhandled_error_count"] == 1  # 대시보드 오류 확인 (ADM-003)
    resumed = admin.post(f"/api/admin/inquiries/{inquiry_id}/resume").json()
    assert resumed["handling_status"] == "관리자 처리 완료" and resumed["handled_at"]
    assert admin.post(f"/api/admin/inquiries/{inquiry_id}/resume").status_code == 409
    assert admin.get(f"/api/admin/postings/{pid}/stats").json()["ai_unhandled_error_count"] == 0
    # 관리자 처리 뒤: 재접속 가능, 같은 응시로 재시험 (APP-014)
    mine = next(i for i in applicant.get("/api/applications").json() if i["application_id"] == aid)
    assert (mine["status"], mine["can_view_interview_guide"]) == ("재접속 가능", True)
    again = _enter(applicant, aid).json()
    assert (again["session_id"], again["status"], again["resumed"]) == (sid, "진행 중", True)


def test_unresolved_applicant_side_can_retake_right_away(monkeypatch, applicant, ready):
    aid, qids = ready
    _long_answer_time(aid)
    sid = _enter(applicant, aid).json()["session_id"]
    monkeypatch.setattr(ws_interview, "get_ai_client", lambda: InquiryAi(qids[:1], cause="지원자 측", resolved_on=None))
    with _socket(applicant, sid) as ws:
        _to_answer_phase(ws, qids[0])
        inquiry_id = _inquire(ws, qids[0])
        for _ in range(3):
            ws.send_json({"type": "inquiry_check", "inquiry_id": inquiry_id, "resolved": False})
        assert _recv(ws, "suspended")["needs_admin"] is False
    assert _inquiry_row(inquiry_id)[:2] == ("AI 미처리", "UNRESOLVED_APPLICANT")
    mine = next(i for i in applicant.get("/api/applications").json() if i["application_id"] == aid)
    assert mine["status"] == "재접속 가능"
    assert _enter(applicant, aid).json()["status"] == "진행 중"


def test_inquiry_during_evaluation_is_held_until_the_next_question(monkeypatch, applicant, ready):
    aid, qids = ready
    sid = _enter(applicant, aid).json()["session_id"]
    fake = InquiryAi(qids[:2])
    monkeypatch.setattr(ws_interview, "get_ai_client", lambda: fake)
    with _socket(applicant, sid) as ws:
        _to_answer_phase(ws, qids[0])
        assert _recv(ws, "answer_end")["reason"] == "timeout"  # 답변 시간 1초
        ws.send_json({"type": "inquiry_open", "question_id": qids[0]})
        assert _recv(ws, "inquiry_reply")["text"].startswith("답변을 처리하고 있습니다")
        # 다음 질문을 낸 뒤 문의가 열린다. 그 질문이 문의의 진행 질문이다
        assert _recv(ws, "question")["question_id"] == qids[1]
        inquiry_id = _recv(ws, "inquiry_opened")["inquiry_id"]
    assert _inquiry_row(inquiry_id)[3] == qids[1]
    # 받아 둔 문의는 이전 질문이 시작된 때부터의 로그를 보낸다 (AI Agent 설계서 4.5)
    logs = [l["content"] for l in fake.inquiries[0]["system_logs"]]
    assert sum(c.startswith("질문 제시") for c in logs) == 2


def test_inquiry_admin_api_is_own_postings_only(client, admin, applicant):
    other = _login(TestClient(client.app), "관리자")  # 공고가 없는 다른 관리자
    assert other.get("/api/admin/inquiries").json() == []
    assert admin.get("/api/admin/inquiries/999999999").status_code == 404
    assert applicant.get("/api/admin/inquiries").status_code == 403


class ReplaceAgainAi(FakeAi):
    """재시험으로 다시 접속하면, 앞의 재시험에서 만든 대체 질문(ai-service 쪽 키 r…)을 또 대체한다."""

    def __init__(self, qids, replaced_qid):
        super().__init__(qids)
        self.replaced_qid = replaced_qid

    async def start_interview(self, session_id, payload):
        self.starts.append(payload)
        return {"actions": [
            {"type": "invalidate", "keep_question": False,
             "question": {"qkey": "rold", "question_id": self.replaced_qid, "kind": "AI", "text": "앞의 대체 질문?"}},
            {"type": "present", "audio_b64": None,
             "question": {"qkey": "rnew", "question_id": None, "kind": "AI", "question_type": "직무", "parent_qkey": None,
                          "text": "또 대체 질문?"}},
        ]}


def test_replacing_a_replacement_keeps_its_seq(monkeypatch, applicant, ready):
    """대체 질문을 다시 대체해도 같은 순번을 이어받는다. main-api는 그 질문을 q{id}로, ai-service는 r…로 안다."""
    aid, qids = ready
    sid = _enter(applicant, aid).json()["session_id"]
    _sql("update interview_question set question_status = '무효' where question_id = :q", q=qids[0])
    old = _sql("insert into interview_question (application_id, question_type, seq, content, is_revealed) "
               "values (:a, '직무', 1, '앞의 대체 질문?', true) returning question_id", a=aid)[0][0]
    monkeypatch.setattr(ws_interview, "get_ai_client", lambda: ReplaceAgainAi(qids[1:], old))
    with _socket(applicant, sid) as ws:
        new = _recv(ws, "question")
    assert (new["text"], new["seq"], new["total"]) == ("또 대체 질문?", 1, 3)
    assert _sql("select seq, question_status from interview_question where question_id = :q", q=new["question_id"])[0] == (1, "유효")
    assert _sql("select question_status from interview_question where question_id = :q", q=old)[0][0] == "무효"
