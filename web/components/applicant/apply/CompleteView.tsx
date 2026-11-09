"use client";

import { useRouter } from "next/navigation";
import Button from "@/components/common/Button";
import { formatFullDate, formatFullDateTime } from "@/lib/format";
import type { ApplicationData } from "@/types/application";
import styles from "./Apply.module.css";

// 화면 16 서류 접수 완료 (APP-011)
export default function CompleteView({ data }: { data: ApplicationData }) {
  const router = useRouter();
  const { posting } = data;

  return (
    <div className={styles.done}>
      <div className={styles.doneIcon} aria-hidden="true">
        <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
          <path d="M8 16.5l5.5 5.5L24 10.5" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <div className={styles.doneText}>
        <h1 className={styles.doneTitle}>서류 접수가 완료되었습니다</h1>
        <p className={styles.doneDesc}>
          서류 전형 결과는 서류 합격자 발표 일시({formatFullDateTime(posting.doc_result_at)})부터
          <br />
          ‘내 지원 현황’에서 확인할 수 있습니다.
        </p>
      </div>
      <div className={styles.doneInfo}>
        <div className={styles.doneKv}>
          <span className={styles.doneKey}>지원 공고</span>
          <span className={styles.doneValue}>{posting.position_name}</span>
        </div>
        <div className={styles.doneKv}>
          <span className={styles.doneKey}>접수 일시</span>
          <span className={styles.doneValue}>{formatFullDateTime(data.submitted_at)}</span>
        </div>
        <div className={styles.doneKv}>
          <span className={styles.doneKey}>서류 전형 마감</span>
          <span className={styles.doneValue}>{formatFullDate(posting.doc_end_at)}</span>
        </div>
      </div>
      <div className={styles.doneActions}>
        <Button type="button" variant="secondary" onClick={() => router.push("/postings")}>
          채용공고 목록
        </Button>
        {/* 내 지원 현황 화면은 아직 없다 */}
        <Button type="button" onClick={() => router.push("/applications")}>
          내 지원 현황 보기
        </Button>
      </div>
    </div>
  );
}
