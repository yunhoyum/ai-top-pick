"use client";

import { useCallback, useRef, type RefObject } from "react";

// 답변 하나를 영상(webm, 화면+음성)으로 녹화한다 (APP-016, 아키텍처 7-7)
// 답변이 끝나면 stop()이 영상을 돌려준다. 화면이 main-api에 올린다
export function useAnswerRecorder(streamRef: RefObject<MediaStream | null>) {
  const recRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const start = useCallback(() => {
    const stream = streamRef.current;
    if (!stream) return;
    chunksRef.current = [];
    const rec = new MediaRecorder(stream, { mimeType: "video/webm" });
    rec.ondataavailable = (e) => {
      if (e.data.size) chunksRef.current.push(e.data);
    };
    rec.start();
    recRef.current = rec;
  }, [streamRef]);

  // 녹화 중이 아니면 null
  const stop = useCallback((): Promise<Blob | null> => {
    const rec = recRef.current;
    recRef.current = null;
    if (!rec || rec.state !== "recording") return Promise.resolve(null);
    return new Promise((resolve) => {
      rec.onstop = () => resolve(new Blob(chunksRef.current, { type: "video/webm" }));
      rec.stop();
    });
  }, []);

  return { start, stop };
}
