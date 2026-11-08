import Link from "next/link";
import Badge from "@/components/common/Badge";
import { endBadge, startBadge, type MilestoneBadge } from "@/lib/dday";
import { formatMonthDayWeek } from "@/lib/format";
import { PROGRESS_TONES, isEditableProgress } from "@/lib/posting";
import type { PostingDetail } from "@/types/posting";
import styles from "./Dashboard.module.css";

type Row = { label: string; iso: string | null; badge: MilestoneBadge | null };

// 공고 요약: 공고명, 상태 배지, 일정과 D-day (ADM-003)
export default function PostingSummary({ postingId, posting }: { postingId: number; posting: PostingDetail }) {
  const now = new Date();
  const rows: Row[] = [
    { label: "서류 접수 시작", iso: posting.doc_start_at, badge: startBadge(posting.doc_start_at, posting.doc_end_at, now) },
    { label: "서류 접수 마감", iso: posting.doc_end_at, badge: endBadge(posting.doc_end_at, now) },
    { label: "면접 시작", iso: posting.interview_start_at, badge: startBadge(posting.interview_start_at, posting.interview_end_at, now) },
    { label: "면접 마감", iso: posting.interview_end_at, badge: endBadge(posting.interview_end_at, now) },
  ];

  return (
    <div className={styles.col}>
      <div className={styles.cardHead}>
        <h2 className={styles.cardTitle}>공고 요약</h2>
        <span className={styles.spacer} />
        <Link href={`/admin/postings/${postingId}`} className={styles.link}>
          상세 보기 ›
        </Link>
      </div>
      <div className={styles.postingHead}>
        <p className={styles.postingName}>{posting.position_name ?? "(제목 없음)"}</p>
        <div className={styles.badges}>
          {posting.employment_type && <Badge tone="gray">{posting.employment_type}</Badge>}
          {posting.progress_status && <Badge tone={PROGRESS_TONES[posting.progress_status] ?? "gray"}>{posting.progress_status}</Badge>}
          {!isEditableProgress(posting.progress_status) && <Badge tone="gray">수정 잠금</Badge>}
        </div>
      </div>
      <hr className={styles.divider} />
      <div className={styles.milestones}>
        {rows.map((r) => (
          <div key={r.label} className={styles.milestone}>
            <span className={styles.milestoneLabel}>{r.label}</span>
            <span className={styles.spacer} />
            <span className={styles.milestoneDate}>{formatMonthDayWeek(r.iso)}</span>
            {r.badge && <Badge tone={r.badge.tone}>{r.badge.label}</Badge>}
          </div>
        ))}
      </div>
    </div>
  );
}
