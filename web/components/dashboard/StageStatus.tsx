"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Badge from "@/components/common/Badge";
import { ApiError, apiFetch } from "@/lib/api";
import { formatTotal } from "@/lib/evaluation";
import { docStage, interviewStage } from "@/lib/posting";
import type { Ranking } from "@/types/evaluation";
import type { PostingStats } from "@/types/posting";
import styles from "./Dashboard.module.css";

type Stage = "doc" | "interview";

type Props = {
  postingId: number;
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

// 상위 순위에 보여줄 인원 (Figma 92:2985)
const TOP_COUNT = 5;

// 전형 현황: 서류 전형과 면접 전형의 지원자 수와 상위 순위 (ADM-003).
// 처음에는 지금 진행 중인 전형을 보여주고, 칩으로 바꿔 볼 수 있다. 공고를 바꾸면 다시 처음 상태가 되도록 key로 새로 만든다
export default function StageStatus({ postingId, progress, stats }: Props) {
  const interviewStarted = interviewStage(progress).started;
  const docClosed = docStage(progress).closed;
  const interviewClosed = interviewStage(progress).closed;
  const [stage, setStage] = useState<Stage>(interviewStarted ? "interview" : "doc");
  const [ranking, setRanking] = useState<Ranking | null>(null);
  const [rankingError, setRankingError] = useState<string | null>(null);

  // 고른 전형이 마감되면 화면 17·27과 같은 순위를 불러온다
  const apiStage = stage === "doc" ? "document" : "interview";
  const closed = stage === "doc" ? docClosed : interviewClosed;
  useEffect(() => {
    setRanking(null);
    if (!closed) return;
    apiFetch<Ranking>(`/api/admin/postings/${postingId}/stages/${apiStage}/ranking`)
      .then(setRanking)
      .catch((e) => setRankingError(e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다."));
  }, [postingId, apiStage, closed]);

  // 보고서가 나온(순위가 매겨진) 지원자만 보인다
  const top = ranking?.rows.filter((r) => r.rank !== null).slice(0, TOP_COUNT) ?? [];
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
        <div className={styles.rankHead}>
          <p className={styles.blockTitle}>상위 순위</p>
          {top.length > 0 && ranking && (
            <>
              <Badge tone={ranking.confirmed ? "gray" : "amber"}>
                {ranking.confirmed ? "합격자 선정 완료" : "합격자 선정 대기"}
              </Badge>
              <Link href={`/admin/postings/${postingId}/${apiStage}/ranking`} className={styles.rankLink}>
                전체 순위 보기 ›
              </Link>
            </>
          )}
        </div>
        {top.length > 0 ? (
          <ol className={styles.rankList}>
            {top.map((r) => (
              <li key={r.application_id} className={styles.rankRow}>
                <span className={styles.rankNo}>{r.rank}</span>
                <span className={styles.rankName}>{r.applicant_name ?? "(이름 없음)"}</span>
                <span className={styles.rankScore}>{formatTotal(r.total!)}점</span>
              </li>
            ))}
          </ol>
        ) : closed ? (
          <div className={styles.rankEmpty}>
            <p className={styles.rankTitle}>{rankingError ?? "AI가 결과 보고서를 생성하고 있습니다"}</p>
            {!rankingError && <p className={styles.rankDesc}>보고서가 나오면 상위 순위가 표시됩니다</p>}
          </div>
        ) : (
          <div className={styles.rankEmpty}>
            <p className={styles.rankTitle}>{name} 종료 후 상위 순위가 표시됩니다</p>
            <p className={styles.rankDesc}>마감 시 AI가 결과 보고서와 순위를 자동 생성합니다</p>
          </div>
        )}
      </div>
    </section>
  );
}
