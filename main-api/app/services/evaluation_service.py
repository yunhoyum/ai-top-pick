"""서류 전형 평가 (코드베이스 6.5 EvaluationService 중 서류 순위·보고서·관리자 의견).

화면 17 지원자 순위(ADM-023, ADM-024)와 화면 18 서류 전형 결과 보고서(ADM-021).
총점은 저장하지 않고 조회할 때 항목 점수 × 공고의 서류 평가 비율로 계산한다 (루브릭 설계서 9).
면접 전형과 합격자 선정은 아직 없다.
"""

from decimal import Decimal

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ErrorCode
from app.domain.enums import ApplicationWriteStatus, JobType, PointType, StageResult, StageType
from app.domain.rules import calc_weighted, is_doc_stage_closed, round1
from app.models.application import Application, ApplicationStage
from app.models.batch import BatchJob
from app.models.member import Member
from app.models.posting import EvalCriteria, JobPosting, PostingEvalRatio
from app.models.report import ReportFit, ReportPoint, ReportScore, StageReport
from app.repositories.posting_repo import PostingRepo
from app.schemas.evaluation import (
    CriteriaRatio,
    RankingOut,
    RankingRow,
    RankingSummary,
    ReportFitOut,
    ReportOut,
    ReportPointOut,
    ReportScoreOut,
    WeightedScore,
)

DOC = StageType.DOCUMENT.value
REPORT_DONE = "완료"


class EvaluationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.postings = PostingRepo(db)

    async def get_ranking(self, admin: Member, posting_id: int) -> RankingOut:
        """ADM-023 서류 지원자 순위. 보고서가 없는 지원자(작업 대기·실패)는 순위 없이 끝에 둔다."""
        posting = await self._closed_posting(admin, posting_id)
        criteria = await self._criteria(posting_id)
        rows = await self._ranking_rows(posting_id, criteria)
        totals = [r.total for r in rows if r.total is not None]
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
            criteria=criteria,
            summary=RankingSummary(
                target_count=len(rows),
                shortfall_count=shortfall or 0,
                average=round1(sum(totals) / len(totals)) if totals else None,
                opinion_count=sum(r.has_opinion for r in rows),
            ),
            rows=rows,
        )

    async def get_report(self, admin: Member, application_id: int) -> ReportOut:
        """ADM-021 서류 전형 결과 보고서."""
        application, posting = await self._owned_application(admin, application_id)
        stage = await self._stage(application_id)
        report = (
            await self.db.scalar(select(StageReport).where(StageReport.application_stage_id == stage.application_stage_id))
            if stage
            else None
        )
        if report is None:
            raise AppError(404, ErrorCode.REPORT_NOT_FOUND, "아직 서류 전형 결과 보고서가 없습니다.")

        criteria = await self._criteria(posting.posting_id)
        names = {c.criteria_id: c.name for c in criteria}
        ratios = {c.criteria_id: c.ratio for c in criteria}
        scores = {s.criteria_id: s for s in await self.db.scalars(select(ReportScore).where(ReportScore.report_id == report.report_id))}
        rows = await self._ranking_rows(posting.posting_id, criteria)
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
                    weighted=round1(calc_weighted(scores[c.criteria_id].score, c.ratio)),
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
                    found=not f.evidence.startswith(NO_FIT_PREFIX),
                )
                for f in fits
            ],
            strengths=[_point(p, names) for p in points if p.point_type == PointType.STRENGTH.value],
            checks=[_point(p, names) for p in points if p.point_type == PointType.NEEDS_CHECK.value],
            opinion=stage.admin_opinion,
        )

    async def save_opinion(self, admin: Member, application_id: int, opinion: str | None) -> str | None:
        """ADM-024 관리자 의견. 서류 전형 행이 없으면 결과를 비워 만든다 (보고서 저장과 같다)."""
        await self._owned_application(admin, application_id)
        text = (opinion or "").strip() or None
        await self.db.execute(
            insert(ApplicationStage)
            .values(application_id=application_id, stage_type=DOC, admin_opinion=text)
            .on_conflict_do_update(index_elements=["application_id", "stage_type"], set_={"admin_opinion": text})
        )
        await self.db.commit()
        return text

    # ---------- 내부 ----------

    async def _closed_posting(self, admin: Member, posting_id: int) -> JobPosting:
        posting = await self.postings.get_owned(admin.member_id, posting_id)
        if posting is None:
            raise AppError(404, ErrorCode.POSTING_NOT_FOUND, "채용공고를 찾을 수 없습니다.")
        if not is_doc_stage_closed(posting.progress_status):
            raise AppError(409, ErrorCode.STAGE_NOT_CLOSED, "서류 전형이 마감된 뒤에 볼 수 있습니다.")
        return posting

    async def _owned_application(self, admin: Member, application_id: int) -> tuple[Application, JobPosting]:
        """본인 공고의 제출된 지원서만. 아니면 404 (다른 관리자의 지원서가 있는지도 알리지 않는다)."""
        application = await self.db.get(Application, application_id)
        if application is None or application.write_status != ApplicationWriteStatus.SUBMITTED.value:
            raise AppError(404, ErrorCode.APPLICATION_NOT_FOUND, "지원서를 찾을 수 없습니다.")
        if await self.postings.get_owned(admin.member_id, application.posting_id) is None:
            raise AppError(404, ErrorCode.APPLICATION_NOT_FOUND, "지원서를 찾을 수 없습니다.")
        return application, await self._closed_posting(admin, application.posting_id)

    async def _stage(self, application_id: int) -> ApplicationStage | None:
        return await self.db.scalar(
            select(ApplicationStage).where(ApplicationStage.application_id == application_id, ApplicationStage.stage_type == DOC)
        )

    async def _criteria(self, posting_id: int) -> list[CriteriaRatio]:
        rows = await self.db.execute(
            select(EvalCriteria.criteria_id, EvalCriteria.criteria_name, PostingEvalRatio.ratio)
            .join(PostingEvalRatio, PostingEvalRatio.criteria_id == EvalCriteria.criteria_id)
            .where(PostingEvalRatio.posting_id == posting_id, EvalCriteria.stage_type == DOC)
            .order_by(EvalCriteria.criteria_id)
        )
        return [CriteriaRatio(criteria_id=i, name=n, ratio=r or 0) for i, n, r in rows]

    async def _ranking_rows(self, posting_id: int, criteria: list[CriteriaRatio]) -> list[RankingRow]:
        """평가 대상: 제출했고 서류 결과가 '필수 기술 미달'이 아닌 지원서 (서류 보고서 작업 대상과 같다)."""
        shortfall = exists().where(
            ApplicationStage.application_id == Application.application_id,
            ApplicationStage.stage_type == DOC,
            ApplicationStage.result == StageResult.SKILL_SHORTFALL.value,
        )
        applications = (
            await self.db.scalars(
                select(Application).where(
                    Application.posting_id == posting_id,
                    Application.write_status == ApplicationWriteStatus.SUBMITTED.value,
                    ~shortfall,
                )
            )
        ).all()
        ids = [a.application_id for a in applications]
        stages = {
            s.application_id: s
            for s in await self.db.scalars(
                select(ApplicationStage).where(ApplicationStage.application_id.in_(ids), ApplicationStage.stage_type == DOC)
            )
        }
        reports = {
            r.application_stage_id: r.report_id
            for r in await self.db.scalars(
                select(StageReport).where(StageReport.application_stage_id.in_([s.application_stage_id for s in stages.values()]))
            )
        }
        scores: dict[int, dict[int, Decimal]] = {}
        for s in await self.db.scalars(select(ReportScore).where(ReportScore.report_id.in_(list(reports.values())))):
            scores.setdefault(s.report_id, {})[s.criteria_id] = s.score
        jobs = dict(
            (
                await self.db.execute(
                    select(BatchJob.application_id, BatchJob.status).where(
                        BatchJob.posting_id == posting_id, BatchJob.job_type == JobType.DOC_REPORT.value
                    )
                )
            ).all()
        )

        rows = []
        for a in applications:
            stage = stages.get(a.application_id)
            report_id = reports.get(stage.application_stage_id) if stage else None
            item_scores = scores.get(report_id, {}) if report_id else {}
            weighted = {c.criteria_id: calc_weighted(item_scores.get(c.criteria_id, Decimal(0)), c.ratio) for c in criteria}
            rows.append(RankingRow(
                application_id=a.application_id,
                rank=None,
                applicant_name=a.applicant_name,
                total=round1(sum(weighted.values(), Decimal(0))) if report_id else None,
                scores=[WeightedScore(criteria_id=k, weighted=round1(v)) for k, v in weighted.items()] if report_id else [],
                has_opinion=bool(stage and stage.admin_opinion),
                report_status=REPORT_DONE if report_id else jobs.get(a.application_id, "없음"),
            ))
        # 총점 내림차순, 같으면 먼저 지원한 순서. 보고서가 없는 지원자는 끝에
        rows.sort(key=lambda r: (r.total is None, -(r.total or 0), r.application_id))
        for rank, row in enumerate((r for r in rows if r.total is not None), start=1):
            row.rank = rank
        return rows


# ai-service가 인재상과 맞는 경험을 찾지 못했을 때 쓰는 문장 (chains/document_report.NO_FIT_NOTE)
NO_FIT_PREFIX = "서류에서 이 인재상과 맞는 경험을 찾지 못했다"


def _talent_kind(talent: str, posting: JobPosting) -> str | None:
    """report_fit에는 인재상 종류가 없다. 공고의 기능적·비기능적 인재상 전문에서 찾는다."""
    if talent in (posting.functional_talent or ""):
        return "기능적"
    if talent in (posting.nonfunctional_talent or ""):
        return "비기능적"
    return None


def _point(p: ReportPoint, names: dict[int, str]) -> ReportPointOut:
    return ReportPointOut(criteria_name=names.get(p.criteria_id) if p.criteria_id else None, content=p.content)
