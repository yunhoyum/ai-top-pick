"""AI 화상 면접 응시 (실시간 면접 1·2단계: APP-014·015·016·018, SYS-004·011). ai-service·Deepgram은 가짜다."""

import base64

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import ws_interview
from app.core.config import get_settings
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
}
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

    def __init__(self, qids):
        self.qids, self.starts, self.answers = qids, [], []

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
        return {"evaluation": EVALUATION, "actions": [self._present(i) if i < len(self.qids) else {"type": "end"}]}

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
