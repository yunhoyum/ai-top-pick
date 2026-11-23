import logging

from fastapi import FastAPI

from app.api import interview, questions, reports

# 기본값(WARNING)이면 app의 INFO 로그(면접 구간 시간)가 안 나온다. 다른 라이브러리는 WARNING 그대로 둔다
logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("app").setLevel(logging.INFO)

app = FastAPI()
app.include_router(reports.router)
app.include_router(questions.router)
app.include_router(interview.router)


@app.get("/health")
def health():
    return {"status": "ok"}
