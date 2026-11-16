// 문의·예외 처리 (화면 26·26-1). main-api /api/admin/inquiries 응답

export type HandlingStatus = "AI 미처리" | "관리자 대기" | "관리자 처리 완료" | "AI 처리";

export type InquiryItem = {
  inquiry_id: number;
  posting_id: number;
  position_name: string | null;
  application_id: number;
  applicant_name: string | null;
  question_text: string | null;
  started_at: string | null;
  ended_at: string | null;
  handling_status: HandlingStatus | null;
  cause: string | null;
  ai_attempt_count: number;
};

export type InquiryDetail = InquiryItem & {
  judgment_basis: string | null;
  ai_action: string | null;
  handling_detail: string | null;
  follow_up: string | null;
  handled_at: string | null;
  messages: { speaker: string | null; content: string | null }[];
  logs: { logged_at: string | null; content: string | null }[];
};
