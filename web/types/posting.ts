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
