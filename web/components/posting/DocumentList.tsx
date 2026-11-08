"use client";

import { useRef, useState } from "react";
import { formatFileSize } from "@/lib/format";
import type { PostingDocument } from "@/types/posting";
import styles from "./DocumentList.module.css";

type Props = {
  documents: PostingDocument[];
  uploading: boolean;
  error: string | null;
  onUpload: (files: File[]) => void;
  onDelete: (documentId: number) => void;
};

// 프로젝트 문서 등록 (ADM-005). 파일 종류·크기 검사는 서버가 한다
export default function DocumentList({ documents, uploading, error, onUpload, onDelete }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function pick(files: FileList | null) {
    if (files && files.length > 0) onUpload(Array.from(files));
    if (input.current) input.current.value = ""; // 같은 파일을 다시 고를 수 있게 비운다
  }

  return (
    <section className={styles.card}>
      <div className={styles.head}>
        <h2 className={styles.title}>프로젝트 문서</h2>
        <p className={styles.desc}>여러 개 등록할 수 있습니다. PDF 파일만 등록할 수 있습니다.</p>
      </div>

      <div
        className={`${styles.dropzone} ${dragging ? styles.dragging : ""}`}
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
        <span className={styles.pdfBadge}>PDF</span>
        <p className={styles.dropText}>{uploading ? "업로드 중..." : "파일을 끌어다 놓거나 클릭해서 선택하세요"}</p>
        <p className={styles.dropHint}>PDF 파일만 등록할 수 있습니다</p>
        <input
          ref={input}
          type="file"
          accept="application/pdf"
          multiple
          hidden
          onChange={(e) => pick(e.target.files)}
        />
      </div>

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {documents.map((doc) => (
        <div key={doc.document_id} className={styles.item}>
          <span className={styles.fileIcon}>PDF</span>
          <div className={styles.fileInfo}>
            <span className={styles.fileName}>{doc.file_name}</span>
            <span className={styles.fileSize}>{formatFileSize(doc.file_size)}</span>
          </div>
          {doc.upload_status && <span className={styles.status}>{doc.upload_status}</span>}
          <button type="button" className={styles.delete} onClick={() => onDelete(doc.document_id)}>
            삭제
          </button>
        </div>
      ))}
    </section>
  );
}
