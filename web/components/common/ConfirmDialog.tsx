"use client";

import { useEffect, useRef } from "react";
import Button from "./Button";
import styles from "./ConfirmDialog.module.css";

type Props = {
  title: string;
  message: string;
  confirmLabel: string;
  busy?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
};

// 되돌릴 수 없는 동작(삭제 등)을 한 번 더 확인하는 팝업
export default function ConfirmDialog({ title, message, confirmLabel, busy, error, onConfirm, onCancel }: Props) {
  const cancelButton = useRef<HTMLButtonElement>(null);

  // 실수로 누르기 쉬운 쪽(삭제)이 아니라 취소에 먼저 포커스를 둔다
  useEffect(() => {
    cancelButton.current?.focus();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !busy && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onCancel]);

  return (
    <div className={styles.overlay}>
      <div className={styles.dialog} role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-message">
        <h2 id="confirm-title" className={styles.title}>
          {title}
        </h2>
        <p id="confirm-message" className={styles.message}>
          {message}
        </p>
        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}
        <div className={styles.actions}>
          <button ref={cancelButton} type="button" className={styles.cancel} disabled={busy} onClick={onCancel}>
            취소
          </button>
          <Button type="button" variant="secondary" inline className={styles.confirm} disabled={busy} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
