// main-api 응답 타입 (공고)
export type PostingDocument = {
  document_id: number;
  file_name: string;
  file_size: number | null;
  upload_status: string | null;
};

export type PostingDetail = {
  posting_id: number;
  write_status: "임시 저장" | "등록 완료";
  progress_status: string | null;
  position_name: string | null;
  job_category: string | null;
  employment_type: "정규직" | "계약직" | null;
  job_description: string | null;
  doc_start_at: string | null;
  doc_end_at: string | null;
  doc_result_at: string | null;
  interview_start_at: string | null;
  interview_end_at: string | null;
  interview_result_at: string | null;
  functional_talent: string | null;
  nonfunctional_talent: string | null;
  documents: PostingDocument[];
};

// 화면 05 서류 작성 문항
export type BasicItem = {
  item_id: number;
  item_name: string;
  is_required: boolean;
  selected: boolean;
};

export type RequiredSkill = {
  skill_name: string;
  // 이 점수 이하면 탈락. null이면 탈락 기준 없음
  cutoff_score: number | null;
};

export type DocItems = {
  basic_items: BasicItem[];
  skills: RequiredSkill[];
  essay_topics: string[];
};

// 화면 06 서류 평가기준
export type EvalCriterion = {
  criteria_id: number;
  criteria_name: string;
  description: string | null;
  // 아직 입력하지 않았으면 null
  ratio: number | null;
};

export type DocCriteria = {
  criteria: EvalCriterion[];
};

// 화면 07 면접 평가기준
export type InterviewCriteria = {
  criteria: EvalCriterion[];
  question_count: number | null;
  // 사용 true, 사용 안 함 false, 아직 고르지 않음 null
  follow_up_enabled: boolean | null;
  think_time_sec: number | null;
  answer_time_sec: number | null;
};

// 화면 08 기업 질문
export type CompanyQuestions = {
  questions: string[];
  // AI 질문 중 직무 질문 비율(%). 아직 정하지 않았으면 null
  job_question_ratio: number | null;
  // 화면 07에서 정한 출제 문제 개수. 아직 입력하지 않았으면 null
  question_count: number | null;
};

// 화면 09 최종 검토
export type ReviewStep = "info" | "doc-items" | "doc-criteria" | "interview-criteria" | "company-questions";

export type Review = {
  posting: PostingDetail;
  doc_items: DocItems;
  doc_criteria: DocCriteria;
  interview_criteria: InterviewCriteria;
  company_questions: CompanyQuestions;
  // 아직 완료하지 못한 단계
  incomplete_steps: ReviewStep[];
};

// 화면 10 채용공고 목록
// 지원자 화면의 채용공고 목록 한 줄 (지원자 수는 공개하지 않는다)
export type PublicPostingItem = Omit<PostingListItem, "applicant_count">;

export type PostingListItem = {
  posting_id: number;
  position_name: string | null;
  employment_type: "정규직" | "계약직" | null;
  progress_status: string | null;
  doc_start_at: string | null;
  doc_end_at: string | null;
  // 제출 완료된 지원서 수
  applicant_count: number;
};

// 이어서 작성할 임시 저장 공고
export type Draft = {
  posting_id: number;
  position_name: string | null;
  // 이어서 열 단계의 주소 이름 (info, doc-items, ..., review)
  resume_step: string;
};

// 화면 11 전형별 지원자 수
export type PostingStats = {
  submitted_count: number;
  interview_target_count: number;
  interview_done_count: number;
  // 서류 제출 때 필수 기술 기준에 걸려 바로 탈락한 지원서 수
  skill_shortfall_count: number;
  // 면접 중 문의에서 AI가 처리하지 못한 건수
  ai_unhandled_error_count: number;
};

// 지원자 화면의 채용공고 상세: 기본 정보와 전형 일정만
export type PublicPostingDetail = {
  posting_id: number;
  position_name: string | null;
  job_category: string | null;
  employment_type: string | null;
  job_description: string | null;
  progress_status: string | null;
  doc_start_at: string | null;
  doc_end_at: string | null;
  doc_result_at: string | null;
  interview_start_at: string | null;
  interview_end_at: string | null;
  interview_result_at: string | null;
};
