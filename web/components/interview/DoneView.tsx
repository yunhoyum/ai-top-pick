"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Button from "@/components/common/Button";
import { apiFetch } from "@/lib/api";
import { formatFullDate, formatFullDateTime } from "@/lib/format";
import type { InterviewGuide } from "@/types/interview";
import styles from "./Interview.module.css";

// 화면 25 면접 종료 안내. 답변한 질문 수와 종료 일시는 면접 화면이 넘겨준다
export default function DoneView({
  applicationId, answered, endedAt,
}: { applicationId: number; answered: number | null; endedAt: string | null }) {
  const router = useRouter();
  const [guide, setGuide] = useState<InterviewGuide | null>(null);

  useEffect(() => {
    apiFetch<InterviewGuide>(`/api/applications/${applicationId}/interview/guide`).then(setGuide).catch(() => {});
  }, [applicationId]);

  return (
    <div className={styles.done}>
      <div className={styles.doneIcon}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/interview/done-check.svg" alt="" />
      </div>
      <div className={styles.doneText}>
        <h1 className={styles.pageTitle}>AI 화상 면접이 종료되었습니다</h1>
        <p className={styles.pageDesc}>
          답변이 저장되었습니다. 면접 전형 결과는 면접 합격자 발표 일시({formatFullDateTime(guide?.interview_result_at ?? null)})부터
          <br />
          ‘내 지원 현황’에서 확인할 수 있습니다.
        </p>
      </div>
      <div className={styles.doneInfo}>
        <div className={styles.kv}>
          <span className={styles.kvKey}>응시 공고</span>
          <span className={styles.kvValue}>{guide?.position_name ?? "-"}</span>
        </div>
        <div className={styles.kv}>
          <span className={styles.kvKey}>답변한 질문</span>
          <span className={styles.kvValue}>{answered === null ? "-" : `${answered}개`}</span>
        </div>
        <div className={styles.kv}>
          <span className={styles.kvKey}>면접 종료</span>
          <span className={styles.kvValue}>{formatFullDateTime(endedAt)}</span>
        </div>
        <div className={styles.kv}>
          <span className={styles.kvKey}>면접 전형 마감</span>
          <span className={styles.kvValue}>{formatFullDate(guide?.interview_end_at ?? null)}</span>
        </div>
      </div>
      <Button type="button" onClick={() => router.push("/applications")}>
        내 지원 현황 보기
      </Button>
    </div>
  );
}
