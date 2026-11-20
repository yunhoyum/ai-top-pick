"""질문 생성 내부 API (ai-service 2, 내부 API 규약 3.2). worker가 서류 합격자 1명씩 부른다. 저장은 worker가 한다."""

from fastapi import APIRouter, Depends

from app.core.internal_auth import verify_internal_token
from app.core.llm import get_chat_model
from app.graphs.question import generate_questions
from app.rag.retriever import search_company_docs
from app.schemas.internal import QuestionGenRequest, QuestionGenResponse

router = APIRouter(prefix="/internal/questions", dependencies=[Depends(verify_internal_token)])


# LLM을 여러 번 부르는 동기 작업이라 def로 둔다. FastAPI가 스레드 풀에서 돌린다
@router.post("/generate", response_model=QuestionGenResponse)
def generate(req: QuestionGenRequest) -> QuestionGenResponse:
    """SYS-006 AI 질문 생성. fallback까지 실패하면 템플릿 질문을 넣으므로 개수는 항상 요청과 같다."""
    posting_id = req.posting.posting_id
    job, personality = generate_questions(
        req.posting, req.documents, req.job_count, req.personality_count,
        model=get_chat_model(),
        # 질문 생성만 리랭커를 켠다 (RAG 개선 2)
        search=lambda query: [c.content for c in search_company_docs(posting_id, [query], rerank=True)],
    )
    return QuestionGenResponse(job=job, personality=personality)
