from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db

app = FastAPI()


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    """서버와 DB 연결을 확인한다. DB에 접속하지 못하면 503."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=503, content={"status": "error", "db": "unreachable"}
        )
    return {"status": "ok", "db": "ok"}
