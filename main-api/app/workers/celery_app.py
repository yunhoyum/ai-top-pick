import os

from celery import Celery

BROKER_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# 작업은 workers/tasks.py에 있다. include로 worker가 시작할 때 불러온다
celery_app = Celery("app", broker=BROKER_URL, backend=BROKER_URL, include=["app.workers.tasks"])

celery_app.conf.timezone = "Asia/Seoul"
# LLM 작업은 llm 큐로 보내고 그 큐는 동시 1개로 받는다. 실시간 면접 응답이 늦어지지 않게 한다 (Celery 2장, 아키텍처 8)
celery_app.conf.task_routes = {
    "report.generate_document_report": {"queue": "llm"},
}
celery_app.conf.beat_schedule = {
    # 공고 진행 상태: 접수 시작·마감, 면접 시작·마감, 면접 결과 발표 시각에 상태를 올린다
    "advance-posting-progress": {"task": "posting.advance_progress", "schedule": 60.0},
}
