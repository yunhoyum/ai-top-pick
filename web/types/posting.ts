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
