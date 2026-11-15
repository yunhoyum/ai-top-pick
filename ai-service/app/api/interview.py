"""면접 내부 API (ai-service 2, 내부 API 규약 2장). main-api가 응시 1건(session_id)마다 부른다.

실시간 면접 1·2단계: /start, /answer(STT 보정·발화 수치). /expression(표정 재분석)은 3단계, /inquiry(문의)는 5단계에서 연다.
"""

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from app.clients.tts import TtsClient
from app.core.config import get_settings
from app.core.internal_auth import verify_internal_token
from app.core.llm import get_chat_model
from app.db.checkpointer import get_checkpointer
from app.graphs.interview import builder
from app.schemas.internal import AnswerRequest, AnswerResponse, StartInterviewRequest, StartInterviewResponse

router = APIRouter(prefix="/internal/interview", dependencies=[Depends(verify_internal_token)])


@lru_cache
def get_tts():
    return TtsClient().synthesize


@lru_cache
def get_interview_graph():
    return builder.build_interview_graph(get_checkpointer(), get_tts(), get_chat_model(), get_settings().FILLER_WORDS)


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
    """답변을 평가하고 다음 행동을 돌려준다. 2단계: STT 보정과 발화 수치 (점수는 3단계)."""
    try:
        evaluation, actions = builder.submit_answer(graph, session_id, req)
        return AnswerResponse(evaluation=evaluation, actions=actions)
    except builder.NotWaitingError:
        raise HTTPException(status_code=409, detail="지금 답변을 받을 질문이 아닙니다.")
