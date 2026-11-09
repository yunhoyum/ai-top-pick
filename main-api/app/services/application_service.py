import os
import re
from datetime import date, datetime, timezone

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ErrorCode
from app.domain.enums import ApplicationWriteStatus, ItemName, Role
from app.domain.rules import is_accepting_applications
from app.models.application import ApplicantProject, Application, Career, Education
from app.models.member import Member
from app.models.posting import JobPosting
from app.repositories.application_repo import ApplicationRepo
from app.repositories.doc_item_repo import DocItemRepo
from app.repositories.posting_repo import PostingRepo
from app.schemas.application import (
    ApplicationOut,
    CareerIO,
    EducationIO,
    EssayOut,
    EssaysIn,
    EssayTopicOut,
    FormOut,
    PortfolioOut,
    PostingBrief,
    ProfileIO,
    ProjectIO,
    ResumeIn,
    SkillCaseOut,
    SkillScoreOut,
    SkillsIn,
)
from app.services import file_service

_PERIOD = re.compile(r"^(\d{4})\.(\d{2})\s*~\s*(?:(\d{4})\.(\d{2}))?$")
_PHONE = re.compile(r"^0\d{1,2}-?\d{3,4}-?\d{4}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# 제출 전에 완료해야 하는 단계 이름 (화면의 스텝 이름)
STEP_RESUME = "이력서"
STEP_SKILLS = "사용기술·적용 사례"
STEP_ESSAYS = "자기소개서"
STEP_PORTFOLIO = "포트폴리오"


def _invalid(message: str) -> AppError:
    return AppError(422, ErrorCode.APPLICATION_INVALID, message)


def _parse_period(text: str | None) -> tuple[date | None, date | None]:
    """'2020.03 ~ 2026.02' → (2020-03-01, 2026-02-01). 종료를 비우면 (시작, None)"""
    if not text:
        return None, None
    m = _PERIOD.match(text)
    if not m:
        raise _invalid("기간은 2020.03 ~ 2026.02 형식으로 입력해 주세요. 진행 중이면 종료를 비워 두세요.")
    ys, ms, ye, me = m.groups()
    try:
        start = date(int(ys), int(ms), 1)
        end = date(int(ye), int(me), 1) if ye else None
    except ValueError:
        raise _invalid("기간의 월은 01~12로 입력해 주세요.") from None
    if end is not None and end < start:
        raise _invalid("기간의 종료는 시작보다 빠를 수 없습니다.")
    return start, end


def _format_period(start: date | None, end: date | None) -> str | None:
    if start is None:
        return None
    return f"{start:%Y.%m} ~ {end:%Y.%m}" if end else f"{start:%Y.%m} ~"


def _blank(row) -> bool:
    return all(not v for v in row.model_dump().values())


class ApplicationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ApplicationRepo(db)
        self.postings = PostingRepo(db)

    # ---------- 조회 ----------
    async def get(self, member: Member, posting_id: int) -> ApplicationOut:
        """지원서를 연다. 지원자는 없으면 새로 만들고(서류 접수 중일 때만), 관리자는 빈 화면을 미리 본다."""
        posting = await self._posting(posting_id)
        if member.role == Role.ADMIN.value:
            return await self._out(posting, None)
        application = await self.repo.get(posting_id, member.member_id)
        if application is None:
            self._ensure_open(posting)
            application = await self.repo.create(posting_id, member)
            await self.db.commit()
        return await self._out(posting, application)

    # ---------- 저장 ----------
    async def save_resume(self, member: Member, posting_id: int, req: ResumeIn, validate: bool) -> ApplicationOut:
        """APP-005 이력서 저장"""
        posting, application = await self._editable(member, posting_id)
        items = await self.repo.item_names(posting_id)
        sections = {
            ItemName.EDUCATION.value: req.educations,
            ItemName.CAREER.value: req.careers,
            ItemName.PROJECT.value: req.projects,
        }
        for name, rows in sections.items():
            if name not in items and any(not _blank(r) for r in rows):
                raise _invalid(f"이 공고는 {name}을(를) 받지 않습니다.")

        educations, careers, projects = [], [], []
        for r in (r for r in req.educations if not _blank(r)):
            if validate and not r.school_name:
                raise _invalid("학교명을 입력해 주세요.")
            start, end = _parse_period(r.period)
            educations.append(Education(application_id=application.application_id, school_name=r.school_name or None, major=r.major or None, start_date=start, end_date=end))
        for r in (r for r in req.careers if not _blank(r)):
            if validate and not r.company_name:
                raise _invalid("회사명을 입력해 주세요.")
            start, end = _parse_period(r.period)
            careers.append(Career(application_id=application.application_id, company_name=r.company_name or None, job_role=r.job_role or None, start_date=start, end_date=end))
        for r in (r for r in req.projects if not _blank(r)):
            if validate and not r.project_name:
                raise _invalid("프로젝트명을 입력해 주세요.")
            start, end = _parse_period(r.period)
            projects.append(ApplicantProject(application_id=application.application_id, project_name=r.project_name or None, description=r.description or None, start_date=start, end_date=end))

        if validate:
            self._check_profile(req.profile)
        application.applicant_name = req.profile.name or None
        application.applicant_phone = req.profile.phone or None
        application.applicant_email = req.profile.email or None
        await self.repo.replace_resume(application.application_id, educations, careers, projects)
        await self.db.commit()
        return await self._out(posting, application)

    async def save_skills(self, member: Member, posting_id: int, req: SkillsIn, validate: bool) -> ApplicationOut:
        """APP-006 사용기술, APP-007 기술 적용 사례 저장"""
        posting, application = await self._editable(member, posting_id)
        required = {name.lower(): name for _, name, _ in await self.repo.required_skills(posting_id)}

        seen: set[str] = set()
        for s in req.skills:
            key = s.skill_name.lower()
            if key in seen:
                raise _invalid(f"같은 기술을 두 번 입력했습니다: {s.skill_name}")
            seen.add(key)
        for c in req.cases:
            if c.skill_name and c.skill_name.lower() not in seen:
                raise _invalid("적용 기술은 입력한 기술 중에서 골라 주세요.")
        cases = [c for c in req.cases if c.skill_name or c.content]
        if validate:
            self._check_skills(required, req)
            for c in cases:
                if not c.skill_name:
                    raise _invalid("기술 적용 사례의 적용 기술을 선택해 주세요.")
                if not c.content:
                    raise _invalid("기술 적용 사례의 내용을 입력해 주세요.")

        doc_items = DocItemRepo(self.db)
        ids = {s.skill_name.lower(): await doc_items.get_or_create_skill(s.skill_name) for s in req.skills}
        await self.repo.replace_skills(
            application.application_id,
            [(ids[s.skill_name.lower()], s.score) for s in req.skills],
            [(ids[c.skill_name.lower()] if c.skill_name else None, c.content or None) for c in cases],
        )
        await self.db.commit()
        return await self._out(posting, application)

    async def save_essays(self, member: Member, posting_id: int, req: EssaysIn, validate: bool) -> ApplicationOut:
        """APP-008 자기소개서 저장"""
        posting, application = await self._editable(member, posting_id)
        topic_ids = {t.topic_id for t in await self.repo.topics(posting_id)}
        if any(e.topic_id not in topic_ids for e in req.essays) or len({e.topic_id for e in req.essays}) != len(req.essays):
            raise _invalid("자기소개서 주제가 올바르지 않습니다.")
        if validate:
            written = {e.topic_id for e in req.essays if e.content}
            if written != topic_ids:
                raise _invalid("모든 주제의 자기소개서를 작성해 주세요.")
        await self.repo.replace_essays(application.application_id, [(e.topic_id, e.content or None) for e in req.essays])
        await self.db.commit()
        return await self._out(posting, application)

    async def upload_portfolio(self, member: Member, posting_id: int, upload: UploadFile) -> ApplicationOut:
        """APP-009 포트폴리오(PDF 1개) 등록. 이미 있으면 바꾼다."""
        posting, application = await self._editable(member, posting_id)
        data = await file_service.read_pdf(upload)
        path = f"applications/{application.application_id}/portfolio.pdf"
        await self.repo.set_portfolio(
            application.application_id, os.path.basename(upload.filename or "portfolio.pdf")[:255], len(data), path
        )
        try:
            file_service.save(path, data)
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return await self._out(posting, application)

    async def delete_portfolio(self, member: Member, posting_id: int) -> ApplicationOut:
        posting, application = await self._editable(member, posting_id)
        portfolio = await self.repo.portfolio(application.application_id)
        if portfolio is not None:
            path = portfolio.file_path
            await self.repo.delete_portfolio(portfolio)
            await self.db.commit()
            file_service.delete(path)
        return await self._out(posting, application)

    # ---------- 제출 ----------
    async def submit(self, member: Member, posting_id: int) -> ApplicationOut:
        """APP-011 서류 제출. 필수 기술 기준에 걸리면 서류 전형 결과를 '필수 기술 미달'로 남긴다."""
        posting, application = await self._editable(member, posting_id)
        out = await self._out(posting, application)
        steps = self.incomplete_steps(out)
        if steps:
            raise _invalid(f"작성하지 않은 단계가 있습니다: {', '.join(steps)}")

        cutoffs = {name: cutoff for _, name, cutoff in await self.repo.required_skills(posting_id)}
        if any(
            s.required and cutoffs.get(s.skill_name) is not None and s.score is not None and s.score <= cutoffs[s.skill_name]
            for s in out.skills
        ):
            await self.repo.record_skill_shortfall(application.application_id)
        application.write_status = ApplicationWriteStatus.SUBMITTED.value
        application.submitted_at = datetime.now(timezone.utc)
        await self.db.commit()
        return await self._out(posting, application)

    @staticmethod
    def incomplete_steps(out: ApplicationOut) -> list[str]:
        """제출하려면 더 작성해야 하는 단계. 화면의 '제출 전 확인'과 같은 기준"""
        steps = []
        p = out.profile
        if not (p.name and p.phone and p.email):
            steps.append(STEP_RESUME)
        if any(s.score is None for s in out.skills if s.required) or not any(c.skill_name and c.content for c in out.cases):
            steps.append(STEP_SKILLS)
        if any(not e.content for e in out.essays) or len(out.essays) != len(out.form.essay_topics):
            steps.append(STEP_ESSAYS)
        if out.portfolio is None:
            steps.append(STEP_PORTFOLIO)
        return steps

    # ---------- 내부 ----------
    async def _posting(self, posting_id: int) -> JobPosting:
        posting = await self.postings.get_registered(posting_id)
        if posting is None:
            raise AppError(404, ErrorCode.POSTING_NOT_FOUND, "채용공고를 찾을 수 없습니다.")
        return posting

    @staticmethod
    def _ensure_open(posting: JobPosting) -> None:
        # 진행 상태가 아니라 접수 시각으로 판단한다: 마감 일시 정각부터는 받지 않는다
        if not is_accepting_applications(posting, datetime.now(timezone.utc)):
            raise AppError(409, ErrorCode.APPLICATION_CLOSED, "서류 접수 중인 공고만 지원할 수 있습니다.")

    async def _editable(self, member: Member, posting_id: int) -> tuple[JobPosting, Application]:
        """저장할 수 있는 지원서: 서류 접수 중인 공고의, 아직 제출하지 않은 본인 지원서"""
        posting = await self._posting(posting_id)
        application = await self.repo.get(posting_id, member.member_id)
        if application is None:
            raise AppError(404, ErrorCode.POSTING_NOT_FOUND, "지원서를 찾을 수 없습니다.")
        if application.write_status == ApplicationWriteStatus.SUBMITTED.value:
            raise AppError(409, ErrorCode.APPLICATION_SUBMITTED, "이미 제출한 지원서는 수정할 수 없습니다.")
        self._ensure_open(posting)
        return posting, application

    @staticmethod
    def _check_profile(p: ProfileIO) -> None:
        if not p.name:
            raise _invalid("이름을 입력해 주세요.")
        if not p.phone:
            raise _invalid("연락처를 입력해 주세요.")
        if not _PHONE.match(p.phone):
            raise _invalid("연락처는 010-0000-0000 형식으로 입력해 주세요.")
        if not p.email:
            raise _invalid("이메일을 입력해 주세요.")
        if not _EMAIL.match(p.email):
            raise _invalid("올바른 이메일 형식이 아닙니다.")

    @staticmethod
    def _check_skills(required: dict[str, str], req: SkillsIn) -> None:
        scored = {s.skill_name.lower(): s.score for s in req.skills}
        for key, name in required.items():
            if scored.get(key) is None:
                raise _invalid(f"{name}의 점수를 선택해 주세요.")
        if not any(c.skill_name and c.content for c in req.cases):
            raise _invalid("기술 적용 사례를 1건 이상 작성해 주세요.")

    async def _out(self, posting: JobPosting, application: Application | None) -> ApplicationOut:
        pid = posting.posting_id
        items = await self.repo.item_names(pid)
        topics = await self.repo.topics(pid)
        required = await self.repo.required_skills(pid)

        form = FormOut(
            has_education=ItemName.EDUCATION.value in items,
            has_career=ItemName.CAREER.value in items,
            has_project=ItemName.PROJECT.value in items,
            essay_topics=[EssayTopicOut(topic_id=t.topic_id, topic_name=t.topic_name) for t in topics],
        )
        brief = PostingBrief(
            posting_id=pid,
            position_name=posting.position_name,
            progress_status=posting.progress_status,
            doc_end_at=posting.doc_end_at,
            doc_result_at=posting.doc_result_at,
        )
        # 필수 기술은 점수를 아직 안 골랐어도 항상 보여 준다
        skills = [SkillScoreOut(skill_name=n, required=True, score=None) for _, n, _ in required]
        if application is None:
            return ApplicationOut(
                posting=brief, form=form, preview=True, write_status=None, submitted_at=None, profile=ProfileIO(),
                educations=[], careers=[], projects=[], skills=skills, cases=[],
                essays=[EssayOut(topic_id=t.topic_id, content=None) for t in topics], portfolio=None,
            )

        aid = application.application_id
        required_ids = {i for i, _, _ in required}
        by_name = {s.skill_name: s for s in skills}
        for skill_id, name, score in await self.repo.skill_scores(aid):
            if skill_id in required_ids:
                by_name[name].score = score
            else:
                skills.append(SkillScoreOut(skill_name=name, required=False, score=score))
        answers = await self.repo.essays(aid)
        portfolio = await self.repo.portfolio(aid)
        return ApplicationOut(
            posting=brief,
            form=form,
            preview=False,
            write_status=application.write_status,
            submitted_at=application.submitted_at,
            profile=ProfileIO(
                name=application.applicant_name, phone=application.applicant_phone, email=application.applicant_email
            ),
            educations=[
                EducationIO(school_name=e.school_name, major=e.major, period=_format_period(e.start_date, e.end_date))
                for e in await self.repo.educations(aid)
            ],
            careers=[
                CareerIO(company_name=c.company_name, job_role=c.job_role, period=_format_period(c.start_date, c.end_date))
                for c in await self.repo.careers(aid)
            ],
            projects=[
                ProjectIO(project_name=p.project_name, description=p.description, period=_format_period(p.start_date, p.end_date))
                for p in await self.repo.projects(aid)
            ],
            skills=skills,
            cases=[SkillCaseOut(skill_name=n, content=c) for _, n, c in await self.repo.cases(aid)],
            essays=[EssayOut(topic_id=t.topic_id, content=answers.get(t.topic_id)) for t in topics],
            portfolio=PortfolioOut(file_name=portfolio.file_name, file_size=portfolio.file_size) if portfolio else None,
        )
