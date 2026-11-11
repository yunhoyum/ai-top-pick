"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Fragment, useEffect, useState } from "react";
import Badge from "@/components/common/Badge";
import { API_URL, ApiError, apiFetch } from "@/lib/api";
import { formatFullDate } from "@/lib/format";
import type { SourceDocuments } from "@/types/evaluation";
import styles from "./Evaluation.module.css";

const TABS = [
  { key: "resume", label: "이력서" },
  { key: "essays", label: "자기소개서" },
  { key: "portfolio", label: "포트폴리오" },
] as const;

const errorMessage = (e: unknown) => (e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다.");

// 구분선으로 나눈 섹션 목록 (비어 있는 섹션은 뺀다)
function Sections({ children }: { children: (React.ReactNode | false)[] }) {
  const shown = children.filter(Boolean);
  return shown.map((section, i) => (
    <Fragment key={i}>
      {i > 0 && <hr className={styles.divider} />}
      {section}
    </Fragment>
  ));
}

function Resume({ d }: { d: SourceDocuments }) {
  return (
    <div className={styles.document}>
      <Sections>
        {[
          <section key="profile" className={styles.section}>
            <h2 className={styles.sectionTitle}>인적사항</h2>
            {[
              ["이름", d.name],
              ["연락처", d.phone],
              ["이메일", d.email],
            ].map(([k, v]) => (
              <p key={k} className={styles.kv}>
                <span className={styles.kvKey}>{k}</span>
                <span className={styles.kvValue}>{v ?? "-"}</span>
              </p>
            ))}
          </section>,
          d.educations.length > 0 && (
            <section key="educations" className={styles.section}>
              <h2 className={styles.sectionTitle}>학력</h2>
              {d.educations.map((e, i) => (
                <p key={i} className={styles.kv}>
                  <span className={styles.kvKey}>{e.school_name ?? "-"}</span>
                  <span className={styles.kvValue}>{[e.major, e.period].filter(Boolean).join(" · ")}</span>
                </p>
              ))}
            </section>
          ),
          d.careers.length > 0 && (
            <section key="careers" className={styles.section}>
              <h2 className={styles.sectionTitle}>경력</h2>
              {d.careers.map((c, i) => (
                <p key={i} className={styles.kv}>
                  <span className={styles.kvKey}>{c.company_name ?? "-"}</span>
                  <span className={styles.kvValue}>{[c.job_role, c.period].filter(Boolean).join(" · ")}</span>
                </p>
              ))}
            </section>
          ),
          d.projects.length > 0 && (
            <section key="projects" className={styles.section}>
              <h2 className={styles.sectionTitle}>프로젝트</h2>
              {d.projects.map((p, i) => (
                <div key={i} className={styles.box}>
                  <div className={styles.boxHead}>
                    <span className={styles.boxTitle}>{p.project_name ?? "-"}</span>
                    {p.period && <span className={styles.boxPeriod}>{p.period}</span>}
                  </div>
                  {p.description && <p className={styles.boxText}>{p.description}</p>}
                </div>
              ))}
            </section>
          ),
          d.skills.length > 0 && (
            <section key="skills" className={styles.section}>
              <h2 className={styles.sectionTitle}>사용기술 (자기평가 5점 척도)</h2>
              <div className={styles.chips}>
                {d.skills.map((s) => (
                  <Badge key={s.skill_name}>
                    {s.skill_name} {s.score ?? "-"}점
                  </Badge>
                ))}
              </div>
            </section>
          ),
          d.cases.length > 0 && (
            <section key="cases" className={styles.section}>
              <h2 className={styles.sectionTitle}>기술 적용 사례</h2>
              {d.cases.map((c, i) => (
                <div key={i} className={styles.box}>
                  {c.skill_name && (
                    <div className={styles.boxHead}>
                      <Badge>{c.skill_name}</Badge>
                    </div>
                  )}
                  <p className={styles.boxText}>{c.content ?? "-"}</p>
                </div>
              ))}
            </section>
          ),
        ]}
      </Sections>
    </div>
  );
}

function Essays({ d }: { d: SourceDocuments }) {
  if (d.essays.length === 0) return <p className={styles.empty}>제출한 자기소개서가 없습니다.</p>;
  return (
    <div className={styles.document}>
      <Sections>
        {d.essays.map((e, i) => (
          <section key={i} className={styles.section}>
            <h2 className={styles.essayTitle}>
              {i + 1}. {e.topic}
            </h2>
            <p className={styles.boxText}>{e.content ?? "-"}</p>
          </section>
        ))}
      </Sections>
    </div>
  );
}

function Portfolio({ d }: { d: SourceDocuments }) {
  if (!d.portfolio) return <p className={styles.empty}>제출한 포트폴리오가 없습니다.</p>;
  return (
    <div className={styles.viewer}>
      <p className={styles.viewerHead}>{d.portfolio.file_name}</p>
      <div className={styles.viewerBody}>
        {/* 쪽 이동은 브라우저 PDF 보기 도구를 쓴다. 쪽 목록 패널은 닫아 둔다 (navpanes=0) */}
        <iframe
          className={styles.viewerFrame}
          title={d.portfolio.file_name}
          src={`${API_URL}/api/admin/applications/${d.application_id}/portfolio/file#navpanes=0`}
        />
      </div>
    </div>
  );
}

// 화면 19 지원자 자료 원본 (ADM-022): 이력서, 자기소개서, 포트폴리오 탭
export default function SourceView({ postingId, applicationId }: { postingId: number; applicationId: number }) {
  const router = useRouter();
  const search = useSearchParams();
  const tab = TABS.find((t) => t.key === search.get("tab"))?.key ?? "resume";
  const [docs, setDocs] = useState<SourceDocuments | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<SourceDocuments>(`/api/admin/applications/${applicationId}/documents`)
      .then(setDocs)
      .catch((e) => setLoadError(errorMessage(e)));
  }, [applicationId]);

  if (loadError) return <p className={styles.loadError}>{loadError}</p>;
  if (!docs) return null;

  const base = `/admin/postings/${postingId}/document/applications/${applicationId}`;
  return (
    <div className={styles.page}>
      <Link href={`${base}/report`} className={styles.back}>
        ‹ 서류 전형 결과 보고서
      </Link>

      <header className={styles.header}>
        <div className={styles.headText}>
          <h1 className={styles.title}>{docs.name ?? "(이름 없음)"} · 제출 자료 원본</h1>
          <p className={styles.subtitle}>
            {docs.position_name ?? "(제목 없음)"} · 서류 전형 마감 {formatFullDate(docs.doc_end_at)}
          </p>
        </div>
      </header>

      <div className={styles.tabs} role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={`${styles.tab} ${tab === t.key ? styles.tabActive : ""}`}
            onClick={() => router.replace(`${base}/source?tab=${t.key}`, { scroll: false })}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "resume" && <Resume d={docs} />}
      {tab === "essays" && <Essays d={docs} />}
      {tab === "portfolio" && <Portfolio d={docs} />}
    </div>
  );
}
