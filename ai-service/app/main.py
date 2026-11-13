from fastapi import FastAPI

from app.api import questions, reports

app = FastAPI()
app.include_router(reports.router)
app.include_router(questions.router)


@app.get("/health")
def health():
    return {"status": "ok"}
