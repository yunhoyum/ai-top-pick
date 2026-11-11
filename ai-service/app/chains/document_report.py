"""서류 보고서 항목 점수 (루브릭 설계서 7장, RAG 설계서 4.1).

항목(이력서, 기술 적용 사례, 포트폴리오, 자기소개)마다 LLM을 여러 번 부른다.
1. 항목 읽기: 회사 자료 없이 지원자가 쓴 것(주장)과 회사와 상관없는 축 점수를 받는다.
2. 주장 비교: 주장마다 따로 회사 자료와 비교해 같음·반대·문서에 없음과 근거 번호를 받는다.
회사 일치 축 점수와 항목 점수는 코드가 계산한다.

회사 일치 축 = 근거 번호가 검증된 '같음' 주장의 비율 × 100 (2026-11-11 결정).
면접(㉡ 50점)과 달리 '문서에 없음'도 0점으로 센다. 서류의 일치 축은 지원자가 한 일이 회사 업무와
얼마나 겹치는지를 보므로, 관계없는 경험이 많을수록 낮아야 한다.
"""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel

from app.chains.structured import invoke_structured
from app.core.llm import get_chat_model
from app.prompts import document_report as prompts
from app.rag.evidence import merge_contexts, number_sentences, split_sentences
from app.rag.retriever import Chunk, search_company_docs
from app.schemas.internal import ApplicantDocuments, PostingBrief
from app.schemas.llm_outputs import (
    ClaimJudgment,
    EssayReadOutput,
    PortfolioReadOutput,
    ResumeReadOutput,
    SkillCaseReadOutput,
)

RESUME, SKILL_CASE, PORTFOLIO, ESSAY = "이력서", "기술 적용 사례", "포트폴리오", "자기소개"

# 인재상·직무 설명 문장 번호의 앞글자. 프로젝트 문서 문장은 '후보 순번-문장 순번'이다
JOB, FUNCTIONAL, NONFUNCTIONAL = ("직", "직무 설명"), ("기", "기능적 인재상"), ("비", "비기능적 인재상")
_SENTENCE_ID = re.compile(r"(?:\d+|[직기비])-\d+")
_BULLET = re.compile(r"^[-•*]\s*")

NO_TEXT_NOTE = "서류에 이 항목의 내용이 없어 0점으로 채점했다."
SKILL_ONLY_NOTE = "공고가 학력·경력·프로젝트를 고르지 않아 필수 기술 점수만으로 채점했다."
NO_CLAIM_NOTE = "서류에서 지원자가 한 일을 찾지 못해 회사 일치 축을 0점으로 채점했다."


@dataclass(frozen=True)
class SourceSentence:
    """번호를 붙인 회사 자료 문장. 근거로 쓰이면 evidence_sentence에 사본으로 저장한다."""

    id: str
    text: str
    source_type: str  # 기능적 인재상, 비기능적 인재상, 직무 설명, 프로젝트 문서
    source_id: int | None = None  # 프로젝트 문서만 document_id
    chunk_id: int | None = None  # 프로젝트 문서만


@dataclass(frozen=True)
class Match:
    """회사 일치 축 하나의 결과."""

    score: Decimal
    counts: dict[str, int]  # 같음, 반대, 문서에 없음. 근거 번호가 모두 빠진 같음·반대는 문서에 없음으로 센다
    evidence: list[SourceSentence]
    judgments: list[dict]


@dataclass(frozen=True)
class ItemScore:
    name: str
    score: Decimal  # 0~100, 소수 둘째 자리 (report_score.score)
    reason: str  # report_score.evidence
    evidence: list[SourceSentence]  # → evidence_sentence(report_id, criteria_id)
    axes: dict[str, Decimal]  # 축 점수. 저장하지 않는다. 평가·디버깅용이다
    llm_output: dict


def score_document_items(
    posting: PostingBrief,
    documents: ApplicantDocuments,
    model: Runnable | None = None,
    search: Callable[[list[str]], list[Chunk]] | None = None,
) -> list[ItemScore]:
    """search: 항목 텍스트로 그 공고의 프로젝트 문서를 찾는다. 없으면 search_company_docs를 쓴다."""
    model = model or get_chat_model()
    search = search or (lambda texts: search_company_docs(posting.posting_id, texts))
    job = _talent(JOB, posting.job_description)
    functional = _talent(FUNCTIONAL, posting.functional_talent)
    nonfunctional = _talent(NONFUNCTIONAL, posting.nonfunctional_talent)

    resume_text = _resume_text(documents)
    skill_cases = "\n\n".join(c for c in documents.skill_cases if c.strip())
    portfolio = (documents.portfolio_text or "").strip()
    essays = "\n\n".join(f"[{e.get('topic', '')}]\n{e.get('content', '')}" for e in documents.essays if e.get("content"))
    skill = _skill_score(documents.skills)

    resume = _resume(model, search, resume_text, skill, job, functional)
    others = [
        # 회사 일치 축: 프로젝트 문서 + 기능적 인재상 (루브릭 설계서 7.3)
        _item(model, SKILL_CASE, skill_cases, SkillCaseReadOutput, {"problem": 20, "process": 30, "result": 20},
              "doc_match", 30, lambda: functional + _project(search, skill_cases)),
        _item(model, PORTFOLIO, portfolio, PortfolioReadOutput, {"decision": 40, "depth": 30},
              "doc_match", 30, lambda: functional + _project(search, portfolio)),
        # 회사 일치도: 비기능적 인재상만. 프로젝트 문서는 검색하지 않는다
        _item(model, ESSAY, essays, EssayReadOutput, {"format": 30, "logic": 40},
              "company_match", 30, lambda: nonfunctional),
    ]
    return [resume, *others]


def _resume(model, search, text: str, skill: Decimal, job, functional) -> ItemScore:
    """직무 관련 경험 40 (직무 설명 + 프로젝트 문서) + 필수 기술 20 (코드) + 기능적 인재상 일치 40."""
    if not text:
        # 공고가 학력·경력·프로젝트를 모두 고르지 않았다. LLM을 부르지 않는다 (루브릭 설계서 7.3)
        return ItemScore(RESUME, skill, SKILL_ONLY_NOTE, [], {"skill": skill}, {})
    read = _read(model, RESUME, text, ResumeReadOutput)
    experience = _match(model, read.claims, job + _project(search, text))
    talent = _match(model, read.claims, functional)
    score = _round((experience.score * 40 + skill * 20 + talent.score * 40) / 100)
    reason = " ".join([read.reason, _match_note("직무 관련 경험", experience), _match_note("기능적 인재상 일치", talent)])
    return ItemScore(
        RESUME, score, reason, _merge(experience.evidence, talent.evidence),
        {"experience": experience.score, "skill": skill, "talent_match": talent.score},
        {"read": read.model_dump(), "experience": experience.judgments, "talent_match": talent.judgments},
    )


def _item(
    model, name: str, text: str, schema: type[BaseModel], ratios: dict[str, int],
    match_key: str, match_ratio: int, sources: Callable[[], list[SourceSentence]],
) -> ItemScore:
    if not text:
        return ItemScore(name, Decimal("0.00"), NO_TEXT_NOTE, [], {}, {})
    read = _read(model, name, text, schema)
    match = _match(model, read.claims, sources())
    axes = {key: Decimal(getattr(read, key)) for key in ratios} | {match_key: match.score}
    score = _round(sum(axes[k] * r for k, r in (ratios | {match_key: match_ratio}).items()) / 100)
    reason = f"{read.reason} {_match_note(_MATCH_NAMES[match_key], match)}"
    return ItemScore(name, score, reason, match.evidence, axes, {"read": read.model_dump(), match_key: match.judgments})


_MATCH_NAMES = {"doc_match": "회사 업무 일치", "company_match": "회사 일치도"}


def _read(model, item: str, text: str, schema: type[BaseModel]):
    """주장을 하나도 뽑지 않으면 한 번 더 묻는다 (면접 답변 읽기와 같다)."""
    messages = prompts.read_item(item, text)
    read = invoke_structured(model, messages, schema)
    if read.claims:
        return read
    retry = messages + [AIMessage(content=read.model_dump_json()), HumanMessage(content=prompts.EMPTY_CLAIMS_RETRY)]
    return invoke_structured(model, retry, schema)


def _match(model, claims: list[str], sources: list[SourceSentence]) -> Match:
    """주장마다 회사 자료와 비교한다. 근거 번호가 검증된 '같음' 주장의 비율이 점수다."""
    counts = {"같음": 0, "반대": 0, "문서에 없음": 0}
    if not claims:
        return Match(Decimal("0.00"), counts, [], [])
    system = prompts.comparison_system([(s.id, s.text) for s in sources])
    by_id = {s.id: s for s in sources}
    evidence: dict[str, SourceSentence] = {}
    judgments = []
    for claim in claims:
        j = invoke_structured(model, prompts.judge_claim(system, claim), ClaimJudgment)
        judgments.append(j.model_dump())
        ids = list(dict.fromkeys(i for raw in j.evidence_ids for i in _SENTENCE_ID.findall(raw) if i in by_id))
        # 같음·반대인데 남은 번호가 없으면 근거를 확인할 수 없다. 문서에 없음으로 센다 (루브릭 설계서 3.3과 같다)
        level = j.level if ids else "문서에 없음"
        counts[level] += 1
        if level != "문서에 없음":
            for i in ids:
                evidence.setdefault(i, by_id[i])
    score = _round(Decimal(counts["같음"] * 100) / len(claims))
    return Match(score, counts, list(evidence.values()), judgments)


def _match_note(axis: str, match: Match) -> str:
    total = sum(match.counts.values())
    if not total:
        return NO_CLAIM_NOTE
    counts = ", ".join(f"{k} {n}" for k, n in match.counts.items() if n)
    return f"{axis}: 서류에서 읽은 내용 {total}개를 회사 자료와 비교했다 ({counts})."


def _talent(kind: tuple[str, str], text: str) -> list[SourceSentence]:
    """인재상·직무 설명 전문에 번호를 붙인다. 목록 기호는 뗀다 (벡터 DB 설계서 2.3)."""
    prefix, source_type = kind
    sentences = [_BULLET.sub("", s) for s in split_sentences(text)]
    return [SourceSentence(f"{prefix}-{i}", s, source_type) for i, s in enumerate((s for s in sentences if s), start=1)]


def _project(search, text: str) -> list[SourceSentence]:
    """항목 텍스트로 프로젝트 문서를 찾아 문장 번호를 붙인다. 긴 텍스트는 검색이 나눠서 찾는다."""
    return [
        SourceSentence(s.id, s.text, s.chunk.source_type, s.chunk.source_id, s.chunk.chunk_id)
        for s in number_sentences(merge_contexts(search([text])))
    ]


def _resume_text(documents: ApplicantDocuments) -> str:
    """공고가 고른 학력·경력·프로젝트. 키 이름에 기대지 않고 값만 잇는다. 인적사항과 필수 기술은 넣지 않는다."""
    lines = []
    for label, rows in (("학력", documents.educations), ("경력", documents.careers), ("프로젝트", documents.projects)):
        lines += [f"[{label}] " + ", ".join(str(v) for v in row.values() if v) for row in rows]
    return "\n".join(lines)


def _skill_score(skills: list[dict]) -> Decimal:
    """필수 기술 자기평가 평균 ÷ 5 × 100 (루브릭 설계서 7.3). 점수가 빈 기술은 뺀다."""
    scores = [s["self_score"] for s in skills if s.get("self_score") is not None]
    if not scores:
        return Decimal("0.00")
    return _round(Decimal(sum(scores)) / len(scores) / 5 * 100)


def _merge(*groups: list[SourceSentence]) -> list[SourceSentence]:
    return list({s.id: s for group in groups for s in group}.values())


def _round(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
