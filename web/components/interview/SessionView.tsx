"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Badge from "@/components/common/Badge";
import Button from "@/components/common/Button";
import BrandLogo from "@/components/layout/BrandLogo";
import { useAnswerRecorder } from "@/hooks/useAnswerRecorder";
import { recheckStream } from "@/hooks/useMediaDevices";
import { useMicStream } from "@/hooks/useMicStream";
import { apiFetch } from "@/lib/api";
import { connectInterview } from "@/lib/ws";
import type { InterviewGuide, ServerMessage } from "@/types/interview";
import styles from "./Interview.module.css";

type Question = Extract<ServerMessage, { type: "question" }>;
// audio: 질문을 읽어 주는 중, think: 생각 시간, answer: 답변 시간, evaluating: 답변을 보내고 다음 질문을 기다림
type Phase = "connecting" | "audio" | "think" | "answer" | "evaluating" | "closed";
type ChatLine = { speaker: "지원자" | "챗봇"; text: string };
// 해결 확인 방법. system: 브라우저가 카메라·마이크를 다시 검사, applicant: 지원자에게 예/아니오를 묻는다
type Check = "system" | "applicant" | null;
const RECHECK_NOTE = "카메라와 마이크를 다시 검사하고 있습니다. 마이크에 대고 말씀해 주세요.";

function remainingSec(endsAt: string | null, now: number): number {
  return endsAt ? Math.max(0, Math.ceil((new Date(endsAt).getTime() - now) / 1000)) : 0;
}

function mmss(sec: number): string {
  return `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
}

// 화면 24 화상 면접 화면 (APP-016, SYS-011)
// 질문을 받으면 글을 보여 주고 음성을 재생한다. 재생이 끝나면 서버에 알리고, 서버가 생각·답변 시간을 정한다
// 답변 시간에는 음성을 서버로 보내 자막을 받고(Deepgram), 답변을 녹화해 끝나면 올린다
// 기술 문의(SYS-003, APP-013·014): 질문을 받은 뒤 챗봇 창을 연다. 문의 중에도 질문 시간은 흐른다
// 챗봇이 해결 확인을 물으면 시스템 재검사는 자동으로, 지원자 확인은 예/아니오로 답한다. 3회 해결되지 않으면 서버가 면접을 중단한다
export default function SessionView({ applicationId, sessionId }: { applicationId: number; sessionId: number }) {
  const router = useRouter();
  const wsRef = useRef<WebSocket | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const { start: startMic, stop: stopMic } = useMicStream(streamRef);
  const { start: startRecording, stop: stopRecording } = useAnswerRecorder(streamRef);
  const [guide, setGuide] = useState<InterviewGuide | null>(null);
  const [question, setQuestion] = useState<Question | null>(null);
  const [asked, setAsked] = useState<Record<number, string>>({}); // 순번 → 이번 접속에서 받은 질문 글
  const [phase, setPhase] = useState<Phase>("connecting");
  const [endsAt, setEndsAt] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [error, setError] = useState<string | null>(null);
  const [cameraOn, setCameraOn] = useState(false);
  // 이번 답변의 자막. 확정 문장과 아직 바뀔 수 있는 중간 결과
  const [finals, setFinals] = useState<string[]>([]);
  const [interim, setInterim] = useState("");
  // 기술 문의
  const [chatOpen, setChatOpen] = useState(false);
  const [chat, setChat] = useState<ChatLine[]>([]);
  const [inquiryId, setInquiryId] = useState<number | null>(null);
  const [check, setCheck] = useState<Check>(null);
  const [waitingReply, setWaitingReply] = useState(false);
  const [draft, setDraft] = useState("");
  const [suspended, setSuspended] = useState(false);
  const inquiryRef = useRef<number | null>(null);
  const chatLinesRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    apiFetch<InterviewGuide>(`/api/applications/${applicationId}/interview/guide`).then(setGuide).catch(() => {});
  }, [applicationId]);

  // 내 화면. 같은 스트림으로 녹화하고 음성을 보낸다
  useEffect(() => {
    let stream: MediaStream | null = null;
    navigator.mediaDevices
      .getUserMedia({ video: true, audio: true })
      .then((s) => {
        stream = s;
        streamRef.current = s;
        if (videoRef.current) videoRef.current.srcObject = s;
        setCameraOn(true);
      })
      .catch(() => setCameraOn(false));
    return () => {
      streamRef.current = null;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  useEffect(() => {
    const ws = connectInterview(sessionId);
    wsRef.current = ws;
    let current: Question | null = null;
    let ended = false;
    const send = (msg: object) => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify(msg));
    const botSays = (text: string) => setChat((c) => [...c, { speaker: "챗봇", text }]);
    // 답변이 끝나면 녹화를 멈추고 영상을 올린다. 서버는 영상이 올라올 때까지 기다렸다가 평가로 넘긴다
    const finishAnswer = (questionId: number) => {
      stopMic();
      stopRecording().then((video) => {
        if (!video) return;
        const form = new FormData();
        form.append("file", video, "answer.webm");
        apiFetch(`/api/interview/sessions/${sessionId}/questions/${questionId}/video`, { method: "POST", body: form }).catch(
          () => {},
        );
      });
    };

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
          setFinals([]);
          setInterim("");
          break;
        case "phase":
          setPhase(msg.phase);
          setEndsAt(msg.ends_at);
          if (msg.phase === "answer") {
            startMic(ws);
            startRecording();
          }
          break;
        case "transcript":
          if (msg.is_final) {
            setFinals((f) => [...f, msg.text]);
            setInterim("");
          } else {
            setInterim(msg.text);
          }
          break;
        case "answer_end":
          finishAnswer(msg.question_id);
          setPhase("evaluating");
          setEndsAt(null);
          break;
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
        case "inquiry_opened":
          inquiryRef.current = msg.inquiry_id;
          setInquiryId(msg.inquiry_id);
          break;
        case "inquiry_reply":
          botSays(msg.text);
          setChatOpen(true);
          setWaitingReply(false);
          setCheck(msg.inquiry_id === null ? null : msg.check);
          if (msg.check === "system" && msg.inquiry_id !== null) {
            // 시스템 재검사: 지금 쓰는 카메라·마이크를 다시 검사해 결과를 보낸다
            const id = msg.inquiry_id;
            botSays(RECHECK_NOTE);
            setWaitingReply(true);
            recheckStream(streamRef.current).then((ok) => send({ type: "inquiry_check", inquiry_id: id, resolved: ok }));
          }
          break;
        case "inquiry_result":
          inquiryRef.current = null;
          setInquiryId(null);
          setCheck(null);
          setWaitingReply(false);
          botSays(
            msg.resolved
              ? msg.follow_up === "기존 질문 그대로 진행"
                ? "문제가 해결되었습니다. 진행 중인 질문에 이어서 답변해 주세요."
                : "문제가 해결되었습니다. 진행 중이던 질문을 다시 제시합니다."
              : "3회 시도했지만 해결하지 못했습니다. 지금까지의 답변을 저장하고 면접을 중단합니다.",
          );
          break;
        case "suspended":
          ended = true;
          setSuspended(true);
          setError(msg.message);
          stopMic();
          stopRecording();
          break;
        case "error":
          setError(msg.message);
          setWaitingReply(false);
          break;
      }
    };
    ws.onclose = () => {
      setPhase("closed");
      if (!ended) setError((e) => e ?? "면접 서버와 연결이 끊겼습니다. 다시 접속하면 이어서 진행합니다.");
    };
    return () => {
      // 화면을 떠날 때(개발 모드에서 두 번 그릴 때 포함) 닫는다. 끊김 안내를 띄우지 않게 처리기를 뗀다
      ended = true;
      ws.onclose = null;
      ws.onmessage = null;
      stopMic();
      stopRecording();
      ws.close();
    };
  }, [applicationId, sessionId, router, startMic, stopMic, startRecording, stopRecording]);

  // 챗봇 창은 새 메시지가 오면 맨 아래로 내린다
  useEffect(() => {
    const el = chatLinesRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [chat, waitingReply, chatOpen]);

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

  const send = (msg: object) => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
  };

  // '기술 문의': 창을 열고, 진행 중인 문의가 없으면 서버에 문의를 연다
  function openInquiry() {
    setChatOpen(true);
    if (inquiryRef.current !== null || waitingReply || !question) return;
    setWaitingReply(true);
    send({ type: "inquiry_open", question_id: question.question_id });
  }

  function sendInquiry() {
    const text = draft.trim();
    if (!text || inquiryId === null || waitingReply) return;
    setChat((c) => [...c, { speaker: "지원자", text }]);
    setDraft("");
    setWaitingReply(true);
    send({ type: "inquiry_message", inquiry_id: inquiryId, text });
  }

  function answerCheck(resolved: boolean) {
    if (inquiryId === null) return;
    setChat((c) => [...c, { speaker: "지원자", text: resolved ? "해결됐어요." : "아직 해결되지 않았어요." }]);
    setCheck(null);
    setWaitingReply(true);
    send({ type: "inquiry_check", inquiry_id: inquiryId, resolved });
  }

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
        {phase === "answer" && (
          <span className={styles.rec}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/interview/rec-dot.svg" alt="" />
            녹화 중
          </span>
        )}
        <Button type="button" variant="secondary" inline disabled={!question || phase === "closed"} onClick={openInquiry}>
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
          {suspended && (
            <div>
              <Button type="button" variant="secondary" inline onClick={() => router.replace("/applications")}>
                내 지원 현황으로
              </Button>
            </div>
          )}
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
          {chatOpen && (
            <section className={`${styles.card} ${styles.chat}`}>
              <div className={styles.cardHead}>
                <h2 className={styles.cardTitle}>기술 문의</h2>
                <button type="button" className={styles.chatClose} onClick={() => setChatOpen(false)} aria-label="닫기">
                  ✕
                </button>
              </div>
              <p className={styles.smallNote}>문의하는 동안에도 질문 시간은 흐릅니다.</p>
              <div ref={chatLinesRef} className={styles.chatLines}>
                {chat.map((line, i) => {
                  const mine = line.speaker === "지원자";
                  return (
                    <div key={i} className={`${styles.chatRow} ${mine ? styles.chatRowMine : ""}`}>
                      <div className={`${styles.bubble} ${mine ? styles.bubbleMine : ""}`}>
                        <span className={`${styles.speaker} ${mine ? styles.speakerMine : ""}`}>{line.speaker}</span>
                        <span>{line.text}</span>
                      </div>
                    </div>
                  );
                })}
                {waitingReply && <p className={styles.smallNote}>확인하고 있습니다…</p>}
              </div>
              {check === "applicant" && !waitingReply ? (
                <div className={styles.chatChecks}>
                  <Button type="button" inline onClick={() => answerCheck(true)}>
                    해결됐어요
                  </Button>
                  <Button type="button" variant="secondary" inline onClick={() => answerCheck(false)}>
                    아직 안 돼요
                  </Button>
                </div>
              ) : (
                <form
                  className={styles.chatInput}
                  onSubmit={(e) => {
                    e.preventDefault();
                    sendInquiry();
                  }}
                >
                  <input
                    className={styles.chatText}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    placeholder="어떤 문제가 있는지 적어 주세요"
                    disabled={inquiryId === null || waitingReply || suspended}
                  />
                  <Button type="submit" inline disabled={!draft.trim() || inquiryId === null || waitingReply}>
                    보내기
                  </Button>
                </form>
              )}
            </section>
          )}
          <section className={`${styles.card} ${styles.transcript}`}>
            <div className={styles.cardHead}>
              <h2 className={styles.cardTitle}>실시간 답변 기록</h2>
              {phase === "answer" && (
                <span className={styles.live}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src="/interview/live-dot.svg" alt="" />
                  음성 인식 중
                </span>
              )}
            </div>
            <p className={styles.smallNote}>말과 다르게 기록되는 부분은 LLM이 수정하여 저장됩니다.</p>
            {finals.map((text, i) => (
              <p key={i} className={styles.line}>
                {text}
              </p>
            ))}
            {interim && <p className={`${styles.line} ${styles.lineInterim}`}>{interim}</p>}
            {!finals.length && !interim && (
              <p className={styles.smallNote}>
                {phase === "answer" ? "말씀하시면 여기에 기록됩니다." : "답변 시간이 시작되면 기록됩니다."}
              </p>
            )}
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
