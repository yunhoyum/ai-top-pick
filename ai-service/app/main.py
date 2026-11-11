from fastapi import FastAPI

from app.api import reports

app = FastAPI()
app.include_router(reports.router)


@app.get("/health")
def health():
    return {"status": "ok"}
