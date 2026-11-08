"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import Button from "@/components/common/Button";
import fieldStyles from "@/components/common/Field.module.css";
import { ApiError, apiFetch } from "@/lib/api";
import type { PostingListItem, PostingStats, Review } from "@/types/posting";
import CriteriaSummary from "./CriteriaSummary";
import styles from "./Dashboard.module.css";
import ErrorCheck from "./ErrorCheck";
import PostingSummary from "./PostingSummary";
import StageStatus from "./StageStatus";

// 진행 중인 공고: 서류 접수 중부터 면접 평가까지
const IN_PROGRESS = ["서류 접수 중", "서류 평가", "면접 진행", "면접 평가"];

const errorMessage = (e: unknown) => (e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다.");

type Loaded = { id: number; review: Review; stats: PostingStats };

// 화면 03 대시보드 (ADM-003): 선택한 공고의 진행 상황을 한 화면에서 본다
export default function DashboardView() {
  const router = useRouter();
  const search = useSearchParams();
  const [postings, setPostings] = useState<PostingListItem[] | null>(null);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<PostingListItem[]>("/api/admin/postings")
      .then(setPostings)
      .catch((e) => setError(errorMessage(e)));
  }, []);

  // 주소에 공고가 있으면 그 공고, 없으면 진행 중인 공고 중 가장 최근 것(없으면 가장 최근 공고)을 고른다.
  // 목록은 최근에 만든 공고가 먼저 온다
  const requested = Number(search.get("posting"));
  const selected = postings?.find((p) => p.posting_id === requested) ?? postings?.find((p) => IN_PROGRESS.includes(p.progress_status ?? "")) ?? postings?.[0];
  const selectedId = selected?.posting_id ?? null;

  useEffect(() => {
    if (selectedId === null) return;
    let cancelled = false;
    Promise.all([
      apiFetch<Review>(`/api/admin/postings/${selectedId}/review`),
      apiFetch<PostingStats>(`/api/admin/postings/${selectedId}/stats`),
    ])
      .then(([review, stats]) => !cancelled && setLoaded({ id: selectedId, review, stats }))
      .catch((e) => !cancelled && setError(errorMessage(e)));
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  if (error) return <p className={styles.error}>{error}</p>;
  if (!postings) return null;

  // 선택을 바꾼 직후 이전 공고의 내용이 잠깐 보이지 않도록, 지금 선택한 공고의 데이터일 때만 보여준다
  const data = loaded && loaded.id === selectedId ? loaded : null;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.headText}>
          <h1 className={styles.title}>대시보드</h1>
          <p className={styles.subtitle}>선택한 공고의 진행 상황을 확인합니다.</p>
        </div>
        {postings.length > 0 && (
          <div className={styles.picker}>
            <label className={fieldStyles.label} htmlFor="posting-picker">
              공고 선택
            </label>
            <select
              id="posting-picker"
              className={`${fieldStyles.input} ${fieldStyles.select}`}
              value={selectedId ?? ""}
              onChange={(e) => router.replace(`/admin/dashboard?posting=${e.target.value}`, { scroll: false })}
            >
              {postings.map((p) => (
                <option key={p.posting_id} value={p.posting_id}>
                  {p.position_name ?? "(제목 없음)"} · {p.progress_status ?? "-"}
                </option>
              ))}
            </select>
          </div>
        )}
      </header>

      {postings.length === 0 && (
        <section className={`${styles.card} ${styles.empty}`}>
          <p>등록한 채용공고가 없습니다. 새 공고를 등록하면 진행 상황을 여기서 볼 수 있습니다.</p>
          <Button type="button" inline onClick={() => router.push("/admin/postings/new/info")}>
            + 새 공고 등록
          </Button>
        </section>
      )}

      {data && selectedId !== null && (
        <>
          <section className={`${styles.card} ${styles.summaryCard}`}>
            <PostingSummary postingId={selectedId} posting={data.review.posting} />
            <div className={styles.vline} />
            <CriteriaSummary
              postingId={selectedId}
              posting={data.review.posting}
              doc={data.review.doc_criteria}
              interview={data.review.interview_criteria}
            />
          </section>

          <div className={styles.rowB}>
            <StageStatus key={selectedId} progress={data.review.posting.progress_status} stats={data.stats} />
            <ErrorCheck postingId={selectedId} posting={data.review.posting} stats={data.stats} />
          </div>
        </>
      )}
    </div>
  );
}
