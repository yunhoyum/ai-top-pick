from fastapi import FastAPI

from app.api import interview, questions, reports

app = FastAPI()
app.include_router(reports.router)
app.include_router(questions.router)
app.include_router(interview.router)


@app.get("/health")
def health():
    return {"status": "ok"}
