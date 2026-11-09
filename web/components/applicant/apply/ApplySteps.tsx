"use client";

import { useState } from "react";
import Badge from "@/components/common/Badge";
import Button from "@/components/common/Button";
import Field from "@/components/common/Field";
import SelectField from "@/components/common/SelectField";
import TextAreaField from "@/components/common/TextAreaField";
import styles from "./Apply.module.css";
import { emptyCareer, emptyEducation, emptyProject, type FormState } from "./applyState";

type StepProps = {
  state: FormState;
  setState: React.Dispatch<React.SetStateAction<FormState>>;
  errors: Record<string, string>;
};

const replaceAt = <T,>(rows: T[], i: number, patch: Partial<T>): T[] => rows.map((r, j) => (j === i ? { ...r, ...patch } : r));
const removeAt = <T,>(rows: T[], i: number): T[] => rows.filter((_, j) => j !== i);

function RemoveRow({ onClick, show }: { onClick: () => void; show: boolean }) {
  if (!show) return null;
  return (
    <div className={styles.rowTools}>
      <button type="button" className={styles.link} onClick={onClick}>
        삭제
      </button>
    </div>
  );
}

// 화면 12 이력서 (APP-005): 인적사항은 필수, 학력·경력·프로젝트는 공고가 받는 항목만 보인다
export function ResumeStep({
  state,
  setState,
  errors,
  has,
}: StepProps & { has: { education: boolean; career: boolean; project: boolean } }) {
  const profile = (key: "name" | "phone" | "email") => ({
    value: state.profile[key],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      setState((s) => ({ ...s, profile: { ...s.profile, [key]: e.target.value } })),
  });

  return (
    <>
      <section className={styles.card}>
        <h2 className={styles.cardTitle}>인적사항</h2>
        <div className={styles.grid}>
          <Field label="이름 *" name="name" placeholder="이름 입력" autoComplete="name" error={errors.name} {...profile("name")} />
          <Field label="연락처 *" name="phone" placeholder="010-0000-0000" autoComplete="tel" error={errors.phone} {...profile("phone")} />
          <Field label="이메일 *" name="email" type="email" placeholder="name@email.com" autoComplete="email" error={errors.email} {...profile("email")} />
        </div>
      </section>

      {has.education && (
        <section className={styles.card}>
          <h2 className={styles.cardTitle}>학력</h2>
          {state.educations.map((r, i) => (
            <div key={i} className={styles.row}>
              <div className={styles.grid}>
                <Field label="학교명" name={`edu-school-${i}`} placeholder="학교명 입력" value={r.school_name} error={errors[`edu.${i}.school_name`]}
                  onChange={(e) => setState((s) => ({ ...s, educations: replaceAt(s.educations, i, { school_name: e.target.value }) }))} />
                <Field label="전공" name={`edu-major-${i}`} placeholder="전공 입력" value={r.major}
                  onChange={(e) => setState((s) => ({ ...s, educations: replaceAt(s.educations, i, { major: e.target.value }) }))} />
                <Field label="기간" name={`edu-period-${i}`} placeholder="2020.03 ~ 2026.02" value={r.period} error={errors[`edu.${i}.period`]}
                  onChange={(e) => setState((s) => ({ ...s, educations: replaceAt(s.educations, i, { period: e.target.value }) }))} />
              </div>
              <RemoveRow show={state.educations.length > 1} onClick={() => setState((s) => ({ ...s, educations: removeAt(s.educations, i) }))} />
            </div>
          ))}
          <Button type="button" variant="secondary" inline className={styles.addButton} onClick={() => setState((s) => ({ ...s, educations: [...s.educations, emptyEducation()] }))}>
            + 학력 추가
          </Button>
        </section>
      )}

      {has.career && (
        <section className={styles.card}>
          <h2 className={styles.cardTitle}>경력</h2>
          {state.careers.map((r, i) => (
            <div key={i} className={styles.row}>
              <div className={styles.grid}>
                <Field label="회사명" name={`career-company-${i}`} placeholder="회사명 입력" value={r.company_name} error={errors[`career.${i}.company_name`]}
                  onChange={(e) => setState((s) => ({ ...s, careers: replaceAt(s.careers, i, { company_name: e.target.value }) }))} />
                <Field label="직무" name={`career-role-${i}`} placeholder="직무 입력" value={r.job_role}
                  onChange={(e) => setState((s) => ({ ...s, careers: replaceAt(s.careers, i, { job_role: e.target.value }) }))} />
                <Field label="기간" name={`career-period-${i}`} placeholder="2024.01 ~ 2025.06" value={r.period} error={errors[`career.${i}.period`]}
                  onChange={(e) => setState((s) => ({ ...s, careers: replaceAt(s.careers, i, { period: e.target.value }) }))} />
              </div>
              <RemoveRow show={state.careers.length > 1} onClick={() => setState((s) => ({ ...s, careers: removeAt(s.careers, i) }))} />
            </div>
          ))}
          <Button type="button" variant="secondary" inline className={styles.addButton} onClick={() => setState((s) => ({ ...s, careers: [...s.careers, emptyCareer()] }))}>
            + 경력 추가
          </Button>
        </section>
      )}

      {has.project && (
        <section className={styles.card}>
          <h2 className={styles.cardTitle}>프로젝트</h2>
          {state.projects.map((r, i) => (
            <div key={i} className={styles.row}>
              <div className={styles.grid}>
                <Field label="프로젝트명" name={`project-name-${i}`} placeholder="프로젝트명 입력" value={r.project_name} error={errors[`project.${i}.project_name`]}
                  onChange={(e) => setState((s) => ({ ...s, projects: replaceAt(s.projects, i, { project_name: e.target.value }) }))} />
                <Field label="기간" name={`project-period-${i}`} placeholder="2025.03 ~ 2025.06" value={r.period} error={errors[`project.${i}.period`]}
                  onChange={(e) => setState((s) => ({ ...s, projects: replaceAt(s.projects, i, { period: e.target.value }) }))} />
              </div>
              <TextAreaField label="설명" name={`project-desc-${i}`} placeholder="맡은 역할과 결과를 입력해 주세요" value={r.description}
                onChange={(e) => setState((s) => ({ ...s, projects: replaceAt(s.projects, i, { description: e.target.value }) }))} />
              <RemoveRow show={state.projects.length > 1} onClick={() => setState((s) => ({ ...s, projects: removeAt(s.projects, i) }))} />
            </div>
          ))}
          <Button type="button" variant="secondary" inline className={styles.addButton} onClick={() => setState((s) => ({ ...s, projects: [...s.projects, emptyProject()] }))}>
            + 프로젝트 추가
          </Button>
        </section>
      )}
    </>
  );
}

// 화면 13 사용기술(APP-006), 기술 적용 사례(APP-007)
export function SkillsStep({ state, setState, errors }: StepProps) {
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [addError, setAddError] = useState<string | null>(null);

  function addSkill() {
    const name = newName.trim();
    if (!name) return setAddError("기술 이름을 입력해 주세요.");
    if (state.skills.some((k) => k.name.toLowerCase() === name.toLowerCase())) return setAddError("이미 있는 기술입니다.");
    setState((s) => ({ ...s, skills: [...s.skills, { name, required: false, score: null }] }));
    setNewName("");
    setAddError(null);
    setAdding(false);
  }

  function removeSkill(name: string) {
    // 지운 기술을 쓰던 사례는 적용 기술을 다시 고르게 비운다
    setState((s) => ({
      ...s,
      skills: s.skills.filter((k) => k.name !== name),
      cases: s.cases.map((c) => (c.skill === name ? { ...c, skill: "" } : c)),
    }));
  }

  return (
    <>
      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>사용기술</h2>
          <p className={styles.cardDesc}>기술별 숙련도를 1~5점으로 선택해 주세요. 점수는 본인이 평가한 값(자기평가)으로 기록됩니다.</p>
        </div>
        <div>
          {state.skills.map((k) => (
            <div key={k.name} className={styles.skillRow}>
              <div className={styles.skillMain}>
                <span className={styles.skillName}>{k.name}</span>
                <Badge tone={k.required ? "navy" : "gray"}>{k.required ? "필수" : "직접 추가"}</Badge>
                {!k.required && (
                  <button type="button" className={styles.link} onClick={() => removeSkill(k.name)}>
                    삭제
                  </button>
                )}
                {errors[`skill.${k.name}`] && <span className={styles.skillError}>{errors[`skill.${k.name}`]}</span>}
              </div>
              <div className={styles.scale} role="group" aria-label={`${k.name} 점수`}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    type="button"
                    className={`${styles.scaleButton} ${k.score === n ? styles.scaleOn : ""}`}
                    aria-pressed={k.score === n}
                    onClick={() =>
                      setState((s) => ({ ...s, skills: s.skills.map((x) => (x.name === k.name ? { ...x, score: n } : x)) }))
                    }
                  >
                    {n}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
        {adding ? (
          <div className={styles.addSkill}>
            <div className={styles.addSkillInput}>
              <Field
                label="기술 이름"
                name="new-skill"
                placeholder="예: Docker"
                value={newName}
                error={addError ?? undefined}
                autoFocus
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addSkill();
                  }
                }}
              />
            </div>
            <div className={styles.addSkillButtons}>
              <Button type="button" inline onClick={addSkill}>
                추가
              </Button>
              <Button type="button" variant="secondary" inline onClick={() => { setAdding(false); setNewName(""); setAddError(null); }}>
                취소
              </Button>
            </div>
          </div>
        ) : (
          <div>
            <Button type="button" variant="secondary" inline onClick={() => setAdding(true)}>
              + 기술 추가
            </Button>
          </div>
        )}
      </section>

      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>기술 적용 사례</h2>
          <p className={styles.cardDesc}>기술을 실제로 적용한 경험을 작성해 주세요. 1건 이상 작성해야 합니다.</p>
        </div>
        {state.cases.map((c, i) => (
          <div key={i} className={styles.caseBox}>
            <div className={styles.caseHead}>
              <span className={styles.caseLabel}>사례 {i + 1}</span>
              {state.cases.length > 1 && (
                <button type="button" className={styles.link} onClick={() => setState((s) => ({ ...s, cases: removeAt(s.cases, i) }))}>
                  삭제
                </button>
              )}
            </div>
            <div className={styles.caseSelect}>
              <SelectField
                label="적용 기술"
                name={`case-skill-${i}`}
                placeholder="기술 선택"
                options={state.skills.map((k) => k.name)}
                value={c.skill}
                error={errors[`case.${i}.skill`]}
                onChange={(e) => setState((s) => ({ ...s, cases: replaceAt(s.cases, i, { skill: e.target.value }) }))}
              />
            </div>
            <TextAreaField
              label="내용"
              name={`case-content-${i}`}
              placeholder="어떤 문제를 어떤 기술로 해결했는지 작성해 주세요"
              value={c.content}
              error={errors[`case.${i}.content`]}
              onChange={(e) => setState((s) => ({ ...s, cases: replaceAt(s.cases, i, { content: e.target.value }) }))}
            />
          </div>
        ))}
        <div>
          <Button type="button" variant="secondary" inline onClick={() => setState((s) => ({ ...s, cases: [...s.cases, { skill: "", content: "" }] }))}>
            + 사례 추가
          </Button>
        </div>
      </section>
    </>
  );
}

// 화면 14 자기소개서 (APP-008)
export function EssaysStep({
  state,
  setState,
  errors,
  topics,
}: StepProps & { topics: { topic_id: number; topic_name: string }[] }) {
  return (
    <section className={styles.card}>
      <div className={styles.cardHead}>
        <h2 className={styles.cardTitle}>자기소개서</h2>
        <p className={styles.cardDesc}>주제별로 자유롭게 작성해 주세요.</p>
      </div>
      {topics.map((t, i) => (
        <TextAreaField
          key={t.topic_id}
          label={`${i + 1}. ${t.topic_name}`}
          name={`essay-${t.topic_id}`}
          placeholder="내용을 입력해 주세요"
          value={state.essays[t.topic_id] ?? ""}
          error={errors[`essay.${t.topic_id}`]}
          onChange={(e) => setState((s) => ({ ...s, essays: { ...s.essays, [t.topic_id]: e.target.value } }))}
        />
      ))}
    </section>
  );
}
