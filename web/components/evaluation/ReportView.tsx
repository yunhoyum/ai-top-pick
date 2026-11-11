"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Badge from "@/components/common/Badge";
import Button from "@/components/common/Button";
import TextAreaField from "@/components/common/TextAreaField";
import { ApiError, apiFetch } from "@/lib/api";
import { formatTotal, formatWeighted, topPercent } from "@/lib/evaluation";
import { formatFullDate } from "@/lib/format";
import type { DocumentReport, ReportPoint } from "@/types/evaluation";
import styles from "./Evaluation.module.css";

const errorMessage = (e: unknown) => (e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다.");

// Figma 막대 색: 이력서·기술 적용 사례는 남색, 포트폴리오·자기소개는 청록
const BAR_TONES = ["", "", styles.teal, styles.teal];

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

// 화면 18 서류 전형 결과 보고서 (ADM-021), 관리자 의견 (ADM-024)
export default function ReportView({ postingId, applicationId }: { postingId: number; applicationId: number }) {
  const [report, setReport] = useState<DocumentReport | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [opinion, setOpinion] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveState, setSaveState] = useState<{ ok: boolean; message: string } | null>(null);

  useEffect(() => {
    apiFetch<DocumentReport>(`/api/admin/applications/${applicationId}/stages/document/report`)
      .then((r) => {
        setReport(r);
        setOpinion(r.opinion ?? "");
      })
      .catch((e) => setLoadError(errorMessage(e)));
  }, [applicationId]);

  async function onSave() {
    setSaving(true);
    setSaveState(null);
    try {
      const saved = await apiFetch<{ opinion: string | null }>(
        `/api/admin/applications/${applicationId}/stages/document/opinion`,
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
  return (
    <div className={styles.page}>
      <Link href={`/admin/postings/${postingId}/document/ranking`} className={styles.back}>
        ‹ 지원자 순위
      </Link>

      <header className={styles.header}>
        <div className={styles.headText}>
          <h1 className={styles.title}>{report.applicant_name ?? "(이름 없음)"} · 서류 전형 결과 보고서</h1>
          <p className={styles.subtitle}>
            {report.position_name ?? "(제목 없음)"} · 서류 전형 마감 {formatFullDate(report.doc_end_at)}
          </p>
        </div>
        {/* 화면 19 지원자 자료 원본은 아직 없다 */}
        <Button type="button" variant="secondary" inline disabled title="준비 중입니다">
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
            <p className={styles.cardDesc}>서류 평가기준 비율 기준</p>
          </div>
          {report.scores.map((s, i) => (
            <div key={s.criteria_id} className={styles.scoreRow} title={s.evidence}>
              <span className={styles.scoreName}>{s.name}</span>
              <span className={styles.track}>
                <span className={`${styles.fill} ${BAR_TONES[i] ?? ""}`} style={{ width: `${Number(s.score)}%` }} />
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
            <p className={styles.cardDesc}>회사 인재상과 지원자 서류의 공통점</p>
          </div>
          {fits.length === 0 && <p className={styles.cardDesc}>서류에서 확인된 인재상이 없습니다.</p>}
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
