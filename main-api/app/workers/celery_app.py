import os

from celery import Celery

BROKER_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery("app", broker=BROKER_URL, backend=BROKER_URL)
