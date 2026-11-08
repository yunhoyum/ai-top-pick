"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Button from "@/components/common/Button";
import Stepper from "@/components/common/Stepper";
import { API_URL, ApiError, apiFetch } from "@/lib/api";
import { formatFileSize, formatMonthDay, formatMonthDayTime } from "@/lib/format";
import { splitAiQuestions } from "@/lib/interview";
import type { Review, ReviewStep } from "@/types/posting";
import shared from "./PostingInfoForm.module.css";
import RatioBar from "./RatioBar";
import styles from "./ReviewForm.module.css";

const STEPS = ["공고 정보", "서류 문항", "서류 평가기준", "면접 평가기준", "기업 질문", "검토"];
// Figma 막대 색: 서류 평가기준은 4색, 면접 평가기준은 3색 (언어는 accent-600, 비언어는 accent-300)
const DOC_COLORS = ["var(--primary-700)", "var(--primary-500)", "var(--accent-600)", "var(--accent-300)"];
const INTERVIEW_COLORS = ["var(--primary-700)", "var(--accent-600)", "var(--accent-300)"];

const errorMessage = (e: unknown) => (e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다.");

// 카드 머리: 제목, 수정 링크, 아직 완료하지 못한 단계 안내
function CardHead({ title, href, incomplete }: { title: string; href: string; incomplete?: boolean }) {
  return (
    <>
      <div className={styles.head}>
        <h2 className={styles.title}>{title}</h2>
        <Link href={href} className={styles.edit}>
          수정
        </Link>
      </div>
      {incomplete && <p className={styles.incomplete}>아직 완료하지 않은 단계입니다. 수정을 눌러 입력해 주세요.</p>}
    </>
  );
}

// 화면 09 작성 내용 최종 검토 (ADM-010)
export default function ReviewForm({ postingId }: { postingId: number }) {
  const router = useRouter();
  const [review, setReview] = useState<Review | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    () =>
      apiFetch<Review>(`/api/admin/postings/${postingId}/review`)
        .then(setReview)
        .catch((e) => setLoadError(errorMessage(e))),
    [postingId],
  );

  useEffect(() => {
    load();
  }, [load]);

  async function onPublish() {
    setError(null);
    setPublishing(true);
    try {
      await apiFetch(`/api/admin/postings/${postingId}/publish`, { method: "POST" });
      router.push("/admin/postings");
    } catch (e) {
      setError(errorMessage(e));
      // 미완료 단계 표시를 최신 상태로 맞춘다
      await load();
    } finally {
      setPublishing(false);
    }
  }

  if (loadError) return <p className={shared.loadError}>{loadError}</p>;
  if (!review) return null;

  const { posting, doc_items, doc_criteria, interview_criteria, company_questions, incomplete_steps } = review;
  const registered = posting.write_status === "등록 완료";
  const editHref = (step: ReviewStep) => `/admin/postings/${postingId}/edit/${step}`;
  const blank = <span className={styles.blank}>미입력</span>;

  const skills = doc_items.skills.map((s) => `${s.skill_name} (${s.cutoff_score === null ? "기준 없음" : `${s.cutoff_score}점 이하 탈락`})`);
  const selectedItems = doc_items.basic_items.filter((i) => i.selected).map((i) => i.item_name);
  const interviewSettings = [
    interview_criteria.question_count !== null && `질문 ${interview_criteria.question_count}개`,
    interview_criteria.follow_up_enabled !== null && `꼬리질문 ${interview_criteria.follow_up_enabled ? "사용" : "사용 안 함"}`,
    interview_criteria.think_time_sec !== null && `생각 ${interview_criteria.think_time_sec}초`,
    interview_criteria.answer_time_sec !== null && `답변 ${interview_criteria.answer_time_sec}초`,
  ].filter((x): x is string => typeof x === "string");
  // 면접 질문 구성: 출제 문제 개수 = 기업 질문 + AI 질문(직무 + 인성). 직무 개수는 반올림한다 (SYS-006)
  const { question_count: totalQuestions, questions: companyList, job_question_ratio: jobRatio } = company_questions;
  const split =
    totalQuestions === null ? null : splitAiQuestions(totalQuestions, companyList.length, jobRatio ?? 0);

  return (
    <div className={shared.page}>
      <header className={shared.header}>
        <h1 className={shared.title}>{registered ? "채용공고 수정" : "새 채용공고 등록"}</h1>
        <p className={shared.subtitle}>등록 전에 작성한 내용을 확인합니다.</p>
      </header>

      <Stepper steps={STEPS} current={5} />

      <p className={styles.notice}>
        수정할 내용이 있으면 각 항목의 ‘수정’을 눌러 해당 단계로 돌아가세요. 서류 접수가 시작되면 공고를 수정·삭제할 수 없습니다.
      </p>

      <section className={styles.card}>
        <CardHead title="공고 정보" href={editHref("info")} incomplete={incomplete_steps.includes("info")} />
        <dl className={styles.kvs}>
          <div className={styles.kv}>
            <dt>포지션명</dt>
            <dd>{posting.position_name ?? blank}</dd>
          </div>
          <div className={styles.kv}>
            <dt>직무 분류 / 고용 형태</dt>
            <dd>
              {posting.job_category ?? blank} / {posting.employment_type ?? blank}
            </dd>
          </div>
          <div className={styles.kv}>
            <dt>전형별 일정</dt>
            <dd>
              <p>
                서류 {formatMonthDay(posting.doc_start_at)} ~ {formatMonthDay(posting.doc_end_at)} · 서류 합격자 발표{" "}
                {formatMonthDayTime(posting.doc_result_at)}
              </p>
              <p>
                면접 {formatMonthDay(posting.interview_start_at)} ~ {formatMonthDay(posting.interview_end_at)} · 면접 합격자 발표{" "}
                {formatMonthDayTime(posting.interview_result_at)}
              </p>
            </dd>
          </div>
          <div className={styles.kv}>
            <dt>인재상</dt>
            <dd>
              <p>기능적: {posting.functional_talent ?? blank}</p>
              <p>비기능적: {posting.nonfunctional_talent ?? blank}</p>
            </dd>
          </div>
        </dl>
      </section>

      <section className={styles.card}>
        <CardHead title={`프로젝트 문서 (${posting.documents.length}개)`} href={editHref("info")} />
        {posting.documents.length === 0 && <p className={styles.empty}>등록한 문서가 없습니다.</p>}
        {posting.documents.map((doc) => (
          <div key={doc.document_id} className={styles.doc}>
            <span className={styles.pdf}>PDF</span>
            <div className={styles.docInfo}>
              <span className={styles.docName}>{doc.file_name}</span>
              <span className={styles.docSize}>{formatFileSize(doc.file_size)}</span>
            </div>
            <a
              className={styles.edit}
              href={`${API_URL}/api/admin/postings/${postingId}/documents/${doc.document_id}/file`}
              target="_blank"
              rel="noopener noreferrer"
            >
              보기 ›
            </a>
          </div>
        ))}
      </section>

      <section className={styles.card}>
        <CardHead title="서류 작성 문항" href={editHref("doc-items")} incomplete={incomplete_steps.includes("doc-items")} />
        <dl className={styles.kvs}>
          <div className={styles.kv}>
            <dt>기본 문항</dt>
            <dd>{selectedItems.join(", ")}</dd>
          </div>
          <div className={styles.kv}>
            <dt>필수 기술</dt>
            <dd>{skills.length ? skills.join(", ") : blank}</dd>
          </div>
          <div className={styles.kv}>
            <dt>자기소개서 주제</dt>
            <dd>{doc_items.essay_topics.length ? doc_items.essay_topics.join(", ") : blank}</dd>
          </div>
        </dl>
      </section>

      <div className={styles.row}>
        <section className={styles.card}>
          <CardHead title="서류 평가기준" href={editHref("doc-criteria")} incomplete={incomplete_steps.includes("doc-criteria")} />
          <RatioBar items={doc_criteria.criteria.map((c) => ({ label: c.criteria_name, value: c.ratio }))} colors={DOC_COLORS} />
        </section>

        <section className={styles.card}>
          <CardHead title="면접 평가기준" href={editHref("interview-criteria")} incomplete={incomplete_steps.includes("interview-criteria")} />
          <RatioBar
            items={interview_criteria.criteria.map((c) => ({ label: c.criteria_name, value: c.ratio }))}
            colors={INTERVIEW_COLORS}
          />
          <div className={styles.badges}>
            {interviewSettings.map((text) => (
              <span key={text} className={styles.badge}>
                {text}
              </span>
            ))}
          </div>
        </section>
      </div>

      <section className={styles.card}>
        <CardHead
          title="면접 질문"
          href={editHref("company-questions")}
          incomplete={incomplete_steps.includes("company-questions")}
        />
        <dl className={styles.kvs}>
          <div className={styles.kv}>
            <dt>출제 문제 개수</dt>
            <dd>{totalQuestions === null ? blank : `${totalQuestions}개`}</dd>
          </div>
          <div className={styles.kv}>
            <dt>기업 질문 ({companyList.length}개)</dt>
            <dd>
              {companyList.length === 0 && <span className={styles.blank}>등록한 기업 질문이 없습니다.</span>}
              {companyList.map((q, i) => (
                <p key={i}>
                  Q{i + 1}. {q}
                </p>
              ))}
            </dd>
          </div>
          <div className={styles.kv}>
            <dt>AI 질문</dt>
            <dd>
              {split === null
                ? blank
                : `${split.ai}개 (출제 ${totalQuestions}개 − 기업 질문 ${companyList.length}개)`}
            </dd>
          </div>
          <div className={styles.kv}>
            <dt>AI 질문 비율</dt>
            <dd>
              {split?.ai === 0 ? (
                <span className={styles.blank}>AI 질문이 없어 적용되지 않습니다.</span>
              ) : jobRatio === null ? (
                blank
              ) : (
                `직무 ${jobRatio}% · 인성 ${100 - jobRatio}%`
              )}
            </dd>
          </div>
          <div className={styles.kv}>
            <dt>반영된 AI 질문 수</dt>
            <dd>
              {split === null || (jobRatio === null && split.ai > 0) ? (
                blank
              ) : (
                `직무 ${split.job}개 · 인성 ${split.personality}개`
              )}
            </dd>
          </div>
        </dl>
      </section>

      {error && (
        <p className={shared.formError} role="alert">
          {error}
        </p>
      )}

      <div className={shared.actions}>
        <span className={shared.spacer} />
        <Button type="button" variant="secondary" inline disabled={publishing} onClick={() => router.push(editHref("company-questions"))}>
          이전
        </Button>
        <Button type="button" inline disabled={publishing} onClick={onPublish}>
          {registered ? "수정 완료" : "등록하기"}
        </Button>
      </div>
    </div>
  );
}
