"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Button from "@/components/common/Button";
import fieldStyles from "@/components/common/Field.module.css";
import Stepper from "@/components/common/Stepper";
import { ApiError, apiFetch } from "@/lib/api";
import { splitAiQuestions } from "@/lib/interview";
import type { CompanyQuestions, PostingDetail } from "@/types/posting";
import styles from "./CompanyQuestionsForm.module.css";
import shared from "./PostingInfoForm.module.css";

const STEPS = ["공고 정보", "서류 문항", "서류 평가기준", "면접 평가기준", "기업 질문", "검토"];

type Row = { key: number; text: string };

const errorMessage = (e: unknown) => (e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다.");

// 화면 08 기업 질문 등록 (ADM-009, ADM-011, ADM-032)
export default function CompanyQuestionsForm({ postingId }: { postingId: number }) {
  const router = useRouter();
  const nextKey = useRef(0);

  const [rows, setRows] = useState<Row[]>([]);
  const [questionCount, setQuestionCount] = useState<number | null>(null);
  // 직무 질문 비율(%). null은 아직 정하지 않은 상태다
  const [ratio, setRatio] = useState<number | null>(null);
  const [newText, setNewText] = useState("");
  const [editingKey, setEditingKey] = useState<number | null>(null);
  const [editText, setEditText] = useState("");
  const [newError, setNewError] = useState<string | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const [writeStatus, setWriteStatus] = useState<PostingDetail["write_status"]>("임시 저장");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiFetch<PostingDetail>(`/api/admin/postings/${postingId}`),
      apiFetch<CompanyQuestions>(`/api/admin/postings/${postingId}/company-questions`),
    ])
      .then(([posting, d]) => {
        setWriteStatus(posting.write_status);
        setRows(d.questions.map((text) => ({ key: nextKey.current++, text })));
        setQuestionCount(d.question_count);
        setRatio(d.job_question_ratio);
      })
      .catch((e) => setLoadError(errorMessage(e)))
      .finally(() => setLoading(false));
  }, [postingId]);

  // 값을 고치면 이전 저장 결과(오류·안내)는 더 이상 맞지 않으므로 지운다
  function touch() {
    setError(null);
    setNotice(null);
    setNewError(null);
    setEditError(null);
  }

  const count = rows.length;
  const noLimit = questionCount === null;
  const full = questionCount !== null && count >= questionCount;
  // AI 질문이 하나도 없으면 직무/인성 비율은 필요 없다
  const aiCount = questionCount === null ? null : Math.max(questionCount - count, 0);
  const sliderDisabled = aiCount === null || aiCount === 0;

  function addQuestion() {
    touch();
    const text = newText.trim();
    if (!text || noLimit || full) return;
    setRows((r) => [...r, { key: nextKey.current++, text }]);
    setNewText("");
  }

  function startEdit(row: Row) {
    touch();
    setEditingKey(row.key);
    setEditText(row.text);
  }

  function saveEdit() {
    const text = editText.trim();
    if (!text) {
      setEditError("질문 내용을 입력해 주세요.");
      return;
    }
    touch();
    setRows((r) => r.map((x) => (x.key === editingKey ? { ...x, text } : x)));
    setEditingKey(null);
  }

  function removeQuestion(key: number) {
    touch();
    if (editingKey === key) setEditingKey(null);
    setRows((r) => r.filter((x) => x.key !== key));
  }

  // validate=false는 임시 저장, true는 '다음'
  async function save(validate: boolean): Promise<boolean> {
    touch();
    // 입력 중이던 내용이 저장에서 조용히 빠지지 않도록 먼저 확정하게 한다
    if (editingKey !== null) {
      setEditError("수정 중인 질문을 저장하거나 취소해 주세요.");
      return false;
    }
    if (newText.trim()) {
      setNewError("입력한 질문을 추가하거나 지워 주세요.");
      return false;
    }
    setSaving(true);
    try {
      await apiFetch(`/api/admin/postings/${postingId}/company-questions?validate=${validate}`, {
        method: "PUT",
        body: JSON.stringify({ questions: rows.map((r) => r.text), job_question_ratio: ratio }),
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
    if (await save(true)) router.push(`/admin/postings/${postingId}/edit/review`);
  }

  // 입력한 내용을 잃지 않도록 임시 저장하고 이동한다. 저장하지 못하면 이동하지 않는다
  async function onPrev() {
    if (await save(false)) router.push(`/admin/postings/${postingId}/edit/interview-criteria`);
  }

  function summary(): string {
    if (aiCount === null) return "출제 문제 개수를 입력하면 AI 질문 수를 계산해 보여줍니다.";
    const base = `AI 질문 ${aiCount}개 (출제 ${questionCount}개 − 기업 질문 ${count}개)`;
    if (aiCount === 0) return `현재 설정 기준: ${base}. 비율은 적용되지 않습니다.`;
    if (ratio === null) return `현재 설정 기준: ${base}. 직무/인성 비율을 설정하면 질문 수를 계산해 보여줍니다.`;
    const { job, personality } = splitAiQuestions(questionCount!, count, ratio);
    return `현재 설정 기준: ${base} → 직무 ${job}개 · 인성 ${personality}개`;
  }

  if (loading) return null;
  if (loadError) return <p className={shared.loadError}>{loadError}</p>;

  const sliderValue = ratio ?? 50;

  return (
    <div className={shared.page}>
      <header className={shared.header}>
        <h1 className={shared.title}>{writeStatus === "등록 완료" ? "채용공고 수정" : "새 채용공고 등록"}</h1>
        <p className={shared.subtitle}>모든 지원자에게 공통으로 확인하고 싶은 질문을 등록합니다.</p>
      </header>

      <Stepper steps={STEPS} current={4} />

      <section className={shared.card}>
        <div className={styles.cardHead}>
          <h2 className={shared.cardTitle}>기업 질문</h2>
          <span className={styles.badge}>
            {count} / {questionCount ?? "-"}
          </span>
        </div>

        {noLimit ? (
          <p className={`${styles.notice} ${styles.noticeWarn}`}>
            출제 문제 개수가 아직 입력되지 않았습니다.{" "}
            <Link href={`/admin/postings/${postingId}/edit/interview-criteria`} className={styles.noticeLink}>
              면접 평가기준
            </Link>
            에서 먼저 입력해 주세요.
          </p>
        ) : (
          <p className={styles.notice}>
            기업 질문은 출제 문제 개수({questionCount}개)를 넘길 수 없습니다. 나머지는 지원자 서류 기반 AI 질문과 꼬리질문으로
            진행됩니다.
          </p>
        )}

        {rows.map((row, i) => (
          <div key={row.key} className={styles.item}>
            <span className={styles.itemNo}>Q{i + 1}</span>
            {editingKey === row.key ? (
              <div className={styles.editWrap}>
                <input
                  className={`${fieldStyles.input} ${editError ? fieldStyles.invalid : ""}`}
                  aria-label={`Q${i + 1} 질문 수정`}
                  value={editText}
                  autoFocus
                  onChange={(e) => {
                    setEditText(e.target.value);
                    setEditError(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") saveEdit();
                    if (e.key === "Escape") setEditingKey(null);
                  }}
                />
                {editError && <p className={fieldStyles.error}>{editError}</p>}
              </div>
            ) : (
              <p className={styles.itemText}>{row.text}</p>
            )}
            {editingKey === row.key ? (
              <>
                <button type="button" className={styles.action} onClick={saveEdit}>
                  저장
                </button>
                <button type="button" className={styles.action} onClick={() => setEditingKey(null)}>
                  취소
                </button>
              </>
            ) : (
              <>
                <button type="button" className={styles.action} onClick={() => startEdit(row)}>
                  수정
                </button>
                <button type="button" className={`${styles.action} ${styles.danger}`} onClick={() => removeQuestion(row.key)}>
                  삭제
                </button>
              </>
            )}
          </div>
        ))}

        <div className={styles.addRow}>
          <div className={fieldStyles.field}>
            <label className={fieldStyles.label} htmlFor="new_question">
              새 질문
            </label>
            <input
              id="new_question"
              className={`${fieldStyles.input} ${newError ? fieldStyles.invalid : ""}`}
              placeholder="질문을 입력해 주세요"
              value={newText}
              disabled={noLimit || full}
              onChange={(e) => {
                setNewText(e.target.value);
                setNewError(null);
              }}
              onKeyDown={(e) => e.key === "Enter" && addQuestion()}
            />
            {newError && <p className={fieldStyles.error}>{newError}</p>}
            {full && <p className={styles.hint}>출제 문제 개수만큼 등록했습니다. 더 추가하려면 출제 문제 개수를 늘려 주세요.</p>}
          </div>
          <Button
            type="button"
            variant="secondary"
            inline
            className={styles.addButton}
            disabled={noLimit || full || !newText.trim()}
            onClick={addQuestion}
          >
            추가
          </Button>
        </div>
      </section>

      <section className={shared.card}>
        <h2 className={shared.cardTitle}>AI 질문 비율 (직무 / 인성) *</h2>
        <p className={styles.notice}>
          비율은 AI 생성 질문(출제 문제 개수 − 기업 질문 수)에만 적용됩니다. 직무 질문 수는 반올림하고, 인성 질문은 나머지
          개수입니다. 질문은 직무 → 인성 → 기업 질문 순으로 진행됩니다.
        </p>

        <div className={styles.slider}>
          <div className={styles.side}>
            <span className={styles.sideLabel}>직무</span>
            <span className={`${styles.sideValue} ${styles.job}`}>{ratio === null ? "--" : `${ratio}%`}</span>
          </div>
          <input
            type="range"
            className={`${styles.range} ${ratio === null ? styles.unset : ""}`}
            style={{ ["--fill" as string]: ratio === null ? "0%" : `${sliderValue}%` }}
            min={0}
            max={100}
            step={1}
            value={sliderValue}
            disabled={sliderDisabled}
            aria-label="직무 질문 비율"
            onChange={(e) => {
              touch();
              setRatio(Number(e.target.value));
            }}
            // 값이 바뀌지 않는 클릭(핸들을 그대로 누름)도 '설정함'으로 처리한다
            onPointerUp={(e) => {
              if (ratio === null) setRatio(Number(e.currentTarget.value));
            }}
          />
          <div className={`${styles.side} ${styles.sideEnd}`}>
            <span className={styles.sideLabel}>인성</span>
            <span className={`${styles.sideValue} ${styles.personality}`}>{ratio === null ? "--" : `${100 - ratio}%`}</span>
          </div>
        </div>

        <p className={styles.summary}>{summary()}</p>
        {ratio === null && !sliderDisabled && <p className={styles.hint}>아직 설정하지 않았습니다. 슬라이더를 움직여 비율을 정해 주세요.</p>}
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
