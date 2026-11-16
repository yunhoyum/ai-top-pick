"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import Badge from "@/components/common/Badge";
import { API_URL, ApiError, apiFetch } from "@/lib/api";
import { stagePath } from "@/lib/evaluation";
import { formatFullDate } from "@/lib/format";
import type { InterviewSource } from "@/types/evaluation";
import styles from "./Evaluation.module.css";

const TABS = [
  { key: "video", label: "면접 영상" },
  { key: "stt", label: "답변 기록" },
] as const;
const KIND_LABELS = { AI: "AI 질문", 꼬리: "꼬리질문", 기업: "기업 질문" } as const;

const errorMessage = (e: unknown) => (e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다.");
const mmss = (sec: number | null) => (sec == null ? "-" : `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`);

// 화면 29 지원자 자료 원본 (면접, ADM-028). 탭: 면접 영상, 답변 기록(STT 보정문, 보정 전 인식 원문)
// 오른쪽 질문 목록에서 질문을 고른다. 고른 질문과 탭은 주소(?q=순번&tab=)에 남겨 보고서에서 바로 들어올 수 있다
export default function InterviewSourceView({ postingId, applicationId }: { postingId: number; applicationId: number }) {
  const router = useRouter();
  const search = useSearchParams();
  const [data, setData] = useState<InterviewSource | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<InterviewSource>(`/api/admin/applications/${applicationId}/interview`)
      .then(setData)
      .catch((e) => setLoadError(errorMessage(e)));
  }, [applicationId]);

  if (loadError) return <p className={styles.loadError}>{loadError}</p>;
  if (!data) return null;

  const base = `${stagePath(postingId, "interview")}/applications/${applicationId}`;
  const tab = search.get("tab") === "stt" ? "stt" : "video";
  const current = data.questions.find((q) => q.seq === Number(search.get("q"))) ?? data.questions[0];
  const go = (q: number, t: string) => router.replace(`${base}/source?q=${q}&tab=${t}`, { scroll: false });

  return (
    <div className={styles.page}>
      <Link href={`${base}/report`} className={styles.back}>
        ‹ 면접 전형 결과 보고서
      </Link>

      <header className={styles.header}>
        <div className={styles.headText}>
          <h1 className={styles.title}>{data.name ?? "(이름 없음)"} · 면접 자료 원본</h1>
          <p className={styles.subtitle}>
            {data.position_name ?? "(제목 없음)"} · 면접 전형 마감 {formatFullDate(data.interview_end_at)}
          </p>
        </div>
      </header>

      <div className={styles.tabs} role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={`${styles.tab} ${tab === t.key ? styles.tabActive : ""}`}
            onClick={() => current && go(current.seq, t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {!current ? (
        <p className={styles.empty}>유효한 답변이 없습니다.</p>
      ) : (
        <div className={styles.sourceLayout}>
          <section className={`${styles.card} ${styles.sourceMain}`}>
            <div className={styles.sourceHead}>
              <Badge tone="gray">Q{current.seq}</Badge>
              <Badge tone={current.kind === "기업" ? "gray" : "navy"}>{KIND_LABELS[current.kind]}</Badge>
              <span className={styles.sourceQuestion}>{current.text}</span>
            </div>
            {tab === "video" ? (
              current.has_video ? (
                // 다른 질문으로 바꾸면 영상을 새로 읽도록 key를 준다. 인증 쿠키는 같은 사이트라 함께 간다
                <video
                  key={current.answer_id}
                  className={styles.sourceVideo}
                  src={`${API_URL}/api/admin/answers/${current.answer_id}/video`}
                  controls
                  preload="metadata"
                />
              ) : (
                <p className={styles.sourceEmpty}>이 답변의 영상이 없습니다. 답변 시간이 끝난 뒤 영상이 올라오지 않았습니다.</p>
              )
            ) : (
              <>
                <p className={styles.sttNote}>말과 다르게 기록된 부분은 LLM이 수정하여 저장했습니다.</p>
                {current.stt.length === 0 && <p className={styles.sourceEmpty}>인식된 말이 없습니다.</p>}
                {current.stt.map((line, i) => {
                  const fixed = line.raw_text && line.corrected_text !== line.raw_text;
                  return (
                    <div key={i} className={styles.sttLine}>
                      <span className={styles.sttTime}>{mmss(line.time_offset_sec)}</span>
                      <div className={styles.sttText}>
                        <p>{line.corrected_text}</p>
                        {fixed && (
                          <p className={styles.sttRaw}>
                            <Badge tone="navy">LLM 수정</Badge>
                            <span>인식 원문: {line.raw_text}</span>
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </>
            )}
          </section>

          <aside className={`${styles.card} ${styles.sourceList}`}>
            <h2 className={styles.cardTitle}>질문 목록</h2>
            {data.questions.map((q) => (
              <button
                key={q.answer_id}
                type="button"
                className={`${styles.sourceItem} ${q.seq === current.seq ? styles.sourceItemActive : ""}`}
                onClick={() => go(q.seq, tab)}
              >
                <span className={styles.sourceItemSeq}>Q{q.seq}</span>
                <span className={styles.sourceItemText}>{q.text}</span>
                <span className={styles.sourceItemTime}>{mmss(q.duration_sec)}</span>
              </button>
            ))}
          </aside>
        </div>
      )}
    </div>
  );
}
