"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Button from "@/components/common/Button";
import { apiFetch, ApiError } from "@/lib/api";
import { formatFullDate, formatMonthDay } from "@/lib/format";
import type { InterviewGuide } from "@/types/interview";
import styles from "./Interview.module.css";

const NOTES = [
  "답변 내용에 따라 이어지는 꼬리질문이 나올 수 있습니다.",
  "답변 중 10초 이상 말이 없으면 답변이 끝난 것으로 처리됩니다.",
  "면접 영상과 음성은 저장되며, 답변 내용과 얼굴 표정이 분석됩니다.",
  "기술적인 문제가 생기면 화면의 ‘기술 문의’ 버튼을 눌러 주세요.",
];

// 화면 22 AI 화상 면접 안내사항 (APP-014, APP-018). 면접 마감이 지났으면 기술적 테스트로 넘어가지 않는다
export default function GuideView({ applicationId }: { applicationId: number }) {
  const router = useRouter();
  const [guide, setGuide] = useState<InterviewGuide | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [agreed, setAgreed] = useState(false);

  useEffect(() => {
    apiFetch<InterviewGuide>(`/api/applications/${applicationId}/interview/guide`)
      .then(setGuide)
      .catch((e) => setError(e instanceof ApiError ? e.message : "안내사항을 불러오지 못했습니다."));
  }, [applicationId]);

  if (error) return <p className={styles.message}>{error}</p>;
  if (!guide) return null;

  return (
    <div className={`${styles.page} ${styles.narrow}`}>
      <div>
        <h1 className={styles.pageTitle}>AI 화상 면접 안내</h1>
        <p className={styles.pageDesc}>
          {guide.position_name} · 응시 기간 {formatFullDate(guide.interview_start_at)} ~ {formatMonthDay(guide.interview_end_at)}
        </p>
      </div>

      <section className={styles.card}>
        <h2 className={styles.cardTitle}>면접 진행 방식</h2>
        <div className={styles.stats}>
          <div className={styles.stat}>
            <span className={styles.statLabel}>질문 수</span>
            <span className={styles.statValue}>{guide.question_count}개</span>
            <span className={styles.statNote}>꼬리질문 포함</span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statLabel}>생각 시간</span>
            <span className={styles.statValue}>{guide.think_time_sec}초</span>
            <span className={styles.statNote}>질문마다</span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statLabel}>답변 시간</span>
            <span className={styles.statValue}>{guide.answer_time_sec}초</span>
            <span className={styles.statNote}>질문마다</span>
          </div>
        </div>
      </section>

      <section className={`${styles.card} ${styles.notes}`}>
        <h2 className={styles.cardTitle}>유의사항</h2>
        {NOTES.map((note) => (
          <p key={note} className={styles.note}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/interview/bullet.svg" alt="" />
            {note}
          </p>
        ))}
      </section>

      <section className={`${styles.card} ${styles.confirm}`}>
        {!guide.can_enter && guide.reason && <p className={styles.message}>{guide.reason}</p>}
        <label className={styles.checkbox}>
          <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
          <span className={styles.checkboxBox}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/interview/checkbox-check.svg" alt="" />
          </span>
          안내사항을 모두 확인했습니다
        </label>
        <Button
          type="button"
          disabled={!agreed || !guide.can_enter}
          onClick={() => router.push(`/interview/${applicationId}/device-test`)}
        >
          기술적 테스트 시작
        </Button>
      </section>
    </div>
  );
}
