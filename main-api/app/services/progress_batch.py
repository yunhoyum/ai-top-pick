"""공고 진행 상태 배치. celery-beat가 1분마다 호출한다 (workers/tasks.py).

등록 완료된 공고의 진행 상태를 일정에 맞는 상태로 앞으로만 올린다.
배치가 오래 멈췄다가 켜지면 중간 상태를 건너뛰고 지금 시각에 맞는 상태로 바로 간다.
'서류 평가'로 올라가거나 그것을 건너뛰면 서류 보고서 작업을 등록한다 (Celery 6장 detect_deadlines).
합격자 선정은 아직 연결하지 않는다.
"""

import logging
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import Engine, create_engine, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.enums import PostingWriteStatus, ProgressStatus
from app.domain.rules import PROGRESS_ORDER, expected_progress
from app.models.posting import JobPosting

log = logging.getLogger(__name__)

_engine: Engine | None = None


def get_engine() -> Engine:
    """배치용 동기 엔진. 처음 쓸 때 만든다 (main-api는 비동기 엔진을 쓰고 워커는 동기로 충분하다)."""
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().sqlalchemy_url, pool_pre_ping=True)
    return _engine


def advance_posting_progress(
    engine: Engine | None = None, now: datetime | None = None, posting_ids: list[int] | None = None
) -> dict[str, int]:
    """진행 상태를 올린다. 새 상태별로 몇 건을 올렸는지 돌려준다. posting_ids는 테스트에서 대상을 좁힐 때 쓴다."""
    now = now or datetime.now(timezone.utc)
    moved: Counter[str] = Counter()
    doc_closed: list[int] = []
    doc_evaluation = PROGRESS_ORDER.index(ProgressStatus.DOC_EVALUATION.value)
    with Session(engine or get_engine()) as db:
        query = select(JobPosting).where(
            JobPosting.write_status == PostingWriteStatus.COMPLETE.value,
            JobPosting.progress_status != ProgressStatus.CLOSED.value,
        )
        if posting_ids is not None:
            query = query.where(JobPosting.posting_id.in_(posting_ids))
        for posting in db.scalars(query):
            target = expected_progress(posting, now)
            current = posting.progress_status or ProgressStatus.BEFORE_RECRUIT.value
            # 앞으로만 간다. 현재 상태가 이미 같거나 더 뒤이면 건드리지 않는다
            if PROGRESS_ORDER.index(target) > PROGRESS_ORDER.index(current):
                # 상태가 그 사이 바뀐 공고는 건드리지 않도록 이전 값을 조건에 건다
                result = db.execute(
                    update(JobPosting)
                    .where(JobPosting.posting_id == posting.posting_id, JobPosting.progress_status == posting.progress_status)
                    .values(progress_status=target)
                )
                if result.rowcount:
                    moved[target] += 1
                    log.info("공고 %s 진행 상태 %s → %s", posting.posting_id, current, target)
                    if PROGRESS_ORDER.index(current) < doc_evaluation <= PROGRESS_ORDER.index(target):
                        doc_closed.append(posting.posting_id)
        db.commit()

    # 상태를 바꾼 뒤에 등록한다. 등록이 실패해도 상태 변경은 남는다 (공고마다 따로 처리)
    from app.services.document_report_batch import start_document_reports  # 순환 import를 피한다

    for posting_id in doc_closed:
        try:
            start_document_reports(posting_id, engine)
        except Exception:
            log.exception("공고 %s 서류 보고서 작업을 등록하지 못했습니다", posting_id)
    return dict(moved)
