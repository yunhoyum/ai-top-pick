"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Badge from "@/components/common/Badge";
import Button from "@/components/common/Button";
import TextAreaField from "@/components/common/TextAreaField";
import { ApiError, apiFetch } from "@/lib/api";
import { type EvalStage, formatTotal, formatWeighted, STAGE_LABEL, stageEndAt, stagePath, topPercent } from "@/lib/evaluation";
import { formatFullDate } from "@/lib/format";
import type { DocumentReport, ReportPoint } from "@/types/evaluation";
import styles from "./Evaluation.module.css";

const errorMessage = (e: unknown) => (e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다.");

// Figma 막대 색: 서류는 이력서·기술 적용 사례 남색, 포트폴리오·자기소개 청록 / 면접은 내용 남색, 언어 청록, 비언어 연한 청록
const BAR_TONES: Record<EvalStage, string[]> = {
  document: ["", "", styles.teal, styles.teal],
  interview: ["", styles.teal, styles.tealLight],
};
const KIND_LABELS = { AI: "AI 질문", 꼬리: "꼬리질문", 기업: "기업 질문" } as const;

function PointList({ points, dot }: { points: ReportPoint[]; dot: string }) {
  if (points.length === 0) return <p className={styles.cardDesc}>없음</p>;
  return points.map((p, i) => (
    <p key={i} className={styles.point}>
      <img src={dot} alt="" width={6} height={6} className={styles.dot} />
      <span className={styles.pointText}>
        {p.content}
        {p.criteria_name && ` (${p.criteria_name})`}
      </span>
    </p>
  ));
}

// 화면 18 서류 전형 결과 보고서 (ADM-021), 화면 28 면접 전형 결과 보고서 (ADM-027), 관리자 의견 (ADM-024·030)
// 면접은 질문별 결과(구분, 주요 표정, 답변 기록 링크)를 더한다 (SYS-010)
export default function ReportView({
  postingId,
  applicationId,
  stage = "document",
}: {
  postingId: number;
  applicationId: number;
  stage?: EvalStage;
}) {
  const router = useRouter();
  const [report, setReport] = useState<DocumentReport | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [opinion, setOpinion] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveState, setSaveState] = useState<{ ok: boolean; message: string } | null>(null);

  useEffect(() => {
    apiFetch<DocumentReport>(`/api/admin/applications/${applicationId}/stages/${stage}/report`)
      .then((r) => {
        setReport(r);
        setOpinion(r.opinion ?? "");
      })
      .catch((e) => setLoadError(errorMessage(e)));
  }, [applicationId, stage]);

  async function onSave() {
    setSaving(true);
    setSaveState(null);
    try {
      const saved = await apiFetch<{ opinion: string | null }>(
        `/api/admin/applications/${applicationId}/stages/${stage}/opinion`,
        { method: "PUT", body: JSON.stringify({ opinion }) },
      );
      setOpinion(saved.opinion ?? "");
      setSaveState({ ok: true, message: "저장했습니다." });
    } catch (e) {
      setSaveState({ ok: false, message: errorMessage(e) });
    } finally {
      setSaving(false);
    }
  }

  if (loadError) return <p className={styles.loadError}>{loadError}</p>;
  if (!report) return null;

  const fits = report.fits.filter((f) => f.found);
  const label = STAGE_LABEL[stage];
  const base = stagePath(postingId, stage);
  const material = stage === "document" ? "서류" : "면접 답변";
  return (
    <div className={styles.page}>
      <Link href={`${base}/ranking`} className={styles.back}>
        ‹ 지원자 순위
      </Link>

      <header className={styles.header}>
        <div className={styles.headText}>
          <h1 className={styles.title}>
            {report.applicant_name ?? "(이름 없음)"} · {label} 전형 결과 보고서
          </h1>
          <p className={styles.subtitle}>
            {report.position_name ?? "(제목 없음)"} · {label} 전형 마감 {formatFullDate(stageEndAt(stage, report))}
          </p>
        </div>
        <Button
          type="button"
          variant="secondary"
          inline
          onClick={() => router.push(`${base}/applications/${applicationId}/source`)}
        >
          원본 보기
        </Button>
      </header>

      <div className={styles.row}>
        <section className={`${styles.card} ${styles.totalCard}`}>
          <p className={styles.statLabel}>총점</p>
          <p className={styles.totalValue}>
            <span className={styles.totalNumber}>{formatTotal(report.total)}</span>
            <span className={styles.totalMax}>/ 100</span>
          </p>
          <div className={styles.badges}>
            <Badge>
              {report.rank}위 / {report.ranked_count}명
            </Badge>
            <Badge tone="teal">상위 {topPercent(report.rank, report.ranked_count)}%</Badge>
          </div>
        </section>
        <section className={`${styles.card} ${styles.cardTight}`}>
          <div className={styles.cardHeader}>
            <div className={styles.cardTitles}>
              <h2 className={styles.cardTitle}>AI 종합 요약</h2>
            </div>
            <Badge tone="teal">AI 자동 생성</Badge>
          </div>
          <p className={styles.body}>{report.summary ?? "요약이 없습니다."}</p>
        </section>
      </div>

      <div className={styles.row}>
        <section className={styles.card}>
          <div className={styles.cardTitles}>
            <h2 className={styles.cardTitle}>항목별 점수</h2>
            <p className={styles.cardDesc}>{label} 평가기준 비율 기준</p>
          </div>
          {report.scores.map((s, i) => (
            <div key={s.criteria_id} className={styles.scoreRow} title={s.evidence}>
              <span className={styles.scoreName}>{s.name}</span>
              <span className={styles.track}>
                <span className={`${styles.fill} ${BAR_TONES[stage][i] ?? ""}`} style={{ width: `${Number(s.score)}%` }} />
              </span>
              <span className={styles.scoreValue}>
                {formatWeighted(s.weighted)} / {s.ratio}
              </span>
            </div>
          ))}
        </section>
        <section className={styles.card}>
          <div className={styles.cardTitles}>
            <h2 className={styles.cardTitle}>인재상 적합도</h2>
            <p className={styles.cardDesc}>회사 인재상과 {stage === "document" ? "지원자 서류" : "면접 답변"}의 공통점</p>
          </div>
          {fits.length === 0 && <p className={styles.cardDesc}>{material}에서 확인된 인재상이 없습니다.</p>}
          {fits.map((f) => (
            <div key={f.talent_content} className={styles.fit}>
              <div className={styles.fitHead}>
                {f.kind && <Badge tone={f.kind === "기능적" ? "navy" : "teal"}>{f.kind}</Badge>}
                <span className={styles.fitTalent}>{f.talent_content}</span>
              </div>
              <p className={styles.fitEvidence}>근거: {f.evidence}</p>
            </div>
          ))}
        </section>
      </div>

      <div className={styles.row}>
        <section className={`${styles.card} ${styles.cardTight}`}>
          <h2 className={styles.cardTitle}>강점</h2>
          <PointList points={report.strengths} dot="/admin/nav-dot-active.svg" />
        </section>
        <section className={`${styles.card} ${styles.cardTight}`}>
          <h2 className={styles.cardTitle}>확인이 필요한 부분</h2>
          <PointList points={report.checks} dot="/admin/dot-amber.svg" />
        </section>
      </div>

      {stage === "interview" && report.questions && (
        <section className={styles.card}>
          <div className={styles.cardTitles}>
            <h2 className={styles.cardTitle}>질문별 결과</h2>
            <p className={styles.cardDesc}>
              질문마다 답변 기록과 표정 분석 결과를 확인합니다.
              {report.follow_up_count != null && ` 받은 꼬리질문 ${report.follow_up_count}회.`}
            </p>
          </div>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <colgroup>
                <col />
                <col style={{ width: 110 }} />
                <col style={{ width: 100 }} />
                <col style={{ width: 90 }} />
              </colgroup>
              <thead>
                <tr>
                  <th>질문</th>
                  <th>구분</th>
                  <th>주요 표정</th>
                  <th>답변 기록</th>
                </tr>
              </thead>
              <tbody>
                {report.questions.map((q) => (
                  <tr key={q.answer_id}>
                    <td className={styles.questionCell}>
                      Q{q.seq}. {q.text}
                    </td>
                    <td>
                      <Badge tone={q.kind === "기업" ? "gray" : "navy"}>{KIND_LABELS[q.kind]}</Badge>
                    </td>
                    <td className={q.main_expression === "fear" || q.main_expression === "sad" ? styles.amberText : ""}>
                      {q.main_expression ?? <span className={styles.muted}>-</span>}
                    </td>
                    <td>
                      <Link href={`${base}/applications/${applicationId}/source?q=${q.seq}`} className={styles.reportLink}>
                        보기 ›
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {report.questions.length === 0 && <p className={styles.empty}>유효한 답변이 없습니다.</p>}
          </div>
        </section>
      )}

      <section className={styles.card}>
        <div className={styles.titleRow}>
          <h2 className={styles.cardTitle}>관리자 의견</h2>
          <Badge tone="gray">선택 사항</Badge>
        </div>
        <p className={styles.cardDesc}>AI 분석 결과와 원본 자료를 보고 의견을 남길 수 있습니다.</p>
        <TextAreaField
          label="의견"
          name="opinion"
          placeholder="합격자 선정에 참고할 의견을 입력해 주세요"
          maxLength={2000}
          value={opinion}
          onChange={(e) => {
            setOpinion(e.target.value);
            setSaveState(null);
          }}
        />
        <div className={styles.actions}>
          {saveState && <span className={saveState.ok ? styles.saved : styles.saveError}>{saveState.message}</span>}
          <Button type="button" inline disabled={saving} onClick={onSave}>
            의견 저장
          </Button>
        </div>
      </section>
    </div>
  );
}
