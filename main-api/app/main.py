from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import auth, postings
from app.api.applicant import applications, my_applications
from app.api.admin import postings as admin_postings
from app.core.config import get_settings
from app.core.deps import get_db
from app.core.errors import register_handlers

app = FastAPI()

# web(다른 포트)에서 쿠키를 보내려면 allow_credentials=True와 명시된 origin이 필요하다 (코드베이스 4.5)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_handlers(app)
app.include_router(auth.router)
app.include_router(admin_postings.router)
app.include_router(postings.router)
app.include_router(applications.router)
app.include_router(my_applications.router)


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
