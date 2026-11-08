import Link from "next/link";
import Badge from "@/components/common/Badge";
import { interviewStage } from "@/lib/posting";
import type { PostingDetail, PostingStats } from "@/types/posting";
import styles from "./Dashboard.module.css";

type Props = {
  postingId: number;
  posting: PostingDetail;
  stats: PostingStats;
};

// 오류 확인: 선택한 공고에서 AI가 처리하지 못한 면접 중 문의 오류 (ADM-003)
export default function ErrorCheck({ postingId, posting, stats }: Props) {
  const count = stats.ai_unhandled_error_count;
  const started = interviewStage(posting.progress_status).started;

  return (
    <section className={`${styles.card} ${styles.errorCard}`}>
      <div className={styles.cardHead}>
        <h2 className={styles.cardTitle}>오류 확인</h2>
        <Badge tone="red">{count}</Badge>
      </div>
      <p className={styles.errorSub}>선택한 공고 기준</p>
      <div className={styles.todo}>
        <p className={styles.todoName}>{posting.position_name ?? "(제목 없음)"}</p>
        <p className={styles.todoDesc}>
          AI 미처리 오류 {count}건{started ? "" : " · 면접 전형 시작 후 집계"}
        </p>
        <Link href={`/admin/inquiries?posting=${postingId}`} className={styles.link}>
          확인하기 ›
        </Link>
      </div>
    </section>
  );
}
