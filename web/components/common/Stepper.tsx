import styles from "./Stepper.module.css";

// 공고 등록 6단계(04~09)와 지원서 4단계(12~15)에서 쓴다. 현재보다 앞 단계는 완료 표시(체크)를 한다
export default function Stepper({ steps, current }: { steps: string[]; current: number }) {
  return (
    <ol className={styles.stepper} aria-label="진행 단계">
      {steps.map((label, i) => (
        <li key={label} className={styles.step} aria-current={i === current ? "step" : undefined}>
          {i > 0 && <span className={styles.line} />}
          {i < current ? (
            <span className={`${styles.circle} ${styles.done}`} aria-label="완료">
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                <path d="M2.5 6.5l2.5 2.5 4.5-5.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
          ) : (
            <span className={`${styles.circle} ${i === current ? styles.current : ""}`}>{i + 1}</span>
          )}
          <span
            className={`${styles.label} ${i === current ? styles.currentLabel : ""} ${i < current ? styles.doneLabel : ""}`}
          >
            {label}
          </span>
        </li>
      ))}
    </ol>
  );
}
