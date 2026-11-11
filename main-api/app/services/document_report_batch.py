"""서류 보고서 작업 (Celery 4장 start_document_reports, generate_document_report, 아키텍처 9.5).

서류 마감 → 대상 지원서마다 '서류 보고서' 작업 등록 → 지원자 1명씩 ai-service 호출 → 결과 저장.
한 명이 실패해도 나머지는 계속한다. 작업이 지원자마다 따로라서 실패는 그 작업만 '실패'로 남는다.
"""

import logging

from sqlalchemy import Engine, delete, exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.clients.ai_service import AiServiceClient
from app.domain.enums import ApplicationWriteStatus, JobStatus, JobType, StageResult, StageType
from app.models.application import Application, ApplicationStage
from app.models.batch import BatchJob
from app.models.report import EvidenceSentence, ReportFit, ReportPoint, ReportScore, StageReport
from app.services import job_queue
from app.services.progress_batch import get_engine
from app.workers import job_tracker
from app.workers.payloads import build_document_report_payload

log = logging.getLogger(__name__)


def start_document_reports(posting_id: int, engine: Engine | None = None) -> list[int]:
    """대상 지원서마다 작업을 '대기'로 등록하고 보낸다. 등록한 job_id 목록을 돌려준다.
    대상: 제출했고 서류 결과가 '필수 기술 미달'이 아닌 지원서 (Celery 4장)."""
    with Session(engine or get_engine()) as db:
        shortfall = exists().where(
            ApplicationStage.application_id == Application.application_id,
            ApplicationStage.stage_type == StageType.DOCUMENT.value,
            ApplicationStage.result == StageResult.SKILL_SHORTFALL.value,
        )
        application_ids = db.scalars(
            select(Application.application_id)
            .where(
                Application.posting_id == posting_id,
                Application.write_status == ApplicationWriteStatus.SUBMITTED.value,
                ~shortfall,
            )
            .order_by(Application.application_id)
        ).all()
        job_ids = [_request(db, posting_id, aid) for aid in application_ids]
        db.commit()
    for job_id in job_ids:
        job_queue.send(JobType.DOC_REPORT.value, job_id)
    log.info("공고 %s 서류 보고서 작업 %d개를 등록했습니다", posting_id, len(job_ids))
    return job_ids


def _request(db: Session, posting_id: int, application_id: int) -> int:
    """job_queue.request와 같다 (worker는 동기 세션이라 따로 둔다). 이미 있으면 '대기'로 되돌린다."""
    stmt = (
        insert(BatchJob)
        .values(job_type=JobType.DOC_REPORT.value, posting_id=posting_id, application_id=application_id)
        .on_conflict_do_update(
            constraint="uq_batch_job_job_type",
            set_={"status": JobStatus.PENDING.value, "error_message": None, "started_at": None, "finished_at": None},
        )
        .returning(BatchJob.job_id)
    )
    return db.execute(stmt).scalar_one()


def generate_document_report(
    job_id: int, engine: Engine | None = None, client: AiServiceClient | None = None
) -> int | None:
    """지원자 1명의 서류 보고서를 만들어 저장한다. report_id를 돌려준다. 작업이 '대기'가 아니면 None."""
    client = client or AiServiceClient()
    with Session(engine or get_engine()) as db:
        started_at = job_tracker.start(db, job_id)
        db.commit()
        if started_at is None:
            log.info("작업 %s는 대기 상태가 아니라 건너뜁니다", job_id)
            return None
        application_id = db.get(BatchJob, job_id).application_id

        try:
            payload = build_document_report_payload(db, application_id)
            result = client.create_document_report(payload)
            # 도는 동안 작업이 다시 요청됐으면 이 결과는 쓰지 않고 새 실행에 맡긴다 (job_tracker 설명)
            if not job_tracker.done(db, job_id, started_at):
                db.rollback()
                log.info("작업 %s가 실행 중에 다시 요청돼 결과를 쓰지 않습니다", job_id)
                return None
            report_id = _save(db, application_id, result)
            db.commit()
        except Exception as e:
            db.rollback()
            job_tracker.fail(db, job_id, started_at, f"{type(e).__name__}: {e}")
            db.commit()
            raise
    log.info("지원서 %s 서류 보고서 %s를 저장했습니다", application_id, report_id)
    return report_id


def _save(db: Session, application_id: int, result: dict) -> int:
    """ReportResult를 stage_report, report_score, evidence_sentence, report_fit, report_point에 넣는다.
    서류 전형 행이 없으면 결과를 비워 만든다(합격·불합격은 관리자가 정한다). 이전 보고서가 있으면 지운다."""
    stage_id = db.execute(
        insert(ApplicationStage)
        .values(application_id=application_id, stage_type=StageType.DOCUMENT.value)
        .on_conflict_do_nothing(index_elements=["application_id", "stage_type"])
        .returning(ApplicationStage.application_stage_id)
    ).scalar_one_or_none()
    if stage_id is None:
        stage_id = db.scalar(
            select(ApplicationStage.application_stage_id).where(
                ApplicationStage.application_id == application_id,
                ApplicationStage.stage_type == StageType.DOCUMENT.value,
            )
        )

    old = db.scalar(select(StageReport.report_id).where(StageReport.application_stage_id == stage_id))
    if old is not None:
        # evidence_sentence는 report_score를 지우면 함께 지워진다 (ON DELETE CASCADE)
        for table in (ReportScore, ReportFit, ReportPoint):
            db.execute(delete(table).where(table.report_id == old))
        db.execute(delete(StageReport).where(StageReport.report_id == old))

    report = StageReport(application_stage_id=stage_id, ai_summary=result["summary"])
    db.add(report)
    db.flush()
    for s in result["scores"]:
        db.add(ReportScore(report_id=report.report_id, criteria_id=s["criteria_id"], score=s["score"], evidence=s["evidence"]))
    db.flush()  # evidence_sentence가 report_score를 가리킨다
    db.add_all(
        EvidenceSentence(
            report_id=report.report_id, criteria_id=s["criteria_id"], seq=seq,
            source_type=e["source_type"], source_id=e["source_id"], chunk_id=e["chunk_id"], sentence=e["sentence"],
        )
        for s in result["scores"]
        for seq, e in enumerate(s["evidence_sentences"], start=1)
    )
    db.add_all(ReportFit(report_id=report.report_id, talent_content=f["talent_content"], evidence=f["evidence"]) for f in result["fits"])
    db.add_all(
        ReportPoint(report_id=report.report_id, criteria_id=p["criteria_id"], point_type=p["point_type"], content=p["content"])
        for p in result["points"]
    )
    db.flush()
    return report.report_id
