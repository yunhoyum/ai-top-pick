"""RAG 설계 반영: doc_chunk 원본을 프로젝트 문서로 한정, 근거 원본에 직무 설명 추가, 답변별 점수 컬럼

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_SOURCE_TYPES = "'기능적 인재상', '비기능적 인재상', '프로젝트 문서'"
NEW_EVIDENCE_SOURCE_TYPES = "'기능적 인재상', '비기능적 인재상', '직무 설명', '프로젝트 문서'"
SCORE_COLUMNS = ('content_score', 'speech_score', 'expression_score')


def upgrade() -> None:
    """Upgrade schema."""
    # doc_chunk: 프로젝트 문서만 남긴다 (벡터 DB 설계서 2.1, 2.3).
    # 인재상 청크와 원본 문서가 이미 지워진 청크는 쓸 곳이 없다. 임베딩 작업을 다시 돌리면 다시 만들어진다
    op.execute(
        "DELETE FROM doc_chunk"
        " WHERE source_type <> '프로젝트 문서'"
        " OR source_id IS NULL"
        " OR source_id NOT IN (SELECT document_id FROM posting_document)"
    )
    op.drop_constraint(op.f('ck_doc_chunk_source_type_valid'), 'doc_chunk', type_='check')
    op.create_check_constraint(
        op.f('ck_doc_chunk_source_type_valid'), 'doc_chunk', "source_type IN ('프로젝트 문서')"
    )
    op.alter_column('doc_chunk', 'source_id', existing_type=sa.BigInteger(), nullable=False)
    op.create_foreign_key(
        op.f('fk_doc_chunk_source_id_posting_document'),
        'doc_chunk', 'posting_document', ['source_id'], ['document_id'], ondelete='CASCADE',
    )

    # evidence_sentence: 직무 설명 근거를 허용한다 (벡터 DB 설계서 2.3)
    op.drop_constraint(
        op.f('ck_evidence_sentence_source_type_valid'), 'evidence_sentence', type_='check'
    )
    op.create_check_constraint(
        op.f('ck_evidence_sentence_source_type_valid'), 'evidence_sentence',
        f"source_type IN ({NEW_EVIDENCE_SOURCE_TYPES})",
    )

    # interview_answer: 답변별 점수와 내용 점수 이유 (루브릭 설계서 3.6, 4.2, 5.3)
    for column in SCORE_COLUMNS:
        op.add_column('interview_answer', sa.Column(column, sa.Numeric(precision=5, scale=2), nullable=True))
        op.create_check_constraint(
            op.f(f'ck_interview_answer_{column}_range'), 'interview_answer',
            f'{column} BETWEEN 0 AND 100',
        )
    op.add_column('interview_answer', sa.Column('content_reason', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema. upgrade에서 지운 doc_chunk 행은 되돌리지 않는다."""
    op.drop_column('interview_answer', 'content_reason')
    for column in reversed(SCORE_COLUMNS):
        op.drop_constraint(op.f(f'ck_interview_answer_{column}_range'), 'interview_answer', type_='check')
        op.drop_column('interview_answer', column)

    op.execute("DELETE FROM evidence_sentence WHERE source_type = '직무 설명'")
    op.drop_constraint(
        op.f('ck_evidence_sentence_source_type_valid'), 'evidence_sentence', type_='check'
    )
    op.create_check_constraint(
        op.f('ck_evidence_sentence_source_type_valid'), 'evidence_sentence',
        f"source_type IN ({OLD_SOURCE_TYPES})",
    )

    op.drop_constraint(op.f('fk_doc_chunk_source_id_posting_document'), 'doc_chunk', type_='foreignkey')
    op.alter_column('doc_chunk', 'source_id', existing_type=sa.BigInteger(), nullable=True)
    op.drop_constraint(op.f('ck_doc_chunk_source_type_valid'), 'doc_chunk', type_='check')
    op.create_check_constraint(
        op.f('ck_doc_chunk_source_type_valid'), 'doc_chunk', f"source_type IN ({OLD_SOURCE_TYPES})"
    )
