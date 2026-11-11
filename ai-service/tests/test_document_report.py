"""서류 보고서 항목 점수 테스트. LLM은 정해 둔 JSON을 차례로 돌려주는 가짜로 바꾼다.

호출 순서: 이력서(읽기 → 직무 경험 주장 비교 → 인재상 주장 비교) → 기술 적용 사례 → 포트폴리오 → 자기소개.
항목마다 읽기 → 주장마다 비교. 내용이 빈 항목은 LLM을 부르지 않는다.
"""

import json
from decimal import Decimal

from langchain_core.messages import AIMessage

from app.chains.document_report import (
    NO_CLAIM_NOTE,
    NO_FIT_NOTE,
    NO_TEXT_NOTE,
    SKILL_ONLY_NOTE,
    build_document_report,
    score_document_items,
)
from app.prompts.document_report import EMPTY_CLAIMS_RETRY
from app.rag.retriever import Chunk
from app.schemas.internal import ApplicantDocuments, PostingBrief

POSTING = PostingBrief(
    posting_id=1,
    position_name="백엔드 개발자",
    job_description="주문·결제 백엔드를 개발한다.",
    functional_talent="- 결제 장애를 재현하고 원인을 기록하는 사람\n- 외부 API 타임아웃을 설계해 본 사람",
    nonfunctional_talent="- 모르면 모른다고 말하는 정직함",
)
PG = Chunk(1, "프로젝트 문서", 101, 0, "PG 승인 응답이 5초 안에 오지 않으면 결제 상태를 확인 중으로 둔다.", 0.7)
CASE = "PG 타임아웃이 나면 결제를 확인 중으로 두었습니다. 결제 버튼도 한 번만 눌리게 했습니다."


class FakeModel:
    """돌려줄 출력을 차례로 내준다. 받은 메시지를 기록한다."""

    def __init__(self, *outputs):
        self.outputs = [o if isinstance(o, str) else json.dumps(o, ensure_ascii=False) for o in outputs]
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content=self.outputs.pop(0))


class FakeSearch:
    def __init__(self, chunks=(PG,)):
        self.chunks = list(chunks)
        self.queries = []

    def __call__(self, texts):
        self.queries.append(texts)
        return self.chunks


def _docs(**fields):
    base = dict(personal={"name": "홍길동"}, skills=[], educations=[], careers=[], projects=[],
                skill_cases=[], essays=[], portfolio_text=None)
    return ApplicantDocuments(**(base | fields))


def _case_read(claims):
    return {"claims": claims, "problem": 80, "process": 70, "result": 60, "reason": "문제와 과정이 분명하다."}


def _claim(level, ids):
    return {"level": level, "evidence_ids": ids}


class FakeEmbed:
    """글마다 정해 둔 방향의 단위 벡터를 준다. 정하지 않은 글은 모두 같은 방향이라 유사도 1이다."""

    def __init__(self, directions=None):
        self.directions = directions or {}

    def embed(self, texts):
        return [[1.0, 0.0] if self.directions.get(t, 0) == 0 else [0.0, 1.0] for t in texts]


def _score(model, docs, search=None, embed=None):
    items = score_document_items(POSTING, docs, model=model, search=search or FakeSearch(), embed=embed or FakeEmbed())
    return {i.name: i for i in items}


# ---------- 기술 적용 사례: 회사와 상관없는 축 + 회사 업무 일치 ----------


def test_skill_case_score_and_doc_match_is_share_of_same_claims():
    model = FakeModel(
        _case_read(["타임아웃이 나면 확인 중으로 두었다", "결제 버튼을 한 번만 눌리게 했다"]),
        _claim("같음", ["1-1"]),
        _claim("문서에 없음", []),
    )
    item = _score(model, _docs(skill_cases=[CASE]))["기술 적용 사례"]
    # 같음 1 / 주장 2 = 50. 80×0.2 + 70×0.3 + 60×0.2 + 50×0.3 = 16 + 21 + 12 + 15
    assert item.axes["doc_match"] == Decimal("50.00")
    assert item.score == Decimal("64.00")
    assert "문제와 과정이 분명하다." in item.reason and "같음 1, 문서에 없음 1" in item.reason
    assert [(e.id, e.source_type, e.source_id, e.chunk_id) for e in item.evidence] == [("1-1", "프로젝트 문서", 101, 1)]


def test_read_call_sees_no_company_material():
    model = FakeModel(_case_read(["타임아웃이 나면 확인 중으로 두었다"]), _claim("같음", ["1-1"]))
    _score(model, _docs(skill_cases=[CASE]))
    read = model.calls[0][-1].content
    assert CASE in read
    assert "PG 승인 응답" not in read and "결제 장애를 재현" not in read and "주문·결제 백엔드" not in read


def test_read_prompt_keeps_only_comparable_claims():
    # D1-v1: 학력·소속, 결과 수치, 자기평가를 주장으로 뽑아 같음 비율이 낮아졌다
    model = FakeModel(_case_read(["a"]), _claim("같음", ["1-1"]))
    _score(model, _docs(skill_cases=[CASE]))
    read = model.calls[0][-1].content
    assert "실제로 한 일, 쓴 방법, 내린 결정" in read
    assert "소속 정보" in read and "결과 수치와 성과" in read and "행동 없이 자신을 평가한 말" in read


def test_comparison_sees_functional_talent_and_project_doc_and_shares_front_part():
    model = FakeModel(_case_read(["a", "b"]), _claim("같음", ["기-2"]), _claim("같음", ["1-1"]))
    item = _score(model, _docs(skill_cases=[CASE]))["기술 적용 사례"]
    first, second = model.calls[1], model.calls[2]
    assert first[0].content == second[0].content  # 앞부분이 같아야 Ollama가 캐시를 다시 쓴다
    assert "[기-1] 결제 장애를 재현하고 원인을 기록하는 사람" in first[0].content  # 목록 기호를 뗀다
    assert "[1-1] PG 승인 응답" in first[0].content
    assert "모르면 모른다고" not in first[0].content  # 비기능적 인재상은 자기소개에만
    assert item.axes["doc_match"] == Decimal("100.00")
    assert {e.source_type for e in item.evidence} == {"기능적 인재상", "프로젝트 문서"}


def test_opposite_counts_zero_but_keeps_evidence():
    model = FakeModel(_case_read(["바로 실패로 처리했다"]), _claim("반대", ["1-1"]))
    item = _score(model, _docs(skill_cases=[CASE]))["기술 적용 사례"]
    assert item.axes["doc_match"] == Decimal("0.00")
    assert [e.id for e in item.evidence] == ["1-1"] and "반대 1" in item.reason


def test_same_without_valid_ids_counts_as_not_in_docs():
    # 목록에 없는 번호만 고르면 근거를 확인할 수 없다
    model = FakeModel(_case_read(["a"]), _claim("같음", ["9-9"]))
    item = _score(model, _docs(skill_cases=[CASE]))["기술 적용 사례"]
    assert item.axes["doc_match"] == Decimal("0.00") and item.evidence == []
    assert "문서에 없음 1" in item.reason


def test_evidence_ids_written_with_sentences_are_parsed():
    model = FakeModel(_case_read(["a"]), _claim("같음", ["[기-1] 결제 장애를 재현하고 원인을 기록하는 사람"]))
    item = _score(model, _docs(skill_cases=[CASE]))["기술 적용 사례"]
    assert [e.id for e in item.evidence] == ["기-1"]


def test_evidence_far_from_claim_is_dropped_but_judgment_stays():
    # D2-v2: 번호 칸에 목록을 통째로 붙여 근거가 수십 개가 됐다. 유사도 0.50 미만은 뺀다
    claim = "타임아웃이 나면 확인 중으로 두었다"
    model = FakeModel(_case_read([claim]), _claim("같음", ["[1-1] ... [기-1] ... [기-2]"]))
    talent = "결제 장애를 재현하고 원인을 기록하는 사람"
    embed = FakeEmbed({talent: 1, "외부 API 타임아웃을 설계해 본 사람": 1})
    item = _score(model, _docs(skill_cases=[CASE]), embed=embed)["기술 적용 사례"]
    assert [e.id for e in item.evidence] == ["1-1"]
    assert item.axes["doc_match"] == Decimal("100.00")


def test_closest_evidence_is_kept_when_all_are_far():
    claim = "타임아웃이 나면 확인 중으로 두었다"
    model = FakeModel(_case_read([claim]), _claim("같음", ["기-1"]))
    item = _score(model, _docs(skill_cases=[CASE]), embed=FakeEmbed({claim: 1}))["기술 적용 사례"]
    assert [e.id for e in item.evidence] == ["기-1"]


def test_empty_claims_retry_then_zero_match():
    model = FakeModel(_case_read([]), _case_read([]))
    item = _score(model, _docs(skill_cases=[CASE]))["기술 적용 사례"]
    assert model.calls[1][-1].content == EMPTY_CLAIMS_RETRY
    # 80×0.2 + 70×0.3 + 60×0.2 + 0
    assert item.score == Decimal("49.00") and NO_CLAIM_NOTE in item.reason


def test_unrelated_applicant_without_search_results_compares_with_talent_only():
    model = FakeModel(_case_read(["앱 이미지 로딩을 줄였다"]), _claim("문서에 없음", []))
    item = _score(model, _docs(skill_cases=[CASE]), search=FakeSearch(chunks=()))["기술 적용 사례"]
    assert "[기-1]" in model.calls[1][0].content and "[1-1]" not in model.calls[1][0].content
    assert item.axes["doc_match"] == Decimal("0.00")


# ---------- 이력서 ----------


def test_resume_without_selected_items_uses_skill_score_only():
    model = FakeModel()
    item = _score(model, _docs(skills=[{"skill_name": "Java", "self_score": 4}, {"skill_name": "SQL", "self_score": 3}]))["이력서"]
    assert model.calls == []
    assert item.score == Decimal("70.00") and item.reason == SKILL_ONLY_NOTE


def test_resume_compares_experience_and_talent_separately():
    docs = _docs(
        personal={"name": "홍길동", "phone": "010-1234-5678"},
        skills=[{"skill_name": "Java", "self_score": 5}, {"skill_name": "SQL", "self_score": None}],
        careers=[{"company_name": "가상페이", "job_role": "결제 백엔드", "start_date": "2023-01"}],
        projects=[{"project_name": "PG 연동", "description": "PG 타임아웃 처리를 만들었다."}],
    )
    model = FakeModel(
        {"claims": ["결제 백엔드 개발", "PG 타임아웃 처리"], "reason": "결제 경험이 있다."},
        _claim("같음", ["직-1"]), _claim("같음", ["1-1"]),  # 직무 관련 경험
        _claim("문서에 없음", []), _claim("같음", ["기-2"]),  # 기능적 인재상 일치
    )
    search = FakeSearch()
    item = _score(model, docs, search=search)["이력서"]
    read = model.calls[0][-1].content
    assert "가상페이, 결제 백엔드, 2023-01" in read and "PG 타임아웃 처리를 만들었다." in read
    assert "홍길동" not in read and "010-1234-5678" not in read and "Java" not in read
    assert "[직-1] 주문·결제 백엔드를 개발한다." in model.calls[1][0].content
    assert "[직-1]" not in model.calls[3][0].content and "[기-1]" in model.calls[3][0].content
    # 경험 100×0.4 + 기술(5만 센다) 100×0.2 + 인재상 50×0.4
    assert item.axes == {"experience": Decimal("100.00"), "skill": Decimal("100.00"), "talent_match": Decimal("50.00")}
    assert item.score == Decimal("80.00")
    assert "직무 관련 경험" in item.reason and "기능적 인재상 일치" in item.reason
    assert {e.id for e in item.evidence} == {"직-1", "1-1", "기-2"}


# ---------- 포트폴리오, 자기소개, 빈 항목 ----------


def test_portfolio_ratios():
    model = FakeModel({"claims": ["a"], "decision": 90, "depth": 60, "reason": "r"}, _claim("같음", ["1-1"]))
    item = _score(model, _docs(portfolio_text="대안을 비교해 골랐다."))["포트폴리오"]
    assert item.score == Decimal("84.00")  # 36 + 18 + 30


def test_essay_compares_with_nonfunctional_talent_only_without_search():
    model = FakeModel({"claims": ["모른다고 말했다"], "format": 80, "logic": 50, "reason": "r"}, _claim("같음", ["비-1"]))
    search = FakeSearch()
    item = _score(model, _docs(essays=[{"topic": "지원 동기", "content": "모른다고 말하고 데이터를 모았다."}]), search=search)["자기소개"]
    assert search.queries == []
    assert "[지원 동기]" in model.calls[0][-1].content
    system = model.calls[1][0].content
    assert "[비-1] 모르면 모른다고 말하는 정직함" in system and "[기-1]" not in system and "PG" not in system
    assert item.score == Decimal("74.00")  # 24 + 20 + 30
    assert [e.source_type for e in item.evidence] == ["비기능적 인재상"]


def test_empty_items_score_zero_without_llm():
    model = FakeModel()
    items = _score(model, _docs(portfolio_text="  ", skill_cases=[""]))
    assert model.calls == []
    for name in ("기술 적용 사례", "포트폴리오", "자기소개"):
        assert items[name].score == Decimal("0.00") and items[name].reason == NO_TEXT_NOTE
    assert list(items) == ["이력서", "기술 적용 사례", "포트폴리오", "자기소개"]

# ---------- 보고서: 인재상 적합도, 강점·확인 필요, 요약 ----------
# 호출 순서: 항목 점수 → 인재상마다 근거 옮기기 (이 공고는 3개) → 항목마다 강점·확인 필요 → 요약


def _report(model, docs):
    return build_document_report(POSTING, docs, model=model, search=FakeSearch(), embed=FakeEmbed())


def _fit(*quotes):
    return {"quotes": list(quotes)}


def _case_calls():
    """기술 적용 사례만 있는 서류의 항목 점수 호출 (읽기 1 + 비교 1)."""
    return [_case_read(["확인 중으로 두었다"]), _claim("같음", ["기-2"])]


def test_report_asks_fits_points_summary_in_order():
    model = FakeModel(
        *_case_calls(),
        _fit(), _fit("PG 타임아웃이 나면 결제를 확인 중으로 두었습니다."), _fit(),
        {"strength": "PG 타임아웃을 확인 중으로 처리했다.", "check": "결제 버튼 중복 방지의 근거가 없다."},
        {"summary": "결제 타임아웃 경험이 있다."},
    )
    report = _report(model, _docs(skill_cases=[CASE]))
    # 필수 기술만 본 이력서와 빈 항목은 강점·확인 필요를 묻지 않는다
    assert len(model.calls) == 2 + 3 + 1 + 1
    assert [(f.talent_content, f.evidence) for f in report.fits] == [
        ("결제 장애를 재현하고 원인을 기록하는 사람", NO_FIT_NOTE),
        ("외부 API 타임아웃을 설계해 본 사람", '기술 적용 사례: "PG 타임아웃이 나면 결제를 확인 중으로 두었습니다."'),
        ("모르면 모른다고 말하는 정직함", NO_FIT_NOTE),
    ]
    assert [(p.point_type, p.item) for p in report.points] == [("강점", "기술 적용 사례"), ("확인 필요", "기술 적용 사례")]
    assert report.summary == "결제 타임아웃 경험이 있다."


def test_fit_calls_share_documents_in_front_part_without_personal_info():
    model = FakeModel(*_case_calls(), _fit(), _fit(), _fit(), {"strength": "", "check": ""}, {"summary": "s"})
    _report(model, _docs(skill_cases=[CASE]))
    fit_calls = model.calls[2:5]
    assert fit_calls[0][0].content == fit_calls[2][0].content  # 앞부분이 같아야 캐시를 다시 쓴다
    assert "[기술 적용 사례]\n" + CASE in fit_calls[0][0].content and "홍길동" not in fit_calls[0][0].content
    assert "외부 API 타임아웃을 설계해 본 사람" in fit_calls[1][-1].content


def test_fit_quote_not_in_documents_is_dropped():
    model = FakeModel(
        *_case_calls(),
        # 서류에 없는 문장, 너무 짧은 조각, 공백·따옴표만 다른 문장
        _fit("결제 장애를 재현하고 원인을 문서로 남겼습니다.", "확인 중"),
        _fit("“PG 타임아웃이 나면   결제를 확인 중으로 두었습니다.”"),
        _fit(),
        {"strength": "", "check": ""}, {"summary": "s"},
    )
    report = _report(model, _docs(skill_cases=[CASE]))
    assert report.fits[0].evidence == NO_FIT_NOTE
    assert report.fits[1].evidence == '기술 적용 사례: "PG 타임아웃이 나면   결제를 확인 중으로 두었습니다."'
    assert report.llm_output["fits"][0]["kept"] == 0


def test_points_see_item_text_and_judgments():
    model = FakeModel(
        _case_read(["확인 중으로 두었다", "바로 실패로 처리했다"]),
        _claim("같음", ["기-2", "1-1"]), _claim("반대", ["1-1"]),
        _fit(), _fit(), _fit(),
        {"strength": "  ", "check": "결과 수치가 없다."},
        {"summary": "s"},
    )
    report = _report(model, _docs(skill_cases=[CASE]))
    prompt = model.calls[6][-1].content
    assert CASE in prompt  # 원문이 있어야 서류에 있는 수치를 '없다'고 쓰지 않는다 (D3-v3)
    assert "- 문제 정의: 80" in prompt and "- 회사 업무 일치: 50" in prompt
    assert '(반대) 바로 실패로 처리했다 ← 회사 자료: "PG 승인 응답이 5초 안에' in prompt
    assert [(p.point_type, p.content) for p in report.points] == [("확인 필요", "결과 수치가 없다.")]  # 빈 강점은 버린다


def test_summary_sees_scores_and_fit_count_but_not_documents():
    model = FakeModel(
        *_case_calls(),
        _fit(), _fit("PG 타임아웃이 나면 결제를 확인 중으로 두었습니다."), _fit(),
        {"strength": "", "check": "실패 처리 방식이 회사와 다르다."},
        {"summary": "s"},
    )
    _report(model, _docs(skill_cases=[CASE]))
    prompt = model.calls[-1][-1].content
    # 점수 없이 쓰게 했더니 관계없는 지원자도 '직무와 잘 부합한다'고 썼다 (D3-v3)
    assert "[기술 적용 사례] 항목 점수 79 (회사 일치: 회사 업무 일치 100)" in prompt
    assert "[인재상 적합도] 3개 중 1개 확인" in prompt
    assert "외부 API 타임아웃을 설계해 본 사람: 확인됨" in prompt
    assert "결제 장애를 재현하고 원인을 기록하는 사람: 서류에서 확인되지 않음" in prompt
    assert "(확인 필요, 기술 적용 사례) 실패 처리 방식이 회사와 다르다." in prompt
    assert "결제 버튼도 한 번만" not in prompt  # 서류 원문은 넣지 않는다
