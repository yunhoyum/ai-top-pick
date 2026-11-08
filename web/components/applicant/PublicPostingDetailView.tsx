"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Badge from "@/components/common/Badge";
import Button from "@/components/common/Button";
import { ApiError, apiFetch } from "@/lib/api";
import { fetchMeIfLoggedIn, type Me } from "@/lib/auth";
import { endBadge } from "@/lib/dday";
import { formatFullDateWeek, formatMonthDay, formatMonthDayWeekTime } from "@/lib/format";
import { PROGRESS_TONES } from "@/lib/posting";
import type { PublicPostingDetail } from "@/types/posting";
import AdminPreviewNotice from "./AdminPreviewNotice";
import styles from "./PublicPostingDetailView.module.css";

const range = (a: string | null, b: string | null) => (a && b ? `${formatMonthDay(a)} ~ ${formatMonthDay(b)}` : "-");

function Kv({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={styles.kv}>
      <p className={styles.key}>{label}</p>
      <p className={styles.value}>{children}</p>
    </div>
  );
}

// 지원 바의 문구: 서류 접수 중일 때만 지원할 수 있다
function applyBar(p: PublicPostingDetail) {
  if (p.progress_status === "서류 접수 중") {
    return { open: true, state: "서류 접수 중", desc: `접수 마감 ${formatFullDateWeek(p.doc_end_at)}` };
  }
  if (p.progress_status === "모집 전") {
    return { open: false, state: "모집 전", desc: `접수 시작 ${formatFullDateWeek(p.doc_start_at)}` };
  }
  return { open: false, state: "접수 마감", desc: `접수 마감 ${formatFullDateWeek(p.doc_end_at)}` };
}

// 화면 11-1 채용공고 상세 (APP-004). 비로그인도 볼 수 있다
export default function PublicPostingDetailView({ postingId }: { postingId: number }) {
  const router = useRouter();
  const [posting, setPosting] = useState<PublicPostingDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    apiFetch<PublicPostingDetail>(`/api/postings/${postingId}`)
      .then(setPosting)
      .catch((e) => setError(e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다."));
    fetchMeIfLoggedIn().then(setMe);
  }, [postingId]);

  if (error) return <p className={styles.error}>{error}</p>;
  if (!posting) return null;

  const bar = applyBar(posting);
  const isAdmin = me?.role === "관리자";
  const dday = bar.open ? endBadge(posting.doc_end_at) : null;

  function onApply() {
    // 로그인하지 않았으면 로그인 화면으로 보내고, 로그인하면 이 공고로 돌아온다
    if (!me) router.push(`/login?next=${encodeURIComponent(`/postings/${postingId}`)}`);
    else router.push(`/postings/${postingId}/apply`); // 지원서 작성 화면은 아직 없다
  }

  return (
    <div className={styles.page}>
      {isAdmin && <AdminPreviewNotice />}

      <Link href="/postings" className={styles.back}>
        ‹ 채용공고
      </Link>

      <div className={styles.head}>
        <h1 className={styles.title}>{posting.position_name ?? "(제목 없음)"}</h1>
        <div className={styles.badges}>
          {posting.employment_type && <Badge tone="gray">{posting.employment_type}</Badge>}
          {posting.progress_status && <Badge tone={PROGRESS_TONES[posting.progress_status] ?? "gray"}>{posting.progress_status}</Badge>}
          {dday && <Badge tone={dday.tone}>{dday.label}</Badge>}
        </div>
      </div>

      <div className={styles.cards}>
        <section className={`${styles.card} ${styles.info}`}>
          <h2 className={styles.cardTitle}>기본 정보</h2>
          <Kv label="포지션명">{posting.position_name ?? "-"}</Kv>
          <Kv label="직무 분류">{posting.job_category ?? "-"}</Kv>
          <Kv label="고용 형태">{posting.employment_type ?? "-"}</Kv>
          <Kv label="직무 설명">{posting.job_description ?? "-"}</Kv>
        </section>
        <section className={`${styles.card} ${styles.schedule}`}>
          <h2 className={styles.cardTitle}>전형 일정</h2>
          <Kv label="서류 접수">{range(posting.doc_start_at, posting.doc_end_at)}</Kv>
          <Kv label="서류 합격자 발표">{formatMonthDayWeekTime(posting.doc_result_at)}</Kv>
          <Kv label="AI 화상 면접">{range(posting.interview_start_at, posting.interview_end_at)}</Kv>
          <Kv label="면접 합격자 발표">{formatMonthDayWeekTime(posting.interview_result_at)}</Kv>
        </section>
      </div>

      <section className={styles.applyBar}>
        <div className={styles.applyText}>
          <p className={styles.applyState}>{bar.state}</p>
          <p className={styles.applyDesc}>{bar.desc}</p>
        </div>
        {/* 관리자는 지원 화면까지 확인할 수 있어야 해서 항상 누를 수 있다 (실제 접수는 지원 화면에서 막는다) */}
        <Button type="button" inline className={styles.applyButton} disabled={!bar.open && !isAdmin} onClick={onApply}>
          지원하기
        </Button>
      </section>
    </div>
  );
}
