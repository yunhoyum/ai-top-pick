"""SYS-006 면접 질문 생성 그래프 (AI Agent 설계서 3장).

직무 질문: 검색어 하나 → 질문 하나. 검색어를 차례로 처리하고 확정 질문 목록(confirmed)을 다음 생성에 넘긴다.
  retrieve → generate → validate → (통과) append
                                  → (evidence 실패) rewrite_query → retrieve
                                  → (question·overlap 실패) generate
                                  → (실패 3회) fallback → (실패) template
인성 질문: 직무 질문을 모두 확정한 뒤 같은 confirmed를 쓰는 분기다. 검색하지 않는다 (설계서 3.10).
  generate_personality → validate_personality → append / generate_personality / fallback_personality → template
template은 LLM 없이 만들어 실패하지 않는다. 그래서 질문 수는 항상 요청과 같다.

LLM 호출 실패(연결 오류, 형식 검증 실패)는 검증 실패와 같이 retry_count에 센다 (2026-11-13, 제안).
fallback 질문은 검증하지 않고 바로 확정한다 (2026-11-13 결정).
검증은 두 단계다 (프롬프트 v2): 적절성을 먼저 보고, 통과하면 확정 질문과 한 쌍씩 겹침을 묻는다. 처음 겹친 쌍에서 멈춘다.
"""

import logging
import re
from itertools import cycle, islice
from typing import Callable, Literal, TypedDict

from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph

from app.chains.structured import invoke_structured
from app.prompts import question as prompts
from app.schemas.internal import ApplicantDocuments, PostingBrief
from app.schemas.llm_outputs import OverlapCheck, QueryOutput, QuestionOutput, QuestionValidation

log = logging.getLogger(__name__)

MAX_RETRIES = 3  # 검증 실패 합산 (설계서 1.3)

# 템플릿 문장 틀 (설계서 7.1 예시, 확정 아님)
JOB_TEMPLATE = "'{}' 기술을 저희 회사 프로젝트에 적용한다면 어떻게 하시겠습니까?"
PERSONALITY_TEMPLATE = "'{}'에 해당하는 본인의 경험을 말씀해 주세요."
FIXED_QUESTION = "본인의 강점이 드러난 경험을 말씀해 주세요."

_SKILL_NAME = re.compile(r"^\[([^\]]+)\]")  # worker가 기술 적용 사례를 '[기술명] 내용'으로 보낸다
_BULLET = re.compile(r"^\s*(?:[-•*·]|\d+[.)])\s*")

Search = Callable[[str], list[str]]  # 검색어 → 청크 본문 목록 (그 공고의 회사 문서만)


class QuestionState(TypedDict, total=False):
    # 전체
    posting: PostingBrief
    documents: ApplicantDocuments
    essays: str  # 자기소개서 전문 (인성 질문 재료)
    queries: list[str]  # 직무 검색어. 길이 = 직무 질문 수
    personality_count: int
    idx: int  # 지금 처리하는 직무 검색어 번호
    confirmed: list[str]  # 확정 질문 (직무 → 인성 순서)
    job: list[str]
    personality: list[str]
    # 질문 하나
    question_type: Literal["직무", "인성"]
    query: str  # rewrite_query가 고친다
    original_query: str  # fallback이 쓴다. 고치지 않는다
    chunks: list[str]
    question: str | None
    failure_type: str | None
    feedback: str
    retry_count: int


def build_queries(documents: ApplicantDocuments, count: int) -> list[str]:
    """직무 검색어 count개. 서류 항목 1건이 검색어 1개다. 이력서는 쓰지 않는다 (설계서 3.2).
    종류를 번갈아(기술 적용 사례 → 포트폴리오 → 자기소개서 → 기술 적용 사례 …) 고르고,
    모자라면 처음부터 다시 쓴다. 같은 검색어로 겹치는 질문은 배타성 검증이 막는다 (2026-11-13 결정)."""
    sources = [
        [c for c in documents.skill_cases if c.strip()],
        [documents.portfolio_text] if documents.portfolio_text and documents.portfolio_text.strip() else [],
        [f"{e['topic']}\n{e['content']}" for e in documents.essays if (e.get("content") or "").strip()],
    ]
    picked = [s[i] for i in range(max(map(len, sources))) for s in sources if i < len(s)]
    return list(islice(cycle(picked or [""]), count))


def essays_text(documents: ApplicantDocuments) -> str:
    return "\n\n".join(f"[{e['topic']}]\n{e['content']}" for e in documents.essays if (e.get("content") or "").strip()) or "(없음)"


def build_template_question(state: QuestionState) -> str:
    """T-09 LLM 없이 만든다. 같은 지원자에게 아직 쓰지 않은 항목부터 쓴다 (설계서 7.1).
    직무: 기술 적용 사례의 기술명 → 공고 필수 기술 → 고정 문장.
    인성: 비기능적 인재상을 줄로 나눈 항목 → 고정 문장 (질문용 항목 변환(B)은 나중에, 2026-11-13 결정)."""
    docs, posting, used = state["documents"], state["posting"], set(state["confirmed"])
    if state["question_type"] == "직무":
        names = [m.group(1).strip() for c in docs.skill_cases if (m := _SKILL_NAME.match(c))]
        names += [s["skill_name"] for s in docs.skills]
        candidates = [JOB_TEMPLATE.format(n) for n in dict.fromkeys(names)]
    else:
        items = [_BULLET.sub("", line).strip() for line in posting.nonfunctional_talent.splitlines()]
        candidates = [PERSONALITY_TEMPLATE.format(i) for i in dict.fromkeys(items) if i]
    return next((q for q in candidates if q not in used), FIXED_QUESTION)


def build_question_graph(model: Runnable, search: Search):
    def call(messages, schema):
        return invoke_structured(model, messages, schema)

    def failed(state: QuestionState, failure_type: str, feedback: str) -> dict:
        return {"failure_type": failure_type, "feedback": feedback, "retry_count": state["retry_count"] + 1}

    def check_overlap(state: QuestionState) -> dict:
        """적절성을 통과한 질문을 확정 질문과 하나씩 비교한다. 겹치면 실패, 아니면 통과."""
        for prev in state["confirmed"]:
            try:
                o = call(prompts.check_overlap(state["question"], prev), OverlapCheck)
            except Exception as e:
                log.warning("겹침 검사 실패: %s", e)
                return failed(state, "question", "")
            if o.same_skill or o.same_competency:
                what = "같은 기술" if o.same_skill else "같은 역량"
                return failed(state, "overlap", f"이미 확정된 질문 '{prev}'와 {what}을 묻는다. {o.reason}".strip())
        return {"failure_type": None, "feedback": ""}

    # ---------- 질문 하나 시작 ----------

    def next_job(state: QuestionState) -> dict:
        query = state["queries"][state["idx"]]
        return {"question_type": "직무", "query": query, "original_query": query, "chunks": [],
                "question": None, "failure_type": None, "feedback": "", "retry_count": 0}

    def next_personality(state: QuestionState) -> dict:
        return {"question_type": "인성", "question": None, "failure_type": None, "feedback": "", "retry_count": 0}

    # ---------- 직무 ----------

    def retrieve(state: QuestionState) -> dict:
        # 결과가 비면 그대로 생성으로 넘긴다. 근거가 없으면 검증이 evidence로 떨어뜨린다 (설계서 2.1 T-01)
        return {"chunks": search(state["query"])}

    def generate(state: QuestionState) -> dict:
        p = state["posting"]
        try:
            out = call(prompts.generate_job(state["query"], state["chunks"], p.job_description, p.functional_talent,
                                            state["confirmed"], state["feedback"]), QuestionOutput)
            return {"question": out.question.strip()}
        except Exception as e:
            log.warning("직무 질문 생성 실패: %s", e)
            return {"question": None}

    def validate(state: QuestionState) -> dict:
        if state["question"] is None:
            return failed(state, "question", "")
        p = state["posting"]
        try:
            v = call(prompts.validate_job(state["question"], state["query"], state["chunks"], p.job_description,
                                          p.functional_talent), QuestionValidation)
        except Exception as e:
            log.warning("직무 질문 검증 실패: %s", e)
            return failed(state, "question", "")
        if v.is_valid:
            return check_overlap(state)
        # 겹침은 check_overlap만 판정한다
        return failed(state, "evidence" if v.failure_type == "evidence" else "question", v.feedback)

    def rewrite_query(state: QuestionState) -> dict:
        try:
            return {"query": call(prompts.rewrite_query(state["query"], state["feedback"]), QueryOutput).query}
        except Exception as e:
            log.warning("검색어 수정 실패: %s", e)
            return {}

    def fallback(state: QuestionState) -> dict:
        try:
            return {"question": call(prompts.fallback_job(state["original_query"]), QuestionOutput).question.strip()}
        except Exception as e:
            log.warning("직무 fallback 질문 생성 실패: %s", e)
            return {"question": None}

    # ---------- 인성 ----------

    def generate_personality(state: QuestionState) -> dict:
        try:
            out = call(prompts.generate_personality(state["essays"], state["posting"].nonfunctional_talent,
                                                    state["confirmed"], state["feedback"]), QuestionOutput)
            return {"question": out.question.strip()}
        except Exception as e:
            log.warning("인성 질문 생성 실패: %s", e)
            return {"question": None}

    def validate_personality(state: QuestionState) -> dict:
        if state["question"] is None:
            return failed(state, "question", "")
        try:
            v = call(prompts.validate_personality(state["question"], state["essays"], state["posting"].nonfunctional_talent),
                     QuestionValidation)
        except Exception as e:
            log.warning("인성 질문 검증 실패: %s", e)
            return failed(state, "question", "")
        if v.is_valid:
            return check_overlap(state)
        # 검색이 없으므로 evidence도 question으로 본다. 겹침은 check_overlap만 판정한다
        return failed(state, "question", v.feedback)

    def fallback_personality(state: QuestionState) -> dict:
        try:
            out = call(prompts.fallback_personality(state["posting"].nonfunctional_talent), QuestionOutput)
            return {"question": out.question.strip()}
        except Exception as e:
            log.warning("인성 fallback 질문 생성 실패: %s", e)
            return {"question": None}

    # ---------- 공통 ----------

    def template(state: QuestionState) -> dict:
        return {"question": build_template_question(state)}

    def append(state: QuestionState) -> dict:
        q = state["question"]
        if state["question_type"] == "직무":
            return {"confirmed": state["confirmed"] + [q], "job": state["job"] + [q], "idx": state["idx"] + 1}
        return {"confirmed": state["confirmed"] + [q], "personality": state["personality"] + [q]}

    # ---------- 라우팅 ----------

    def route_next(state: QuestionState) -> str:
        if state["idx"] < len(state["queries"]):
            return "next_job"
        if len(state["personality"]) < state["personality_count"]:
            return "next_personality"
        return END

    def route_after_validate(state: QuestionState) -> str:
        if state["failure_type"] is None:
            return "append"
        if state["retry_count"] >= MAX_RETRIES:
            return "fallback"
        return "rewrite_query" if state["failure_type"] == "evidence" else "generate"

    def route_after_validate_personality(state: QuestionState) -> str:
        if state["failure_type"] is None:
            return "append"
        return "fallback_personality" if state["retry_count"] >= MAX_RETRIES else "generate_personality"

    def route_after_fallback(state: QuestionState) -> str:
        return "append" if state["question"] else "template"

    g = StateGraph(QuestionState)
    for name, fn in [
        ("next_job", next_job), ("retrieve", retrieve), ("generate", generate), ("validate", validate),
        ("rewrite_query", rewrite_query), ("fallback", fallback),
        ("next_personality", next_personality), ("generate_personality", generate_personality),
        ("validate_personality", validate_personality), ("fallback_personality", fallback_personality),
        ("template", template), ("append", append),
    ]:
        g.add_node(name, fn)

    g.add_conditional_edges(START, route_next, ["next_job", "next_personality", END])
    g.add_edge("next_job", "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "validate")
    g.add_conditional_edges("validate", route_after_validate, ["append", "fallback", "rewrite_query", "generate"])
    g.add_edge("rewrite_query", "retrieve")
    g.add_conditional_edges("fallback", route_after_fallback, ["append", "template"])

    g.add_edge("next_personality", "generate_personality")
    g.add_edge("generate_personality", "validate_personality")
    g.add_conditional_edges("validate_personality", route_after_validate_personality,
                            ["append", "fallback_personality", "generate_personality"])
    g.add_conditional_edges("fallback_personality", route_after_fallback, ["append", "template"])

    g.add_edge("template", "append")
    g.add_conditional_edges("append", route_next, ["next_job", "next_personality", END])
    return g.compile()


# 질문 하나에 지나는 노드 수의 상한: 시작 1 + (검색·수정 2 + 생성·검증 2) × 3 + fallback·template·append 3
_STEPS_PER_QUESTION = 1 + 4 * MAX_RETRIES + 3


def generate_questions(posting: PostingBrief, documents: ApplicantDocuments, job_count: int, personality_count: int,
                       model: Runnable, search: Search) -> tuple[list[str], list[str]]:
    """(직무 질문, 인성 질문). 개수는 요청과 같다."""
    graph = build_question_graph(model, search)
    state = graph.invoke(
        {"posting": posting, "documents": documents, "essays": essays_text(documents),
         "queries": build_queries(documents, job_count), "personality_count": personality_count,
         "idx": 0, "confirmed": [], "job": [], "personality": []},
        {"recursion_limit": _STEPS_PER_QUESTION * (job_count + personality_count) + 10},
    )
    return state["job"], state["personality"]
