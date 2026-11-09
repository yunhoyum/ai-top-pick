"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Badge from "@/components/common/Badge";
import Button from "@/components/common/Button";
import Stepper from "@/components/common/Stepper";
import { ApiError, apiFetch } from "@/lib/api";
import { fetchMeIfLoggedIn } from "@/lib/auth";
import { endBadge } from "@/lib/dday";
import { formatFullDateWeek } from "@/lib/format";
import type { ApplicationData } from "@/types/application";
import AdminPreviewNotice from "../AdminPreviewNotice";
import styles from "./Apply.module.css";
import { ResumeStep, EssaysStep, SkillsStep } from "./ApplySteps";
import {
  STEPS,
  essaysBody,
  resumeBody,
  skillsBody,
  stepDone,
  toFormState,
  validateStep,
  type FormState,
} from "./applyState";
import CompleteView from "./CompleteView";
import PortfolioStep from "./PortfolioStep";

const PREVIEW_MESSAGE = "관리자 계정은 접수되지 않습니다.";
const errorMessage = (e: unknown) => (e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다.");

// 화면 12~16 지원서 작성과 제출 (APP-005~011)
export default function ApplyView({ postingId }: { postingId: number }) {
  const router = useRouter();
  const base = `/api/postings/${postingId}/application`;
  const [data, setData] = useState<ApplicationData | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [step, setStep] = useState(0);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      // 비로그인이면 로그인한 뒤 이 화면으로 돌아오게 한다
      const me = await fetchMeIfLoggedIn();
      if (cancelled) return;
      if (!me) return router.replace(`/login?next=${encodeURIComponent(`/postings/${postingId}/apply`)}`);
      try {
        const d = await apiFetch<ApplicationData>(base);
        if (cancelled) return;
        setData(d);
        setForm(toFormState(d));
      } catch (e) {
        if (cancelled) return;
        // 서류 접수 중이 아닌 공고는 상세로 돌려보낸다
        if (e instanceof ApiError && e.code === "APPLICATION_CLOSED") router.replace(`/postings/${postingId}`);
        else setLoadError(errorMessage(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [base, postingId, router]);

  if (loadError) return <p className={styles.loadError}>{loadError}</p>;
  if (!data || !form) return null;
  if (data.write_status === "제출") return <CompleteView data={data} />;

  const preview = data.preview;
  const topics = data.form.essay_topics;
  const dday = endBadge(data.posting.doc_end_at);
  const hasPortfolio = data.portfolio !== null;

  function change(next: React.SetStateAction<FormState>) {
    setForm((s) => (typeof next === "function" ? next(s!) : next));
    setNotice(null);
  }

  // 한 단계를 서버에 저장한다. validate=false는 임시 저장
  async function saveStep(i: number, validate: boolean) {
    const f = form!;
    const [path, body] =
      i === 0 ? ["resume", resumeBody(f)] : i === 1 ? ["skills", skillsBody(f)] : ["essays", essaysBody(f)];
    const updated = await apiFetch<ApplicationData>(`${base}/${path}?validate=${validate}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
    setData(updated);
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setMessage(null);
    setNotice(null);
    try {
      await action();
    } catch (e) {
      setMessage(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const saveAllAsDraft = async () => {
    for (const i of [0, 1, 2]) await saveStep(i, false);
  };

  async function onDraft() {
    if (preview) return setNotice(PREVIEW_MESSAGE);
    await run(async () => {
      await saveAllAsDraft();
      setNotice("임시 저장했습니다.");
    });
  }

  async function onNext() {
    if (preview) {
      setStep(step + 1);
      return;
    }
    const errs = validateStep(step, form!, topics);
    setErrors(errs);
    if (Object.keys(errs).length > 0) return setMessage("입력한 내용을 확인해 주세요.");
    await run(async () => {
      await saveStep(step, true);
      setStep(step + 1);
    });
  }

  async function onSubmit() {
    if (preview) return setNotice(PREVIEW_MESSAGE);
    const todo = STEPS.filter((_, i) => !stepDone(i, form!, topics, hasPortfolio));
    if (todo.length > 0) return setMessage(`작성하지 않은 단계가 있습니다: ${todo.join(", ")}`);
    await run(async () => {
      await saveAllAsDraft(); // 이전 단계에서 고친 내용까지 서버에 반영한 뒤 제출한다
      setData(await apiFetch<ApplicationData>(`${base}/submit`, { method: "POST" }));
    });
  }

  async function onUpload(file: File) {
    if (preview) return setNotice(PREVIEW_MESSAGE);
    setUploading(true);
    setPortfolioError(null);
    setMessage(null);
    try {
      const body = new FormData();
      body.append("file", file);
      setData(await apiFetch<ApplicationData>(`${base}/portfolio`, { method: "POST", body }));
    } catch (e) {
      setPortfolioError(errorMessage(e));
    } finally {
      setUploading(false);
    }
  }

  async function onDeletePortfolio() {
    if (preview) return;
    setPortfolioError(null);
    setMessage(null);
    try {
      setData(await apiFetch<ApplicationData>(`${base}/portfolio`, { method: "DELETE" }));
    } catch (e) {
      setPortfolioError(errorMessage(e));
    }
  }

  function go(i: number) {
    setStep(i);
    setErrors({});
    setMessage(null);
    setNotice(null);
  }

  return (
    <div className={styles.page}>
      {preview && <AdminPreviewNotice />}

      <header className={styles.header}>
        <div className={styles.headText}>
          <h1 className={styles.title}>{data.posting.position_name} 지원서</h1>
          <p className={styles.subtitle}>서류 접수 마감 {formatFullDateWeek(data.posting.doc_end_at)}</p>
        </div>
        {dday && <Badge tone={dday.tone}>{dday.label}</Badge>}
      </header>

      <Stepper steps={STEPS} current={step} />

      {step === 0 && (
        <ResumeStep
          state={form}
          setState={change}
          errors={errors}
          has={{ education: data.form.has_education, career: data.form.has_career, project: data.form.has_project }}
        />
      )}
      {step === 1 && <SkillsStep state={form} setState={change} errors={errors} />}
      {step === 2 && <EssaysStep state={form} setState={change} errors={errors} topics={topics} />}
      {step === 3 && (
        <PortfolioStep
          portfolio={data.portfolio}
          uploading={uploading}
          error={portfolioError}
          onUpload={onUpload}
          onDelete={onDeletePortfolio}
          checklist={[
            { label: "이력서", done: stepDone(0, form, topics, hasPortfolio) },
            { label: "사용기술·기술 적용 사례", done: stepDone(1, form, topics, hasPortfolio) },
            { label: "자기소개서", done: stepDone(2, form, topics, hasPortfolio) },
            { label: "포트폴리오", done: hasPortfolio },
          ]}
        />
      )}

      {message && (
        <p className={styles.error} role="alert">
          {message}
        </p>
      )}
      {notice && (
        <p className={styles.notice} role="status">
          {notice}
        </p>
      )}

      <div className={styles.actions}>
        <Button type="button" variant="secondary" inline disabled={busy} onClick={onDraft}>
          임시 저장
        </Button>
        <div className={styles.spacer} />
        {step > 0 && (
          <Button type="button" variant="secondary" inline disabled={busy} onClick={() => go(step - 1)}>
            이전
          </Button>
        )}
        {step < 3 ? (
          <Button type="button" inline disabled={busy} onClick={onNext}>
            다음
          </Button>
        ) : (
          <Button type="button" inline disabled={busy || uploading} onClick={onSubmit}>
            서류 제출
          </Button>
        )}
      </div>
    </div>
  );
}
