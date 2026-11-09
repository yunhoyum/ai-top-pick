import os

from celery import Celery

BROKER_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# 작업은 workers/tasks.py에 있다. include로 worker가 시작할 때 불러온다
celery_app = Celery("app", broker=BROKER_URL, backend=BROKER_URL, include=["app.workers.tasks"])

celery_app.conf.timezone = "Asia/Seoul"
celery_app.conf.beat_schedule = {
    # 공고 진행 상태: 접수 시작·마감, 면접 시작·마감, 면접 결과 발표 시각에 상태를 올린다
    "advance-posting-progress": {"task": "posting.advance_progress", "schedule": 60.0},
}
