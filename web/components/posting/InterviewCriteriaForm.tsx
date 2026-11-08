"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Button from "@/components/common/Button";
import NumberInput from "@/components/common/NumberInput";
import Stepper from "@/components/common/Stepper";
import { ApiError, apiFetch } from "@/lib/api";
import { summarizeRatios } from "@/lib/ratio";
import type { EvalCriterion, InterviewCriteria, PostingDetail } from "@/types/posting";
import styles from "./InterviewCriteriaForm.module.css";
import shared from "./PostingInfoForm.module.css";
import RatioSection from "./RatioSection";

const STEPS = ["공고 정보", "서류 문항", "서류 평가기준", "면접 평가기준", "면접 질문", "검토"];
const QUESTION_COUNT_TOO_LOW = "QUESTION_COUNT_TOO_LOW";

const errorMessage = (e: unknown) => (e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다.");
const toText = (n: number | null) => (n === null ? "" : String(n));
const toNumber = (v: string) => (v === "" ? null : Number(v));

// 화면 07 면접 평가기준 등록 (ADM-008, ADM-011)
export default function InterviewCriteriaForm({ postingId }: { postingId: number }) {
  const router = useRouter();
  const [criteria, setCriteria] = useState<EvalCriterion[]>([]);
  // 입력 중인 값. 빈 문자열은 아직 입력하지 않은 항목이다 (0과 구분한다)
  const [values, setValues] = useState<Record<number, string>>({});
  const [questionCount, setQuestionCount] = useState("");
  const [followUp, setFollowUp] = useState<boolean | null>(null);
  const [thinkTime, setThinkTime] = useState("");
  const [answerTime, setAnswerTime] = useState("");
  const [writeStatus, setWriteStatus] = useState<PostingDetail["write_status"]>("임시 저장");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 출제 문제 개수가 등록된 기업 질문 수보다 작을 때 서버가 알려 주는 오류. 해당 입력 아래에 보여준다
  const [countError, setCountError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiFetch<PostingDetail>(`/api/admin/postings/${postingId}`),
      apiFetch<InterviewCriteria>(`/api/admin/postings/${postingId}/interview-criteria`),
    ])
      .then(([posting, d]) => {
        setWriteStatus(posting.write_status);
        setCriteria(d.criteria);
        setValues(Object.fromEntries(d.criteria.map((c) => [c.criteria_id, toText(c.ratio)])));
        setQuestionCount(toText(d.question_count));
        setFollowUp(d.follow_up_enabled);
        setThinkTime(toText(d.think_time_sec));
        setAnswerTime(toText(d.answer_time_sec));
      })
      .catch((e) => setLoadError(errorMessage(e)))
      .finally(() => setLoading(false));
  }, [postingId]);

  // 값을 고치면 이전 저장 결과(오류·안내)는 더 이상 맞지 않으므로 지운다
  function touch() {
    setError(null);
    setCountError(null);
    setNotice(null);
  }

  function setSetting(setter: (v: string) => void) {
    return (v: string) => {
      touch();
      setter(v);
    };
  }

  function onRatioChange(criteriaId: number, value: string) {
    touch();
    setValues((v) => ({ ...v, [criteriaId]: value }));
  }

  const itemError = (c: EvalCriterion) => {
    const v = values[c.criteria_id];
    if (Number(v) > 100) return "0~100 사이의 정수를 입력해 주세요.";
    // 비언어는 표정 분석이 실패했을 때만 빼고 계산하는 예외 규칙이 있어 0%로 정할 수 없다
    if (c.criteria_name === "비언어" && v === "0") return "비언어는 1% 이상 입력해 주세요.";
    return undefined;
  };
  const hasItemError = criteria.some((c) => itemError(c));
  const { sum } = summarizeRatios(criteria, values, hasItemError);

  // validate=false는 임시 저장(합계가 100 이하이면 됨), true는 '다음'(합계가 정확히 100, 모든 값 입력)
  async function save(validate: boolean): Promise<boolean> {
    touch();
    if (hasItemError) {
      setError("평가 요소 비율을 확인해 주세요.");
      return false;
    }
    // 합이 100을 넘으면 임시 저장도 할 수 없다. 서버도 같은 규칙으로 막는다
    if (sum > 100) {
      setError(`비율의 합은 100을 넘을 수 없습니다. 현재 ${sum}입니다.`);
      return false;
    }
    setSaving(true);
    try {
      await apiFetch(`/api/admin/postings/${postingId}/interview-criteria?validate=${validate}`, {
        method: "PUT",
        body: JSON.stringify({
          ratios: criteria.map((c) => ({ criteria_id: c.criteria_id, ratio: toNumber(values[c.criteria_id]) })),
          question_count: toNumber(questionCount),
          follow_up_enabled: followUp,
          think_time_sec: toNumber(thinkTime),
          answer_time_sec: toNumber(answerTime),
        }),
      });
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.code === QUESTION_COUNT_TOO_LOW) setCountError(e.message);
      else setError(errorMessage(e));
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function onTempSave() {
    if (await save(false)) setNotice("임시 저장되었습니다.");
  }

  async function onNext() {
    if (await save(true)) router.push(`/admin/postings/${postingId}/edit/company-questions`);
  }

  // 입력한 내용을 잃지 않도록 임시 저장하고 이동한다. 저장하지 못하면 이동하지 않는다
  async function onPrev() {
    if (await save(false)) router.push(`/admin/postings/${postingId}/edit/doc-criteria`);
  }

  if (loading) return null;
  if (loadError) return <p className={shared.loadError}>{loadError}</p>;

  return (
    <div className={shared.page}>
      <header className={shared.header}>
        <h1 className={shared.title}>{writeStatus === "등록 완료" ? "채용공고 수정" : "새 채용공고 등록"}</h1>
        <p className={shared.subtitle}>AI 화상 면접의 평가 요소와 진행 방식을 정합니다.</p>
      </header>

      <Stepper steps={STEPS} current={3} />

      <section className={shared.card}>
        <div className={shared.cardHead}>
          <h2 className={shared.cardTitle}>평가 요소 비율 *</h2>
          <p className={shared.cardDesc}>요소의 합은 100이어야 합니다.</p>
        </div>
        <RatioSection criteria={criteria} values={values} onChange={onRatioChange} itemError={itemError} />
      </section>

      <section className={shared.card}>
        <h2 className={shared.cardTitle}>진행 설정 *</h2>
        <div className={styles.settings}>
          <div className={styles.setting}>
            <div className={styles.settingText}>
              <label className={styles.settingName} htmlFor="question_count">
                출제 문제 개수
              </label>
              <p className={styles.settingDesc}>꼬리질문이 있으면 꼬리질문을 포함한 개수입니다.</p>
            </div>
            <NumberInput
              id="question_count"
              unit="개"
              value={questionCount}
              onValueChange={setSetting(setQuestionCount)}
              error={countError ?? undefined}
            />
          </div>

          <div className={styles.setting}>
            <div className={styles.settingText}>
              <span className={styles.settingName} id="follow_up_label">
                꼬리질문
              </span>
              <p className={styles.settingDesc}>
                직무 질문의 답변 점수(답변 내용·표정·발화 합산)가 80점 이상이면 꼬리질문을 만듭니다. 하나의 기본 질문에서
                최대 2개까지 만듭니다.
              </p>
            </div>
            <div className={styles.radios} role="radiogroup" aria-labelledby="follow_up_label">
              <label className={styles.radio}>
                <input
                  type="radio"
                  name="follow_up"
                  checked={followUp === true}
                  onChange={() => {
                    touch();
                    setFollowUp(true);
                  }}
                />
                사용
              </label>
              <label className={styles.radio}>
                <input
                  type="radio"
                  name="follow_up"
                  checked={followUp === false}
                  onChange={() => {
                    touch();
                    setFollowUp(false);
                  }}
                />
                사용 안 함
              </label>
            </div>
          </div>

          <div className={styles.setting}>
            <div className={styles.settingText}>
              <label className={styles.settingName} htmlFor="think_time_sec">
                생각 시간
              </label>
              <p className={styles.settingDesc}>질문을 보고 답변을 준비하는 시간입니다.</p>
            </div>
            <NumberInput id="think_time_sec" unit="초" value={thinkTime} onValueChange={setSetting(setThinkTime)} />
          </div>

          <div className={styles.setting}>
            <div className={styles.settingText}>
              <label className={styles.settingName} htmlFor="answer_time_sec">
                답변 시간
              </label>
              <p className={styles.settingDesc}>10초 이상 말이 없으면 답변 종료로 간주합니다.</p>
            </div>
            <NumberInput id="answer_time_sec" unit="초" value={answerTime} onValueChange={setSetting(setAnswerTime)} />
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
