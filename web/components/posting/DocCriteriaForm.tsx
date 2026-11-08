"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Button from "@/components/common/Button";
import Stepper from "@/components/common/Stepper";
import { ApiError, apiFetch } from "@/lib/api";
import type { DocCriteria, EvalCriterion, PostingDetail } from "@/types/posting";
import shared from "./PostingInfoForm.module.css";
import styles from "./DocCriteriaForm.module.css";

const STEPS = ["공고 정보", "서류 문항", "서류 평가기준", "면접 평가기준", "기업 질문", "검토"];
const SEGMENT_CLASSES = [styles.seg0, styles.seg1, styles.seg2, styles.seg3];

const errorMessage = (e: unknown) => (e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다.");

// 화면 06 서류 평가기준 등록 (ADM-007, ADM-011)
export default function DocCriteriaForm({ postingId }: { postingId: number }) {
  const router = useRouter();
  const [criteria, setCriteria] = useState<EvalCriterion[]>([]);
  // 입력 중인 값. 빈 문자열은 아직 입력하지 않은 항목이다 (0%와 구분한다)
  const [values, setValues] = useState<Record<number, string>>({});
  const [writeStatus, setWriteStatus] = useState<PostingDetail["write_status"]>("임시 저장");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiFetch<PostingDetail>(`/api/admin/postings/${postingId}`),
      apiFetch<DocCriteria>(`/api/admin/postings/${postingId}/doc-criteria`),
    ])
      .then(([posting, d]) => {
        setWriteStatus(posting.write_status);
        setCriteria(d.criteria);
        setValues(Object.fromEntries(d.criteria.map((c) => [c.criteria_id, c.ratio === null ? "" : String(c.ratio)])));
      })
      .catch((e) => setLoadError(errorMessage(e)))
      .finally(() => setLoading(false));
  }, [postingId]);

  function onChange(criteriaId: number, raw: string) {
    // 숫자만, 최대 3자리. 앞의 0은 지운다 ("007" → "7")
    const digits = raw.replace(/\D/g, "").slice(0, 3);
    setValues((v) => ({ ...v, [criteriaId]: digits === "" ? "" : String(Number(digits)) }));
    setError(null);
    setNotice(null);
  }

  const numbers = criteria.map((c) => (values[c.criteria_id] ? Number(values[c.criteria_id]) : 0));
  const sum = numbers.reduce((a, b) => a + b, 0);
  const blanks = criteria.filter((c) => values[c.criteria_id] === "").length;
  const itemError = (id: number) =>
    Number(values[id]) > 100 ? "0~100 사이의 정수를 입력해 주세요." : undefined;
  const hasItemError = criteria.some((c) => itemError(c.criteria_id));
  const complete = sum === 100 && blanks === 0 && !hasItemError;

  function status(): { text: string; tone: "ok" | "warn" | "bad" } {
    if (complete) return { text: "입력 완료", tone: "ok" };
    if (blanks === criteria.length) return { text: "비율을 입력해 주세요", tone: "warn" };
    if (sum > 100) return { text: `${sum - 100} 초과`, tone: "bad" };
    if (sum < 100) return { text: `${100 - sum} 부족`, tone: "warn" };
    return { text: "비어 있는 항목이 있습니다", tone: "warn" };
  }

  // validate=false는 임시 저장(합계가 100 이하이면 됨), true는 '다음'(합계가 정확히 100)
  async function save(validate: boolean): Promise<boolean> {
    setError(null);
    setNotice(null);
    if (hasItemError) {
      setError("비율은 0~100 사이의 정수로 입력해 주세요.");
      return false;
    }
    // 합이 100을 넘으면 임시 저장도 할 수 없다. 서버도 같은 규칙으로 막는다
    if (sum > 100) {
      setError(`비율의 합은 100을 넘을 수 없습니다. 현재 ${sum}입니다.`);
      return false;
    }
    setSaving(true);
    try {
      await apiFetch(`/api/admin/postings/${postingId}/doc-criteria?validate=${validate}`, {
        method: "PUT",
        body: JSON.stringify({
          ratios: criteria.map((c) => ({
            criteria_id: c.criteria_id,
            ratio: values[c.criteria_id] === "" ? null : Number(values[c.criteria_id]),
          })),
        }),
      });
      return true;
    } catch (e) {
      setError(errorMessage(e));
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function onTempSave() {
    if (await save(false)) setNotice("임시 저장되었습니다.");
  }

  async function onNext() {
    if (await save(true)) router.push(`/admin/postings/${postingId}/edit/interview-criteria`);
  }

  // 입력한 내용을 잃지 않도록 임시 저장하고 이동한다. 저장하지 못하면 이동하지 않는다
  async function onPrev() {
    if (await save(false)) router.push(`/admin/postings/${postingId}/edit/doc-items`);
  }

  if (loading) return null;
  if (loadError) return <p className={shared.loadError}>{loadError}</p>;

  const { text, tone } = status();

  return (
    <div className={shared.page}>
      <header className={shared.header}>
        <h1 className={shared.title}>{writeStatus === "등록 완료" ? "채용공고 수정" : "새 채용공고 등록"}</h1>
        <p className={shared.subtitle}>서류 전형의 평가 항목별 비율을 정합니다.</p>
      </header>

      <Stepper steps={STEPS} current={2} />

      <section className={shared.card}>
        <div className={shared.cardHead}>
          <h2 className={shared.cardTitle}>평가 항목 비율 *</h2>
          <p className={shared.cardDesc}>
            AI가 회사 인재상과의 유사도를 기준으로 각 항목을 평가합니다. 비율의 합은 100이어야 합니다.
          </p>
        </div>

        {criteria.map((c) => {
          const err = itemError(c.criteria_id);
          return (
            <div key={c.criteria_id} className={styles.row}>
              <div className={styles.rowText}>
                <label className={styles.rowName} htmlFor={`ratio-${c.criteria_id}`}>
                  {c.criteria_name}
                </label>
                {c.description && <p className={styles.rowDesc}>{c.description}</p>}
              </div>
              <div className={styles.rowInput}>
                <div className={`${styles.numberBox} ${err ? styles.invalid : ""}`}>
                  <input
                    id={`ratio-${c.criteria_id}`}
                    className={styles.number}
                    inputMode="numeric"
                    autoComplete="off"
                    placeholder="0"
                    aria-invalid={err ? true : undefined}
                    value={values[c.criteria_id] ?? ""}
                    onChange={(e) => onChange(c.criteria_id, e.target.value)}
                  />
                  <span className={styles.unit}>%</span>
                </div>
                {err && <p className={styles.itemError}>{err}</p>}
              </div>
            </div>
          );
        })}

        <div className={styles.total}>
          <span className={styles.totalLabel}>합계</span>
          <span className={`${styles.totalValue} ${styles[`total_${tone}`]}`}>{sum} / 100</span>
          <span className={`${styles.badge} ${styles[`badge_${tone}`]}`} role="status">
            {text}
          </span>
        </div>

        <div className={styles.preview}>
          <p className={styles.previewLabel}>미리보기</p>
          <div className={styles.bar} aria-hidden="true">
            {criteria.map((c, i) =>
              numbers[i] > 0 ? (
                <span key={c.criteria_id} className={SEGMENT_CLASSES[i % SEGMENT_CLASSES.length]} style={{ flexGrow: numbers[i] }} />
              ) : null,
            )}
            {sum < 100 && <span style={{ flexGrow: 100 - sum }} />}
          </div>
        </div>
      </section>

      {error && (
        <p className={shared.formError} role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className={shared.notice} role="status">
          {notice}
        </p>
      )}

      <div className={shared.actions}>
        <Button type="button" variant="secondary" inline disabled={saving} onClick={onTempSave}>
          임시 저장
        </Button>
        <span className={shared.spacer} />
        <Button type="button" variant="secondary" inline disabled={saving} onClick={onPrev}>
          이전
        </Button>
        <Button type="button" inline disabled={saving} onClick={onNext}>
          다음
        </Button>
      </div>
    </div>
  );
}
