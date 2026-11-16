"""면접 보고서 테스트 (루브릭 설계서 8·10.2). LLM은 정해 둔 JSON을 차례로 돌려주는 가짜다.

호출 순서: 인재상 적합도(번호 고르기) → 요약. 항목 점수와 강점·확인 필요는 LLM을 부르지 않는다.
"""

import json
from decimal import Decimal

import pytest

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.chains import interview_report as chain
from app.chains.answer_content import RELEVANCE_CAP_NOTES
from app.chains.interview_report import CONTENT, EXPRESSION, NO_FIT_NOTE, SPEECH, build_interview_report, score_items
from app.schemas.internal import AnswerRecord, PostingBrief

POSTING = PostingBrief(
    posting_id=1, position_name="백엔드 개발자", job_description="주문·결제 백엔드를 개발한다.",
    functional_talent="- 결제 장애를 재현하고 원인을 기록하는 사람",
    nonfunctional_talent="- 모르면 모른다고 말하는 정직함",
)


def _answer(question, text, content, reason, speech="90", face="80", main="neutral", fillers=1, silence="3", delay="2"):
    return AnswerRecord(
        question_text=question, kind="AI", corrected_text=text,
        answer_score=None, content_score=None if content is None else Decimal(content), content_reason=reason,
        speech_score=Decimal(speech), expression_score=None if face is None else Decimal(face), main_expression=main,
        expression_ratio=None, silence_sec=Decimal(silence), filler_count=fillers, response_delay_sec=Decimal(delay),
    )


ANSWERS = [
    _answer("장애를 어떻게 찾았나요?", "로그를 남겨 재현했습니다. 원인을 문서로 정리했습니다.", "90", "재현 과정이 구체적이다. 근거가 있다."),
    _answer("캐시를 왜 썼나요?", "잘 모르겠습니다.", "40", "근거가 부족하다.", speech="50", face=None, main=None, fillers=4, delay="12"),
    _answer("지원 동기는?", "결제 시스템에 관심이 많습니다.", "55", "답이 짧다. " + RELEVANCE_CAP_NOTES["안 함"], face="60", main="fear"),
]


class FakeEmbed:
    """embed-server 가짜. 정해 둔 글은 그 벡터를, 그 밖에는 [1, 0]을 준다(서로 유사도 1)."""

    def __init__(self, vectors=None):
        self.vectors = vectors or {}

    def embed(self, texts):
        return [self.vectors.get(t, [1.0, 0.0]) for t in texts]


@pytest.fixture(autouse=True)
def fake_embed(monkeypatch):
    monkeypatch.setattr(chain, "EmbedClient", FakeEmbed)


class FakeModel:
    def __init__(self, *outputs):
        self.outputs = [o if isinstance(o, str) else json.dumps(o, ensure_ascii=False) for o in outputs]
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content=self.outputs.pop(0))


def test_item_scores_are_averages_of_realtime_scores():
    items = {i.name: i for i in score_items(ANSWERS)}
    assert items[CONTENT].score == Decimal("61.67")  # (90 + 40 + 55) / 3
    assert items[CONTENT].evidence.splitlines()[0] == "Q1. 재현 과정이 구체적이다. 근거가 있다."
    assert items[SPEECH].score == Decimal("76.67")  # (90 + 50 + 90) / 3
    assert items[SPEECH].evidence == "평균 간투사 2.0회, 평균 침묵 3.0초, 응답 지연 10초 이상 1회 (답변 3개)"
    # 표정이 없는 답변은 뺀다
    assert items[EXPRESSION].score == Decimal("70.00")
    assert items[EXPRESSION].evidence == "주요 표정 neutral 1회, fear 1회 (표정을 분석한 답변 2개)"


def test_no_expression_item_when_every_face_failed_and_failed_content_is_skipped():
    answers = [_answer("Q?", "답.", None, None, face=None), _answer("Q2?", "답.", "70", "보통이다.", face=None)]
    items = {i.name: i for i in score_items(answers)}
    assert set(items) == {CONTENT, SPEECH}  # 비언어 없음 (루브릭 설계서 8.2)
    assert items[CONTENT].score == Decimal("70.00") and items[CONTENT].evidence == "Q2. 보통이다."


def test_report_fits_use_verified_answer_sentences_and_points_come_from_scores():
    model = FakeModel(
        {"fits": [{"talent_id": "기-1", "sentence_ids": ["Q1-1", "Q9-9", "Q1-2", "Q1-1"]},
                  {"talent_id": "비-1", "sentence_ids": []}]},
        {"summary": "재현 과정이 구체적이다."},
    )
    report = build_interview_report(POSTING, ANSWERS, model=model)
    # 없는 번호는 버리고 답변 원문을 근거로 넣는다. 바꿔 쓰지 않는다
    assert [(f.talent_content, f.evidence) for f in report.fits] == [
        ("결제 장애를 재현하고 원인을 기록하는 사람", 'Q1 답변: "로그를 남겨 재현했습니다." / Q1 답변: "원인을 문서로 정리했습니다."'),
        ("모르면 모른다고 말하는 정직함", NO_FIT_NOTE),
    ]
    points = [(p.point_type, p.item, p.content) for p in report.points]
    assert ("강점", CONTENT, "Q1 '장애를 어떻게 찾았나요?': 재현 과정이 구체적이다.") in points
    assert ("확인 필요", CONTENT, "Q2 '캐시를 왜 썼나요?': 근거가 부족하다.") in points
    assert ("확인 필요", CONTENT, "Q3 '지원 동기는?': 질문이 묻는 것에 답하지 않았다. 같은 내용을 다시 확인한다.") in points
    assert not any(p[1] in (SPEECH, EXPRESSION) for p in points)  # 언어·비언어는 60 이상
    assert report.summary == "재현 과정이 구체적이다."
    # 답변 문장에 번호를 붙여 보인다. 요약 자료에는 점수 숫자가 없다
    assert "[Q1-2] 원인을 문서로 정리했습니다." in model.calls[0][-1].content
    brief = model.calls[1][-1].content
    assert "[내용] 항목 점수 보통" in brief and "61.67" not in brief
    assert "[면접에서 확인된 인재상]\n- 결제 장애를 재현하고 원인을 기록하는 사람" in brief
    assert "[면접에서 확인되지 않은 인재상]\n- 모르면 모른다고 말하는 정직함" in brief
    assert "Q2 '" not in brief  # 질문 번호를 요약에 옮겨 쓰지 않게 뺀다


def test_functional_talent_is_not_confirmed_by_a_low_scoring_answer():
    """기능적 인재상은 내용 점수 60 미만 답변으로 확인하지 않는다. 비기능적(정직함)은 점수와 상관없다 (실험 R1)."""
    model = FakeModel({"fits": [{"talent_id": "기-1", "sentence_ids": ["Q2-1"]}, {"talent_id": "비-1", "sentence_ids": ["Q2-1"]}]},
                      {"summary": "요약."})
    fits = build_interview_report(POSTING, ANSWERS, model=model).fits
    assert [f.evidence for f in fits] == [NO_FIT_NOTE, 'Q2 답변: "잘 모르겠습니다."']


def test_check_point_uses_the_weak_sentence_of_the_reason():
    """확인 필요에는 채점 이유 중 모자란 점을 말하는 문장을 쓴다. 첫 문장은 대개 칭찬이다 (실험 R1)."""
    answers = [_answer("Q?", "답.", "50", "답변은 질문에 잘 대응한다. 그러나 사례가 부족하다. specificity 점수가 낮다.")]
    points = build_interview_report(POSTING, answers, model=FakeModel({"fits": []}, {"summary": "요약."})).points
    assert [p.content for p in points] == ["Q1 'Q?': 그러나 사례가 부족하다."]


def test_api_interview_report(monkeypatch):
    from app.core.config import get_settings
    from app.main import app

    monkeypatch.setattr(chain, "get_chat_model", lambda: FakeModel({"fits": []}, {"summary": "요약."}))
    criteria = [{"criteria_id": i, "name": n, "ratio": 30} for i, n in ((5, "내용"), (6, "언어"), (7, "비언어"))]
    body = {"application_id": 1, "posting": POSTING.model_dump(), "criteria": criteria,
            "answers": [a.model_dump(mode="json") for a in ANSWERS]}
    client = TestClient(app)
    headers = {"X-Internal-Token": get_settings().INTERNAL_TOKEN}
    r = client.post("/internal/reports/interview", json=body, headers=headers)
    assert r.status_code == 200, r.text
    out = r.json()
    assert [s["criteria_id"] for s in out["scores"]] == [5, 6, 7] and out["summary"] == "요약."
    assert {p["criteria_id"] for p in out["points"]} == {5}
    r = client.post("/internal/reports/interview", json=body | {"criteria": criteria[:2]}, headers=headers)
    assert r.status_code == 422


def test_check_point_prefers_code_written_notes_over_llm_text():
    """'문서 부족 상황'처럼 낱말만 걸린 칭찬 문장보다 코드가 쓴 문구를 먼저 쓴다 (실험 R2)."""
    partly = "답변은 문서 부족 상황을 명확히 제시한다. " + RELEVANCE_CAP_NOTES["일부"]
    opposite = "답변은 직접적이다. 사례가 부족하다. 회사 문서와 비교한 주장 1개: 반대 1 (일치 단계: 반대)."
    answers = [_answer("Q1?", "답.", "42", partly), _answer("Q2?", "답.", "30", opposite)]
    points = build_interview_report(POSTING, answers, model=FakeModel({"fits": []}, {"summary": "요약."})).points
    assert [p.content for p in points] == [
        "Q1 'Q1?': " + RELEVANCE_CAP_NOTES["일부"], "Q2 'Q2?': 답변 내용이 회사 문서와 맞지 않는다."]


def test_fit_pairs_far_from_the_talent_are_dropped():
    """LLM이 고른 짝이라도 인재상과 답변 문장의 유사도가 FIT_MIN_SIMILARITY 미만이면 버린다 (실험 R3)."""
    model = FakeModel({"fits": [{"talent_id": "기-1", "sentence_ids": ["Q1-1", "Q1-2"]}]}, {"summary": "요약."})
    embed = FakeEmbed({"원인을 문서로 정리했습니다.": [0.0, 1.0]})  # 인재상([1, 0])과 유사도 0
    fits = build_interview_report(POSTING, ANSWERS, model=model, embed=embed).fits
    assert fits[0].evidence == 'Q1 답변: "로그를 남겨 재현했습니다."'
