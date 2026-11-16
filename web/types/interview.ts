// AI 화상 면접 (화면 22~25). main-api 응답과 면접 WebSocket 메시지 (내부 API 규약 1장)

export type InterviewGuide = {
  application_id: number;
  position_name: string | null;
  question_count: number;
  think_time_sec: number;
  answer_time_sec: number;
  interview_start_at: string | null;
  interview_end_at: string | null;
  interview_result_at: string | null;
  // 기술적 테스트(23)로 넘어갈 수 있는지. 아니면 reason에 이유가 있다
  can_enter: boolean;
  reason: string | null;
};

export type InterviewSessionOut = {
  session_id: number;
  status: string;
  resumed: boolean;
};

// 서버 → 브라우저 (규약 1.2). 질문 음성(wav)은 question 바로 다음에 바이너리로 온다
export type ServerMessage =
  | { type: "connected"; session_id: number }
  | { type: "question"; question_id: number; seq: number; total: number; text: string; think_sec: number; answer_sec: number }
  | { type: "phase"; phase: "think" | "answer"; ends_at: string }
  // 답변 음성 인식 결과 (Deepgram). is_final이 거짓이면 중간 결과라 바뀔 수 있다
  | { type: "transcript"; text: string; is_final: boolean }
  | { type: "answer_end"; question_id: number; reason: "button" | "silence" | "timeout" }
  | { type: "evaluating"; question_id: number }
  | { type: "interview_end"; answered_count: number; ended_at: string }
  // 기술 문의 (5단계). inquiry_reply의 check: system이면 브라우저가 장치를 다시 검사해 보내고, applicant면 지원자에게 묻는다
  // inquiry_id가 없는 inquiry_reply는 안내만 한다(답변 평가 중이라 받아 둠, 면접이 끝남)
  | { type: "inquiry_opened"; inquiry_id: number }
  | { type: "inquiry_reply"; inquiry_id: number | null; text: string; check: "system" | "applicant" | null }
  | { type: "inquiry_result"; inquiry_id: number; resolved: boolean; cause: string; follow_up: string }
  | { type: "suspended"; message: string; needs_admin: boolean }
  | { type: "error"; code: string; message: string };
