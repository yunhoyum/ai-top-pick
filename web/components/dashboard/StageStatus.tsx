"use client";

import { useState } from "react";
import { interviewStage } from "@/lib/posting";
import type { PostingStats } from "@/types/posting";
import styles from "./Dashboard.module.css";

type Stage = "doc" | "interview";

type Props = {
  progress: string | null;
  stats: PostingStats;
};

function Tile({ label, value, tone }: { label: string; value: string; tone?: "red" | "teal" }) {
  return (
    <div className={styles.tile}>
      <p className={styles.tileLabel}>{label}</p>
      <p className={styles.tileValue}>
        <strong className={tone ? styles[`tile_${tone}`] : undefined}>{value}</strong>
        <span>명</span>
      </p>
    </div>
  );
}

// 전형 현황: 서류 전형과 면접 전형의 지원자 수와 상위 순위 (ADM-003).
// 처음에는 지금 진행 중인 전형을 보여주고, 칩으로 바꿔 볼 수 있다. 공고를 바꾸면 다시 처음 상태가 되도록 key로 새로 만든다
export default function StageStatus({ progress, stats }: Props) {
  const interviewStarted = interviewStage(progress).started;
  const [stage, setStage] = useState<Stage>(interviewStarted ? "interview" : "doc");
  const name = stage === "doc" ? "서류 전형" : "면접 전형";
  // 면접 전형이 시작되기 전에는 아직 집계할 수 없다
  const interviewValue = (n: number) => (interviewStarted ? String(n) : "-");

  return (
    <section className={`${styles.card} ${styles.stageCard}`}>
      <div className={styles.cardHead}>
        <h2 className={styles.cardTitle}>전형 현황</h2>
        <div className={styles.chips} role="group" aria-label="전형 선택">
          {(["doc", "interview"] as const).map((s) => (
            <button
              key={s}
              type="button"
              className={`${styles.chip} ${stage === s ? styles.chipActive : ""}`}
              aria-pressed={stage === s}
              onClick={() => setStage(s)}
            >
              {s === "doc" ? "서류 전형" : "면접 전형"}
            </button>
          ))}
        </div>
      </div>

      <div className={styles.tiles}>
        {stage === "doc" ? (
          <>
            <Tile label="제출 수" value={String(stats.submitted_count)} />
            <Tile label="필수 기술 미달 탈락" value={String(stats.skill_shortfall_count)} tone="red" />
            <Tile label="서류 접수 완료" value={String(stats.submitted_count - stats.skill_shortfall_count)} tone="teal" />
          </>
        ) : (
          <>
            <Tile label="면접 대상" value={interviewValue(stats.interview_target_count)} />
            <Tile label="응시 완료" value={interviewValue(stats.interview_done_count)} tone="teal" />
          </>
        )}
      </div>

      <div className={styles.rank}>
        <p className={styles.blockTitle}>상위 순위</p>
        <div className={styles.rankEmpty}>
          <p className={styles.rankTitle}>{name} 종료 후 상위 순위가 표시됩니다</p>
          <p className={styles.rankDesc}>마감 시 AI가 결과 보고서와 순위를 자동 생성합니다</p>
        </div>
      </div>
    </section>
  );
}
