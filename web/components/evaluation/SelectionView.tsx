"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Button from "@/components/common/Button";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import { ApiError, apiFetch } from "@/lib/api";
import { type EvalStage, formatTotal, reportStatusLabel, STAGE_LABEL, stageEndAt, stagePath } from "@/lib/evaluation";
import { formatFullDate } from "@/lib/format";
import type { Ranking } from "@/types/evaluation";
import styles from "./Evaluation.module.css";

const errorMessage = (e: unknown) => (e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다.");

// 화면 20 서류 전형 합격자 선정 (ADM-025), 화면 30 면접 전형 합격자 선정 (ADM-031). 한 번 확정하면 바꿀 수 없다.
// 면접 미응시자는 고를 수 없다(서버가 422). 면접 합격자를 확정하면 공고가 마감된다
export default function SelectionView({ postingId, stage = "document" }: { postingId: number; stage?: EvalStage }) {
  const router = useRouter();
  const [ranking, setRanking] = useState<Ranking | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  const donePath = `${stagePath(postingId, stage)}/selection/done`;
  const label = STAGE_LABEL[stage];

  useEffect(() => {
    apiFetch<Ranking>(`/api/admin/postings/${postingId}/stages/${stage}/ranking`)
      .then(setRanking)
      .catch((e) => setLoadError(errorMessage(e)));
  }, [postingId, stage]);

  // 이미 확정했으면 화면 20-1 합격자 확정 완료로 보낸다
  useEffect(() => {
    if (ranking?.confirmed) router.replace(donePath);
  }, [ranking, donePath, router]);

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function onConfirm() {
    setBusy(true);
    setConfirmError(null);
    try {
      await apiFetch(`/api/admin/postings/${postingId}/stages/${stage}/pass`, {
        method: "POST",
        body: JSON.stringify({ application_ids: [...selected] }),
      });
      router.push(donePath);
    } catch (e) {
      setConfirmError(errorMessage(e));
      setBusy(false);
    }
  }

  if (loadError) return <p className={styles.loadError}>{loadError}</p>;
  if (!ranking || ranking.confirmed) return null;

  const { rows } = ranking;
  const position = ranking.position_name ?? "(제목 없음)";
  return (
    <div className={styles.page}>
      <Link href={`/admin/postings/${postingId}`} className={styles.back}>
        ‹ {position}
      </Link>

      <header className={styles.header}>
        <div className={styles.headText}>
          <h1 className={styles.title}>{label} 전형 합격자 선정</h1>
          <p className={styles.subtitle}>
            {position} · {label} 전형 마감 {formatFullDate(stageEndAt(stage, ranking))}
          </p>
        </div>
      </header>

      <p className={`${styles.notice} ${styles.noticeNavy}`}>
        <img src="/admin/dot-navy.svg" alt="" width={6} height={6} className={styles.dot} />
        {stage === "document"
          ? "합격자를 확정하면 합격자의 면접 전형이 시작됩니다. 지원자는 결과 조회에서 본인 결과만 확인합니다. 확정한 뒤에는 바꿀 수 없습니다."
          : "합격자를 확정하면 채용 공고가 마감됩니다. 지원자는 면접 합격자 발표 일시부터 결과 조회에서 본인 결과만 확인합니다. 확정한 뒤에는 바꿀 수 없습니다."}
      </p>

      <div className={styles.selectBar}>
        <span className={styles.selectLabel}>선택한 합격자</span>
        <span className={styles.selectCount}>{selected.size}명</span>
        <Button type="button" variant="ghost" inline disabled={selected.size === 0} onClick={() => setSelected(new Set())}>
          선택 초기화
        </Button>
        <Button type="button" inline disabled={selected.size === 0} onClick={() => setConfirming(true)}>
          합격자 확정
        </Button>
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <colgroup>
            <col style={{ width: 80 }} />
            <col style={{ width: 64 }} />
            <col style={{ width: 160 }} />
            <col style={{ width: 90 }} />
            {stage === "interview" && <col style={{ width: 90 }} />}
            <col />
            <col style={{ width: 96 }} />
          </colgroup>
          <thead>
            <tr>
              <th>선택</th>
              <th>순위</th>
              <th>지원자</th>
              <th>총점</th>
              {stage === "interview" && <th>꼬리질문</th>}
              <th>관리자 의견</th>
              <th>보고서</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const name = row.applicant_name ?? "(이름 없음)";
              return (
                <tr key={row.application_id}>
                  <td>
                    <input
                      type="checkbox"
                      className={styles.checkbox}
                      aria-label={`${name} 합격`}
                      disabled={row.report_status === "미응시"}
                      checked={selected.has(row.application_id)}
                      onChange={() => toggle(row.application_id)}
                    />
                  </td>
                  <td className={styles.rank}>{row.rank ?? "-"}</td>
                  <td className={styles.name}>{name}</td>
                  <td className={styles.total}>{row.total ? formatTotal(row.total) : "-"}</td>
                  {/* 면접은 지원자별 꼬리질문 횟수를 보인다 (ADM-031). 총점에는 더하지 않는다 */}
                  {stage === "interview" && (
                    <td className={styles.total}>{row.follow_up_count != null ? `${row.follow_up_count}회` : "-"}</td>
                  )}
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
                      <span className={styles.muted}>{reportStatusLabel(row.report_status)}</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {rows.length === 0 && <p className={styles.empty}>평가 대상 지원자가 없습니다.</p>}
      </div>

      {confirming && (
        <ConfirmDialog
          title={`${label} 합격자 ${selected.size}명을 확정하시겠습니까?`}
          message={`선택하지 않은 ${rows.length - selected.size}명은 불합격이 됩니다. 확정한 뒤에는 바꿀 수 없습니다.`}
          confirmLabel="합격자 확정"
          busy={busy}
          error={confirmError}
          onConfirm={onConfirm}
          onCancel={() => {
            setConfirming(false);
            setConfirmError(null);
          }}
        />
      )}
    </div>
  );
}
