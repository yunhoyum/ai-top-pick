"""ai-service 요청 본문 만들기 (Celery 5장). 본문 형식은 '6. 내부 API·WebSocket 규약' 3장이다.

ai-service는 업무 테이블을 읽지 않는다. 그래서 worker가 읽어서 넘긴다 (아키텍처 4.1-3).
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import ItemName, StageType
from app.models.application import (
    ApplicantProject,
    ApplicantSkill,
    Application,
    Career,
    Education,
    EssayAnswer,
    Portfolio,
    SkillCase,
)
from app.models.posting import (
    BasicItem,
    EssayTopic,
    EvalCriteria,
    JobPosting,
    PostingBasicItem,
    PostingEvalRatio,
    RequiredSkill,
    Skill,
)
from app.services import file_service
from app.workers.pdf_text import extract_text


def build_document_report_payload(db: Session, application_id: int) -> dict:
    """DocumentReportRequest (규약 3.3)."""
    application = db.get(Application, application_id)
    posting = db.get(JobPosting, application.posting_id)
    return {
        "application_id": application_id,
        "posting": posting_brief(posting),
        "criteria": _criteria(db, posting.posting_id, StageType.DOCUMENT.value),
        "documents": applicant_documents(db, application),
    }


def posting_brief(posting: JobPosting) -> dict:
    """PostingBrief. 직무 설명·인재상은 검색하지 않고 전문을 넣는다 (벡터 DB 설계서 2.3)."""
    return {
        "posting_id": posting.posting_id,
        "position_name": posting.position_name or "",
        "job_description": posting.job_description or "",
        "functional_talent": posting.functional_talent or "",
        "nonfunctional_talent": posting.nonfunctional_talent or "",
    }


def applicant_documents(db: Session, application: Application) -> dict:
    """ApplicantDocuments. 학력·경력·프로젝트는 공고가 고른 문항만 넣는다 (ADM-007).
    필수 기술은 공고가 정한 기술의 자기평가만 넣는다. 이력서 필수 기술 축이 그 평균이다 (루브릭 설계서 7.3)."""
    aid, pid = application.application_id, application.posting_id
    selected = set(
        db.scalars(
            select(BasicItem.item_name)
            .join(PostingBasicItem, PostingBasicItem.item_id == BasicItem.item_id)
            .where(PostingBasicItem.posting_id == pid)
        )
    )
    educations = careers = projects = []
    if ItemName.EDUCATION.value in selected:
        educations = [
            {"school_name": e.school_name, "major": e.major, "start_date": _month(e.start_date), "end_date": _month(e.end_date)}
            for e in db.scalars(select(Education).where(Education.application_id == aid).order_by(Education.education_id))
        ]
    if ItemName.CAREER.value in selected:
        careers = [
            {"company_name": c.company_name, "job_role": c.job_role, "start_date": _month(c.start_date), "end_date": _month(c.end_date)}
            for c in db.scalars(select(Career).where(Career.application_id == aid).order_by(Career.career_id))
        ]
    if ItemName.PROJECT.value in selected:
        projects = [
            {"project_name": p.project_name, "start_date": _month(p.start_date), "end_date": _month(p.end_date), "description": p.description}
            for p in db.scalars(
                select(ApplicantProject).where(ApplicantProject.application_id == aid).order_by(ApplicantProject.project_id)
            )
        ]

    skills = [
        {"skill_name": name, "self_score": score}
        for name, score in db.execute(
            select(Skill.skill_name, ApplicantSkill.self_score)
            .join(ApplicantSkill, ApplicantSkill.skill_id == Skill.skill_id)
            .join(RequiredSkill, (RequiredSkill.skill_id == Skill.skill_id) & (RequiredSkill.posting_id == pid))
            .where(ApplicantSkill.application_id == aid)
            .order_by(Skill.skill_name)
        )
    ]
    skill_cases = [
        f"[{name}] {content}" if name else content
        for name, content in db.execute(
            select(Skill.skill_name, SkillCase.content)
            .outerjoin(Skill, Skill.skill_id == SkillCase.skill_id)
            .where(SkillCase.application_id == aid, SkillCase.content.is_not(None))
            .order_by(SkillCase.seq, SkillCase.skill_case_id)
        )
    ]
    essays = [
        {"topic": topic, "content": content}
        for topic, content in db.execute(
            select(EssayTopic.topic_name, EssayAnswer.content)
            .join(EssayAnswer, EssayAnswer.topic_id == EssayTopic.topic_id)
            .where(EssayAnswer.application_id == aid, EssayAnswer.content.is_not(None))
            .order_by(EssayTopic.seq)
        )
    ]
    portfolio = db.scalar(select(Portfolio).where(Portfolio.application_id == aid))
    # ai-service는 PC2에 있어 파일을 읽지 못한다. worker가 PC1 디스크에서 추출해 넣는다 (Celery 5장)
    portfolio_text = extract_text(file_service.resolve(portfolio.file_path)) if portfolio else None

    return {
        # 인적사항은 점수에 넣지 않는다 (루브릭 설계서 7.3). 규약 형식을 맞추려고 보낸다
        "personal": {"name": application.applicant_name, "phone": application.applicant_phone, "email": application.applicant_email},
        "skills": skills,
        "educations": educations,
        "careers": careers,
        "projects": projects,
        "skill_cases": skill_cases,
        "essays": essays,
        "portfolio_text": portfolio_text or None,
    }


def _criteria(db: Session, posting_id: int, stage_type: str) -> list[dict]:
    """CriteriaItem. 항목 설명은 eval_criteria에서 읽어 넣는다 (Celery 5장)."""
    rows = db.execute(
        select(EvalCriteria, PostingEvalRatio.ratio)
        .join(PostingEvalRatio, PostingEvalRatio.criteria_id == EvalCriteria.criteria_id)
        .where(PostingEvalRatio.posting_id == posting_id, EvalCriteria.stage_type == stage_type)
        .order_by(EvalCriteria.criteria_id)
    )
    return [
        {"criteria_id": c.criteria_id, "name": c.criteria_name, "description": c.description, "ratio": ratio or 0}
        for c, ratio in rows
    ]


def _month(d: date | None) -> str | None:
    return d.strftime("%Y-%m") if d else None
