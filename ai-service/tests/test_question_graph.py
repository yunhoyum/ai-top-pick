"""SYS-006 질문 생성 그래프 테스트. LLM은 작업 종류(생성·검증·검색어 수정)마다 정해 둔 출력을 차례로 내주는 가짜다."""

import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.api import questions
from app.core.config import get_settings
from app.graphs.question import FIXED_QUESTION, build_queries, generate_questions
from app.main import app
from app.schemas.internal import ApplicantDocuments, PostingBrief

POSTING = PostingBrief(
    posting_id=1, position_name="백엔드 개발자", job_description="주문·결제 백엔드를 개발한다.",
    functional_talent="- 결제 장애를 재현하는 사람",
    nonfunctional_talent="- 모르면 모른다고 말하는 정직함\n- 끝까지 파고드는 태도",
)
CASE_A = "[Java] 주문 API 응답을 캐시로 줄였습니다."
CASE_B = "[Redis] 재고를 분산 락으로 지켰습니다."
ESSAY = {"topic": "지원 동기", "content": "결제 장애를 끝까지 추적했습니다."}
PASS = {"is_valid": True, "failure_type": None, "feedback": ""}
NO_OVERLAP = {"same_skill": False, "same_competency": False, "reason": "다른 기술"}
SAME_SKILL = {"same_skill": True, "same_competency": False, "reason": "둘 다 캐시를 묻는다"}
BROKEN = "형식이 아닌 출력"  # 형식 검증에 계속 실패한다 (invoke_structured가 2번 더 묻는다)


def _docs(**over):
    base = dict(personal={"name": "홍길동"}, skills=[{"skill_name": "Spring", "self_score": 4}], educations=[],
                careers=[], projects=[], skill_cases=[CASE_A, CASE_B], essays=[ESSAY], portfolio_text="포트폴리오 본문")
    return ApplicantDocuments(**(base | over))


def _q(text):
    return {"question": text}


def _fail(kind, feedback="고쳐라"):
    return {"is_valid": False, "failure_type": kind, "feedback": feedback}


class FakeModel:
    """작업 종류별 출력 줄. 받은 마지막 메시지를 (종류, 내용)으로 기록한다."""

    def __init__(self, generate=(), validate=(), query=(), overlap=()):
        self.queues = {k: [o if isinstance(o, str) else json.dumps(o, ensure_ascii=False) for o in v]
                       for k, v in {"generate": generate, "validate": validate, "query": query, "overlap": overlap}.items()}
        self.calls = []

    def invoke(self, messages):
        text = messages[-1].content
        if "형식에 맞지 않습니다" in text:  # invoke_structured의 다시 묻기는 원래 작업과 같다
            kind = self.calls[-1][0]
        elif "[비교할 두 질문]" in text:
            kind = "overlap"
        elif "[검증할 질문]" in text:
            kind = "validate"
        elif "다시 검색할 검색어" in text:
            kind = "query"
        else:
            kind = "generate"
        self.calls.append((kind, text))
        return AIMessage(content=self.queues[kind].pop(0))


class FakeSearch:
    def __init__(self):
        self.queries = []

    def __call__(self, query):
        self.queries.append(query)
        return [f"문서: {query[:10]}"]


def _run(model, job=1, personality=0, docs=None):
    search = FakeSearch()
    job_qs, personality_qs = generate_questions(POSTING, docs or _docs(), job, personality, model, search)
    return job_qs, personality_qs, search


# ---------- 검색어 ----------


def test_queries_alternate_sources_and_repeat_when_short():
    d = _docs()
    essay = "지원 동기\n결제 장애를 끝까지 추적했습니다."
    assert build_queries(d, 4) == [CASE_A, "포트폴리오 본문", essay, CASE_B]
    assert build_queries(d, 6) == [CASE_A, "포트폴리오 본문", essay, CASE_B, CASE_A, "포트폴리오 본문"]
    assert build_queries(_docs(portfolio_text=None, essays=[]), 3) == [CASE_A, CASE_B, CASE_A]
    assert build_queries(d, 0) == []


# ---------- 정상 흐름 ----------


def test_all_pass_job_then_personality_with_confirmed_passed_on():
    # 겹침 검사: 직무2 ↔ 직무1, 인성1 ↔ 직무1·직무2
    model = FakeModel(generate=[_q("직무1"), _q("직무2"), _q("인성1")], validate=[PASS] * 3, overlap=[NO_OVERLAP] * 3)
    job, personality, search = _run(model, job=2, personality=1)

    assert (job, personality) == (["직무1", "직무2"], ["인성1"])
    assert search.queries == [CASE_A, "포트폴리오 본문"]
    # 두 번째 직무 질문과 인성 질문은 앞에서 확정된 질문을 받는다 (배타성)
    generates = [t for k, t in model.calls if k == "generate"]
    assert "- 직무1" in generates[1] and "- 직무1\n- 직무2" in generates[2]
    # 인성은 검색하지 않고 자기소개서와 비기능적 인재상으로 만든다
    assert "결제 장애를 끝까지 추적했습니다." in generates[2] and "정직함" in generates[2]


def test_zero_counts_call_nothing():
    model = FakeModel()
    assert _run(model, job=0, personality=0)[:2] == ([], [])
    assert model.calls == []


# ---------- 실패 원인별 되돌아가기 ----------


def test_evidence_failure_rewrites_query_and_searches_again():
    model = FakeModel(generate=[_q("첫 질문"), _q("새 질문")], validate=[_fail("evidence", "문서가 캐시와 관계없다"), PASS],
                      query=[{"query": "주문 API 캐시"}])
    job, _, search = _run(model)
    assert job == ["새 질문"]
    assert search.queries == [CASE_A, "주문 API 캐시"]
    assert "문서가 캐시와 관계없다" in [t for k, t in model.calls if k == "query"][0]


def test_question_failure_regenerates_with_feedback_without_new_search():
    model = FakeModel(generate=[_q("첫 질문"), _q("새 질문")], validate=[_fail("question", "질문이 둘이다"), PASS])
    job, _, search = _run(model)
    assert job == ["새 질문"] and search.queries == [CASE_A]
    assert "질문이 둘이다" in [t for k, t in model.calls if k == "generate"][1]


def test_overlap_is_checked_pair_by_pair_after_validation_and_regenerates():
    model = FakeModel(generate=[_q("직무1"), _q("직무1 비슷"), _q("직무2")], validate=[PASS] * 3,
                      overlap=[SAME_SKILL, NO_OVERLAP])
    job, _, search = _run(model, job=2)
    assert job == ["직무1", "직무2"]
    # 첫 질문은 확정 질문이 없어 겹침을 묻지 않는다. 겹친 뒤에는 검색하지 않고 다시 만든다
    assert [k for k, _ in model.calls] == ["generate", "validate", "generate", "validate", "overlap",
                                         "generate", "validate", "overlap"]
    assert search.queries == [CASE_A, "포트폴리오 본문"]
    overlap_prompt = [t for k, t in model.calls if k == "overlap"][0]
    assert "직무1 비슷" in overlap_prompt and "포트폴리오 본문" not in overlap_prompt  # 두 질문만 넣는다
    assert "이미 확정된 질문 '직무1'와 같은 기술" in [t for k, t in model.calls if k == "generate"][2]


def test_validation_does_not_judge_overlap_itself():
    model = FakeModel(generate=[_q("q")], validate=[PASS])
    _run(model)
    assert "[이미 확정된 질문]" not in [t for k, t in model.calls if k == "validate"][0]


def test_three_failures_go_to_fallback_with_original_query_without_validation():
    model = FakeModel(
        generate=[_q("q1"), _q("q2"), _q("q3"), _q("적용 방안 질문")],
        validate=[_fail("evidence"), _fail("question"), _fail("overlap")],
        query=[{"query": "고친 검색어"}],
    )
    job, _, _ = _run(model)
    assert job == ["적용 방안 질문"]
    fallback_prompt = [t for k, t in model.calls if k == "generate"][-1]
    assert CASE_A in fallback_prompt and "고친 검색어" not in fallback_prompt
    assert [k for k, _ in model.calls].count("validate") == 3  # fallback은 검증하지 않는다


# ---------- fallback 실패 → 템플릿 ----------


def _always_broken(n_questions):
    # 질문마다: 생성 3번 형식 실패(각 3번 물음) + fallback 형식 실패(3번 물음)
    return FakeModel(generate=[BROKEN] * (3 * 3 + 3) * n_questions)


def test_job_template_uses_skill_case_names_then_required_skills_then_fixed():
    job, _, _ = _run(_always_broken(4), job=4)
    assert job == [
        "'Java' 기술을 저희 회사 프로젝트에 적용한다면 어떻게 하시겠습니까?",
        "'Redis' 기술을 저희 회사 프로젝트에 적용한다면 어떻게 하시겠습니까?",
        "'Spring' 기술을 저희 회사 프로젝트에 적용한다면 어떻게 하시겠습니까?",
        FIXED_QUESTION,
    ]


def test_personality_template_uses_talent_lines_then_fixed():
    _, personality, _ = _run(_always_broken(3), job=0, personality=3)
    assert personality == [
        "'모르면 모른다고 말하는 정직함'에 해당하는 본인의 경험을 말씀해 주세요.",
        "'끝까지 파고드는 태도'에 해당하는 본인의 경험을 말씀해 주세요.",
        FIXED_QUESTION,
    ]


class DownModel:
    def invoke(self, messages):
        raise ConnectionError("LLM 서버에 연결할 수 없다")


def test_llm_down_still_returns_requested_counts():
    job, personality, _ = _run(DownModel(), job=5, personality=3)
    assert len(job) == 5 and len(personality) == 3


# ---------- 내부 API ----------

BODY = {
    "application_id": 7,
    "posting": POSTING.model_dump(),
    "documents": _docs().model_dump(),
    "job_count": 2,
    "personality_count": 1,
}


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("EMBED_URL", "http://embed")
    monkeypatch.setenv("INTERNAL_TOKEN", "secret")
    get_settings.cache_clear()
    seen = {}

    def fake(posting, documents, job_count, personality_count, model, search):
        seen.update(posting_id=posting.posting_id, counts=(job_count, personality_count))
        return ["직무1", "직무2"], ["인성1"]

    monkeypatch.setattr(questions, "generate_questions", fake)
    monkeypatch.setattr(questions, "get_chat_model", lambda: None)
    yield TestClient(app), seen
    get_settings.cache_clear()


def test_api_requires_internal_token(api):
    client, _ = api
    assert client.post("/internal/questions/generate", json=BODY).status_code == 401


def test_api_returns_questions(api):
    client, seen = api
    r = client.post("/internal/questions/generate", json=BODY, headers={"X-Internal-Token": "secret"})
    assert r.status_code == 200, r.text
    assert r.json() == {"job": ["직무1", "직무2"], "personality": ["인성1"]}
    assert seen == {"posting_id": 1, "counts": (2, 1)}
