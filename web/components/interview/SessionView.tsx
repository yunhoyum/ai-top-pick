"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Badge from "@/components/common/Badge";
import Button from "@/components/common/Button";
import BrandLogo from "@/components/layout/BrandLogo";
import { apiFetch } from "@/lib/api";
import { connectInterview } from "@/lib/ws";
import type { InterviewGuide, ServerMessage } from "@/types/interview";
import styles from "./Interview.module.css";

type Question = Extract<ServerMessage, { type: "question" }>;
// audio: 질문을 읽어 주는 중, think: 생각 시간, answer: 답변 시간, evaluating: 답변을 보내고 다음 질문을 기다림
type Phase = "connecting" | "audio" | "think" | "answer" | "evaluating" | "closed";

function remainingSec(endsAt: string | null, now: number): number {
  return endsAt ? Math.max(0, Math.ceil((new Date(endsAt).getTime() - now) / 1000)) : 0;
}

function mmss(sec: number): string {
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
}

// 화면 24 화상 면접 화면 (APP-016, SYS-011)
// 질문을 받으면 글을 보여 주고 음성을 재생한다. 재생이 끝나면 서버에 알리고, 서버가 생각·답변 시간을 정한다
// 실시간 면접 1단계: 답변 음성 중계·자막(Deepgram), 녹화·업로드, 기술 문의는 아직 없다
export default function SessionView({ applicationId, sessionId }: { applicationId: number; sessionId: number }) {
  const router = useRouter();
  const wsRef = useRef<WebSocket | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [guide, setGuide] = useState<InterviewGuide | null>(null);
  const [question, setQuestion] = useState<Question | null>(null);
  const [asked, setAsked] = useState<Record<number, string>>({}); // 순번 → 이번 접속에서 받은 질문 글
  const [phase, setPhase] = useState<Phase>("connecting");
  const [endsAt, setEndsAt] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [error, setError] = useState<string | null>(null);
  const [cameraOn, setCameraOn] = useState(false);

  useEffect(() => {
    apiFetch<InterviewGuide>(`/api/applications/${applicationId}/interview/guide`).then(setGuide).catch(() => {});
  }, [applicationId]);

  // 내 화면 (녹화는 2단계에서)
  useEffect(() => {
    let stream: MediaStream | null = null;
    navigator.mediaDevices
      .getUserMedia({ video: true })
      .then((s) => {
        stream = s;
        if (videoRef.current) videoRef.current.srcObject = s;
        setCameraOn(true);
      })
      .catch(() => setCameraOn(false));
    return () => stream?.getTracks().forEach((t) => t.stop());
  }, []);

  useEffect(() => {
    const ws = connectInterview(sessionId);
    wsRef.current = ws;
    let current: Question | null = null;
    let ended = false;
    const send = (msg: object) => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify(msg));

    ws.onmessage = (ev) => {
      if (ev.data instanceof ArrayBuffer) {
        // 질문 음성. 다시 듣기는 없다 (SYS-011). 재생이 막혀도 면접이 멈추지 않게 바로 끝났다고 알린다
        const q = current;
        const url = URL.createObjectURL(new Blob([ev.data], { type: "audio/wav" }));
        const audio = new Audio(url);
        const done = () => {
          URL.revokeObjectURL(url);
          if (q) send({ type: "question_audio_ended", question_id: q.question_id });
        };
        audio.onended = done;
        audio.play().catch(done);
        return;
      }
      const msg = JSON.parse(ev.data as string) as ServerMessage;
      switch (msg.type) {
        case "question":
          current = msg;
          setQuestion(msg);
          setAsked((a) => ({ ...a, [msg.seq]: msg.text }));
          setPhase("audio");
          setEndsAt(null);
          break;
        case "phase":
          setPhase(msg.phase);
          setEndsAt(msg.ends_at);
          break;
        case "answer_end":
        case "evaluating":
          setPhase("evaluating");
          setEndsAt(null);
          break;
        case "interview_end":
          ended = true;
          router.replace(
            `/interview/${applicationId}/done?answered=${msg.answered_count}&ended=${encodeURIComponent(msg.ended_at)}`,
          );
          break;
        case "error":
          setError(msg.message);
          break;
      }
    };
    ws.onclose = () => {
      setPhase("closed");
      if (!ended) setError((e) => e ?? "면접 서버와 연결이 끊겼습니다. 다시 접속하면 이어서 진행합니다.");
    };
    return () => {
      ended = true;
      ws.close();
    };
  }, [applicationId, sessionId, router]);

  // 남은 시간 표시
  useEffect(() => {
    if (phase !== "think" && phase !== "answer") return;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [phase]);

  const left = remainingSec(endsAt, now);
  const thinkSec = question?.think_sec ?? guide?.think_time_sec ?? 0;
  const answerSec = question?.answer_sec ?? guide?.answer_time_sec ?? 0;
  const thinkDone = phase === "answer" || phase === "evaluating";
  const thinkFill = phase === "think" && thinkSec ? 1 - left / thinkSec : thinkDone ? 1 : 0;
  const answerFill = phase === "answer" && answerSec ? 1 - left / answerSec : phase === "evaluating" ? 1 : 0;
  const total = question?.total ?? guide?.question_count ?? 0;

  function answerDone() {
    if (question && phase === "answer") {
      wsRef.current?.send(JSON.stringify({ type: "answer_done", question_id: question.question_id }));
    }
  }

  return (
    <div className={styles.interview}>
      <header className={styles.bar}>
        <BrandLogo />
        <span className={styles.barDivider} />
        <span className={styles.barTitle}>{guide?.position_name ?? ""} · AI 화상 면접</span>
        {/* 문의(챗봇)는 실시간 면접 5단계에서 연다 */}
        <Button type="button" variant="secondary" inline disabled title="준비 중입니다">
          기술 문의
        </Button>
      </header>

      <div className={styles.body}>
        <div className={styles.main}>
          <section className={`${styles.card} ${styles.questionCard}`}>
            <div>
              <Badge tone="navy">{question ? `질문 ${question.seq} / ${question.total}` : "질문 준비 중"}</Badge>
            </div>
            <p className={`${styles.questionText} ${question ? "" : styles.questionWaiting}`}>
              {question ? question.text : "면접 서버에 연결하고 있습니다"}
            </p>
            <div className={styles.timers}>
              <div className={styles.timer}>
                <div className={styles.timerHead}>
                  <span className={styles.timerLabel}>생각 시간</span>
                  <span className={`${styles.timerValue} ${phase === "think" ? styles.timerValueActive : ""}`}>
                    {phase === "think" ? `${mmss(left)} 남음` : thinkDone ? "완료" : mmss(thinkSec)}
                  </span>
                </div>
                <div className={styles.track}>
                  <div
                    className={`${styles.fill} ${phase === "think" ? styles.fillActive : ""}`}
                    style={{ width: `${thinkFill * 100}%` }}
                  />
                </div>
              </div>
              <div className={styles.timer}>
                <div className={styles.timerHead}>
                  <span className={styles.timerLabel}>답변 시간</span>
                  <span className={`${styles.timerValue} ${phase === "answer" ? styles.timerValueActive : ""}`}>
                    {phase === "answer" ? `${mmss(left)} 남음` : phase === "evaluating" ? "완료" : mmss(answerSec)}
                  </span>
                </div>
                <div className={styles.track}>
                  <div
                    className={`${styles.fill} ${phase === "answer" ? styles.fillActive : ""}`}
                    style={{ width: `${answerFill * 100}%` }}
                  />
                </div>
              </div>
            </div>
          </section>

          <div className={styles.selfView}>
            <video ref={videoRef} className={styles.previewVideo} autoPlay muted playsInline hidden={!cameraOn} />
            {!cameraOn && (
              <>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img className={styles.selfPlaceholder} src="/interview/self-placeholder.svg" alt="" />
                <p className={styles.previewHint}>내 화면</p>
              </>
            )}
          </div>

          {error && <p className={styles.message}>{error}</p>}
          <div className={styles.footer}>
            <p className={styles.footerNote}>
              {phase === "audio"
                ? "질문을 읽어 주고 있습니다. 읽기가 끝나면 생각 시간이 시작됩니다."
                : phase === "think"
                  ? "생각 시간이 끝나면 답변 시간이 시작되고 ‘답변 완료’ 버튼을 누를 수 있습니다."
                  : phase === "evaluating"
                    ? "답변을 처리하고 있습니다. 잠시만 기다려 주세요."
                    : "10초 이상 말이 없으면 답변이 끝난 것으로 처리됩니다."}
            </p>
            <Button type="button" inline disabled={phase !== "answer"} onClick={answerDone}>
              답변 완료
            </Button>
          </div>
        </div>

        <aside className={styles.side}>
          <section className={`${styles.card} ${styles.transcript}`}>
            <div className={styles.cardHead}>
              <h2 className={styles.cardTitle}>실시간 답변 기록</h2>
            </div>
            <p className={styles.smallNote}>말과 다르게 기록되는 부분은 LLM이 수정하여 저장됩니다.</p>
            {/* 답변 음성 인식(Deepgram)은 실시간 면접 2단계에서 연다 */}
            <p className={styles.smallNote}>답변 기록은 준비 중입니다.</p>
          </section>

          <section className={`${styles.card} ${styles.progress}`}>
            <h2 className={styles.cardTitle}>질문 진행</h2>
            {Array.from({ length: total }, (_, i) => i + 1).map((seq) => {
              const cur = question?.seq ?? 0;
              const isCur = seq === cur;
              const isDone = seq < cur || (isCur && phase === "evaluating");
              const text = asked[seq];
              return (
                <div key={seq} className={styles.progressItem}>
                  <span
                    className={`${styles.progressText} ${isCur ? styles.progressCurrent : ""} ${!text && !isDone ? styles.progressHidden : ""}`}
                  >
                    Q{seq}. {text ?? (seq < cur ? "답변한 질문" : "아직 공개되지 않은 질문")}
                  </span>
                  <Badge tone={isCur && !isDone ? "teal" : "gray"}>{isDone ? "완료" : isCur ? "진행 중" : "대기"}</Badge>
                </div>
              );
            })}
          </section>
        </aside>
      </div>
    </div>
  );
}
