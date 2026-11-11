"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Badge from "@/components/common/Badge";
import Button from "@/components/common/Button";
import { ApiError, apiFetch } from "@/lib/api";
import { formatTotal, formatWeighted, reportStatusLabel, shortCriteriaName } from "@/lib/evaluation";
import { formatFullDate } from "@/lib/format";
import type { Ranking } from "@/types/evaluation";
import styles from "./Evaluation.module.css";

// Figma 열 너비: 순위 56, 총점 70, 항목 80·90·100·90, 의견 64, 결과 보고서 130 (지원자는 남는 너비)
const CRITERIA_WIDTHS = [80, 90, 100, 90];

const errorMessage = (e: unknown) => (e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다.");

function Stat({ label, value, unit, tone }: { label: string; value: string; unit: string; tone?: "red" | "teal" }) {
  return (
    <div className={styles.stat}>
      <p className={styles.statLabel}>{label}</p>
      <p className={styles.statValue}>
        <span className={`${styles.statNumber} ${tone ? styles[tone] : ""}`}>{value}</span>
        <span className={styles.statUnit}>{unit}</span>
      </p>
    </div>
  );
}

// 화면 17 서류 지원자 순위 (ADM-023). 관리자 의견은 결과 보고서 화면에서 등록한다
export default function RankingView({ postingId }: { postingId: number }) {
  const [ranking, setRanking] = useState<Ranking | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<Ranking>(`/api/admin/postings/${postingId}/stages/document/ranking`)
      .then(setRanking)
      .catch((e) => setLoadError(errorMessage(e)));
  }, [postingId]);

  if (loadError) return <p className={styles.loadError}>{loadError}</p>;
  if (!ranking) return null;

  const { criteria, summary, rows } = ranking;
  const position = ranking.position_name ?? "(제목 없음)";
  return (
    <div className={styles.page}>
      <Link href={`/admin/postings/${postingId}`} className={styles.back}>
        ‹ {position}
      </Link>

      <header className={styles.header}>
        <div className={styles.headText}>
          <h1 className={styles.title}>서류 전형 · 지원자 순위</h1>
          <p className={styles.subtitle}>
            {position} · 서류 전형 마감 {formatFullDate(ranking.doc_end_at)}
          </p>
        </div>
        {/* 화면 20 합격자 선정은 아직 없다 */}
        <Button type="button" inline disabled title="준비 중입니다">
          합격자 선정
        </Button>
      </header>

      <p className={styles.notice}>
        <img src="/admin/nav-dot-active.svg" alt="" width={6} height={6} className={styles.dot} />
        서류 전형 마감 시 AI가 결과 보고서와 순위를 자동으로 만들었습니다.
      </p>

      <div className={styles.stats}>
        <Stat label="평가 대상" value={String(summary.target_count)} unit="명" />
        <Stat label="필수 기술 미달 탈락" value={String(summary.shortfall_count)} unit="명" tone="red" />
        <Stat label="평균 점수" value={summary.average ? formatTotal(summary.average) : "-"} unit="점" />
        <Stat label="의견 등록" value={String(summary.opinion_count)} unit="명" tone="teal" />
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <colgroup>
            <col style={{ width: 72 }} />
            <col />
            <col style={{ width: 78 }} />
            {criteria.map((c, i) => (
              <col key={c.criteria_id} style={{ width: (CRITERIA_WIDTHS[i] ?? 90) + 8 }} />
            ))}
            <col style={{ width: 72 }} />
            <col style={{ width: 146 }} />
          </colgroup>
          <thead>
            <tr>
              <th>순위</th>
              <th>지원자</th>
              <th>총점</th>
              {criteria.map((c) => (
                <th key={c.criteria_id}>
                  {shortCriteriaName(c.name)} {c.ratio}
                </th>
              ))}
              <th>의견</th>
              <th>결과 보고서</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const weighted = Object.fromEntries(row.scores.map((s) => [s.criteria_id, s.weighted]));
              return (
                <tr key={row.application_id}>
                  <td className={styles.rank}>{row.rank ?? "-"}</td>
                  <td className={styles.name}>{row.applicant_name ?? "(이름 없음)"}</td>
                  <td className={styles.total}>{row.total ? formatTotal(row.total) : "-"}</td>
                  {criteria.map((c) => (
                    <td key={c.criteria_id}>{weighted[c.criteria_id] ? formatWeighted(weighted[c.criteria_id]) : "-"}</td>
                  ))}
                  <td>{row.has_opinion ? <Badge tone="teal">등록</Badge> : <span className={styles.muted}>-</span>}</td>
                  <td>
                    {row.rank !== null ? (
                      <Link
                        href={`/admin/postings/${postingId}/document/applications/${row.application_id}/report`}
                        className={styles.reportLink}
                      >
                        결과 보고서 보기
                      </Link>
                    ) : (
                      <span className={styles.muted}>{reportStatusLabel(row.report_status)}</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {rows.length === 0 && <p className={styles.empty}>평가 대상 지원자가 없습니다.</p>}
      </div>
    </div>
  );
}
