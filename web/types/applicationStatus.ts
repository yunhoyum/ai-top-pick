// 내 지원 현황의 카드 한 장 (APP-012, APP-017)
export type ApplicationStatusItem = {
  posting_id: number;
  position_name: string | null;
  write_status: "임시 저장" | "제출";
  submitted_at: string | null;
  // 작성 중, 서류 전형 진행 중, 면접 전형 예정, 면접 전형 진행 중, 면접 결과 대기, 면접 전형 완료, 전형 종료
  status: string;
  doc_end_at: string | null;
  doc_result_at: string | null;
  interview_start_at: string | null;
  interview_end_at: string | null;
  interview_result_at: string | null;
  // 발표 전이거나 아직 결과가 없으면 null
  doc_result: "합격" | "불합격" | null;
  interview_result: "합격" | "불합격" | null;
  interview_taken: boolean;
  can_view_interview_guide: boolean;
};
