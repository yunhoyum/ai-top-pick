"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import Badge from "@/components/common/Badge";
import Button from "@/components/common/Button";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import { ApiError, apiFetch } from "@/lib/api";
import { formatMonthDay } from "@/lib/format";
import { PROGRESS_TONES, STEP_LABELS, docStage, interviewStage, isEditableProgress, type StageState } from "@/lib/posting";
import type { PostingStats, Review } from "@/types/posting";
import CriteriaTab from "./CriteriaTab";
import DocItemsTab from "./DocItemsTab";
import InfoTab from "./InfoTab";
import QuestionsTab from "./QuestionsTab";
import styles from "./PostingDetail.module.css";

const TABS = [
  { key: "info", label: "공고 정보" },
  { key: "doc-items", label: "서류 문항" },
  { key: "criteria", label: "평가기준" },
  { key: "company-questions", label: "면접 질문" },
] as const;

const errorMessage = (e: unknown) => (e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다.");

type StageRowProps = {
  name: string;
  stage: StageState;
  period: string;
  counts: string[];
  closedText: string;
  evalLabel: string;
  onEvaluate: () => void;
  last?: boolean;
};

// 전형 진행 카드의 한 줄 (서류 전형, 면접 전형)
function StageRow({ name, stage, period, counts, closedText, evalLabel, onEvaluate, last }: StageRowProps) {
  return (
    <div className={`${styles.stage} ${last ? styles.stageLast : ""}`}>
      <span className={styles.stageName}>{name}</span>
      <Badge tone={stage.tone}>{stage.label}</Badge>
      <span className={styles.stagePeriod}>{period}</span>
      {counts.map((c) => (
        <span key={c} className={styles.stageCount}>
          {c}
        </span>
      ))}
      <span className={styles.spacer} />
      {!stage.closed && <span className={styles.stageHint}>{closedText}</span>}
      <Button type="button" variant="secondary" inline className={styles.evalButton} disabled={!stage.closed} onClick={onEvaluate}>
        {evalLabel}
      </Button>
    </div>
  );
}

// 화면 11 채용공고 상세 (ADM-013, ADM-035~040)
export default function PostingDetailView({ postingId }: { postingId: number }) {
  const router = useRouter();
  const search = useSearchParams();
  const tab = TABS.find((t) => t.key === search.get("tab"))?.key ?? "info";

  const [review, setReview] = useState<Review | null>(null);
  const [stats, setStats] = useState<PostingStats | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiFetch<Review>(`/api/admin/postings/${postingId}/review`),
      apiFetch<PostingStats>(`/api/admin/postings/${postingId}/stats`),
    ])
      .then(([r, s]) => {
        setReview(r);
        setStats(s);
      })
      .catch((e) => setLoadError(errorMessage(e)));
  }, [postingId]);

  // 등록하지 않은(임시 저장) 공고는 상세가 아니라 작성 화면에서 이어서 쓴다
  const isDraft = review?.posting.write_status === "임시 저장";
  useEffect(() => {
    if (isDraft) router.replace(`/admin/postings/${postingId}/edit/info`);
  }, [isDraft, postingId, router]);

  async function onDelete() {
    setDeleteError(null);
    setDeleting(true);
    try {
      await apiFetch(`/api/admin/postings/${postingId}`, { method: "DELETE" });
      router.push("/admin/postings");
    } catch (e) {
      setDeleteError(errorMessage(e));
      setDeleting(false);
    }
  }

  if (loadError) return <p className={styles.loadError}>{loadError}</p>;
  if (!review || !stats || isDraft) return null;

  const { posting, incomplete_steps } = review;
  const editable = isEditableProgress(posting.progress_status);
  const doc = docStage(posting.progress_status);
  const interview = interviewStage(posting.progress_status);
  const range = (a: string | null, b: string | null) => (a && b ? `${formatMonthDay(a)} ~ ${formatMonthDay(b)}` : "-");
  const count = (n: number) => (interview.started ? `${n}명` : "-명");

  return (
    <div className={styles.page}>
      <Link href="/admin/postings" className={styles.back}>
        ‹ 채용공고 목록
      </Link>

      <header className={styles.header}>
        <h1 className={styles.title}>{posting.position_name ?? "(제목 없음)"}</h1>
        <Button
          type="button"
          variant="secondary"
          inline
          disabled={!editable}
          onClick={() => router.push(`/admin/postings/${postingId}/edit/info`)}
        >
          수정
        </Button>
        <Button
          type="button"
          variant="secondary"
          inline
          className={styles.danger}
          disabled={!editable}
          onClick={() => setConfirmDelete(true)}
        >
          삭제
        </Button>
      </header>

      <div className={styles.badges}>
        {posting.employment_type && <Badge tone="gray">{posting.employment_type}</Badge>}
        {posting.progress_status && <Badge tone={PROGRESS_TONES[posting.progress_status] ?? "gray"}>{posting.progress_status}</Badge>}
      </div>

      {!editable && <p className={styles.notice}>모집 전 공고만 수정·삭제할 수 있습니다.</p>}

      {incomplete_steps.length > 0 && (
        <p className={styles.warning} role="alert">
          수정이 끝나지 않은 단계가 있습니다:{" "}
          {incomplete_steps.map((step, i) => (
            <span key={step}>
              {i > 0 && ", "}
              <Link href={`/admin/postings/${postingId}/edit/${step}`}>{STEP_LABELS[step]}</Link>
            </span>
          ))}
        </p>
      )}

      <section className={styles.card}>
        <h2 className={styles.cardTitle}>전형 진행</h2>
        <StageRow
          name="서류 전형"
          stage={doc}
          period={range(posting.doc_start_at, posting.doc_end_at)}
          counts={[`제출 ${stats.submitted_count}명`]}
          closedText={`${formatMonthDay(posting.doc_end_at)} 마감 후 이용 가능`}
          evalLabel="서류 전형 평가"
          onEvaluate={() => router.push(`/admin/postings/${postingId}/document-evaluation`)}
        />
        <StageRow
          name="면접 전형"
          stage={interview}
          period={range(posting.interview_start_at, posting.interview_end_at)}
          counts={[`대상 ${count(stats.interview_target_count)}`, `응시 완료 ${count(stats.interview_done_count)}`]}
          closedText={`${formatMonthDay(posting.interview_end_at)} 마감 후 이용 가능`}
          evalLabel="면접 전형 평가"
          onEvaluate={() => router.push(`/admin/postings/${postingId}/interview-evaluation`)}
          last
        />
      </section>

      <div className={styles.tabs} role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={`${styles.tab} ${tab === t.key ? styles.tabActive : ""}`}
            onClick={() => router.replace(`/admin/postings/${postingId}?tab=${t.key}`, { scroll: false })}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "info" && <InfoTab postingId={postingId} posting={posting} />}
      {tab === "doc-items" && <DocItemsTab items={review.doc_items} />}
      {tab === "criteria" && <CriteriaTab doc={review.doc_criteria} interview={review.interview_criteria} />}
      {tab === "company-questions" && <QuestionsTab data={review.company_questions} />}

      {confirmDelete && (
        <ConfirmDialog
          title="채용공고를 삭제하시겠습니까?"
          message="삭제한 공고와 올린 문서는 복구할 수 없습니다."
          confirmLabel="삭제"
          busy={deleting}
          error={deleteError}
          onConfirm={onDelete}
          onCancel={() => {
            setConfirmDelete(false);
            setDeleteError(null);
          }}
        />
      )}
    </div>
  );
}
