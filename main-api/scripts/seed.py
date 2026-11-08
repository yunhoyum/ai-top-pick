"""기준 데이터(코드 테이블) 입력 스크립트.

테이블 명세서의 basic_item, eval_criteria, judgment_type 값을 넣는다.
이미 있는 행은 건너뛰므로 여러 번 실행해도 된다(평가 항목 설명만 갱신한다).

실행 (main-api 폴더에서):  python -m scripts.seed
컨테이너 안에서:          docker compose exec main-api python -m scripts.seed
"""

from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.domain.enums import DefectCause, FollowUpAction, ItemName, JudgmentCode, StageType
from app.models.inquiry import JudgmentType
from app.models.posting import BasicItem, EvalCriteria

# 인적사항과 기술 적용 사례는 필수이며 관리자가 해제할 수 없다 (명세서 basic_item)
BASIC_ITEMS = [
    {"item_id": 1, "item_name": ItemName.PROFILE.value, "is_required": True},
    {"item_id": 2, "item_name": ItemName.EDUCATION.value, "is_required": False},
    {"item_id": 3, "item_name": ItemName.CAREER.value, "is_required": False},
    {"item_id": 4, "item_name": ItemName.PROJECT.value, "is_required": False},
    {"item_id": 5, "item_name": ItemName.SKILL_CASE.value, "is_required": True},
]

# 서류 4개, 면접 3개. 이력서 설명은 공고가 고른 기본 문항에 따라 달라져 서버가 만들어 보여 준다.
# 면접 항목 설명은 명세서에 값이 없어 비워 둔다
_D, _I = StageType.DOCUMENT.value, StageType.INTERVIEW.value
EVAL_CRITERIA = [
    {"criteria_id": 1, "stage_type": _D, "criteria_name": "이력서", "description": None},
    {"criteria_id": 2, "stage_type": _D, "criteria_name": "기술 적용 사례", "description": "기술을 실제로 적용한 경험"},
    {"criteria_id": 3, "stage_type": _D, "criteria_name": "포트폴리오", "description": "제출한 PDF 포트폴리오"},
    {"criteria_id": 4, "stage_type": _D, "criteria_name": "자기소개", "description": "자기소개서 주제별 답변"},
    {"criteria_id": 5, "stage_type": _I, "criteria_name": "내용", "description": None},
    {"criteria_id": 6, "stage_type": _I, "criteria_name": "언어", "description": None},
    {"criteria_id": 7, "stage_type": _I, "criteria_name": "비언어", "description": None},
]

# 해결 여부 x 결함 원인. ai_handled: 해결=true(문의 중 해결), 미해결=false
_RESUME = FollowUpAction.REPRESENT_AND_RESUME.value
_CONTINUE = FollowUpAction.CONTINUE_AS_IS.value
_RETAKE = FollowUpAction.ABORT_AND_RETAKE.value
JUDGMENT_TYPES = [
    (JudgmentCode.RESOLVED_SYSTEM, DefectCause.SYSTEM, True, _RESUME),
    (JudgmentCode.RESOLVED_APPLICANT, DefectCause.APPLICANT, True, _CONTINUE),
    (JudgmentCode.RESOLVED_UNKNOWN, DefectCause.UNKNOWN, True, _RESUME),
    (JudgmentCode.UNRESOLVED_SYSTEM, DefectCause.SYSTEM, False, _RETAKE),
    (JudgmentCode.UNRESOLVED_APPLICANT, DefectCause.APPLICANT, False, _RETAKE),
    (JudgmentCode.UNRESOLVED_UNKNOWN, DefectCause.UNKNOWN, False, _RETAKE),
]


def main() -> None:
    engine = create_engine(get_settings().sqlalchemy_url)
    judgment_rows = [
        {"judgment_code": code.value, "cause": cause.value, "ai_handled": handled, "follow_up": follow_up}
        for code, cause, handled, follow_up in JUDGMENT_TYPES
    ]
    with engine.begin() as conn:
        for model, rows in (
            (BasicItem, BASIC_ITEMS),
            (EvalCriteria, EVAL_CRITERIA),
            (JudgmentType, judgment_rows),
        ):
            stmt = insert(model).values(rows)
            if model is EvalCriteria:
                # 항목 설명 문구는 나중에 바뀔 수 있어 다시 실행하면 갱신한다
                stmt = stmt.on_conflict_do_update(
                    index_elements=["criteria_id"], set_={"description": stmt.excluded.description}
                )
            else:
                stmt = stmt.on_conflict_do_nothing()
            conn.execute(stmt)
            total = conn.scalar(select(func.count()).select_from(model))
            print(f"{model.__tablename__}: {total}건")


if __name__ == "__main__":
    main()
