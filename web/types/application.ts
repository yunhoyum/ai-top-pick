// 지원자 지원서 (APP-005~011). 기간은 'YYYY.MM ~ YYYY.MM', 재학·재직 중이면 'YYYY.MM ~'
export type Profile = { name: string | null; phone: string | null; email: string | null };

export type EducationRow = { school_name: string | null; major: string | null; period: string | null };
export type CareerRow = { company_name: string | null; job_role: string | null; period: string | null };
export type ProjectRow = { project_name: string | null; period: string | null; description: string | null };

export type SkillScore = {
  skill_name: string;
  // 공고의 필수 기술이면 true, 지원자가 직접 추가했으면 false
  required: boolean;
  score: number | null;
};

export type SkillCase = { skill_name: string | null; content: string | null };

export type ApplicationData = {
  posting: {
    posting_id: number;
    position_name: string | null;
    progress_status: string | null;
    doc_end_at: string | null;
    doc_result_at: string | null;
  };
  form: {
    has_education: boolean;
    has_career: boolean;
    has_project: boolean;
    essay_topics: { topic_id: number; topic_name: string }[];
  };
  // 관리자가 지원자 화면을 미리 보는 경우. 저장할 수 없다
  preview: boolean;
  write_status: "임시 저장" | "제출" | null;
  submitted_at: string | null;
  profile: Profile;
  educations: EducationRow[];
  careers: CareerRow[];
  projects: ProjectRow[];
  skills: SkillScore[];
  cases: SkillCase[];
  essays: { topic_id: number; content: string | null }[];
  portfolio: { file_name: string; file_size: number | null } | null;
};
