"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Button from "@/components/common/Button";
import Field from "@/components/common/Field";
import SelectField from "@/components/common/SelectField";
import Stepper from "@/components/common/Stepper";
import TextAreaField from "@/components/common/TextAreaField";
import { ApiError, apiFetch } from "@/lib/api";
import { formatPeriod, toInputValue, toIso } from "@/lib/format";
import { validateSchedule } from "@/lib/schedule";
import type { PostingDetail, PostingDocument } from "@/types/posting";
import DocumentList from "./DocumentList";
import styles from "./PostingInfoForm.module.css";

const STEPS = ["공고 정보", "서류 문항", "서류 평가기준", "면접 평가기준", "기업 질문", "검토"];

type FormState = {
  position_name: string;
  job_category: string;
  employment_type: string;
  job_description: string;
  doc_start_at: string;
  doc_end_at: string;
  interview_start_at: string;
  interview_end_at: string;
  doc_result_at: string;
  interview_result_at: string;
  functional_talent: string;
  nonfunctional_talent: string;
};

const EMPTY: FormState = {
  position_name: "",
  job_category: "",
  employment_type: "",
  job_description: "",
  doc_start_at: "",
  doc_end_at: "",
  interview_start_at: "",
  interview_end_at: "",
  doc_result_at: "",
  interview_result_at: "",
  functional_talent: "",
  nonfunctional_talent: "",
};

const DATETIME_KEYS = [
  "doc_start_at",
  "doc_end_at",
  "doc_result_at",
  "interview_start_at",
  "interview_end_at",
  "interview_result_at",
] as const;

const errorMessage = (e: unknown) => (e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다.");

// 화면 04 포지션 채용공고 입력 (ADM-004, ADM-005, ADM-011)
// postingId가 없으면 새 공고이고, 처음 저장하거나 파일을 올릴 때 공고를 만든다
export default function PostingInfoForm({ postingId: initialId }: { postingId?: number }) {
  const router = useRouter();
  const [form, setForm] = useState<FormState>(EMPTY);
  const [documents, setDocuments] = useState<PostingDocument[]>([]);
  const [writeStatus, setWriteStatus] = useState<PostingDetail["write_status"]>("임시 저장");
  const [loading, setLoading] = useState(initialId !== undefined);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [docError, setDocError] = useState<string | null>(null);

  const idRef = useRef<number | null>(initialId ?? null);
  const creating = useRef<Promise<number> | null>(null);

  useEffect(() => {
    if (initialId === undefined) return;
    apiFetch<PostingDetail>(`/api/admin/postings/${initialId}`)
      .then((d) => {
        setForm({
          position_name: d.position_name ?? "",
          job_category: d.job_category ?? "",
          employment_type: d.employment_type ?? "",
          job_description: d.job_description ?? "",
          doc_start_at: toInputValue(d.doc_start_at),
          doc_end_at: toInputValue(d.doc_end_at),
          interview_start_at: toInputValue(d.interview_start_at),
          interview_end_at: toInputValue(d.interview_end_at),
          doc_result_at: toInputValue(d.doc_result_at),
          interview_result_at: toInputValue(d.interview_result_at),
          functional_talent: d.functional_talent ?? "",
          nonfunctional_talent: d.nonfunctional_talent ?? "",
        });
        setDocuments(d.documents);
        setWriteStatus(d.write_status);
      })
      .catch((e) => setLoadError(errorMessage(e)))
      .finally(() => setLoading(false));
  }, [initialId]);

  // 값을 고치면 이전 저장 결과(오류·안내)는 더 이상 맞지 않으므로 지운다
  const set = (key: keyof FormState) => (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
  ) => {
    setForm((f) => ({ ...f, [key]: e.target.value }));
    setError(null);
    setNotice(null);
  };

  // 입력하는 동안 바로 보여 주는 일정 순서 오류. 해당 입력 아래에 표시한다
  const scheduleErrors = validateSchedule(form);

  // 공고가 아직 없으면 만들고 id를 돌려준다. 저장과 파일 업로드가 동시에 눌려도 한 번만 만든다
  function ensurePostingId(): Promise<number> {
    if (idRef.current !== null) return Promise.resolve(idRef.current);
    creating.current ??= apiFetch<{ posting_id: number }>("/api/admin/postings", { method: "POST" })
      .then((r) => {
        idRef.current = r.posting_id;
        // 화면 상태를 잃지 않도록 페이지를 다시 그리지 않고 주소만 바꾼다
        window.history.replaceState(null, "", `/admin/postings/${r.posting_id}/edit/info`);
        return r.posting_id;
      })
      .catch((e) => {
        creating.current = null;
        throw e;
      });
    return creating.current;
  }

  function buildBody() {
    const text = (v: string) => v.trim() || null;
    const body: Record<string, string | null> = {
      position_name: text(form.position_name),
      job_category: text(form.job_category),
      employment_type: form.employment_type || null,
      job_description: text(form.job_description),
      functional_talent: text(form.functional_talent),
      nonfunctional_talent: text(form.nonfunctional_talent),
    };
    for (const key of DATETIME_KEYS) body[key] = form[key] ? toIso(form[key]) : null;
    return body;
  }

  // validate=false는 임시 저장(필수 항목 검사 없음), true는 '다음'
  async function save(validate: boolean): Promise<number | null> {
    setError(null);
    setNotice(null);
    if (Object.keys(scheduleErrors).length > 0) {
      setError("전형별 일정을 확인해 주세요.");
      return null;
    }
    setSaving(true);
    try {
      const id = await ensurePostingId();
      await apiFetch(`/api/admin/postings/${id}/info?validate=${validate}`, {
        method: "PUT",
        body: JSON.stringify(buildBody()),
      });
      return id;
    } catch (e) {
      setError(errorMessage(e));
      return null;
    } finally {
      setSaving(false);
    }
  }

  async function onTempSave() {
    if ((await save(false)) !== null) setNotice("임시 저장되었습니다.");
  }

  async function onNext() {
    const id = await save(true);
    if (id !== null) router.push(`/admin/postings/${id}/edit/doc-items`);
  }

  async function onUpload(files: File[]) {
    setDocError(null);
    setUploading(true);
    try {
      const id = await ensurePostingId();
      for (const file of files) {
        const data = new FormData();
        data.append("file", file);
        try {
          const doc = await apiFetch<PostingDocument>(`/api/admin/postings/${id}/documents`, {
            method: "POST",
            body: data,
          });
          setDocuments((d) => [...d, doc]);
        } catch (e) {
          setDocError(`${file.name}: ${errorMessage(e)}`);
        }
      }
    } catch (e) {
      setDocError(errorMessage(e));
    } finally {
      setUploading(false);
    }
  }

  async function onDeleteDocument(documentId: number) {
    setDocError(null);
    try {
      await apiFetch(`/api/admin/postings/${idRef.current}/documents/${documentId}`, { method: "DELETE" });
      setDocuments((d) => d.filter((x) => x.document_id !== documentId));
    } catch (e) {
      setDocError(errorMessage(e));
    }
  }

  if (loading) return null;
  if (loadError) return <p className={styles.loadError}>{loadError}</p>;

  const period = formatPeriod(form.doc_start_at, form.interview_result_at);

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>{writeStatus === "등록 완료" ? "채용공고 수정" : "새 채용공고 등록"}</h1>
        <p className={styles.subtitle}>지원자가 보는 채용공고의 기본 내용을 입력합니다.</p>
      </header>

      <Stepper steps={STEPS} current={0} />

      <section className={styles.card}>
        <h2 className={styles.cardTitle}>기본 정보</h2>
        <div className={styles.grid}>
          <Field label="포지션명 *" name="position_name" placeholder="예) 백엔드 개발자 (신입)" value={form.position_name} onChange={set("position_name")} />
          <Field label="직무 분류 *" name="job_category" placeholder="예) 백엔드" value={form.job_category} onChange={set("job_category")} />
          <SelectField
            label="고용 형태 *"
            name="employment_type"
            placeholder="선택"
            options={["정규직", "계약직"]}
            value={form.employment_type}
            onChange={set("employment_type")}
          />
        </div>
        <TextAreaField label="직무 설명 *" name="job_description" placeholder="담당 업무와 사용 기술을 입력해 주세요" value={form.job_description} onChange={set("job_description")} />
      </section>

      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>전형별 일정 *</h2>
          <p className={styles.cardDesc}>
            전형별 기한을 입력하면 전체 채용 기간이 자동으로 계산됩니다. 일정은 서류 접수 → 서류 합격자 발표 → 면접 → 면접
            합격자 발표 순서여야 합니다.
          </p>
        </div>
        <div className={styles.grid}>
          <Field label="서류 접수 시작" name="doc_start_at" type="datetime-local" value={form.doc_start_at} onChange={set("doc_start_at")} />
          <Field label="서류 접수 마감" name="doc_end_at" error={scheduleErrors.doc_end_at} type="datetime-local" value={form.doc_end_at} onChange={set("doc_end_at")} />
          <Field label="면접 시작" name="interview_start_at" error={scheduleErrors.interview_start_at} type="datetime-local" value={form.interview_start_at} onChange={set("interview_start_at")} />
          <Field label="면접 마감" name="interview_end_at" error={scheduleErrors.interview_end_at} type="datetime-local" value={form.interview_end_at} onChange={set("interview_end_at")} />
          <Field label="서류 합격자 발표 일시" name="doc_result_at" error={scheduleErrors.doc_result_at} type="datetime-local" value={form.doc_result_at} onChange={set("doc_result_at")} />
          <Field label="면접 합격자 발표 일시" name="interview_result_at" error={scheduleErrors.interview_result_at} type="datetime-local" value={form.interview_result_at} onChange={set("interview_result_at")} />
        </div>
        <div className={styles.period}>
          <span className={styles.periodLabel}>전체 채용 기간</span>
          <span className={styles.periodValue}>{period ? `${period} (자동 계산)` : "일정을 입력하면 자동으로 계산됩니다"}</span>
        </div>
      </section>

      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>인재상 *</h2>
          <p className={styles.cardDesc}>
            서류와 면접 평가에서 지원자와 비교하는 기준입니다. 상세히 작성해 주시면 지원자를 면밀히 파악할 수 있습니다.
          </p>
        </div>
        <div className={styles.grid}>
          <TextAreaField label="기능적 인재상 *" name="functional_talent" placeholder="예) Spring 기반 REST API 설계·구현 경험" value={form.functional_talent} onChange={set("functional_talent")} />
          <TextAreaField label="비기능적 인재상 *" name="nonfunctional_talent" placeholder="예) 문제를 끝까지 파고드는 태도" value={form.nonfunctional_talent} onChange={set("nonfunctional_talent")} />
        </div>
      </section>

      <DocumentList documents={documents} uploading={uploading} error={docError} onUpload={onUpload} onDelete={onDeleteDocument} />

      {error && (
        <p className={styles.formError} role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className={styles.notice} role="status">
          {notice}
        </p>
      )}

      <div className={styles.actions}>
        <Button type="button" variant="secondary" inline disabled={saving} onClick={onTempSave}>
          임시 저장
        </Button>
        <span className={styles.spacer} />
        <Button type="button" variant="ghost" inline onClick={() => router.push("/admin/postings")}>
          취소
        </Button>
        <Button type="button" inline disabled={saving} onClick={onNext}>
          다음
        </Button>
      </div>
    </div>
  );
}
