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
