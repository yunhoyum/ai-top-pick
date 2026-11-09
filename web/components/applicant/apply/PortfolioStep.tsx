"use client";

import { useRef, useState } from "react";
import docStyles from "@/components/posting/DocumentList.module.css";
import { formatFileSize } from "@/lib/format";
import type { ApplicationData } from "@/types/application";
import styles from "./Apply.module.css";

type Props = {
  portfolio: ApplicationData["portfolio"];
  uploading: boolean;
  error: string | null;
  onUpload: (file: File) => void;
  onDelete: () => void;
  // 제출 전 확인: 단계별 작성 여부
  checklist: { label: string; done: boolean }[];
};

// 화면 15 포트폴리오 등록 (APP-009)과 제출 전 확인. 파일 종류·크기 검사는 서버가 한다
export default function PortfolioStep({ portfolio, uploading, error, onUpload, onDelete, checklist }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function pick(files: FileList | null) {
    if (files && files.length > 0) onUpload(files[0]);
    if (input.current) input.current.value = ""; // 같은 파일을 다시 고를 수 있게 비운다
  }

  return (
    <>
      <section className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>포트폴리오</h2>
          <p className={styles.cardDesc}>자유 양식의 PDF 파일 1개를 등록해 주세요.</p>
        </div>

        <div
          className={`${docStyles.dropzone} ${dragging ? docStyles.dragging : ""}`}
          role="button"
          tabIndex={0}
          onClick={() => input.current?.click()}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            pick(e.dataTransfer.files);
          }}
        >
          <span className={docStyles.pdfBadge}>PDF</span>
          <p className={docStyles.dropText}>{uploading ? "업로드 중..." : "파일을 끌어다 놓거나 클릭해서 선택하세요"}</p>
          <p className={docStyles.dropHint}>PDF 파일만 등록할 수 있습니다</p>
          {/* input.click()가 부모 영역의 클릭으로 다시 올라가 파일 창을 거듭 여는 것을 막는다 */}
          <input
            ref={input}
            type="file"
            accept="application/pdf"
            hidden
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => pick(e.target.files)}
          />
        </div>

        {error && (
          <p className={styles.error} role="alert">
            {error}
          </p>
        )}

        {portfolio && (
          <div className={docStyles.item}>
            <span className={docStyles.fileIcon}>PDF</span>
            <div className={docStyles.fileInfo}>
              <span className={docStyles.fileName}>{portfolio.file_name}</span>
              <span className={docStyles.fileSize}>{formatFileSize(portfolio.file_size)}</span>
            </div>
            <span className={docStyles.status}>등록 완료</span>
            <button type="button" className={docStyles.delete} onClick={onDelete}>
              삭제
            </button>
          </div>
        )}
      </section>

      <section className={styles.card}>
        <h2 className={styles.cardTitle}>제출 전 확인</h2>
        {checklist.map((c) => (
          <div key={c.label} className={styles.check}>
            <span className={`${styles.checkIcon} ${c.done ? "" : styles.checkIconPending}`} aria-hidden="true">
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M2.5 6.5l2.5 2.5 4.5-5.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <span className={styles.checkLabel}>{c.label}</span>
            <span className={`${styles.checkState} ${c.done ? "" : styles.checkStatePending}`}>{c.done ? "작성 완료" : "미작성"}</span>
          </div>
        ))}
      </section>
    </>
  );
}
