import os

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ErrorCode
from app.domain.enums import StageType, UploadStatus
from app.domain.rules import can_edit_posting, resume_description, validate_schedule
from app.models.member import Member
from app.models.posting import JobPosting, PostingDocument
from app.repositories.doc_item_repo import DocItemRepo
from app.repositories.eval_ratio_repo import EvalRatioRepo
from app.repositories.posting_repo import PostingRepo
from app.schemas.doc_criteria import CriteriaOut, DocCriteriaIn, DocCriteriaOut
from app.schemas.doc_items import BasicItemOut, DocItemsIn, DocItemsOut, SkillOut
from app.schemas.posting import PostingDetail, PostingInfoIn
from app.services import file_service

# 임시 저장이 아닌 '다음'에서 반드시 입력해야 하는 항목 (ADM-004)
_REQUIRED = {
    "position_name": "포지션명",
    "job_category": "직무 분류",
    "employment_type": "고용 형태",
    "job_description": "직무 설명",
    "doc_start_at": "서류 접수 시작",
    "doc_end_at": "서류 접수 마감",
    "doc_result_at": "서류 합격자 발표 일시",
    "interview_start_at": "면접 시작",
    "interview_end_at": "면접 마감",
    "interview_result_at": "면접 합격자 발표 일시",
    "functional_talent": "기능적 인재상",
    "nonfunctional_talent": "비기능적 인재상",
}


class PostingService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.postings = PostingRepo(db)
        self.doc_items = DocItemRepo(db)
        self.eval_ratios = EvalRatioRepo(db)

    async def create_draft(self, admin: Member) -> int:
        """ADM-004, ADM-011 공고 행을 만든다. 작성 상태 '임시 저장', 진행 상태 '모집 전'"""
        posting = await self.postings.create(admin.member_id)
        await self.db.commit()
        return posting.posting_id

    async def get_detail(self, admin: Member, posting_id: int) -> PostingDetail:
        """ADM-013 공고 정보와 첨부 문서 조회 (지금은 화면 04에 필요한 부분만)"""
        posting = await self._get_owned(admin, posting_id)
        return await self._detail(posting)

    async def save_info(
        self, admin: Member, posting_id: int, req: PostingInfoIn, validate: bool
    ) -> PostingDetail:
        """ADM-004, ADM-011 기본 정보, 일정, 인재상 저장.
        validate=True면 필수 항목을 검사한다. 일정 순서는 DB 제약이 있어 임시 저장에도 항상 검사한다."""
        posting = await self._get_owned(admin, posting_id)
        self._ensure_editable(posting)

        if validate:
            missing = [label for key, label in _REQUIRED.items() if getattr(req, key) is None]
            if missing:
                raise AppError(
                    422, ErrorCode.POSTING_INVALID, "필수 항목을 입력해 주세요: " + ", ".join(missing)
                )
        schedule_errors = validate_schedule(req)
        if schedule_errors:
            raise AppError(422, ErrorCode.POSTING_INVALID, " ".join(schedule_errors))

        for key in PostingInfoIn.model_fields:
            value = getattr(req, key)
            setattr(posting, key, value.value if key == "employment_type" and value else value)
        await self.db.commit()
        return await self._detail(posting)

    async def add_document(self, admin: Member, posting_id: int, upload: UploadFile) -> PostingDocument:
        """ADM-005 프로젝트 문서(PDF) 등록. 여러 개 등록할 수 있다."""
        posting = await self._get_owned(admin, posting_id)
        self._ensure_editable(posting)
        data = await file_service.read_pdf(upload)

        document = await self.postings.add_document(
            PostingDocument(
                posting_id=posting_id,
                file_name=os.path.basename(upload.filename or "document.pdf")[:255],
                file_size=len(data),
                file_path="",
                upload_status=UploadStatus.DONE.value,
            )
        )
        # 파일 이름은 DB가 정한 document_id로 만든다 (사용자 파일명을 경로에 쓰지 않는다)
        document.file_path = f"postings/{posting_id}/documents/{document.document_id}.pdf"
        try:
            file_service.save(document.file_path, data)
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return document

    async def delete_document(self, admin: Member, posting_id: int, document_id: int) -> None:
        """ADM-015 프로젝트 문서 삭제. 행과 파일을 함께 지운다."""
        posting = await self._get_owned(admin, posting_id)
        self._ensure_editable(posting)
        document = await self.postings.get_document(posting_id, document_id)
        if document is None:
            raise AppError(404, ErrorCode.DOCUMENT_NOT_FOUND, "문서를 찾을 수 없습니다.")
        path = document.file_path
        await self.postings.delete_document(document)
        await self.db.commit()
        file_service.delete(path)

    async def get_doc_items(self, admin: Member, posting_id: int) -> DocItemsOut:
        """ADM-006, ADM-037 서류 작성 문항 조회. 기본 문항 전체 목록에 선택 여부를 붙여 돌려준다."""
        await self._get_owned(admin, posting_id)
        return await self._doc_items_out(posting_id)

    async def save_doc_items(
        self, admin: Member, posting_id: int, req: DocItemsIn, validate: bool
    ) -> DocItemsOut:
        """ADM-006, ADM-011 기본 문항, 필수 기술, 자소서 주제 저장. 있던 값은 보낸 값으로 모두 바뀐다.
        validate=True('다음')면 필수 기술과 자소서 주제가 각각 1개 이상이어야 한다."""
        posting = await self._get_owned(admin, posting_id)
        self._ensure_editable(posting)

        catalog = await self.doc_items.list_basic_items()
        known = {item.item_id for item in catalog}
        unknown = set(req.basic_item_ids) - known
        if unknown:
            raise AppError(422, ErrorCode.POSTING_INVALID, "알 수 없는 기본 문항입니다.")
        # 필수 문항은 관리자가 해제할 수 없으므로 항상 포함한다
        item_ids = sorted(set(req.basic_item_ids) | {i.item_id for i in catalog if i.is_required})

        skills = [(s.skill_name, s.cutoff_score) for s in req.skills if s.skill_name]
        names = [name.lower() for name, _ in skills]
        duplicated = sorted({name for name in names if names.count(name) > 1})
        if duplicated:
            raise AppError(
                422, ErrorCode.POSTING_INVALID, "같은 기술을 두 번 입력할 수 없습니다: " + ", ".join(duplicated)
            )
        topics = [t for t in req.essay_topics if t]

        if validate:
            missing = []
            if not skills:
                missing.append("필수 기술을 1개 이상 입력해 주세요.")
            if not topics:
                missing.append("자기소개서 주제를 1개 이상 입력해 주세요.")
            if missing:
                raise AppError(422, ErrorCode.POSTING_INVALID, " ".join(missing))

        await self.doc_items.replace_all(posting_id, item_ids, skills, topics)
        await self.db.commit()
        return await self._doc_items_out(posting_id)

    async def get_doc_criteria(self, admin: Member, posting_id: int) -> DocCriteriaOut:
        """ADM-007, ADM-038 서류 평가기준 조회"""
        await self._get_owned(admin, posting_id)
        return await self._doc_criteria_out(posting_id)

    async def save_doc_criteria(
        self, admin: Member, posting_id: int, req: DocCriteriaIn, validate: bool
    ) -> DocCriteriaOut:
        """ADM-007, ADM-011 서류 평가 항목별 비율 저장. 서류 항목의 비율만 바뀌고 면접 항목은 그대로다.
        합이 100을 넘으면 임시 저장도 할 수 없다. validate=True('다음')면 모든 항목을 입력해야 하고 합이 100이어야 한다."""
        posting = await self._get_owned(admin, posting_id)
        self._ensure_editable(posting)

        criteria_ids = [c.criteria_id for c in await self.eval_ratios.list_criteria(StageType.DOCUMENT.value)]
        sent = [r.criteria_id for r in req.ratios]
        if set(sent) - set(criteria_ids) or len(sent) != len(set(sent)):
            raise AppError(422, ErrorCode.POSTING_INVALID, "알 수 없거나 중복된 평가 항목입니다.")
        ratios = {r.criteria_id: r.ratio for r in req.ratios if r.ratio is not None}

        total = sum(ratios.values())
        if total > 100:
            raise AppError(
                422, ErrorCode.POSTING_INVALID, f"비율의 합은 100을 넘을 수 없습니다. 현재 {total}입니다."
            )
        if validate:
            if len(ratios) < len(criteria_ids):
                raise AppError(422, ErrorCode.POSTING_INVALID, "모든 항목의 비율을 입력해 주세요.")
            if total != 100:
                raise AppError(
                    422, ErrorCode.POSTING_INVALID, f"비율의 합은 100이어야 합니다. 현재 {total}입니다."
                )

        await self.eval_ratios.replace(posting_id, criteria_ids, ratios)
        await self.db.commit()
        return await self._doc_criteria_out(posting_id)

    async def _doc_criteria_out(self, posting_id: int) -> DocCriteriaOut:
        criteria = await self.eval_ratios.list_criteria(StageType.DOCUMENT.value)
        ratios = await self.eval_ratios.ratios(posting_id, [c.criteria_id for c in criteria])
        # 이력서 설명은 공고가 고른 기본 문항에 따라 달라진다 (ADM-007)
        selected = await self.doc_items.selected_item_ids(posting_id)
        names = [i.item_name for i in await self.doc_items.list_basic_items() if i.item_id in selected]
        return DocCriteriaOut(
            criteria=[
                CriteriaOut(
                    criteria_id=c.criteria_id,
                    criteria_name=c.criteria_name,
                    description=resume_description(names) if c.criteria_name == "이력서" else c.description,
                    ratio=ratios.get(c.criteria_id),
                )
                for c in criteria
            ]
        )

    async def _doc_items_out(self, posting_id: int) -> DocItemsOut:
        catalog = await self.doc_items.list_basic_items()
        selected = await self.doc_items.selected_item_ids(posting_id)
        return DocItemsOut(
            basic_items=[
                BasicItemOut(
                    item_id=i.item_id,
                    item_name=i.item_name,
                    is_required=i.is_required,
                    selected=i.is_required or i.item_id in selected,
                )
                for i in catalog
            ],
            skills=[
                SkillOut(skill_name=n, cutoff_score=c) for n, c in await self.doc_items.list_skills(posting_id)
            ],
            essay_topics=await self.doc_items.list_topics(posting_id),
        )

    async def _get_owned(self, admin: Member, posting_id: int) -> JobPosting:
        """본인 공고가 아니면 404 (다른 관리자의 공고가 있는지도 알리지 않는다)"""
        posting = await self.postings.get_owned(admin.member_id, posting_id)
        if posting is None:
            raise AppError(404, ErrorCode.POSTING_NOT_FOUND, "채용공고를 찾을 수 없습니다.")
        return posting

    @staticmethod
    def _ensure_editable(posting: JobPosting) -> None:
        if not can_edit_posting(posting):
            raise AppError(
                409, ErrorCode.POSTING_NOT_EDITABLE, "모집 전 공고만 수정할 수 있습니다."
            )

    async def _detail(self, posting: JobPosting) -> PostingDetail:
        fields = {k: getattr(posting, k) for k in PostingDetail.model_fields if k != "documents"}
        documents = await self.postings.list_documents(posting.posting_id)
        return PostingDetail.model_validate({**fields, "documents": documents})
