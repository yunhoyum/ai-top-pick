"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Button from "@/components/common/Button";
import { ApiError, apiFetch } from "@/lib/api";
import { type EvalStage, formatTotal, STAGE_LABEL, stageEndAt, stagePath } from "@/lib/evaluation";
import { formatFullDate } from "@/lib/format";
import type { Ranking } from "@/types/evaluation";
import styles from "./Evaluation.module.css";

const errorMessage = (e: unknown) => (e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다.");

// 화면 20-1 서류 전형 합격자 확정 완료, 화면 30-1 면접 전형 합격자 확정 완료. 합격자를 확정한 뒤 보인다
export default function SelectionDoneView({ postingId, stage = "document" }: { postingId: number; stage?: EvalStage }) {
  const router = useRouter();
  const [ranking, setRanking] = useState<Ranking | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<Ranking>(`/api/admin/postings/${postingId}/stages/${stage}/ranking`)
      .then(setRanking)
      .catch((e) => setLoadError(errorMessage(e)));
  }, [postingId, stage]);

  // 아직 확정하지 않았으면 화면 20으로 보낸다
  useEffect(() => {
    if (ranking && !ranking.confirmed) router.replace(`${stagePath(postingId, stage)}/selection`);
  }, [ranking, postingId, stage, router]);

  if (loadError) return <p className={styles.loadError}>{loadError}</p>;
  if (!ranking?.confirmed) return null;

  const position = ranking.position_name ?? "(제목 없음)";
  const passed = ranking.rows.filter((r) => r.result === "합격");
  return (
    <div className={styles.page}>
      <Link href={`/admin/postings/${postingId}`} className={styles.back}>
        ‹ {position}
      </Link>

      <header className={styles.header}>
        <div className={styles.headText}>
          <h1 className={styles.title}>{STAGE_LABEL[stage]} 전형 합격자 확정 완료</h1>
          <p className={styles.subtitle}>
            {position} · {STAGE_LABEL[stage]} 전형 마감 {formatFullDate(stageEndAt(stage, ranking))}
          </p>
        </div>
      </header>

      <p className={`${styles.notice} ${styles.noticeNavy}`}>
        <img src="/admin/dot-navy.svg" alt="" width={6} height={6} className={styles.dot} />
        {stage === "document"
          ? "합격자를 확정했습니다. 지원자는 결과 조회에서 본인 결과만 확인합니다."
          : "면접 합격자를 확정해 채용 공고를 마감했습니다. 지원자는 면접 합격자 발표 일시부터 본인 결과만 확인합니다."}
      </p>

      <div className={styles.selectBar}>
        <span className={styles.selectLabel}>확정된 합격자 명단</span>
        <span className={styles.selectCount}>{passed.length}명</span>
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <colgroup>
            <col style={{ width: 64 }} />
            <col style={{ width: 160 }} />
            <col style={{ width: 90 }} />
            <col />
            <col style={{ width: 80 }} />
          </colgroup>
          <thead>
            <tr>
              <th>순위</th>
              <th>지원자</th>
              <th>총점</th>
              <th>관리자 의견</th>
              <th>보고서</th>
            </tr>
          </thead>
          <tbody>
            {passed.map((row) => (
              <tr key={row.application_id}>
                <td className={styles.rank}>{row.rank ?? "-"}</td>
                <td className={styles.name}>{row.applicant_name ?? "(이름 없음)"}</td>
                <td className={styles.total}>{row.total ? formatTotal(row.total) : "-"}</td>
                <td className={styles.opinionCell} title={row.opinion ?? undefined}>
                  {row.opinion ?? <span className={styles.muted}>-</span>}
                </td>
                <td>
                  {row.rank !== null ? (
                    <Link
                      href={`${stagePath(postingId, stage)}/applications/${row.application_id}/report`}
                      className={styles.reportLink}
                    >
                      보기 ›
                    </Link>
                  ) : (
                    <span className={styles.muted}>-</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {passed.length === 0 && <p className={styles.empty}>합격자가 없습니다.</p>}
      </div>

      <div className={styles.actions}>
        <Button type="button" variant="secondary" inline onClick={() => router.push(`/admin/postings/${postingId}`)}>
          공고 상세
        </Button>
        <Button type="button" inline onClick={() => router.push(`/admin/dashboard?posting=${postingId}`)}>
          대시보드
        </Button>
      </div>
    </div>
  );
}
