// main-api 전형 평가 응답 (app/schemas/evaluation.py). Decimal은 문자열로 온다. 서류·면접이 같은 모양이다

export type CriteriaRatio = { criteria_id: number; name: string; ratio: number };

export type RankingRow = {
  application_id: number;
  rank: number | null;
  applicant_name: string | null;
  total: string | null;
  scores: { criteria_id: number; weighted: string }[];
  has_opinion: boolean;
  opinion: string | null;
  // 서류 전형 결과 (합격, 불합격). 합격자를 확정하기 전에는 null
  result: string | null;
  // '완료'면 보고서가 있다. 그 밖에는 보고서 작업 상태(대기, 실행 중, 실패), '없음', 면접은 '미응시'
  report_status: string;
  follow_up_count?: number | null; // 면접만
};

export type Ranking = {
  posting_id: number;
  position_name: string | null;
  doc_end_at: string | null;
  interview_end_at?: string | null;
  criteria: CriteriaRatio[];
  confirmed: boolean;
  summary: {
    target_count: number;
    shortfall_count: number;
    taken_count?: number | null; // 면접만. 응시 완료
    average: string | null;
    opinion_count: number;
  };
  rows: RankingRow[];
};

export type ReportPoint = { criteria_name: string | null; content: string };

export type DocumentReport = {
  application_id: number;
  posting_id: number;
  applicant_name: string | null;
  position_name: string | null;
  doc_end_at: string | null;
  total: string;
  rank: number;
  ranked_count: number;
  summary: string | null;
  scores: { criteria_id: number; name: string; ratio: number; score: string; weighted: string; evidence: string }[];
  fits: { talent_content: string; kind: "기능적" | "비기능적" | null; evidence: string; found: boolean }[];
  strengths: ReportPoint[];
  checks: ReportPoint[];
  opinion: string | null;
  interview_end_at?: string | null;
  // 면접만: 질문별 결과 (화면 28)와 꼬리질문 횟수
  questions?: { seq: number; question_id: number; text: string; kind: QuestionKind; main_expression: string | null; answer_id: number }[];
  follow_up_count?: number | null;
};

export type QuestionKind = "AI" | "꼬리" | "기업";

// 화면 19 지원자 자료 원본 (ADM-022)
export type SourceDocuments = {
  application_id: number;
  posting_id: number;
  position_name: string | null;
  doc_end_at: string | null;
  name: string | null;
  phone: string | null;
  email: string | null;
  educations: { school_name: string | null; major: string | null; period: string | null }[];
  careers: { company_name: string | null; job_role: string | null; period: string | null }[];
  projects: { project_name: string | null; period: string | null; description: string | null }[];
  skills: { skill_name: string; score: number | null }[];
  cases: { skill_name: string | null; content: string | null }[];
  essays: { topic: string; content: string | null }[];
  portfolio: { file_name: string; file_size: number | null } | null;
};

// 화면 29 지원자 자료 원본 (면접, ADM-028)
export type InterviewSource = {
  application_id: number;
  posting_id: number;
  position_name: string | null;
  interview_end_at: string | null;
  name: string | null;
  questions: {
    seq: number;
    question_id: number;
    text: string;
    kind: QuestionKind;
    answer_id: number;
    duration_sec: number | null;
    has_video: boolean;
    stt: { time_offset_sec: number | null; corrected_text: string | null; raw_text: string | null }[];
  }[];
};
