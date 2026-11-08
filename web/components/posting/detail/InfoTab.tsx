import { API_URL } from "@/lib/api";
import { formatFileSize, formatMonthDay, formatMonthDayWeekTime } from "@/lib/format";
import type { PostingDetail } from "@/types/posting";
import styles from "./PostingDetail.module.css";

const range = (a: string | null, b: string | null) => (a && b ? `${formatMonthDay(a)} ~ ${formatMonthDay(b)}` : "-");

function KV({ label, wide, children }: { label: string; wide?: boolean; children: React.ReactNode }) {
  return (
    <div className={styles.kv}>
      <dt className={wide ? styles.kvWide : undefined}>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

// 공고 정보 탭: 기본 정보, 전형 일정, 인재상, 프로젝트 문서 (ADM-035, ADM-036)
export default function InfoTab({ postingId, posting }: { postingId: number; posting: PostingDetail }) {
  return (
    <>
      <div className={styles.row}>
        <section className={`${styles.card} ${styles.grow}`}>
          <h2 className={styles.cardTitle}>기본 정보</h2>
          <dl className={styles.kvs}>
            <KV label="포지션명">{posting.position_name ?? "-"}</KV>
            <KV label="직무 분류">{posting.job_category ?? "-"}</KV>
            <KV label="고용 형태">{posting.employment_type ?? "-"}</KV>
            <KV label="직무 설명">{posting.job_description ?? "-"}</KV>
          </dl>
        </section>
        <section className={`${styles.card} ${styles.schedule}`}>
          <h2 className={styles.cardTitle}>전형 일정</h2>
          <dl className={styles.kvs}>
            <KV label="서류 접수" wide>
              {range(posting.doc_start_at, posting.doc_end_at)}
            </KV>
            <KV label="서류 합격자 발표" wide>
              {formatMonthDayWeekTime(posting.doc_result_at)}
            </KV>
            <KV label="AI 화상 면접" wide>
              {range(posting.interview_start_at, posting.interview_end_at)}
            </KV>
            <KV label="면접 합격자 발표" wide>
              {formatMonthDayWeekTime(posting.interview_result_at)}
            </KV>
          </dl>
        </section>
      </div>

      <section className={styles.card}>
        <h2 className={styles.cardTitle}>인재상</h2>
        <dl className={styles.kvs}>
          <KV label="기능적 인재상">{posting.functional_talent ?? "-"}</KV>
          <KV label="비기능적 인재상">{posting.nonfunctional_talent ?? "-"}</KV>
        </dl>
      </section>

      <section className={styles.card}>
        <h2 className={styles.cardTitle}>프로젝트 문서</h2>
        {posting.documents.length === 0 && <p className={styles.empty}>등록한 문서가 없습니다.</p>}
        {posting.documents.map((doc) => (
          <div key={doc.document_id} className={styles.doc}>
            <span className={styles.pdf}>PDF</span>
            <div className={styles.docInfo}>
              <span className={styles.docName}>{doc.file_name}</span>
              <span className={styles.docSize}>{formatFileSize(doc.file_size)}</span>
            </div>
            <a
              className={styles.link}
              href={`${API_URL}/api/admin/postings/${postingId}/documents/${doc.document_id}/file`}
              target="_blank"
              rel="noopener noreferrer"
            >
              보기 ›
            </a>
          </div>
        ))}
      </section>
    </>
  );
}
