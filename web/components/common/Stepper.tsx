import styles from "./Stepper.module.css";

// 공고 등록 6단계(04~09)와 지원서 4단계(12~15)에서 쓴다
export default function Stepper({ steps, current }: { steps: string[]; current: number }) {
  return (
    <ol className={styles.stepper} aria-label="진행 단계">
      {steps.map((label, i) => (
        <li key={label} className={styles.step} aria-current={i === current ? "step" : undefined}>
          {i > 0 && <span className={styles.line} />}
          <span className={`${styles.circle} ${i === current ? styles.current : ""}`}>{i + 1}</span>
          <span className={`${styles.label} ${i === current ? styles.currentLabel : ""}`}>{label}</span>
        </li>
      ))}
    </ol>
  );
}
