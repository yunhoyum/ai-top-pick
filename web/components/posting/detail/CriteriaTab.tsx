import type { DocCriteria, EvalCriterion, InterviewCriteria } from "@/types/posting";
import RatioBar from "../RatioBar";
import styles from "./PostingDetail.module.css";

// Figma 막대 색: 서류 평가기준은 4색, 면접 평가기준은 3색 (언어는 accent-600, 비언어는 accent-300)
const DOC_COLORS = ["var(--primary-700)", "var(--primary-500)", "var(--accent-600)", "var(--accent-300)"];
const INTERVIEW_COLORS = ["var(--primary-700)", "var(--accent-600)", "var(--accent-300)"];

function Criteria({ criteria, colors }: { criteria: EvalCriterion[]; colors: string[] }) {
  return (
    <>
      {criteria.map((c) => (
        <div key={c.criteria_id} className={styles.line}>
          <div className={styles.lineText}>
            <span className={styles.lineName}>{c.criteria_name}</span>
            {c.description && <span className={styles.lineDesc}>{c.description}</span>}
          </div>
          <span className={styles.percent}>{c.ratio === null ? "-" : `${c.ratio}%`}</span>
        </div>
      ))}
      <RatioBar thin hideLegend items={criteria.map((c) => ({ label: c.criteria_name, value: c.ratio }))} colors={colors} />
    </>
  );
}

// 평가기준 탭: 서류·면접 평가기준과 면접 진행 설정 (ADM-038, ADM-039)
export default function CriteriaTab({ doc, interview }: { doc: DocCriteria; interview: InterviewCriteria }) {
  const dash = (v: number | null, suffix = "") => (v === null ? "-" : `${v}${suffix}`);
  return (
    <div className={styles.row}>
      <section className={`${styles.card} ${styles.grow}`}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>서류 평가기준</h2>
          <p className={styles.cardDesc}>회사 인재상과의 유사도를 기준으로 평가합니다.</p>
        </div>
        <Criteria criteria={doc.criteria} colors={DOC_COLORS} />
      </section>

      <section className={`${styles.card} ${styles.grow}`}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>면접 평가기준</h2>
          <p className={styles.cardDesc}>요소의 합은 100입니다.</p>
        </div>
        <Criteria criteria={interview.criteria} colors={INTERVIEW_COLORS} />
        <dl className={`${styles.kvs} ${styles.settings}`}>
          <div className={styles.kv}>
            <dt className={styles.kvWide}>출제 문제 개수</dt>
            <dd>{interview.question_count === null ? "-" : `${interview.question_count}개 (꼬리질문 포함)`}</dd>
          </div>
          <div className={styles.kv}>
            <dt className={styles.kvWide}>꼬리질문</dt>
            <dd>
              {interview.follow_up_enabled === null
                ? "-"
                : interview.follow_up_enabled
                  ? "사용 (직무 질문 답변 점수 80점 이상 시 생성, 기본 질문당 최대 2개)"
                  : "사용 안 함"}
            </dd>
          </div>
          <div className={styles.kv}>
            <dt className={styles.kvWide}>생각 시간</dt>
            <dd>{dash(interview.think_time_sec, "초")}</dd>
          </div>
          <div className={styles.kv}>
            <dt className={styles.kvWide}>답변 시간</dt>
            <dd>{interview.answer_time_sec === null ? "-" : `${interview.answer_time_sec}초 (10초 이상 말이 없으면 종료)`}</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
