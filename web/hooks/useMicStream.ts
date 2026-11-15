"use client";

import { useCallback, useRef, type RefObject } from "react";

// 음성 조각 길이(ms). 짧을수록 자막이 빨리 뜬다 (제안)
const CHUNK_MS = 250;

// 답변 시간 동안 마이크 음성을 webm/opus 조각으로 면접 WebSocket에 보낸다 (아키텍처 7-6, SYS-004)
// main-api가 받아 Deepgram으로 넘긴다. 답변마다 새로 시작해야 조각 맨 앞에 webm 머리가 붙는다
export function useMicStream(streamRef: RefObject<MediaStream | null>) {
  const recRef = useRef<MediaRecorder | null>(null);

  const stop = useCallback(() => {
    if (recRef.current?.state === "recording") recRef.current.stop();
    recRef.current = null;
  }, []);

  const start = useCallback(
    (ws: WebSocket) => {
      stop();
      const tracks = streamRef.current?.getAudioTracks() ?? [];
      if (!tracks.length) return;
      const rec = new MediaRecorder(new MediaStream(tracks), { mimeType: "audio/webm;codecs=opus" });
      rec.ondataavailable = (e) => {
        if (e.data.size && ws.readyState === WebSocket.OPEN) ws.send(e.data);
      };
      rec.start(CHUNK_MS);
      recRef.current = rec;
    },
    [streamRef, stop],
  );

  return { start, stop };
}
