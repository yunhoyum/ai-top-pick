"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Button from "@/components/common/Button";
import Stepper from "@/components/common/Stepper";
import { ApiError, apiFetch } from "@/lib/api";
import { summarizeRatios } from "@/lib/ratio";
import type { DocCriteria, EvalCriterion, PostingDetail } from "@/types/posting";
import shared from "./PostingInfoForm.module.css";
import RatioSection from "./RatioSection";

const STEPS = ["공고 정보", "서류 문항", "서류 평가기준", "면접 평가기준", "면접 질문", "검토"];

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

  function onChange(criteriaId: number, value: string) {
    setValues((v) => ({ ...v, [criteriaId]: value }));
    setError(null);
    setNotice(null);
  }

  const itemError = (c: EvalCriterion) =>
    Number(values[c.criteria_id]) > 100 ? "0~100 사이의 정수를 입력해 주세요." : undefined;
  const hasItemError = criteria.some((c) => itemError(c));
  const { sum } = summarizeRatios(criteria, values, hasItemError);

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
        <RatioSection criteria={criteria} values={values} onChange={onChange} itemError={itemError} preview />
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
        {writeStatus !== "등록 완료" && (
          <Button type="button" variant="secondary" inline disabled={saving} onClick={onTempSave}>
            임시 저장
          </Button>
        )}
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
