"""문의 처리 상태 컬럼과 관리자 처리 후속 조치 (테이블 명세서 inquiry, 실시간 면접 5단계)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-16

명세서에 있는데 0001에서 빠진 inquiry.handling_status, handled_at, ai_attempt_count를 더한다.
judgment_type.follow_up에 '중단 후 관리자 처리, 재시험'을 더하고, 미해결·시스템 측과 미해결·판단 불가 행을 그 값으로 바꾼다
(코드베이스 2. Celery 8장 judgment_type 표, SYS-003).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

HANDLING = "'AI 처리', 'AI 미처리', '관리자 대기', '관리자 처리 완료'"
OLD_FOLLOW_UP = "'질문 다시 제시 후 재개', '기존 질문 그대로 진행', '중단 후 재시험'"
NEW_FOLLOW_UP = OLD_FOLLOW_UP + ", '중단 후 관리자 처리, 재시험'"
ADMIN_CODES = "('UNRESOLVED_SYSTEM', 'UNRESOLVED_UNKNOWN')"


def upgrade() -> None:
    op.add_column('inquiry', sa.Column('handling_status', sa.String(length=255), nullable=True))
    op.add_column('inquiry', sa.Column('handled_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('inquiry', sa.Column('ai_attempt_count', sa.Integer(), server_default='0', nullable=False))
    op.create_check_constraint(op.f('ck_inquiry_handling_status_valid'), 'inquiry', f"handling_status IN ({HANDLING})")
    op.drop_constraint(op.f('ck_judgment_type_follow_up_valid'), 'judgment_type', type_='check')
    op.create_check_constraint(op.f('ck_judgment_type_follow_up_valid'), 'judgment_type', f"follow_up IN ({NEW_FOLLOW_UP})")
    op.execute(f"UPDATE judgment_type SET follow_up = '중단 후 관리자 처리, 재시험' WHERE judgment_code IN {ADMIN_CODES}")


def downgrade() -> None:
    op.execute(f"UPDATE judgment_type SET follow_up = '중단 후 재시험' WHERE judgment_code IN {ADMIN_CODES}")
    op.drop_constraint(op.f('ck_judgment_type_follow_up_valid'), 'judgment_type', type_='check')
    op.create_check_constraint(op.f('ck_judgment_type_follow_up_valid'), 'judgment_type', f"follow_up IN ({OLD_FOLLOW_UP})")
    op.drop_constraint(op.f('ck_inquiry_handling_status_valid'), 'inquiry', type_='check')
    op.drop_column('inquiry', 'ai_attempt_count')
    op.drop_column('inquiry', 'handled_at')
    op.drop_column('inquiry', 'handling_status')
