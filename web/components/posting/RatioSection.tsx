import NumberInput from "@/components/common/NumberInput";
import { summarizeRatios } from "@/lib/ratio";
import type { EvalCriterion } from "@/types/posting";
import styles from "./RatioSection.module.css";

const SEGMENT_CLASSES = [styles.seg0, styles.seg1, styles.seg2, styles.seg3];

type Props = {
  criteria: EvalCriterion[];
  values: Record<number, string>;
  onChange: (criteriaId: number, value: string) => void;
  // 항목 하나의 입력 오류. 오류가 없으면 undefined
  itemError: (criterion: EvalCriterion) => string | undefined;
  // 항목별 비율 막대 (서류 평가기준에만 있다)
  preview?: boolean;
};

// 평가 항목별 비율 입력, 합계 안내, 미리보기 (화면 06 서류 평가기준, 화면 07 면접 평가기준)
export default function RatioSection({ criteria, values, onChange, itemError, preview }: Props) {
  const hasItemError = criteria.some((c) => itemError(c));
  const { sum, blanks, complete } = summarizeRatios(criteria, values, hasItemError);

  function status(): { text: string; tone: "ok" | "warn" | "bad" } {
    if (complete) return { text: "입력 완료", tone: "ok" };
    if (hasItemError) return { text: "입력값을 확인해 주세요", tone: "bad" };
    if (blanks === criteria.length) return { text: "비율을 입력해 주세요", tone: "warn" };
    if (sum > 100) return { text: `${sum - 100} 초과`, tone: "bad" };
    if (sum < 100) return { text: `${100 - sum} 부족`, tone: "warn" };
    return { text: "비어 있는 항목이 있습니다", tone: "warn" };
  }
  const { text, tone } = status();

  return (
    <>
      {criteria.map((c) => (
        <div key={c.criteria_id} className={styles.row}>
          <div className={styles.rowText}>
            <label className={styles.rowName} htmlFor={`ratio-${c.criteria_id}`}>
              {c.criteria_name}
            </label>
            {c.description && <p className={styles.rowDesc}>{c.description}</p>}
          </div>
          <NumberInput
            id={`ratio-${c.criteria_id}`}
            unit="%"
            maxDigits={3}
            value={values[c.criteria_id] ?? ""}
            onValueChange={(v) => onChange(c.criteria_id, v)}
            error={itemError(c)}
          />
        </div>
      ))}

      <div className={styles.total}>
        <span className={styles.totalLabel}>합계</span>
        <span className={`${styles.totalValue} ${styles[`total_${tone}`]}`}>{sum} / 100</span>
        <span className={`${styles.badge} ${styles[`badge_${tone}`]}`} role="status">
          {text}
        </span>
      </div>

      {preview && (
        <div className={styles.preview}>
          <p className={styles.previewLabel}>미리보기</p>
          <div className={styles.bar} aria-hidden="true">
            {criteria.map((c, i) => {
              const n = values[c.criteria_id] ? Number(values[c.criteria_id]) : 0;
              return n > 0 ? (
                <span key={c.criteria_id} className={SEGMENT_CLASSES[i % SEGMENT_CLASSES.length]} style={{ flexGrow: n }} />
              ) : null;
            })}
            {sum < 100 && <span style={{ flexGrow: 100 - sum }} />}
          </div>
        </div>
      )}
    </>
  );
}
