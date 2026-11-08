"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Button from "@/components/common/Button";
import { ApiError, apiFetch } from "@/lib/api";
import type { Draft } from "@/types/posting";
import styles from "./DraftResumeDialog.module.css";

// 새 공고를 작성하려는데 임시 저장한 공고가 있을 때 묻는다 (ADM-011)
export default function DraftResumeDialog({ draft, onDiscarded }: { draft: Draft; onDiscarded: () => void }) {
  const router = useRouter();
  const resumeButton = useRef<HTMLButtonElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 가장 안전한 선택(이어서 작성)에 먼저 포커스를 둔다
  useEffect(() => {
    resumeButton.current?.focus();
  }, []);

  const cancel = () => router.push("/admin/postings");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !busy && router.push("/admin/postings");
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, router]);

  function resume() {
    router.replace(`/admin/postings/${draft.posting_id}/edit/${draft.resume_step}`);
  }

  async function discard() {
    setError(null);
    setBusy(true);
    try {
      await apiFetch(`/api/admin/postings/${draft.posting_id}`, { method: "DELETE" });
      onDiscarded();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "서버에 연결하지 못했습니다.");
      setBusy(false);
    }
  }

  return (
    <div className={styles.overlay}>
      <div className={styles.dialog} role="dialog" aria-modal="true" aria-labelledby="draft-dialog-title">
        <h2 id="draft-dialog-title" className={styles.title}>
          등록 중인 공고가 있습니다
        </h2>
        <p className={styles.question}>이어서 하시겠습니까?</p>
        {draft.position_name && <p className={styles.name}>‘{draft.position_name}’</p>}
        <p className={styles.warning}>‘새로 작성’을 누르면 기존 임시 저장 내용이 삭제됩니다.</p>
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
        <div className={styles.actions}>
          <Button type="button" variant="secondary" inline className={styles.discard} disabled={busy} onClick={discard}>
            새로 작성
          </Button>
          <span className={styles.spacer} />
          <Button type="button" variant="ghost" inline disabled={busy} onClick={cancel}>
            취소
          </Button>
          <button ref={resumeButton} type="button" className={styles.resume} disabled={busy} onClick={resume}>
            이어서 작성
          </button>
        </div>
      </div>
    </div>
  );
}
