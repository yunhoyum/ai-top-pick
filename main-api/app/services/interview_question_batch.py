"""면접 질문 생성 작업 (SYS-006, Celery 4장 generate_interview_questions).

서류 합격자 확정(ADM-025) → 합격자마다 '면접 질문 생성' 작업 등록 → 지원자 1명씩 ai-service 질문 생성 그래프 호출
→ 직무 → 인성 → 기업 순서로 순번을 매겨 interview_question에 저장한다.
한 명이 실패해도 나머지는 계속한다. 작업이 지원자마다 따로라서 실패는 그 작업만 '실패'로 남는다.
"""

import logging

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from app.clients.ai_service import AiServiceClient
from app.domain.enums import QuestionType
from app.domain.rules import calc_question_counts
from app.models.application import Application
from app.models.batch import BatchJob
from app.models.interview import InterviewQuestion
from app.models.posting import CompanyQuestion, JobPosting
from app.services.progress_batch import get_engine
from app.workers import job_tracker
from app.workers.payloads import build_question_payload

log = logging.getLogger(__name__)


def generate_interview_questions(
    job_id: int, engine: Engine | None = None, client: AiServiceClient | None = None
) -> int | None:
    """SYS-006 지원자 1명의 면접 질문을 만들어 저장한다. 저장한 질문 수를 돌려준다. 작업이 '대기'가 아니면 None."""
    client = client or AiServiceClient()
    with Session(engine or get_engine()) as db:
        started_at = job_tracker.start(db, job_id)
        db.commit()
        if started_at is None:
            log.info("작업 %s는 대기 상태가 아니라 건너뜁니다", job_id)
            return None
        application_id = db.get(BatchJob, job_id).application_id

        try:
            posting = db.get(JobPosting, db.get(Application, application_id).posting_id)
            company_ids = db.scalars(
                select(CompanyQuestion.company_question_id)
                .where(CompanyQuestion.posting_id == posting.posting_id)
                .order_by(CompanyQuestion.seq, CompanyQuestion.company_question_id)
            ).all()
            job_count, personality_count = calc_question_counts(
                posting.question_count or 0, len(company_ids), posting.job_question_ratio or 0
            )
            job, personality = [], []
            # 기업 질문 수가 출제 문제 개수와 같으면 AI 질문은 0개다. ai-service를 부르지 않는다
            if job_count + personality_count:
                result = client.generate_questions(build_question_payload(db, application_id, job_count, personality_count))
                job, personality = result["job"], result["personality"]
                if (len(job), len(personality)) != (job_count, personality_count):
                    raise ValueError(
                        f"질문 수가 요청과 다릅니다: 직무 {len(job)}/{job_count}, 인성 {len(personality)}/{personality_count}"
                    )
            # 도는 동안 작업이 다시 요청됐으면 이 결과는 쓰지 않고 새 실행에 맡긴다 (job_tracker 설명)
            if not job_tracker.done(db, job_id, started_at):
                db.rollback()
                log.info("작업 %s가 실행 중에 다시 요청돼 결과를 쓰지 않습니다", job_id)
                return None
            saved = _save(db, application_id, job, personality, company_ids)
            db.commit()
        except Exception as e:
            db.rollback()
            job_tracker.fail(db, job_id, started_at, f"{type(e).__name__}: {e}")
            db.commit()
            raise
    log.info("지원서 %s 면접 질문 %d개를 저장했습니다", application_id, saved)
    return saved


def _save(db: Session, application_id: int, job: list[str], personality: list[str], company_ids: list[int]) -> int:
    """직무 → 인성 → 기업 순서로 seq 1부터 넣는다. 기업 질문은 내용을 비우고 company_question_id만 넣는다 (테이블 명세서).
    다시 만들면 이전 질문을 지운다. 면접 답변이 달린 질문은 외래 키 때문에 지워지지 않아 작업이 실패한다."""
    db.execute(delete(InterviewQuestion).where(InterviewQuestion.application_id == application_id))
    rows = [dict(question_type=QuestionType.JOB.value, content=q) for q in job]
    rows += [dict(question_type=QuestionType.PERSONALITY.value, content=q) for q in personality]
    rows += [dict(company_question_id=cid) for cid in company_ids]
    db.add_all(
        InterviewQuestion(application_id=application_id, seq=seq, is_revealed=False, **row)
        for seq, row in enumerate(rows, start=1)
    )
    db.flush()
    return len(rows)
