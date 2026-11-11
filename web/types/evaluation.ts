// main-api 서류 전형 평가 응답 (app/schemas/evaluation.py). Decimal은 문자열로 온다

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
  // '완료'면 보고서가 있다. 그 밖에는 서류 보고서 작업 상태(대기, 실행 중, 실패) 또는 '없음'
  report_status: string;
};

export type Ranking = {
  posting_id: number;
  position_name: string | null;
  doc_end_at: string | null;
  criteria: CriteriaRatio[];
  confirmed: boolean;
  summary: { target_count: number; shortfall_count: number; average: string | null; opinion_count: number };
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
};

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
