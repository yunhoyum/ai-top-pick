"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Badge, { type BadgeTone } from "@/components/common/Badge";
import Button from "@/components/common/Button";
import fieldStyles from "@/components/common/Field.module.css";
import { ApiError, apiFetch } from "@/lib/api";
import { fetchMeIfLoggedIn } from "@/lib/auth";
import { formatFullDate, formatFullDateTime, formatFullDateWeek, formatMonthDay, formatMonthDayTime } from "@/lib/format";
import type { ApplicationStatusItem } from "@/types/applicationStatus";
import styles from "./MyApplications.module.css";

const TONES: Record<string, BadgeTone> = {
  "작성 중": "amber",
  "서류 전형 진행 중": "navy",
  "면접 전형 예정": "navy",
  "면접 전형 진행 중": "teal",
  "면접 결과 대기": "navy",
  "면접 전형 완료": "teal",
  "전형 종료": "gray",
};

const Check = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
    <path d="M2.5 6.5l2.5 2.5 4.5-5.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

type StepState = "done" | "fail" | "todo";

function Step({ n, name, note, state }: { n: number; name: string; note: string; state: StepState }) {
  return (
    <div className={styles.step}>
      <span className={`${styles.circle} ${state === "done" ? styles.circleDone : state === "fail" ? styles.circleFail : ""}`}>
        {state === "done" ? <Check /> : state === "fail" ? "✕" : n}
      </span>
      <span className={`${styles.stepName} ${state !== "todo" ? styles.stepNameOn : ""}`}>{name}</span>
      <span className={`${styles.stepNote} ${state === "done" ? styles.stepNoteDone : state === "fail" ? styles.stepNoteFail : ""}`}>{note}</span>
    </div>
  );
}

const Line = ({ done }: { done: boolean }) => <div className={`${styles.line} ${done ? styles.lineDone : ""}`} />;

// 제출한 지원서의 4단계 타임라인: 서류 접수 → 서류 전형 → AI 면접 → 최종 결과(면접 전형)
function Timeline({ a }: { a: ApplicationStatusItem }) {
  const docFail = a.doc_result === "불합격";
  const docPass = a.doc_result === "합격";
  const interviewResult = a.interview_result;
  const interviewRange = `${formatMonthDay(a.interview_start_at)} ~ ${formatMonthDay(a.interview_end_at)}`;

  const doc: [string, StepState] = docPass ? ["합격", "done"] : docFail ? ["불합격", "fail"] : [`${formatMonthDayTime(a.doc_result_at)} 발표`, "todo"];
  const interview: [string, StepState] = docFail ? ["-", "todo"] : a.interview_taken ? ["응시 완료", "done"] : [interviewRange, "todo"];
  const last: [string, string, StepState] = docFail
    ? ["최종 결과", "-", "todo"]
    : interviewResult
      ? ["면접 전형", interviewResult, interviewResult === "합격" ? "done" : "fail"]
      : ["최종 결과", `${formatMonthDayTime(a.interview_result_at)} 발표`, "todo"];

  return (
    <div className={styles.timeline}>
      <Step n={1} name="서류 접수" note="완료" state="done" />
      <Line done />
      <Step n={2} name="서류 전형" note={doc[0]} state={doc[1]} />
      <Line done={docPass} />
      <Step n={3} name="AI 면접" note={interview[0]} state={interview[1]} />
      <Line done={a.interview_taken} />
      <Step n={4} name={last[0]} note={last[1]} state={last[2]} />
    </div>
  );
}

// 결과 영역. 발표 일시 전에는 서버가 결과를 보내지 않아서 '확인할 수 있습니다' 안내만 나온다
function ResultBox({ a }: { a: ApplicationStatusItem }) {
  const router = useRouter();

  if (a.write_status === "임시 저장") {
    return (
      <div className={styles.result}>
        <p className={styles.resultTitle}>작성 중인 지원서입니다</p>
        <p className={styles.resultText}>서류 접수 마감 {formatFullDateWeek(a.doc_end_at)} 전에 제출해 주세요.</p>
        <Button type="button" inline onClick={() => router.push(`/postings/${a.posting_id}/apply`)}>
          이어서 작성
        </Button>
      </div>
    );
  }
  if (a.interview_result) {
    const pass = a.interview_result === "합격";
    return (
      <div className={`${styles.result} ${pass ? styles.resultPass : ""}`}>
        <Badge tone={pass ? "teal" : "gray"}>면접 전형 결과</Badge>
        <p className={styles.resultTitle}>{pass ? "면접 전형에 합격했습니다" : "이번 면접 전형에서는 합격하지 못했습니다"}</p>
        <p className={styles.resultText}>{pass ? "다음 절차는 채용 담당자가 따로 안내합니다." : "지원해 주셔서 감사합니다."}</p>
      </div>
    );
  }
  if (a.doc_result === "합격") {
    const closed = a.status === "면접 결과 대기";
    return (
      <div className={`${styles.result} ${styles.resultPass}`}>
        <Badge tone="teal">서류 전형 결과</Badge>
        <p className={styles.resultTitle}>서류 전형에 합격했습니다</p>
        <p className={styles.resultText}>
          {closed ? (
            `면접 전형 결과는 면접 합격자 발표 일시(${formatFullDateTime(a.interview_result_at)})부터 확인할 수 있습니다.`
          ) : (
            <>
              AI 화상 면접은 {formatFullDate(a.interview_start_at)} ~ {formatMonthDay(a.interview_end_at)} 사이에 응시할 수 있습니다.
              <br />
              응시 전 안내사항과 기술적 테스트를 꼭 확인해 주세요.
            </>
          )}
        </p>
        {a.can_view_interview_guide && (
          // 면접 안내 화면은 아직 없다
          <Button type="button" inline onClick={() => router.push(`/postings/${a.posting_id}/interview`)}>
            AI 면접 안내 보기
          </Button>
        )}
      </div>
    );
  }
  if (a.doc_result === "불합격") {
    return (
      <div className={styles.result}>
        <Badge tone="gray">서류 전형 결과</Badge>
        <p className={styles.resultTitle}>이번 서류 전형에서는 합격하지 못했습니다</p>
        <p className={styles.resultText}>지원해 주셔서 감사합니다.</p>
      </div>
    );
  }
  return (
    <div className={styles.result}>
      <Badge tone="navy">서류 전형 결과</Badge>
      <p className={styles.resultTitle}>서류 전형 결과를 기다리고 있습니다</p>
      <p className={styles.resultText}>서류 합격자 발표 일시({formatFullDateTime(a.doc_result_at)})부터 확인할 수 있습니다.</p>
    </div>
  );
}

// 내 지원 현황 (APP-012, APP-017). 지원자만 쓴다: 비로그인은 로그인으로, 관리자는 대시보드로 보낸다
export default function MyApplications() {
  const router = useRouter();
  const [items, setItems] = useState<ApplicationStatusItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const me = await fetchMeIfLoggedIn();
      if (cancelled) return;
      if (!me) return router.replace(`/login?next=${encodeURIComponent("/applications")}`);
      if (me.role !== "지원자") return router.replace("/admin/dashboard");
      try {
        const list = await apiFetch<ApplicationStatusItem[]>("/api/applications");
        if (!cancelled) setItems(list);
      } catch (e) {
        if (!cancelled) setError(e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (error) return <p className={styles.error}>{error}</p>;
  if (!items) return null;

  // 지원 내역은 드롭다운으로 하나씩 본다 (처음에는 가장 최근 지원)
  const current = items.find((a) => a.posting_id === selected) ?? items[0];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.headText}>
          <h1 className={styles.title}>내 지원 현황</h1>
          <p className={styles.subtitle}>지원한 공고의 전형 결과를 확인합니다.</p>
        </div>
        {items.length > 1 && (
          <div className={styles.picker}>
            <label className={fieldStyles.label} htmlFor="application-picker">
              지원 공고 선택
            </label>
            <select
              id="application-picker"
              className={`${fieldStyles.input} ${fieldStyles.select}`}
              value={current.posting_id}
              onChange={(e) => setSelected(Number(e.target.value))}
            >
              {items.map((a) => (
                <option key={a.posting_id} value={a.posting_id}>
                  {a.position_name ?? "(제목 없음)"} · {a.status}
                  {a.submitted_at ? ` · ${formatMonthDayTime(a.submitted_at)} 지원` : ""}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {items.length === 0 && (
        <div className={styles.empty}>
          <p>지원한 공고가 없습니다. 채용공고에서 지원해 보세요.</p>
          <Link href="/postings">
            <Button type="button" inline>
              채용공고 보기
            </Button>
          </Link>
        </div>
      )}

      {current && (
        <section className={styles.card}>
          <div className={styles.cardHead}>
            <h2 className={styles.cardTitle}>{current.position_name ?? "(제목 없음)"}</h2>
            <Badge tone={TONES[current.status] ?? "gray"}>{current.status}</Badge>
          </div>
          {current.write_status === "제출" && <Timeline a={current} />}
          <ResultBox a={current} />
        </section>
      )}
    </div>
  );
}
