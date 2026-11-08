"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Badge from "@/components/common/Badge";
import styles from "@/components/posting/PostingList.module.css";
import { ApiError, apiFetch } from "@/lib/api";
import { formatMonthDay } from "@/lib/format";
import { PROGRESS_TONES } from "@/lib/posting";
import type { PublicPostingItem } from "@/types/posting";

// 필터 칩. '전형 진행'은 서류 평가부터 면접 평가까지를 묶는다
const FILTERS = [
  { key: "all", label: "전체", match: () => true },
  { key: "before", label: "모집 전", match: (s: string | null) => s === "모집 전" },
  { key: "receiving", label: "서류 접수 중", match: (s: string | null) => s === "서류 접수 중" },
  { key: "ongoing", label: "전형 진행", match: (s: string | null) => ["서류 평가", "면접 진행", "면접 평가"].includes(s ?? "") },
  { key: "closed", label: "마감", match: (s: string | null) => s === "마감" },
] as const;

const period = (p: PublicPostingItem) =>
  p.doc_start_at && p.doc_end_at ? `${formatMonthDay(p.doc_start_at)} ~ ${formatMonthDay(p.doc_end_at)}` : "-";

// 화면 10-1 채용공고 목록 (APP-003). 비로그인도 볼 수 있고 지원자 수는 보여주지 않는다
export default function PublicPostingList() {
  const [items, setItems] = useState<PublicPostingItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["key"]>("all");

  useEffect(() => {
    apiFetch<PublicPostingItem[]>("/api/postings")
      .then(setItems)
      .catch((e) => setError(e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다."));
  }, []);

  if (error) return <p className={styles.error}>{error}</p>;
  if (!items) return null;

  const current = FILTERS.find((f) => f.key === filter)!;
  const shown = items.filter((p) => current.match(p.progress_status));

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headText}>
          <h1 className={styles.title}>채용공고</h1>
          <p className={styles.subtitle}>지원할 채용공고를 확인하세요.</p>
        </div>
      </header>

      <div className={styles.filters} role="group" aria-label="진행 상태 필터">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            className={`${styles.chip} ${filter === f.key ? styles.chipActive : ""}`}
            aria-pressed={filter === f.key}
            onClick={() => setFilter(f.key)}
          >
            {f.label} {items.filter((p) => f.match(p.progress_status)).length}
          </button>
        ))}
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <colgroup>
            <col />
            <col style={{ width: 110 }} />
            <col style={{ width: 140 }} />
            <col style={{ width: 180 }} />
            <col style={{ width: 80 }} />
          </colgroup>
          <thead>
            <tr>
              <th>공고명</th>
              <th>고용 형태</th>
              <th>진행 상태</th>
              <th>서류 접수 기간</th>
              <th>상세</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((p) => (
              <tr key={p.posting_id}>
                <td className={styles.name}>{p.position_name ?? "(제목 없음)"}</td>
                <td>{p.employment_type ?? "-"}</td>
                <td>
                  {p.progress_status ? <Badge tone={PROGRESS_TONES[p.progress_status] ?? "gray"}>{p.progress_status}</Badge> : "-"}
                </td>
                <td>{period(p)}</td>
                <td>
                  <Link href={`/postings/${p.posting_id}`} className={styles.detail}>
                    상세 ›
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {shown.length === 0 && (
          <p className={styles.empty}>{items.length === 0 ? "등록된 채용공고가 없습니다." : "해당하는 채용공고가 없습니다."}</p>
        )}
      </div>
    </div>
  );
}
