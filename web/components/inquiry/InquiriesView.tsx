"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Badge, { type BadgeTone } from "@/components/common/Badge";
import Button from "@/components/common/Button";
import { ApiError, apiFetch } from "@/lib/api";
import { formatDuration, formatMonthDayTime, formatTime } from "@/lib/format";
import type { HandlingStatus, InquiryDetail, InquiryItem } from "@/types/inquiry";
import styles from "./Inquiry.module.css";

const TABS: HandlingStatus[] = ["AI 미처리", "관리자 대기", "관리자 처리 완료", "AI 처리"];
const TONES: Record<HandlingStatus, BadgeTone> = {
  "AI 미처리": "red",
  "관리자 대기": "amber",
  "관리자 처리 완료": "gray",
  "AI 처리": "teal",
};
const CAUSE: Record<string, string> = { "시스템 측": "시스템 측 원인", "지원자 측": "지원자 측 원인" };
// 시스템 로그는 사건을 글로 남긴다. 실패·오류·끊김이면 ERROR로 보인다 (Figma 26 시스템 로그)
const isError = (content: string | null) => /오류|실패|끊김|올라오지 않음/.test(content ?? "");

function KV({ label, value, wide }: { label: string; value: React.ReactNode; wide?: boolean }) {
  return (
    <div className={styles.kv}>
      <span className={`${styles.kvLabel} ${wide ? styles.kvLabelWide : ""}`}>{label}</span>
      <span className={styles.kvValue}>{value}</span>
    </div>
  );
}

// 화면 26·26-1 문의·예외 처리 (ADM-026·041)
// 왼쪽은 처리 상태 탭과 문의 목록, 오른쪽은 고른 문의의 정보·대화·로그·AI 처리 결과
// '관리자 대기'인 문의는 담당자가 문제를 처리한 뒤 '면접 재개'를 누른다. 지원자는 내 지원 현황에서 '재접속 가능'을 본다
export default function InquiriesView() {
  const postingId = useSearchParams().get("posting"); // 대시보드 '오류 확인'에서 오면 그 공고만
  const [items, setItems] = useState<InquiryItem[] | null>(null);
  const [tab, setTab] = useState<HandlingStatus>("관리자 대기");
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<InquiryDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resuming, setResuming] = useState(false);

  const load = useCallback(async () => {
    try {
      setItems(await apiFetch<InquiryItem[]>(`/api/admin/inquiries${postingId ? `?posting_id=${postingId}` : ""}`));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다.");
    }
  }, [postingId]);

  useEffect(() => {
    load();
  }, [load]);

  const shown = (items ?? []).filter((i) => i.handling_status === tab);
  const currentId = shown.some((i) => i.inquiry_id === selected) ? selected : (shown[0]?.inquiry_id ?? null);

  useEffect(() => {
    if (currentId === null) return;
    apiFetch<InquiryDetail>(`/api/admin/inquiries/${currentId}`)
      .then(setDetail)
      .catch((e) => setError(e instanceof ApiError ? e.message : "문의를 불러오지 못했습니다."));
  }, [currentId]);

  async function resume(inquiryId: number) {
    setResuming(true);
    setError(null);
    try {
      const d = await apiFetch<InquiryDetail>(`/api/admin/inquiries/${inquiryId}/resume`, { method: "POST" });
      setDetail(d);
      setSelected(d.inquiry_id);
      setTab("관리자 처리 완료");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "면접을 재개하지 못했습니다.");
    } finally {
      setResuming(false);
    }
  }

  const count = (s: HandlingStatus) => (items ?? []).filter((i) => i.handling_status === s).length;
  const d = detail && detail.inquiry_id === currentId ? detail : null;
  const resolved = d?.handling_status === "AI 처리";
  const waiting = d?.handling_status === "관리자 대기";

  return (
    <div className={styles.page}>
      <div className={styles.headText}>
        <h1 className={styles.title}>문의·예외 처리</h1>
        <p className={styles.subtitle}>AI가 오류를 스스로 처리합니다. 처리 결과와 AI가 처리하지 못한 오류를 확인합니다.</p>
      </div>
      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.layout}>
        <section className={styles.list}>
          <div className={styles.tabs}>
            {TABS.map((s) => (
              <button key={s} type="button" className={`${styles.tab} ${tab === s ? styles.tabOn : ""}`} onClick={() => setTab(s)}>
                {s} {count(s)}
              </button>
            ))}
          </div>
          {items && !shown.length && <p className={styles.empty}>{tab} 문의가 없습니다.</p>}
          {shown.map((i) => (
            <button
              key={i.inquiry_id}
              type="button"
              className={`${styles.item} ${i.inquiry_id === currentId ? styles.itemOn : ""}`}
              onClick={() => setSelected(i.inquiry_id)}
            >
              <span className={styles.itemHead}>
                <span className={styles.itemName}>{i.applicant_name ?? "(이름 없음)"}</span>
                {i.handling_status && <Badge tone={TONES[i.handling_status]}>{i.handling_status}</Badge>}
              </span>
              <span className={styles.itemSub}>
                {i.position_name ?? "(제목 없음)"} · {formatMonthDayTime(i.started_at)}
              </span>
            </button>
          ))}
        </section>

        {d && (
          <div className={styles.detail}>
            <section className={styles.card}>
              <div className={styles.cardHead}>
                <h2 className={`${styles.cardTitle} ${styles.grow}`}>문의 정보</h2>
                <Badge tone={resolved ? "teal" : "red"}>{resolved ? "챗봇 응대로 해결" : "챗봇 응대로 해결 안 됨"}</Badge>
              </div>
              <div className={styles.columns}>
                <div className={styles.column}>
                  <KV label="지원자" value={d.applicant_name ?? "-"} />
                  <KV label="공고" value={d.position_name ?? "-"} />
                  <KV label="진행 질문" value={d.question_text ?? "-"} />
                  <KV label="처리 상태" value={d.handling_status ?? "-"} />
                </div>
                <div className={styles.column}>
                  <KV label="문의 시작" value={formatTime(d.started_at)} />
                  <KV label={resolved ? "해결 시각" : "문의 종료"} value={formatTime(d.ended_at)} />
                  <KV label="문의 소요 시간" value={formatDuration(d.started_at, d.ended_at)} />
                  {!resolved && <KV label="처리 시각" value={d.handled_at ? formatTime(d.handled_at) : waiting ? "처리 전" : "-"} />}
                </div>
              </div>
            </section>

            <div className={styles.row}>
              <section className={`${styles.card} ${styles.half}`}>
                <h2 className={styles.cardTitle}>챗봇 대화 기록</h2>
                {d.messages.map((m, idx) => {
                  const mine = m.speaker === "지원자";
                  return (
                    <div key={idx} className={`${styles.bubbleRow} ${mine ? styles.bubbleRowMine : ""}`}>
                      <div className={`${styles.bubble} ${mine ? styles.bubbleMine : ""}`}>
                        <span className={`${styles.speaker} ${mine ? styles.speakerMine : ""}`}>{m.speaker}</span>
                        <span>{m.content}</span>
                      </div>
                    </div>
                  );
                })}
              </section>
              <section className={`${styles.card} ${styles.half} ${styles.logs}`}>
                <h2 className={styles.cardTitle}>시스템 로그</h2>
                {d.logs.map((l, idx) => {
                  const err = isError(l.content);
                  return (
                    <div key={idx} className={`${styles.log} ${err ? styles.logError : ""}`}>
                      <span className={styles.logTime}>{formatTime(l.logged_at)}</span>
                      <Badge tone={err ? "red" : "gray"}>{err ? "ERROR" : "INFO"}</Badge>
                      <span className={styles.logText}>{l.content}</span>
                    </div>
                  );
                })}
              </section>
            </div>

            <section className={`${styles.card} ${styles.result}`}>
              <div className={styles.cardHead}>
                <h2 className={styles.cardTitle}>AI 처리 결과</h2>
                {d.handling_status && <Badge tone={TONES[d.handling_status]}>{d.handling_status}</Badge>}
              </div>
              <div className={`${styles.note} ${resolved ? styles.noteOk : styles.noteFail}`}>
                <p className={styles.noteTitle}>{resolved ? "처리 내용" : "처리하지 못한 내용"}</p>
                <p className={styles.noteText}>{d.judgment_basis}</p>
              </div>
              <div className={styles.column}>
                <KV wide label="AI가 시도한 조치" value={d.ai_action ?? "-"} />
                <KV wide label="AI 시도 횟수" value={`${d.ai_attempt_count}회 (최대 3회)`} />
                <KV wide label="판단 결과" value={d.cause ? (CAUSE[d.cause] ?? d.cause) : "-"} />
              </div>
              <div className={`${styles.note} ${styles.noteInfo}`}>
                <p className={styles.noteTitle}>
                  후속 조치: {d.follow_up}
                  {waiting ? " (관리자 처리 필요)" : ""}
                </p>
                <p className={styles.noteText}>{d.handling_detail}</p>
              </div>
              {waiting && (
                <div className={styles.actions}>
                  <Button type="button" inline disabled={resuming} onClick={() => resume(d.inquiry_id)}>
                    면접 재개
                  </Button>
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
