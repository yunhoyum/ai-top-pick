"""보고서 내부 API (ai-service 2, 내부 API 규약 3.3). worker가 지원자 1명씩 부른다. 저장은 worker가 한다."""

from fastapi import APIRouter, Depends, HTTPException

from app.chains.document_report import ITEMS, build_document_report
from app.chains.interview_report import ITEMS as INTERVIEW_ITEMS
from app.chains.interview_report import build_interview_report
from app.chains.structured import StructuredOutputError
from app.core.internal_auth import verify_internal_token
from app.schemas.internal import (
    CriteriaScore,
    DocumentReportRequest,
    EvidenceSentence,
    FitItem,
    InterviewReportRequest,
    PointItem,
    ReportResult,
)

router = APIRouter(prefix="/internal/reports", dependencies=[Depends(verify_internal_token)])


# LLM을 여러 번 부르는 동기 작업이라 def로 둔다. FastAPI가 스레드 풀에서 돌린다
@router.post("/document", response_model=ReportResult)
def document_report(req: DocumentReportRequest) -> ReportResult:
    criteria_ids = {c.name: c.criteria_id for c in req.criteria}
    if missing := [name for name in ITEMS if name not in criteria_ids]:
        raise HTTPException(status_code=422, detail=f"서류 평가 항목이 없습니다: {', '.join(missing)}")
    try:
        report = build_document_report(req.posting, req.documents)
    except StructuredOutputError as e:
        # 다시 물어도 LLM 출력이 형식에 맞지 않았다. worker는 이 지원자를 실패로 두고 다음으로 넘어간다 (아키텍처 9.5)
        raise HTTPException(status_code=502, detail=str(e)) from e

    return ReportResult(
        scores=[
            CriteriaScore(
                criteria_id=criteria_ids[item.name],
                score=item.score,
                evidence=item.reason,
                evidence_sentences=[
                    EvidenceSentence(source_type=s.source_type, source_id=s.source_id, chunk_id=s.chunk_id, sentence=s.text)
                    for s in item.evidence
                ],
            )
            for item in report.items
        ],
        fits=[FitItem(talent_content=f.talent_content, evidence=f.evidence) for f in report.fits],
        points=[PointItem(point_type=p.point_type, criteria_id=criteria_ids[p.item], content=p.content) for p in report.points],
        summary=report.summary,
    )


@router.post("/interview", response_model=ReportResult)
def interview_report(req: InterviewReportRequest) -> ReportResult:
    """면접 보고서 (규약 3.4, 루브릭 설계서 8·10.2). 항목 점수는 실시간 답변별 점수의 평균이다.
    표정이 모두 없으면 비언어 항목을 내지 않는다. 총점은 main-api가 남은 항목 비율을 늘려 계산한다 (루브릭 설계서 9)."""
    criteria_ids = {c.name: c.criteria_id for c in req.criteria}
    if missing := [name for name in INTERVIEW_ITEMS if name not in criteria_ids]:
        raise HTTPException(status_code=422, detail=f"면접 평가 항목이 없습니다: {', '.join(missing)}")
    try:
        report = build_interview_report(req.posting, req.answers)
    except StructuredOutputError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return ReportResult(
        # 근거 문장은 답변별 evidence_sentence(answer_id)를 보여 준다. 보고서 항목용으로 다시 저장하지 않는다 (8.2)
        scores=[CriteriaScore(criteria_id=criteria_ids[i.name], score=i.score, evidence=i.evidence, evidence_sentences=[])
                for i in report.items],
        fits=[FitItem(talent_content=f.talent_content, evidence=f.evidence) for f in report.fits],
        points=[PointItem(point_type=p.point_type, criteria_id=criteria_ids[p.item], content=p.content) for p in report.points],
        summary=report.summary,
    )
