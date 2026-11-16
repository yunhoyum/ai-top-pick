"""면접 전형 평가 화면 API (화면 27 순위, 28 보고서, 29 자료 원본, 30 합격자 선정, ADM-027~031).
응시·답변은 SQL로 넣고, 보고서는 면접 보고서 작업에 가짜 ai-service를 넣어 만든다."""

import pytest
from fastapi.testclient import TestClient

from app.services import file_service, interview_report_batch
from test_applications import _open_posting
from test_document_report_batch import _apply
from test_postings import _login, _sql, admin  # noqa: F401  (admin은 fixture)


@pytest.fixture
def pid(admin):
    return _open_posting(admin)


def _ratios(pid):
    return dict(_sql("select c.criteria_name, r.ratio from posting_eval_ratio r join eval_criteria c using (criteria_id) "
                     "where r.posting_id = :p and c.stage_type = '면접'", p=pid))


class ReportClient:
    def __init__(self, scores):
        self.scores = scores  # criteria_id → 점수 문자열. 없는 항목은 내지 않는다

    def create_interview_report(self, payload):
        return {
            "scores": [{"criteria_id": k, "score": v, "evidence": f"근거 {k}", "evidence_sentences": []} for k, v in self.scores.items()],
            "fits": [{"talent_content": "Spring 기반 REST API 경험", "evidence": 'Q1 답변: "캐시를 썼습니다."'},
                     {"talent_content": "정직함", "evidence": "면접 답변에서 이 인재상을 보여 주는 내용을 찾지 못했다."}],
            "points": [{"point_type": "확인 필요", "criteria_id": 5, "content": "Q2 근거가 부족하다."}],
            "summary": "면접 요약.",
        }


def _take(aid, video=None):
    """응시 '완료'와 유효 답변 2개(질문 1·2), 무효 답변 1개, 유효 꼬리질문 1개를 넣는다. 첫 답변에 STT 두 구간."""
    sid = _sql("insert into interview_session (application_id, status, started_at, ended_at) "
               "values (:a, '완료', now(), now()) returning session_id", a=aid)[0][0]
    q1, q2, q3 = (_sql("insert into interview_question (application_id, question_type, seq, content, is_revealed, question_status) "
                       "values (:a, '직무', :s, :c, true, :st) returning question_id", a=aid, s=seq, c=c, st=st)[0][0]
                  for seq, c, st in ((1, "캐시를 왜 썼나요?", "유효"), (2, "장애를 어떻게 찾았나요?", "유효"), (3, "빠진 질문?", "무효")))
    _sql("insert into interview_question (application_id, parent_question_id, question_type, seq, content, question_status) "
         "values (:a, :p, '직무', 3, '꼬리?', '유효')", a=aid, p=q1)
    answers = []
    for q, main, status in ((q1, "neutral", "유효"), (q2, "fear", "유효"), (q3, "neutral", "무효")):
        answers.append(_sql("insert into interview_answer (session_id, question_id, main_expression, duration_sec, video_path, "
                            "speech_score, answer_status) values (:s, :q, :m, 42, :v, 90, :st) returning answer_id",
                            s=sid, q=q, m=main, v=video, st=status)[0][0])
    _sql("insert into stt_record (answer_id, time_offset_sec, corrected_text, raw_text) values "
         "(:a, 0, 'API 캐시를 썼습니다.', 'AP 캐시를 썼습니다.'), (:a, 4, '빨라졌습니다.', '빨라졌습니다.')", a=answers[0])
    return sid, answers


def _report(pid, aid, scores):
    job = _sql("insert into batch_job (job_type, posting_id, application_id) values ('면접 보고서', :p, :a) returning job_id",
               p=pid, a=aid)[0][0]
    interview_report_batch.generate_interview_report(job, client=ReportClient(scores))


@pytest.fixture
def interviewed(client, pid):
    """서류 합격 3명: 보고서 2명(high: 비언어까지, noface: 표정 없어 비언어 없음), 미응시 1명. 서류 불합격 1명."""
    ids = {k: _apply(client, pid) for k in ("high", "noface", "absent", "doc_fail")}
    for k, aid in ids.items():
        _sql("insert into application_stage (application_id, stage_type, result) values (:a, '서류', :r)",
             a=aid, r="불합격" if k == "doc_fail" else "합격")
        if k != "doc_fail":
            _sql("insert into application_stage (application_id, stage_type) values (:a, '면접')", a=aid)
    _take(ids["high"])
    _take(ids["noface"])
    _report(pid, ids["high"], {5: "80.00", 6: "90.00", 7: "70.00"})
    _report(pid, ids["noface"], {5: "60.00", 6: "80.00"})
    _sql("update job_posting set progress_status = '면접 평가' where posting_id = :p", p=pid)
    return ids


def _ranking(c, pid):
    return c.get(f"/api/admin/postings/{pid}/stages/interview/ranking")


def test_interview_ranking_scales_missing_item_and_puts_absent_last(admin, pid, interviewed):
    r = _ranking(admin, pid)
    assert r.status_code == 200, r.text
    data = r.json()
    ratio = _ratios(pid)
    assert [c["name"] for c in data["criteria"]] == ["내용", "언어", "비언어"]
    content, speech, face = ratio["내용"], ratio["언어"], ratio["비언어"]
    high = round((80 * content + 90 * speech + 70 * face) / 100, 1)
    noface = round((60 * content + 80 * speech) / (content + speech), 1)  # 비언어가 없으면 내용·언어 비율을 늘린다
    rows = [(row["application_id"], row["rank"], row["total"], row["report_status"], row["follow_up_count"]) for row in data["rows"]]
    assert rows == [
        (interviewed["high"], 1, f"{high:.1f}", "완료", 1),
        (interviewed["noface"], 2, f"{noface:.1f}", "완료", 1),
        (interviewed["absent"], None, None, "미응시", None),
    ]
    assert data["summary"]["target_count"] == 3 and data["summary"]["taken_count"] == 2 and data["summary"]["shortfall_count"] == 0
    # 비언어가 없는 지원자는 그 칸이 비어 있다 (0점이 아니다)
    assert [len(row["scores"]) for row in data["rows"]] == [3, 2, 0]


def test_interview_ranking_before_interview_deadline_is_409(admin, pid, interviewed):
    _sql("update job_posting set progress_status = '면접 진행' where posting_id = :p", p=pid)
    r = _ranking(admin, pid)
    assert r.status_code == 409 and r.json()["code"] == "STAGE_NOT_CLOSED"


def test_interview_report_has_question_results_and_follow_up_count(admin, pid, interviewed):
    r = admin.get(f"/api/admin/applications/{interviewed['high']}/stages/interview/report")
    assert r.status_code == 200, r.text
    data = r.json()
    assert (data["rank"], data["ranked_count"], data["summary"], data["follow_up_count"]) == (1, 2, "면접 요약.", 1)
    assert [(s["name"], s["score"]) for s in data["scores"]] == [("내용", "80.00"), ("언어", "90.00"), ("비언어", "70.00")]
    # 유효 답변만 진행 순서대로 (무효 답변의 질문은 빠진다)
    assert [(q["seq"], q["text"], q["kind"], q["main_expression"]) for q in data["questions"]] == [
        (1, "캐시를 왜 썼나요?", "AI", "neutral"), (2, "장애를 어떻게 찾았나요?", "AI", "fear")]
    assert [f["found"] for f in data["fits"]] == [True, False]
    assert data["checks"] == [{"criteria_name": "내용", "content": "Q2 근거가 부족하다."}]
    # 미응시자는 보고서가 없다
    assert admin.get(f"/api/admin/applications/{interviewed['absent']}/stages/interview/report").status_code == 404


def test_interview_opinion_is_separate_from_document_opinion(admin, pid, interviewed):
    aid = interviewed["high"]
    r = admin.put(f"/api/admin/applications/{aid}/stages/interview/opinion", json={"opinion": "면접 의견"})
    assert r.status_code == 200 and r.json()["opinion"] == "면접 의견"
    assert _sql("select stage_type, admin_opinion from application_stage where application_id = :a order by stage_type", a=aid) == [
        ("면접", "면접 의견"), ("서류", None)]
    assert _ranking(admin, pid).json()["summary"]["opinion_count"] == 1


def test_interview_source_has_stt_lines_and_video(admin, pid, interviewed, tmp_path, monkeypatch):
    aid = interviewed["high"]
    data = admin.get(f"/api/admin/applications/{aid}/interview").json()
    assert [(q["seq"], q["text"], q["duration_sec"], q["has_video"]) for q in data["questions"]] == [
        (1, "캐시를 왜 썼나요?", 42, False), (2, "장애를 어떻게 찾았나요?", 42, False)]
    assert data["questions"][0]["stt"] == [
        {"time_offset_sec": 0, "corrected_text": "API 캐시를 썼습니다.", "raw_text": "AP 캐시를 썼습니다."},
        {"time_offset_sec": 4, "corrected_text": "빨라졌습니다.", "raw_text": "빨라졌습니다."}]
    answer_id = data["questions"][0]["answer_id"]
    assert admin.get(f"/api/admin/answers/{answer_id}/video").json()["code"] == "VIDEO_NOT_FOUND"
    # 영상이 있으면 webm으로 준다
    monkeypatch.setattr(file_service, "resolve", lambda path: tmp_path / "a.webm")
    (tmp_path / "a.webm").write_bytes(b"webm-bytes")
    _sql("update interview_answer set video_path = 'interviews/x.webm' where answer_id = :a", a=answer_id)
    r = admin.get(f"/api/admin/answers/{answer_id}/video")
    assert r.status_code == 200 and r.headers["content-type"] == "video/webm" and r.content == b"webm-bytes"


def test_other_admin_cannot_see_interview_evaluation(client, pid, interviewed):
    other = _login(TestClient(client.app))
    assert _ranking(other, pid).status_code == 404
    assert other.get(f"/api/admin/applications/{interviewed['high']}/interview").status_code == 404


def test_confirm_interview_pass_closes_posting_once(admin, pid, interviewed):
    url = f"/api/admin/postings/{pid}/stages/interview/pass"
    # 미응시자는 고를 수 없다
    assert admin.post(url, json={"application_ids": [interviewed["absent"]]}).status_code == 422
    r = admin.post(url, json={"application_ids": [interviewed["high"]]})
    assert r.status_code == 200 and r.json() == {"passed": 1, "failed": 2}
    results = dict(_sql("select application_id, result from application_stage where stage_type = '면접' and application_id = any(:ids)",
                        ids=[interviewed[k] for k in ("high", "noface", "absent")]))
    assert results == {interviewed["high"]: "합격", interviewed["noface"]: "불합격", interviewed["absent"]: "불합격"}
    assert _sql("select progress_status from job_posting where posting_id = :p", p=pid)[0][0] == "마감"
    assert _ranking(admin, pid).json()["confirmed"] is True
    assert admin.post(url, json={"application_ids": [interviewed["high"]]}).status_code == 409
