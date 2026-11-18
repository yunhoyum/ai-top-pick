"""면접 내부 API (ai-service 2, 내부 API 규약 2장). main-api가 응시 1건(session_id)마다 부른다.

/start, /answer(STT 보정·채점), /expression(표정 재분석 결과), /inquiry(문의).
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
from app.chains.structured import invoke_structured
from app.graphs.interview.follow_up_nodes import make_follow_up
from app.graphs.question import generate_questions
from app.prompts import inquiry as inquiry_prompts
from app.schemas.llm_outputs import InquiryAnalysis
from app.graphs.interview.nodes import Deps
from app.rag.retriever import search_company_docs
from app.schemas.internal import (
    AnswerRequest,
    AnswerResponse,
    ExpressionRequest,
    ApplicantDocuments,
    ExpressionResponse,
    InquiryRequest,
    InquiryResponse,
    PostingBrief,
    StartInterviewRequest,
    StartInterviewResponse,
)

router = APIRouter(prefix="/internal/interview", dependencies=[Depends(verify_internal_token)])


@lru_cache
def get_tts():
    return TtsClient().synthesize


def _replacement(model, posting: dict, documents: dict, qtype: str, existing: list[str]) -> str:
    """문의 처리로 AI 질문을 대신할 새 질문 하나 (T-24). 질문 생성 그래프를 1개짜리로 쓴다.
    이미 나온 질문을 확정 목록에 넣어 겹침 검사가 비교하게 한다. fallback까지 실패하면 템플릿이라 항상 하나가 나온다."""
    job, personality = generate_questions(
        PostingBrief(**posting), ApplicantDocuments(**documents), int(qtype == "직무"), int(qtype != "직무"),
        model=model, search=lambda q: [c.content for c in search_company_docs(posting["posting_id"], [q])],
        existing=existing,
    )
    return (job or personality)[0]


@lru_cache
def get_interview_graph():
    model = get_chat_model()
    deps = Deps(
        tts=get_tts(), model=model, fillers=get_settings().FILLER_WORDS,
        search=search_company_docs, analyze=VisionClient().analyze,
        follow_up=lambda inputs: make_follow_up(model, inputs),
        analyze_inquiry=lambda messages, logs, tried: invoke_structured(
            model, inquiry_prompts.analyze(messages, logs, tried), InquiryAnalysis).model_dump(),
        replace_question=lambda posting, documents, qtype, existing: _replacement(model, posting, documents, qtype, existing),
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
    except builder.GraphBusyError:
        raise HTTPException(status_code=409, detail="이전 요청을 아직 처리하고 있습니다.")


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


@router.post("/{session_id}/inquiry", response_model=InquiryResponse)
def inquiry(session_id: int, req: InquiryRequest, graph=Depends(get_interview_graph)):
    """문의 시작·메시지·해결 확인을 처리한다 (규약 2.4)."""
    try:
        return InquiryResponse(**builder.submit_inquiry(graph, session_id, req))
    except builder.NotWaitingError:
        raise HTTPException(status_code=409, detail="지금 받을 수 있는 문의 요청이 아닙니다.")
