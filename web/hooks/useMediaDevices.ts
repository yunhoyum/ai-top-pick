"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// 마이크 입력이 이 값보다 크면 소리가 들어온 것으로 본다 (0~1, 제안)
const MIC_OK_LEVEL = 0.08;

// 면접 중 기술 문의의 시스템 재검사: 이미 연 스트림의 카메라가 살아 있고, sec초 안에 마이크 입력이 기준을 넘는지
export async function recheckStream(stream: MediaStream | null, sec = 5): Promise<boolean> {
  if (!stream || !stream.getVideoTracks().some((t) => t.readyState === "live")) return false;
  if (!stream.getAudioTracks().some((t) => t.readyState === "live")) return false;
  const ctx = new AudioContext();
  try {
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const data = new Float32Array(analyser.fftSize);
    const until = Date.now() + sec * 1000;
    while (Date.now() < until) {
      analyser.getFloatTimeDomainData(data);
      const rms = Math.sqrt(data.reduce((sum, v) => sum + v * v, 0) / data.length);
      if (Math.min(1, rms * 5) >= MIC_OK_LEVEL) return true;
      await new Promise((r) => setTimeout(r, 100));
    }
    return false;
  } finally {
    ctx.close();
  }
}

export type MediaCheck = {
  stream: MediaStream | null;
  cameraOk: boolean;
  micOk: boolean;
  // 마이크 입력 크기 0~1 (화면 23 Mic Level 막대)
  micLevel: number;
  error: string | null;
  restart: () => void;
  stop: () => void;
};

// 카메라·마이크 권한을 받고 입력을 확인한다 (APP-015, 화면 23)
// 카메라: 영상 트랙이 살아 있으면 정상. 마이크: 입력이 한 번이라도 기준보다 크면 정상
export function useMediaDevices(): MediaCheck {
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [cameraOk, setCameraOk] = useState(false);
  const [micOk, setMicOk] = useState(false);
  const [micLevel, setMicLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const streamRef = useRef<MediaStream | null>(null);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => {
    let cancelled = false;
    let frame = 0;
    let audioCtx: AudioContext | null = null;

    (async () => {
      setCameraOk(false);
      setMicOk(false);
      setMicLevel(0);
      setError(null);
      try {
        const s = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
        if (cancelled) {
          s.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = s;
        setStream(s);
        setCameraOk(s.getVideoTracks().some((t) => t.readyState === "live"));

        audioCtx = new AudioContext();
        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 1024;
        audioCtx.createMediaStreamSource(s).connect(analyser);
        const data = new Float32Array(analyser.fftSize);
        const tick = () => {
          analyser.getFloatTimeDomainData(data);
          const rms = Math.sqrt(data.reduce((sum, v) => sum + v * v, 0) / data.length);
          const level = Math.min(1, rms * 5);
          setMicLevel(level);
          if (level >= MIC_OK_LEVEL) setMicOk(true);
          frame = requestAnimationFrame(tick);
        };
        tick();
      } catch {
        if (!cancelled) setError("카메라와 마이크를 사용할 수 없습니다. 브라우저의 권한 설정을 확인해 주세요.");
      }
    })();

    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      audioCtx?.close();
      stop();
      setStream(null);
    };
  }, [attempt, stop]);

  const restart = useCallback(() => setAttempt((n) => n + 1), []);

  return { stream, cameraOk, micOk, micLevel, error, restart, stop };
}
