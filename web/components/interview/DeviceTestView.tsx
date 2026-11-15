"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Badge from "@/components/common/Badge";
import Button from "@/components/common/Button";
import { useMediaDevices } from "@/hooks/useMediaDevices";
import { apiFetch, ApiError } from "@/lib/api";
import type { InterviewSessionOut } from "@/types/interview";
import styles from "./Interview.module.css";

const METER_BARS = 16;

// 화면 23 화상 면접 기술적 테스트 (APP-015). 카메라·마이크가 모두 정상이어야 면접을 시작할 수 있다
export default function DeviceTestView({ applicationId }: { applicationId: number }) {
  const router = useRouter();
  const media = useMediaDevices();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    if (videoRef.current) videoRef.current.srcObject = media.stream;
  }, [media.stream]);

  const ready = media.cameraOk && media.micOk;
  const lit = Math.round(media.micLevel * METER_BARS);

  async function start() {
    setStarting(true);
    setError(null);
    try {
      const s = await apiFetch<InterviewSessionOut>(`/api/applications/${applicationId}/interview/sessions`, {
        method: "POST",
        body: JSON.stringify({ camera_ok: media.cameraOk, mic_ok: media.micOk }),
      });
      // 면접 화면이 카메라를 다시 연다. 여기서 쓰던 장치는 닫는다
      media.stop();
      router.push(`/interview/${applicationId}/session?session=${s.session_id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "면접을 시작하지 못했습니다.");
      setStarting(false);
    }
  }

  return (
    <div className={`${styles.page} ${styles.wide}`}>
      <div>
        <h1 className={styles.pageTitle}>기술적 테스트</h1>
        <p className={styles.pageDesc}>면접 전에 카메라와 마이크 입력이 정상인지 확인합니다.</p>
      </div>

      <div className={styles.testRow}>
        <div className={styles.preview}>
          <video ref={videoRef} className={styles.previewVideo} autoPlay muted playsInline />
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className={styles.faceGuide} src="/interview/face-guide.png" alt="" width={120} height={150} />
          <p className={styles.previewHint}>얼굴이 가이드 안에 들어오도록 맞춰 주세요</p>
        </div>

        <section className={`${styles.card} ${styles.checks}`}>
          <h2 className={styles.cardTitle}>입력 확인</h2>
          <div className={styles.check}>
            <div className={styles.checkText}>
              <span className={styles.checkName}>카메라</span>
              <span className={styles.checkDesc}>
                {media.cameraOk ? "영상 입력이 확인되었습니다" : "카메라를 확인하고 있습니다"}
              </span>
            </div>
            <Badge tone={media.cameraOk ? "teal" : "gray"}>{media.cameraOk ? "정상" : "확인 중"}</Badge>
          </div>
          <div className={styles.check}>
            <div className={styles.checkText}>
              <span className={styles.checkName}>마이크</span>
              <span className={styles.checkDesc}>‘안녕하세요’라고 말해 보세요</span>
            </div>
            <Badge tone={media.micOk ? "teal" : "gray"}>{media.micOk ? "정상" : "확인 중"}</Badge>
          </div>
          <div className={styles.meter} aria-label="마이크 입력 크기">
            {Array.from({ length: METER_BARS }, (_, i) => (
              <span key={i} className={`${styles.meterBar} ${i < lit ? styles.meterBarOn : ""}`} />
            ))}
          </div>
        </section>
      </div>

      {(media.error || error) && <p className={styles.message}>{media.error ?? error}</p>}
      <p className={styles.notice}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/interview/notice-dot.svg" alt="" />
        입력이 정상으로 확인되어야 면접을 시작할 수 있습니다.
      </p>

      <div className={styles.actions}>
        <Button type="button" variant="secondary" inline onClick={media.restart}>
          다시 테스트
        </Button>
        <Button type="button" inline disabled={!ready || starting} onClick={start}>
          면접 시작
        </Button>
      </div>
    </div>
  );
}
