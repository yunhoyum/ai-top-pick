from datetime import datetime

from pydantic import BaseModel


class ApplicationStatusItem(BaseModel):
    """화면 내 지원 현황의 카드 한 장 (APP-012, APP-017)"""

    posting_id: int
    position_name: str | None
    # '임시 저장'(작성 중)/'제출'
    write_status: str
    submitted_at: datetime | None
    # 카드 위쪽 배지: 작성 중, 서류 전형 진행 중, 면접 전형 예정, 면접 전형 진행 중, 면접 결과 대기, 면접 전형 완료, 전형 종료
    status: str
    doc_end_at: datetime | None
    doc_result_at: datetime | None
    interview_start_at: datetime | None
    interview_end_at: datetime | None
    interview_result_at: datetime | None
    # '합격'/'불합격'. 발표 일시 전이거나 아직 결과가 없으면 None (필수 기술 미달은 '불합격'으로 보여 준다)
    doc_result: str | None
    interview_result: str | None
    # 면접을 끝까지 응시했는지
    interview_taken: bool
    # 서류 합격이고 면접 마감 전이면 AI 면접 안내를 볼 수 있다
    can_view_interview_guide: bool
