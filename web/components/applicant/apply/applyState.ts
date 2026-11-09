import type { ApplicationData } from "@/types/application";

// 지원서 입력 중인 값. 서버 응답의 null은 빈 문자열로 바꿔 입력칸에 바로 연결한다
export type EducationInput = { school_name: string; major: string; period: string };
export type CareerInput = { company_name: string; job_role: string; period: string };
export type ProjectInput = { project_name: string; period: string; description: string };
export type SkillInput = { name: string; required: boolean; score: number | null };
export type CaseInput = { skill: string; content: string };

export type FormState = {
  profile: { name: string; phone: string; email: string };
  educations: EducationInput[];
  careers: CareerInput[];
  projects: ProjectInput[];
  skills: SkillInput[];
  cases: CaseInput[];
  essays: Record<number, string>;
};

export const STEPS = ["이력서", "사용기술·적용 사례", "자기소개서", "포트폴리오"];

export const emptyEducation = (): EducationInput => ({ school_name: "", major: "", period: "" });
export const emptyCareer = (): CareerInput => ({ company_name: "", job_role: "", period: "" });
export const emptyProject = (): ProjectInput => ({ project_name: "", period: "", description: "" });

// 항목을 쓰는 공고는 빈 줄 하나를 먼저 보여준다
const rowsOrBlank = <T,>(rows: T[], enabled: boolean, blank: () => T): T[] =>
  enabled && rows.length === 0 ? [blank()] : rows;

export function toFormState(a: ApplicationData): FormState {
  return {
    profile: { name: a.profile.name ?? "", phone: a.profile.phone ?? "", email: a.profile.email ?? "" },
    educations: rowsOrBlank(
      a.educations.map((r) => ({ school_name: r.school_name ?? "", major: r.major ?? "", period: r.period ?? "" })),
      a.form.has_education,
      emptyEducation,
    ),
    careers: rowsOrBlank(
      a.careers.map((r) => ({ company_name: r.company_name ?? "", job_role: r.job_role ?? "", period: r.period ?? "" })),
      a.form.has_career,
      emptyCareer,
    ),
    projects: rowsOrBlank(
      a.projects.map((r) => ({ project_name: r.project_name ?? "", period: r.period ?? "", description: r.description ?? "" })),
      a.form.has_project,
      emptyProject,
    ),
    skills: a.skills.map((s) => ({ name: s.skill_name, required: s.required, score: s.score })),
    cases: a.cases.length
      ? a.cases.map((c) => ({ skill: c.skill_name ?? "", content: c.content ?? "" }))
      : [{ skill: "", content: "" }],
    essays: Object.fromEntries(a.form.essay_topics.map((t) => [t.topic_id, a.essays.find((e) => e.topic_id === t.topic_id)?.content ?? ""])),
  };
}

// ---------- 서버로 보내는 값 ----------
export const resumeBody = (s: FormState) => ({
  profile: s.profile,
  educations: s.educations,
  careers: s.careers,
  projects: s.projects,
});

export const skillsBody = (s: FormState) => ({
  skills: s.skills.map((k) => ({ skill_name: k.name, score: k.score })),
  cases: s.cases.map((c) => ({ skill_name: c.skill || null, content: c.content })),
});

export const essaysBody = (s: FormState) => ({
  essays: Object.entries(s.essays).map(([id, content]) => ({ topic_id: Number(id), content })),
});

// ---------- 입력 검사 (서버도 같은 기준으로 다시 검사한다) ----------
const PERIOD = /^(\d{4})\.(0[1-9]|1[0-2])\s*~\s*(?:(\d{4})\.(0[1-9]|1[0-2]))?$/;
const PHONE = /^0\d{1,2}-?\d{3,4}-?\d{4}$/;
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const PERIOD_FORMAT = "2020.03 ~ 2026.02 형식으로 입력해 주세요. 진행 중이면 종료를 비워 두세요.";

// 빈 칸이면 null, 올바르면 null, 아니면 오류 문구
export function periodError(text: string): string | null {
  const t = text.trim();
  if (!t) return null;
  const m = PERIOD.exec(t);
  if (!m) return PERIOD_FORMAT;
  const [, ys, ms, ye, me] = m;
  if (ye && `${ye}${me}` < `${ys}${ms}`) return "종료가 시작보다 빠를 수 없습니다.";
  return null;
}

const blank = (...v: string[]) => v.every((x) => !x.trim());

// 단계별 오류. 키는 입력칸 이름(예: 'edu.0.school_name')
export function validateStep(step: number, s: FormState, topics: { topic_id: number }[]): Record<string, string> {
  const e: Record<string, string> = {};
  if (step === 0) {
    const { name, phone, email } = s.profile;
    if (!name.trim()) e.name = "이름을 입력해 주세요.";
    if (!phone.trim()) e.phone = "연락처를 입력해 주세요.";
    else if (!PHONE.test(phone.trim())) e.phone = "010-0000-0000 형식으로 입력해 주세요.";
    if (!email.trim()) e.email = "이메일을 입력해 주세요.";
    else if (!EMAIL.test(email.trim())) e.email = "올바른 이메일 형식이 아닙니다.";
    s.educations.forEach((r, i) => {
      if (blank(r.school_name, r.major, r.period)) return;
      if (!r.school_name.trim()) e[`edu.${i}.school_name`] = "학교명을 입력해 주세요.";
      const p = periodError(r.period);
      if (p) e[`edu.${i}.period`] = p;
    });
    s.careers.forEach((r, i) => {
      if (blank(r.company_name, r.job_role, r.period)) return;
      if (!r.company_name.trim()) e[`career.${i}.company_name`] = "회사명을 입력해 주세요.";
      const p = periodError(r.period);
      if (p) e[`career.${i}.period`] = p;
    });
    s.projects.forEach((r, i) => {
      if (blank(r.project_name, r.period, r.description)) return;
      if (!r.project_name.trim()) e[`project.${i}.project_name`] = "프로젝트명을 입력해 주세요.";
      const p = periodError(r.period);
      if (p) e[`project.${i}.period`] = p;
    });
  } else if (step === 1) {
    s.skills.forEach((k) => {
      if (k.required && k.score === null) e[`skill.${k.name}`] = "점수를 선택해 주세요.";
    });
    const filled = s.cases.filter((c) => c.skill || c.content.trim());
    s.cases.forEach((c, i) => {
      if (!c.skill && !c.content.trim()) return;
      if (!c.skill) e[`case.${i}.skill`] = "적용 기술을 선택해 주세요.";
      if (!c.content.trim()) e[`case.${i}.content`] = "내용을 입력해 주세요.";
    });
    if (filled.length === 0) e["case.0.content"] = "기술 적용 사례를 1건 이상 작성해 주세요.";
  } else if (step === 2) {
    topics.forEach((t) => {
      if (!(s.essays[t.topic_id] ?? "").trim()) e[`essay.${t.topic_id}`] = "내용을 입력해 주세요.";
    });
  }
  return e;
}

// 제출 전 확인: 단계를 모두 채웠는지 (포트폴리오는 파일이 있어야 한다)
export const stepDone = (step: number, s: FormState, topics: { topic_id: number }[], hasPortfolio: boolean) =>
  step === 3 ? hasPortfolio : Object.keys(validateStep(step, s, topics)).length === 0;
