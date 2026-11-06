from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db

settings = get_settings()

app = FastAPI()

# 쿠키 인증이라 allow_credentials=True, origin은 명시한다 (코드베이스 4.5)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
