import Badge from "@/components/common/Badge";
import { splitAiQuestions } from "@/lib/interview";
import type { CompanyQuestions } from "@/types/posting";
import RatioBar from "../RatioBar";
import styles from "./PostingDetail.module.css";

const AI_COLORS = ["var(--primary-700)", "var(--accent-600)"];

// 면접 질문 탭: 기업 질문 목록과 AI 질문 구성 (ADM-040). 평가기준 탭처럼 두 카드로 나눠 보여준다
export default function QuestionsTab({ data }: { data: CompanyQuestions }) {
  const { questions, question_count: total, job_question_ratio: ratio } = data;

  const ai = total === null ? null : Math.max(total - questions.length, 0);
  const hasAi = ai !== null && ai > 0;
  // 비율을 정했고 AI 질문이 있을 때만 직무·인성 개수를 계산한다
  const split = total !== null && ratio !== null ? splitAiQuestions(total, questions.length, ratio) : null;
  const count = (n: number | undefined) => (split && n !== undefined ? `${n}개` : "-");

  const ratioDesc = (label: string, value: number | null) => {
    if (ai === 0) return "AI 질문이 없어 비율은 적용되지 않습니다.";
    return value === null ? "비율 미입력" : `AI 질문 중 ${label} ${value}%`;
  };

  return (
    <div className={styles.row}>
      <section className={`${styles.card} ${styles.grow}`}>
        <div className={styles.cardHead}>
          <div className={styles.titleRow}>
            <h2 className={styles.cardTitle}>기업 질문</h2>
            <Badge tone="navy">
              {questions.length} / {total ?? "-"}
            </Badge>
          </div>
          <p className={styles.cardDesc}>
            모든 지원자에게 공통으로 묻는 질문입니다.
            {total !== null && ` 출제 문제 개수(${total}개)를 넘길 수 없습니다.`}
          </p>
        </div>
        {questions.length === 0 && <p className={styles.empty}>등록한 기업 질문이 없습니다.</p>}
        {questions.map((q, i) => (
          <div key={i} className={styles.line}>
            <span className={styles.topicNo}>Q{i + 1}</span>
            <span className={styles.topicName}>{q}</span>
          </div>
        ))}
      </section>

      <section className={`${styles.card} ${styles.grow}`}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>AI 질문</h2>
          <p className={styles.cardDesc}>지원자 서류를 바탕으로 AI가 만드는 질문입니다. 직무 질문 수는 반올림하고, 인성 질문은 나머지입니다.</p>
        </div>
        <div className={styles.line}>
          <div className={styles.lineText}>
            <span className={styles.lineName}>직무 질문</span>
            <span className={styles.lineDesc}>{ratioDesc("직무", ratio)}</span>
          </div>
          <span className={styles.percent}>{ai === 0 ? "0개" : count(split?.job)}</span>
        </div>
        <div className={styles.line}>
          <div className={styles.lineText}>
            <span className={styles.lineName}>인성 질문</span>
            <span className={styles.lineDesc}>{ratioDesc("인성", ratio === null ? null : 100 - ratio)}</span>
          </div>
          <span className={styles.percent}>{ai === 0 ? "0개" : count(split?.personality)}</span>
        </div>
        {hasAi && ratio !== null && (
          <RatioBar
            thin
            hideLegend
            items={[
              { label: "직무", value: ratio },
              { label: "인성", value: 100 - ratio },
            ]}
            colors={AI_COLORS}
          />
        )}
        <dl className={`${styles.kvs} ${styles.settings}`}>
          <div className={styles.kv}>
            <dt className={styles.kvWide}>출제 문제 개수</dt>
            <dd>{total === null ? "-" : `${total}개`}</dd>
          </div>
          <div className={styles.kv}>
            <dt className={styles.kvWide}>기업 질문</dt>
            <dd>{questions.length}개</dd>
          </div>
          <div className={styles.kv}>
            <dt className={styles.kvWide}>AI 질문</dt>
            <dd>{ai === null ? "-" : `${ai}개 (출제 ${total}개 − 기업 질문 ${questions.length}개)`}</dd>
          </div>
          <div className={styles.kv}>
            <dt className={styles.kvWide}>질문 순서</dt>
            <dd>직무 질문 → 인성 질문 → 기업 질문</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
