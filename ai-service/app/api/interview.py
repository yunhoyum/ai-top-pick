"""면접 내부 API (ai-service 2, 내부 API 규약 2장). main-api가 응시 1건(session_id)마다 부른다.

/start, /answer(STT 보정·채점), /expression(표정 재분석 결과). /inquiry(문의)는 5단계에서 연다.
"""

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from app.clients.tts import TtsClient
from app.clients.vision import VisionClient
from app.core.config import get_settings
from app.core.internal_auth import verify_internal_token
from app.core.llm import get_chat_model
from app.db.checkpointer import get_checkpointer
from app.graphs.interview import builder
from app.graphs.interview.nodes import Deps
from app.rag.retriever import search_company_docs
from app.schemas.internal import (
    AnswerRequest,
    AnswerResponse,
    ExpressionRequest,
    ExpressionResponse,
    StartInterviewRequest,
    StartInterviewResponse,
)

router = APIRouter(prefix="/internal/interview", dependencies=[Depends(verify_internal_token)])


@lru_cache
def get_tts():
    return TtsClient().synthesize


@lru_cache
def get_interview_graph():
    deps = Deps(
        tts=get_tts(), model=get_chat_model(), fillers=get_settings().FILLER_WORDS,
        search=search_company_docs, analyze=VisionClient().analyze,
    )
    return builder.build_interview_graph(get_checkpointer(), deps)


# TTS·DB를 부르는 동기 작업이라 def로 둔다. FastAPI가 스레드 풀에서 돌린다
@router.post("/{session_id}/start", response_model=StartInterviewResponse)
def start(session_id: int, req: StartInterviewRequest, graph=Depends(get_interview_graph), tts=Depends(get_tts)):
    """그래프를 시작하거나 재개한다. 첫 행동(질문 + 음성)을 돌려준다."""
    if req.session_id != session_id:
        raise HTTPException(status_code=422, detail="경로와 본문의 session_id가 다릅니다.")
    try:
        return StartInterviewResponse(actions=builder.start_or_resume(graph, req, tts))
    except builder.NoCheckpointError:
        raise HTTPException(status_code=409, detail="이어서 진행할 면접 상태가 없습니다.")


@router.post("/{session_id}/answer", response_model=AnswerResponse)
def answer(session_id: int, req: AnswerRequest, graph=Depends(get_interview_graph)):
    """답변을 평가하고 다음 행동을 돌려준다. 표정 분석이 실패하면 행동은 await_expression 하나다."""
    try:
        evaluation, actions = builder.submit_answer(graph, session_id, req)
        return AnswerResponse(evaluation=evaluation, actions=actions)
    except builder.NotWaitingError:
        raise HTTPException(status_code=409, detail="지금 답변을 받을 질문이 아닙니다.")


@router.post("/{session_id}/expression", response_model=ExpressionResponse)
def expression(session_id: int, req: ExpressionRequest, graph=Depends(get_interview_graph)):
    """다시 분석한 표정 결과로 답변 점수를 내고 다음 행동을 돌려준다 (규약 2.5)."""
    try:
        evaluation, actions = builder.submit_expression(graph, session_id, req)
        return ExpressionResponse(
            expression_score=evaluation["expression_score"], answer_score=evaluation["answer_score"], actions=actions
        )
    except builder.NotWaitingError:
        raise HTTPException(status_code=409, detail="지금 표정 결과를 받을 답변이 아닙니다.")
