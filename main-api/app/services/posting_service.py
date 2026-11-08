import os
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ErrorCode
from app.domain.enums import PostingWriteStatus, StageType, UploadStatus
from app.domain.rules import can_edit_posting, resume_description, validate_schedule
from app.models.member import Member
from app.models.posting import EvalCriteria, JobPosting, PostingDocument
from app.repositories.company_question_repo import CompanyQuestionRepo
from app.repositories.doc_item_repo import DocItemRepo
from app.repositories.eval_ratio_repo import EvalRatioRepo
from app.repositories.posting_repo import PostingRepo
from app.schemas.company_questions import CompanyQuestionsIn, CompanyQuestionsOut
from app.schemas.doc_criteria import CriteriaOut, DocCriteriaIn, DocCriteriaOut
from app.schemas.interview_criteria import InterviewCriteriaIn, InterviewCriteriaOut
from app.schemas.doc_items import BasicItemOut, DocItemsIn, DocItemsOut, SkillOut
from app.schemas.posting import PostingDetail, PostingInfoIn
from app.schemas.posting_list import DraftOut, PostingListItem
from app.schemas.review import PublishOut, ReviewOut
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


# 공고 등록 전에 완료해야 하는 단계 (화면 주소의 단계 이름 → 화면에 보이는 이름)
STEP_LABELS = {
    "info": "공고 정보",
    "doc-items": "서류 문항",
    "doc-criteria": "서류 평가기준",
    "interview-criteria": "면접 평가기준",
    "company-questions": "기업 질문",
}


def _missing_required(obj) -> list[str]:
    """필수 항목 중 비어 있는 것의 이름. 저장 요청(PostingInfoIn)과 저장된 공고(JobPosting) 모두 쓴다."""
    return [label for key, label in _REQUIRED.items() if getattr(obj, key) is None]


class PostingService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.postings = PostingRepo(db)
        self.doc_items = DocItemRepo(db)
        self.eval_ratios = EvalRatioRepo(db)
        self.company_questions = CompanyQuestionRepo(db)

    async def create_draft(self, admin: Member) -> int:
        """ADM-004, ADM-011 공고 행을 만든다. 작성 상태 '임시 저장', 진행 상태 '모집 전'"""
        posting = await self.postings.create(admin.member_id)
        await self.db.commit()
        return posting.posting_id

    async def list_postings(self, admin: Member) -> list[PostingListItem]:
        """ADM-012 본인이 등록한 채용공고 목록"""
        rows = await self.postings.list_registered(admin.member_id)
        return [
            PostingListItem(
                posting_id=p.posting_id,
                position_name=p.position_name,
                employment_type=p.employment_type,
                progress_status=p.progress_status,
                doc_start_at=p.doc_start_at,
                doc_end_at=p.doc_end_at,
                applicant_count=count,
            )
            for p, count in rows
        ]

    async def get_draft(self, admin: Member) -> DraftOut | None:
        """ADM-011 이어서 작성할 임시 저장 공고. 없으면 None"""
        posting = await self.postings.latest_draft(admin.member_id)
        if posting is None:
            return None
        incomplete = (await self._review(posting)).incomplete_steps
        return DraftOut(
            posting_id=posting.posting_id,
            position_name=posting.position_name,
            resume_step=incomplete[0] if incomplete else "review",
        )

    async def delete_posting(self, admin: Member, posting_id: int) -> None:
        """ADM-020 채용공고 삭제 ('모집 전' 공고만). 올린 문서 파일도 함께 지운다."""
        posting = await self._get_owned(admin, posting_id)
        self._ensure_editable(posting, "삭제")
        paths = [d.file_path for d in await self.postings.list_documents(posting_id)]
        await self.postings.delete_posting(posting)
        await self.db.commit()
        for path in paths:
            file_service.delete(path)

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
            missing = _missing_required(req)
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

        criteria, ratios, problems = await self._checked_ratios(StageType.DOCUMENT.value, req.ratios, validate)
        if problems:
            raise AppError(422, ErrorCode.POSTING_INVALID, " ".join(problems))

        criteria_ids = [c.criteria_id for c in criteria]
        await self.eval_ratios.replace(posting_id, criteria_ids, ratios)
        await self.db.commit()
        return await self._doc_criteria_out(posting_id)

    async def get_interview_criteria(self, admin: Member, posting_id: int) -> InterviewCriteriaOut:
        """ADM-008, ADM-039 면접 평가기준 조회"""
        posting = await self._get_owned(admin, posting_id)
        return await self._interview_criteria_out(posting)

    async def save_interview_criteria(
        self, admin: Member, posting_id: int, req: InterviewCriteriaIn, validate: bool
    ) -> InterviewCriteriaOut:
        """ADM-008, ADM-011 면접 평가 요소 비율과 진행 설정 저장. 면접 항목의 비율만 바뀌고 서류 항목은 그대로다.
        합이 100을 넘거나 비언어가 0%이거나 출제 문제 개수가 등록된 기업 질문 수보다 작으면 임시 저장도 할 수 없다.
        validate=True('다음')면 모든 값을 입력해야 하고 합이 100이어야 한다."""
        posting = await self._get_owned(admin, posting_id)
        self._ensure_editable(posting)

        criteria, ratios, problems = await self._checked_ratios(StageType.INTERVIEW.value, req.ratios, validate)
        # 비언어는 표정 분석이 실패했을 때만 빼고 계산하는 예외 규칙이 있어, 회사가 정하는 비율은 0%일 수 없다
        for c in criteria:
            if c.criteria_name == "비언어" and ratios.get(c.criteria_id) == 0:
                raise AppError(422, ErrorCode.POSTING_INVALID, "비언어 비율은 1% 이상이어야 합니다.")

        if req.question_count is not None:
            registered = await self.postings.count_company_questions(posting_id)
            if req.question_count < registered:
                raise AppError(
                    422,
                    ErrorCode.QUESTION_COUNT_TOO_LOW,
                    f"기업 질문이 {registered}개 등록되어 있어 출제 문제 개수를 {registered}개 미만으로 줄일 수 없습니다. "
                    "기업 질문을 먼저 줄여 주세요.",
                )

        if validate:
            labels = {
                "question_count": "출제 문제 개수",
                "follow_up_enabled": "꼬리질문",
                "think_time_sec": "생각 시간",
                "answer_time_sec": "답변 시간",
            }
            missing = [label for key, label in labels.items() if getattr(req, key) is None]
            if missing:
                problems.append("다음 항목을 입력해 주세요: " + ", ".join(missing) + ".")
        if problems:
            raise AppError(422, ErrorCode.POSTING_INVALID, " ".join(problems))

        await self.eval_ratios.replace(posting_id, [c.criteria_id for c in criteria], ratios)
        posting.question_count = req.question_count
        posting.follow_up_enabled = req.follow_up_enabled
        posting.think_time_sec = req.think_time_sec
        posting.answer_time_sec = req.answer_time_sec
        await self.db.commit()
        return await self._interview_criteria_out(posting)

    async def _checked_ratios(
        self, stage_type: str, sent: list, validate: bool
    ) -> tuple[list[EvalCriteria], dict[int, int], list[str]]:
        """전형(서류/면접)의 평가 항목 비율을 검사한다. 항목이 틀렸거나 합이 100을 넘으면 바로 거절하고,
        '다음'에서만 필요한 검사(모두 입력, 합 100)에 걸린 내용은 메시지 목록으로 돌려준다."""
        criteria = await self.eval_ratios.list_criteria(stage_type)
        ids = [c.criteria_id for c in criteria]
        sent_ids = [r.criteria_id for r in sent]
        if set(sent_ids) - set(ids) or len(sent_ids) != len(set(sent_ids)):
            raise AppError(422, ErrorCode.POSTING_INVALID, "알 수 없거나 중복된 평가 항목입니다.")
        ratios = {r.criteria_id: r.ratio for r in sent if r.ratio is not None}

        total = sum(ratios.values())
        if total > 100:
            raise AppError(
                422, ErrorCode.POSTING_INVALID, f"비율의 합은 100을 넘을 수 없습니다. 현재 {total}입니다."
            )
        problems = []
        if validate:
            if len(ratios) < len(ids):
                problems.append("모든 항목의 비율을 입력해 주세요.")
            elif total != 100:
                problems.append(f"비율의 합은 100이어야 합니다. 현재 {total}입니다.")
        return criteria, ratios, problems

    async def _interview_criteria_out(self, posting: JobPosting) -> InterviewCriteriaOut:
        criteria = await self.eval_ratios.list_criteria(StageType.INTERVIEW.value)
        ratios = await self.eval_ratios.ratios(posting.posting_id, [c.criteria_id for c in criteria])
        return InterviewCriteriaOut(
            criteria=[
                CriteriaOut(
                    criteria_id=c.criteria_id,
                    criteria_name=c.criteria_name,
                    description=c.description,
                    ratio=ratios.get(c.criteria_id),
                )
                for c in criteria
            ],
            question_count=posting.question_count,
            follow_up_enabled=posting.follow_up_enabled,
            think_time_sec=posting.think_time_sec,
            answer_time_sec=posting.answer_time_sec,
        )

    async def get_company_questions(self, admin: Member, posting_id: int) -> CompanyQuestionsOut:
        """ADM-009, ADM-040 기업 질문과 AI 질문 비율 조회"""
        posting = await self._get_owned(admin, posting_id)
        return await self._company_questions_out(posting)

    async def save_company_questions(
        self, admin: Member, posting_id: int, req: CompanyQuestionsIn, validate: bool
    ) -> CompanyQuestionsOut:
        """ADM-009, ADM-011, ADM-032 기업 질문 목록과 AI 질문 비율 저장. 있던 질문은 보낸 목록으로 모두 바뀐다.
        기업 질문은 0개도 된다. 출제 문제 개수를 넘으면 임시 저장도 할 수 없다.
        validate=True('다음')면 출제 문제 개수가 입력돼 있어야 하고, AI 질문이 있으면 비율을 정해야 한다."""
        posting = await self._get_owned(admin, posting_id)
        self._ensure_editable(posting)

        questions = [q for q in req.questions if q]
        count = posting.question_count
        if questions and count is None:
            raise AppError(422, ErrorCode.POSTING_INVALID, "면접 평가기준에서 출제 문제 개수를 먼저 입력해 주세요.")
        if count is not None and len(questions) > count:
            raise AppError(
                422,
                ErrorCode.POSTING_INVALID,
                f"기업 질문은 출제 문제 개수({count}개)를 넘길 수 없습니다. 현재 {len(questions)}개입니다.",
            )

        if validate:
            if count is None:
                raise AppError(422, ErrorCode.POSTING_INVALID, "면접 평가기준에서 출제 문제 개수를 먼저 입력해 주세요.")
            # AI 질문이 하나도 없으면(기업 질문 수 = 출제 문제 개수) 비율은 필요 없다
            if count - len(questions) > 0 and req.job_question_ratio is None:
                raise AppError(422, ErrorCode.POSTING_INVALID, "AI 질문의 직무/인성 비율을 설정해 주세요.")

        await self.company_questions.replace_all(posting_id, questions)
        posting.job_question_ratio = req.job_question_ratio
        await self.db.commit()
        return await self._company_questions_out(posting)

    async def get_review(self, admin: Member, posting_id: int) -> ReviewOut:
        """ADM-010 최종 검토 화면에 필요한 모든 단계의 내용과, 아직 완료하지 못한 단계"""
        posting = await self._get_owned(admin, posting_id)
        return await self._review(posting)

    async def publish(self, admin: Member, posting_id: int) -> PublishOut:
        """ADM-010 등록. 모든 단계가 완료됐는지 저장된 값으로 다시 확인하고 작성 상태를 '등록 완료'로 바꾼다.
        이미 등록된 공고는 같은 검사를 하고 그대로 둔다. 진행 상태('모집 전')는 서류 접수 시작 때 별도 작업이 바꾼다."""
        posting = await self._get_owned(admin, posting_id)
        self._ensure_editable(posting)

        incomplete = (await self._review(posting)).incomplete_steps
        if incomplete:
            labels = ", ".join(STEP_LABELS[step] for step in incomplete)
            raise AppError(422, ErrorCode.POSTING_INVALID, f"다음 단계를 완료해 주세요: {labels}.")

        posting.write_status = PostingWriteStatus.COMPLETE.value
        await self.db.commit()
        return PublishOut(posting_id=posting.posting_id, write_status=posting.write_status)

    async def get_document_file(self, admin: Member, posting_id: int, document_id: int) -> tuple[Path, str]:
        """ADM-010, ADM-036 프로젝트 문서(PDF) 보기. 본인 공고의 문서만 볼 수 있다."""
        await self._get_owned(admin, posting_id)
        document = await self.postings.get_document(posting_id, document_id)
        if document is None:
            raise AppError(404, ErrorCode.DOCUMENT_NOT_FOUND, "문서를 찾을 수 없습니다.")
        path = file_service.resolve(document.file_path)
        if not path.is_file():
            raise AppError(404, ErrorCode.DOCUMENT_NOT_FOUND, "문서 파일을 찾을 수 없습니다.")
        return path, document.file_name

    async def _review(self, posting: JobPosting) -> ReviewOut:
        detail = await self._detail(posting)
        doc_items = await self._doc_items_out(posting.posting_id)
        doc_criteria = await self._doc_criteria_out(posting.posting_id)
        interview = await self._interview_criteria_out(posting)
        company = await self._company_questions_out(posting)
        return ReviewOut(
            posting=detail,
            doc_items=doc_items,
            doc_criteria=doc_criteria,
            interview_criteria=interview,
            company_questions=company,
            incomplete_steps=self._incomplete_steps(posting, doc_items, doc_criteria, interview, company),
        )

    @staticmethod
    def _incomplete_steps(posting, doc_items, doc_criteria, interview, company) -> list[str]:
        """저장된 값만 보고 완료하지 못한 단계를 찾는다. 각 단계의 '다음' 검증과 같은 기준이다."""
        steps = []
        if _missing_required(posting) or validate_schedule(posting):
            steps.append("info")
        if not doc_items.skills or not doc_items.essay_topics:
            steps.append("doc-items")

        def ratios_ok(criteria) -> bool:
            values = [c.ratio for c in criteria]
            return None not in values and sum(values) == 100

        if not ratios_ok(doc_criteria.criteria):
            steps.append("doc-criteria")
        nonverbal_zero = any(c.criteria_name == "비언어" and c.ratio == 0 for c in interview.criteria)
        settings = (interview.question_count, interview.follow_up_enabled, interview.think_time_sec, interview.answer_time_sec)
        if not ratios_ok(interview.criteria) or nonverbal_zero or None in settings:
            steps.append("interview-criteria")

        count = interview.question_count
        asked = len(company.questions)
        if count is None or asked > count or (count - asked > 0 and company.job_question_ratio is None):
            steps.append("company-questions")
        return steps

    async def _company_questions_out(self, posting: JobPosting) -> CompanyQuestionsOut:
        return CompanyQuestionsOut(
            questions=await self.company_questions.list_contents(posting.posting_id),
            job_question_ratio=posting.job_question_ratio,
            question_count=posting.question_count,
        )

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
    def _ensure_editable(posting: JobPosting, action: str = "수정") -> None:
        if not can_edit_posting(posting):
            raise AppError(
                409, ErrorCode.POSTING_NOT_EDITABLE, f"모집 전 공고만 {action}할 수 있습니다."
            )

    async def _detail(self, posting: JobPosting) -> PostingDetail:
        fields = {k: getattr(posting, k) for k in PostingDetail.model_fields if k != "documents"}
        documents = await self.postings.list_documents(posting.posting_id)
        return PostingDetail.model_validate({**fields, "documents": documents})
