"""전형 평가 (코드베이스 6.5 EvaluationService). 서류와 면접을 같은 함수로 다룬다 (stage 인자).

서류: 화면 17 지원자 순위(ADM-023, ADM-024), 18 결과 보고서(ADM-021), 19 자료 원본(ADM-022), 20 합격자 선정(ADM-025).
면접: 화면 27 지원자 순위(ADM-029, ADM-030), 28 결과 보고서(ADM-027), 29 자료 원본(ADM-028), 30 합격자 선정(ADM-031).
총점은 저장하지 않고 조회할 때 항목 점수 × 공고의 평가 비율로 계산한다 (루브릭 설계서 9).
면접 보고서에 비언어 항목이 없으면(표정이 모두 없음) 남은 항목 비율을 합 100으로 늘린다.
면접 미응시자(응시 '완료'가 없음)는 0점으로 보고 순위와 평균에서 뺀다.
"""

from decimal import Decimal
from pathlib import Path

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ErrorCode
from app.domain.enums import (
    ApplicationWriteStatus,
    JobType,
    PointType,
    ProgressStatus,
    SessionStatus,
    StageResult,
    StageType,
    ValidStatus,
)
from app.domain.rules import calc_weighted, is_doc_stage_closed, is_interview_stage_closed, round1
from app.models.application import (
    ApplicantProject,
    ApplicantSkill,
    Application,
    ApplicationStage,
    Career,
    Education,
    EssayAnswer,
    Portfolio,
    SkillCase,
)
from app.models.batch import BatchJob
from app.models.interview import InterviewAnswer, InterviewQuestion, InterviewSession, SttRecord
from app.models.member import Member
from app.models.posting import CompanyQuestion, EssayTopic, EvalCriteria, JobPosting, PostingEvalRatio, Skill
from app.models.report import ReportFit, ReportPoint, ReportScore, StageReport
from app.repositories.posting_repo import PostingRepo
from app.services import file_service, job_queue
from app.services.application_service import _format_period
from app.schemas.evaluation import (
    CriteriaRatio,
    InterviewSourceOut,
    InterviewSourceQuestion,
    PassOut,
    QuestionResultOut,
    RankingOut,
    RankingRow,
    RankingSummary,
    ReportFitOut,
    ReportOut,
    ReportPointOut,
    ReportScoreOut,
    SourceCareer,
    SourceCase,
    SourceDocumentsOut,
    SourceEducation,
    SourceEssay,
    SourcePortfolio,
    SourceProject,
    SourceSkill,
    SttLineOut,
    WeightedScore,
)

DOC = StageType.DOCUMENT.value
INTERVIEW = StageType.INTERVIEW.value
REPORT_DONE = "완료"
NOT_TAKEN = "미응시"
CONFIRMED_RESULTS = (StageResult.PASS.value, StageResult.FAIL.value)
REPORT_JOBS = {DOC: JobType.DOC_REPORT.value, INTERVIEW: JobType.INTERVIEW_REPORT.value}
STAGE_LABELS = {DOC: "서류", INTERVIEW: "면접"}


class EvaluationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.postings = PostingRepo(db)

    async def get_ranking(self, admin: Member, posting_id: int, stage: str = DOC) -> RankingOut:
        """ADM-023·029 지원자 순위. 보고서가 없는 지원자(작업 대기·실패, 면접 미응시)는 순위 없이 끝에 둔다."""
        posting = await self._closed_posting(admin, posting_id, stage)
        criteria = await self._criteria(posting_id, stage)
        rows = await self._ranking_rows(posting_id, criteria, stage)
        totals = [r.total for r in rows if r.total is not None]
        shortfall = 0
        if stage == DOC:
            shortfall = await self.db.scalar(
                select(func.count())
                .select_from(ApplicationStage)
                .join(Application, Application.application_id == ApplicationStage.application_id)
                .where(
                    Application.posting_id == posting_id,
                    ApplicationStage.stage_type == DOC,
                    ApplicationStage.result == StageResult.SKILL_SHORTFALL.value,
                )
            )
        return RankingOut(
            posting_id=posting_id,
            position_name=posting.position_name,
            doc_end_at=posting.doc_end_at,
            interview_end_at=posting.interview_end_at,
            criteria=criteria,
            confirmed=any(r.result in CONFIRMED_RESULTS for r in rows),
            summary=RankingSummary(
                target_count=len(rows),
                shortfall_count=shortfall or 0,
                taken_count=sum(r.report_status != NOT_TAKEN for r in rows) if stage == INTERVIEW else None,
                average=round1(sum(totals) / len(totals)) if totals else None,
                opinion_count=sum(r.has_opinion for r in rows),
            ),
            rows=rows,
        )

    async def get_report(self, admin: Member, application_id: int, stage: str = DOC) -> ReportOut:
        """ADM-021·027 결과 보고서. 면접은 질문별 결과(구분, 주요 표정)와 꼬리질문 횟수를 더한다 (SYS-010)."""
        application, posting = await self._owned_application(admin, application_id, stage)
        row = await self._stage(application_id, stage)
        report = (
            await self.db.scalar(select(StageReport).where(StageReport.application_stage_id == row.application_stage_id))
            if row
            else None
        )
        if report is None:
            raise AppError(404, ErrorCode.REPORT_NOT_FOUND, f"아직 {STAGE_LABELS[stage]} 전형 결과 보고서가 없습니다.")

        criteria = await self._criteria(posting.posting_id, stage)
        names = {c.criteria_id: c.name for c in criteria}
        scores = {s.criteria_id: s for s in await self.db.scalars(select(ReportScore).where(ReportScore.report_id == report.report_id))}
        factor = _scale(criteria, scores, stage)
        rows = await self._ranking_rows(posting.posting_id, criteria, stage)
        ranked = [r for r in rows if r.rank is not None]
        me = next(r for r in ranked if r.application_id == application_id)

        fits = (await self.db.scalars(select(ReportFit).where(ReportFit.report_id == report.report_id).order_by(ReportFit.fit_id))).all()
        points = (
            await self.db.scalars(select(ReportPoint).where(ReportPoint.report_id == report.report_id).order_by(ReportPoint.point_id))
        ).all()
        return ReportOut(
            application_id=application_id,
            posting_id=posting.posting_id,
            applicant_name=application.applicant_name,
            position_name=posting.position_name,
            doc_end_at=posting.doc_end_at,
            interview_end_at=posting.interview_end_at,
            total=me.total,
            rank=me.rank,
            ranked_count=len(ranked),
            summary=report.ai_summary,
            scores=[
                ReportScoreOut(
                    criteria_id=c.criteria_id,
                    name=c.name,
                    ratio=c.ratio,
                    score=scores[c.criteria_id].score,
                    weighted=round1(calc_weighted(scores[c.criteria_id].score, c.ratio) * factor),
                    scaled_ratio=round1(c.ratio * factor) if factor != 1 else None,
                    evidence=scores[c.criteria_id].evidence,
                )
                for c in criteria
                if c.criteria_id in scores
            ],
            fits=[
                ReportFitOut(
                    talent_content=f.talent_content,
                    kind=_talent_kind(f.talent_content, posting),
                    evidence=f.evidence,
                    found=not f.evidence.startswith(NO_FIT_PREFIXES),
                )
                for f in fits
            ],
            strengths=[_point(p, names) for p in points if p.point_type == PointType.STRENGTH.value],
            checks=[_point(p, names) for p in points if p.point_type == PointType.NEEDS_CHECK.value],
            opinion=row.admin_opinion,
            questions=await self._question_results(application_id) if stage == INTERVIEW else [],
            follow_up_count=report.follow_up_count if stage == INTERVIEW else None,
        )

    async def save_opinion(self, admin: Member, application_id: int, opinion: str | None, stage: str = DOC) -> str | None:
        """ADM-024·030 관리자 의견. 전형 행이 없으면 결과를 비워 만든다 (보고서 저장과 같다)."""
        await self._owned_application(admin, application_id, stage)
        text = (opinion or "").strip() or None
        await self.db.execute(
            insert(ApplicationStage)
            .values(application_id=application_id, stage_type=stage, admin_opinion=text)
            .on_conflict_do_update(index_elements=["application_id", "stage_type"], set_={"admin_opinion": text})
        )
        await self.db.commit()
        return text

    async def confirm_pass(self, admin: Member, posting_id: int, application_ids: list[int], stage: str = DOC) -> PassOut:
        """ADM-025·031 합격자 확정. 고른 지원서는 '합격', 나머지 평가 대상은 '불합격'이다. 한 번만 확정할 수 있다.
        서류: 필수 기술 미달은 그대로 두고, 합격자마다 면접 전형 행과 '면접 질문 생성' 작업(SYS-006)을 만든다.
        면접: 미응시자는 고를 수 없어 '불합격'이 된다. 확정하면 공고를 '마감'으로 바꾼다 (코드베이스 6.5)."""
        posting = await self._closed_posting(admin, posting_id, stage)
        rows = await self._ranking_rows(posting_id, await self._criteria(posting_id, stage), stage)
        if any(r.result in CONFIRMED_RESULTS for r in rows):
            raise AppError(409, ErrorCode.STAGE_ALREADY_CONFIRMED, f"이미 {STAGE_LABELS[stage]} 합격자를 확정했습니다.")
        targets = {r.application_id for r in rows}
        selectable = targets if stage == DOC else {r.application_id for r in rows if r.report_status != NOT_TAKEN}
        selected = set(application_ids)
        if not selected <= selectable:
            raise AppError(422, ErrorCode.APPLICATION_INVALID, "평가 대상이 아닌 지원서가 있습니다.")

        for application_id in targets:
            result = StageResult.PASS.value if application_id in selected else StageResult.FAIL.value
            await self.db.execute(
                insert(ApplicationStage)
                .values(application_id=application_id, stage_type=stage, result=result)
                .on_conflict_do_update(index_elements=["application_id", "stage_type"], set_={"result": result})
            )
        job_ids = []
        if stage == DOC:
            for application_id in selected:
                await self.db.execute(
                    insert(ApplicationStage)
                    .values(application_id=application_id, stage_type=INTERVIEW)
                    .on_conflict_do_nothing(index_elements=["application_id", "stage_type"])
                )
            job_ids = [
                await job_queue.request(self.db, JobType.INTERVIEW_QUESTIONS.value, posting_id, application_id)
                for application_id in sorted(selected)
            ]
        else:
            posting.progress_status = ProgressStatus.CLOSED.value
        await self.db.commit()
        for job_id in job_ids:
            job_queue.send(JobType.INTERVIEW_QUESTIONS.value, job_id)
        return PassOut(passed=len(selected), failed=len(targets - selected))

    async def get_source_documents(self, admin: Member, application_id: int) -> SourceDocumentsOut:
        """ADM-022 지원자가 제출한 자료 원본 (이력서 탭, 자기소개서 탭, 포트폴리오 파일 정보)."""
        a, posting = await self._owned_application(admin, application_id)
        aid = a.application_id
        educations = await self.db.scalars(select(Education).where(Education.application_id == aid).order_by(Education.education_id))
        careers = await self.db.scalars(select(Career).where(Career.application_id == aid).order_by(Career.career_id))
        projects = await self.db.scalars(
            select(ApplicantProject).where(ApplicantProject.application_id == aid).order_by(ApplicantProject.project_id)
        )
        skills = await self.db.execute(
            select(Skill.skill_name, ApplicantSkill.self_score)
            .join(ApplicantSkill, ApplicantSkill.skill_id == Skill.skill_id)
            .where(ApplicantSkill.application_id == aid)
            .order_by(Skill.skill_name)
        )
        cases = await self.db.execute(
            select(Skill.skill_name, SkillCase.content)
            .outerjoin(Skill, Skill.skill_id == SkillCase.skill_id)
            .where(SkillCase.application_id == aid)
            .order_by(SkillCase.seq, SkillCase.skill_case_id)
        )
        essays = await self.db.execute(
            select(EssayTopic.topic_name, EssayAnswer.content)
            .join(EssayAnswer, EssayAnswer.topic_id == EssayTopic.topic_id)
            .where(EssayAnswer.application_id == aid)
            .order_by(EssayTopic.seq)
        )
        portfolio = await self.db.scalar(select(Portfolio).where(Portfolio.application_id == aid))
        return SourceDocumentsOut(
            application_id=aid,
            posting_id=posting.posting_id,
            position_name=posting.position_name,
            doc_end_at=posting.doc_end_at,
            name=a.applicant_name,
            phone=a.applicant_phone,
            email=a.applicant_email,
            educations=[SourceEducation(school_name=e.school_name, major=e.major, period=_format_period(e.start_date, e.end_date))
                        for e in educations],
            careers=[SourceCareer(company_name=c.company_name, job_role=c.job_role, period=_format_period(c.start_date, c.end_date))
                     for c in careers],
            projects=[SourceProject(project_name=p.project_name, period=_format_period(p.start_date, p.end_date),
                                    description=p.description) for p in projects],
            skills=[SourceSkill(skill_name=n, score=sc) for n, sc in skills],
            cases=[SourceCase(skill_name=n, content=c) for n, c in cases],
            essays=[SourceEssay(topic=t, content=c) for t, c in essays],
            portfolio=SourcePortfolio(file_name=portfolio.file_name, file_size=portfolio.file_size) if portfolio else None,
        )

    async def get_portfolio_file(self, admin: Member, application_id: int) -> tuple[Path, str]:
        """ADM-022 포트폴리오 PDF. 브라우저에서 바로 연다."""
        await self._owned_application(admin, application_id)
        portfolio = await self.db.scalar(select(Portfolio).where(Portfolio.application_id == application_id))
        path = file_service.resolve(portfolio.file_path) if portfolio else None
        if path is None or not path.is_file():
            raise AppError(404, ErrorCode.PORTFOLIO_NOT_FOUND, "포트폴리오 파일을 찾을 수 없습니다.")
        return path, portfolio.file_name

    async def get_interview_source(self, admin: Member, application_id: int) -> InterviewSourceOut:
        """ADM-028 면접 자료 원본: 유효 답변마다 질문, 답변 길이, 영상 유무, STT 기록(시점, 보정문, 인식 원문)."""
        a, posting = await self._owned_application(admin, application_id, INTERVIEW)
        questions = []
        for seq, (answer, question, text, kind) in enumerate(await self._valid_answers(application_id), start=1):
            stt = await self.db.scalars(
                select(SttRecord).where(SttRecord.answer_id == answer.answer_id).order_by(SttRecord.time_offset_sec, SttRecord.stt_id)
            )
            questions.append(InterviewSourceQuestion(
                seq=seq, question_id=question.question_id, text=text, kind=kind, answer_id=answer.answer_id,
                duration_sec=answer.duration_sec, has_video=bool(answer.video_path),
                stt=[SttLineOut(time_offset_sec=s.time_offset_sec, corrected_text=s.corrected_text, raw_text=s.raw_text) for s in stt],
            ))
        return InterviewSourceOut(
            application_id=a.application_id, posting_id=posting.posting_id, position_name=posting.position_name,
            interview_end_at=posting.interview_end_at, name=a.applicant_name, questions=questions,
        )

    async def get_answer_video(self, admin: Member, answer_id: int) -> Path:
        """ADM-028 답변 영상(webm). 본인 공고의 면접 전형이 마감된 지원서의 답변만."""
        answer = await self.db.get(InterviewAnswer, answer_id)
        session = await self.db.get(InterviewSession, answer.session_id) if answer else None
        if session is None:
            raise AppError(404, ErrorCode.VIDEO_NOT_FOUND, "답변 영상을 찾을 수 없습니다.")
        await self._owned_application(admin, session.application_id, INTERVIEW)
        path = file_service.resolve(answer.video_path) if answer.video_path else None
        if path is None or not path.is_file():
            raise AppError(404, ErrorCode.VIDEO_NOT_FOUND, "답변 영상을 찾을 수 없습니다.")
        return path

    # ---------- 내부 ----------

    async def _closed_posting(self, admin: Member, posting_id: int, stage: str = DOC) -> JobPosting:
        posting = await self.postings.get_owned(admin.member_id, posting_id)
        if posting is None:
            raise AppError(404, ErrorCode.POSTING_NOT_FOUND, "채용공고를 찾을 수 없습니다.")
        closed = is_doc_stage_closed if stage == DOC else is_interview_stage_closed
        if not closed(posting.progress_status):
            raise AppError(409, ErrorCode.STAGE_NOT_CLOSED, f"{STAGE_LABELS[stage]} 전형이 마감된 뒤에 볼 수 있습니다.")
        return posting

    async def _owned_application(self, admin: Member, application_id: int, stage: str = DOC) -> tuple[Application, JobPosting]:
        """본인 공고의 제출된 지원서만. 아니면 404 (다른 관리자의 지원서가 있는지도 알리지 않는다)."""
        application = await self.db.get(Application, application_id)
        if application is None or application.write_status != ApplicationWriteStatus.SUBMITTED.value:
            raise AppError(404, ErrorCode.APPLICATION_NOT_FOUND, "지원서를 찾을 수 없습니다.")
        if await self.postings.get_owned(admin.member_id, application.posting_id) is None:
            raise AppError(404, ErrorCode.APPLICATION_NOT_FOUND, "지원서를 찾을 수 없습니다.")
        return application, await self._closed_posting(admin, application.posting_id, stage)

    async def _stage(self, application_id: int, stage: str = DOC) -> ApplicationStage | None:
        return await self.db.scalar(
            select(ApplicationStage).where(ApplicationStage.application_id == application_id, ApplicationStage.stage_type == stage)
        )

    async def _criteria(self, posting_id: int, stage: str = DOC) -> list[CriteriaRatio]:
        rows = await self.db.execute(
            select(EvalCriteria.criteria_id, EvalCriteria.criteria_name, PostingEvalRatio.ratio)
            .join(PostingEvalRatio, PostingEvalRatio.criteria_id == EvalCriteria.criteria_id)
            .where(PostingEvalRatio.posting_id == posting_id, EvalCriteria.stage_type == stage)
            .order_by(EvalCriteria.criteria_id)
        )
        return [CriteriaRatio(criteria_id=i, name=n, ratio=r or 0) for i, n, r in rows]

    async def _targets(self, posting_id: int, stage: str) -> list[Application]:
        """서류: 제출했고 '필수 기술 미달'이 아닌 지원서 (서류 보고서 작업 대상과 같다). 면접: 서류 '합격'인 지원서."""
        if stage == DOC:
            condition = ~exists().where(
                ApplicationStage.application_id == Application.application_id,
                ApplicationStage.stage_type == DOC,
                ApplicationStage.result == StageResult.SKILL_SHORTFALL.value,
            )
        else:
            condition = exists().where(
                ApplicationStage.application_id == Application.application_id,
                ApplicationStage.stage_type == DOC,
                ApplicationStage.result == StageResult.PASS.value,
            )
        return (
            await self.db.scalars(
                select(Application).where(
                    Application.posting_id == posting_id,
                    Application.write_status == ApplicationWriteStatus.SUBMITTED.value,
                    condition,
                )
            )
        ).all()

    async def _ranking_rows(self, posting_id: int, criteria: list[CriteriaRatio], stage: str = DOC) -> list[RankingRow]:
        applications = await self._targets(posting_id, stage)
        ids = [a.application_id for a in applications]
        stages = {
            s.application_id: s
            for s in await self.db.scalars(
                select(ApplicationStage).where(ApplicationStage.application_id.in_(ids), ApplicationStage.stage_type == stage)
            )
        }
        reports = {
            r.application_stage_id: r
            for r in await self.db.scalars(
                select(StageReport).where(StageReport.application_stage_id.in_([s.application_stage_id for s in stages.values()]))
            )
        }
        scores: dict[int, dict[int, Decimal]] = {}
        report_ids = [r.report_id for r in reports.values()]
        for s in await self.db.scalars(select(ReportScore).where(ReportScore.report_id.in_(report_ids))):
            scores.setdefault(s.report_id, {})[s.criteria_id] = s.score
        jobs = dict(
            (
                await self.db.execute(
                    select(BatchJob.application_id, BatchJob.status).where(
                        BatchJob.posting_id == posting_id, BatchJob.job_type == REPORT_JOBS[stage]
                    )
                )
            ).all()
        )
        taken = set()
        if stage == INTERVIEW:
            taken = set(await self.db.scalars(
                select(InterviewSession.application_id).where(
                    InterviewSession.application_id.in_(ids), InterviewSession.status == SessionStatus.COMPLETED.value
                )
            ))

        rows = []
        for a in applications:
            row = stages.get(a.application_id)
            report = reports.get(row.application_stage_id) if row else None
            not_taken = stage == INTERVIEW and a.application_id not in taken
            item_scores = scores.get(report.report_id, {}) if report and not not_taken else {}
            factor = _scale(criteria, item_scores, stage)
            # 면접 보고서에 없는 항목(비언어)은 0점이 아니라 '없음'이라 칸을 비운다. 서류는 없으면 0점이다
            shown = [c for c in criteria if stage == DOC or c.criteria_id in item_scores]
            weighted = {c.criteria_id: calc_weighted(item_scores.get(c.criteria_id, Decimal(0)), c.ratio) * factor for c in shown}
            has_report = report is not None and not not_taken
            status = NOT_TAKEN if not_taken else REPORT_DONE if report else jobs.get(a.application_id, "없음")
            rows.append(RankingRow(
                application_id=a.application_id,
                rank=None,
                applicant_name=a.applicant_name,
                total=round1(sum(weighted.values(), Decimal(0))) if has_report else None,
                scores=[WeightedScore(criteria_id=k, weighted=round1(v)) for k, v in weighted.items()] if has_report else [],
                has_opinion=bool(row and row.admin_opinion),
                opinion=row.admin_opinion if row else None,
                result=row.result if row else None,
                report_status=status,
                follow_up_count=report.follow_up_count if stage == INTERVIEW and has_report else None,
            ))
        # 총점 내림차순, 같으면 먼저 지원한 순서. 보고서가 없는 지원자는 끝에
        rows.sort(key=lambda r: (r.total is None, -(r.total or 0), r.application_id))
        for rank, row in enumerate((r for r in rows if r.total is not None), start=1):
            row.rank = rank
        return rows

    async def _valid_answers(self, application_id: int) -> list[tuple[InterviewAnswer, InterviewQuestion, str, str]]:
        """유효 질문의 유효 답변을 진행 순서(순번)대로. (답변, 질문, 질문 글, 구분)."""
        rows = await self.db.execute(
            select(InterviewAnswer, InterviewQuestion, CompanyQuestion.content)
            .join(InterviewQuestion, InterviewQuestion.question_id == InterviewAnswer.question_id)
            .join(InterviewSession, InterviewSession.session_id == InterviewAnswer.session_id)
            .outerjoin(CompanyQuestion, CompanyQuestion.company_question_id == InterviewQuestion.company_question_id)
            .where(
                InterviewSession.application_id == application_id,
                InterviewAnswer.answer_status == ValidStatus.VALID.value,
                InterviewQuestion.question_status == ValidStatus.VALID.value,
            )
            .order_by(InterviewQuestion.seq, InterviewQuestion.question_id)
        )
        return [
            (a, q, q.content or company or "", "기업" if q.company_question_id else ("꼬리" if q.parent_question_id else "AI"))
            for a, q, company in rows
        ]

    async def _question_results(self, application_id: int) -> list[QuestionResultOut]:
        return [
            QuestionResultOut(seq=seq, question_id=q.question_id, text=text, kind=kind,
                              main_expression=a.main_expression, answer_id=a.answer_id)
            for seq, (a, q, text, kind) in enumerate(await self._valid_answers(application_id), start=1)
        ]


# ai-service가 인재상과 맞는 근거를 찾지 못했을 때 쓰는 문장
# (chains/document_report.NO_FIT_NOTE, chains/interview_report.NO_FIT_NOTE)
NO_FIT_PREFIXES = ("서류에서 이 인재상과 맞는 경험을 찾지 못했다", "면접 답변에서 이 인재상을 보여 주는 내용을 찾지 못했다")


def _scale(criteria: list[CriteriaRatio], scores: dict, stage: str) -> Decimal:
    """면접 보고서에 없는 항목(표정이 모두 없어 비언어 없음)이 있으면 남은 항목 비율을 합 100으로 늘린다 (루브릭 설계서 9).
    서류는 늘리지 않는다(항목 점수가 없으면 0점이다)."""
    if stage != INTERVIEW or not scores:
        return Decimal(1)
    present = sum(c.ratio for c in criteria if c.criteria_id in scores)
    total = sum(c.ratio for c in criteria)
    return Decimal(total) / Decimal(present) if present else Decimal(1)


def _talent_kind(talent: str, posting: JobPosting) -> str | None:
    """report_fit에는 인재상 종류가 없다. 공고의 기능적·비기능적 인재상 전문에서 찾는다."""
    if talent in (posting.functional_talent or ""):
        return "기능적"
    if talent in (posting.nonfunctional_talent or ""):
        return "비기능적"
    return None


def _point(p: ReportPoint, names: dict[int, str]) -> ReportPointOut:
    return ReportPointOut(criteria_name=names.get(p.criteria_id) if p.criteria_id else None, content=p.content)
