import type { TextareaHTMLAttributes } from "react";
import styles from "./Field.module.css";

type TextAreaFieldProps = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label: string;
  error?: string;
};

export default function TextAreaField({ label, error, id, ...props }: TextAreaFieldProps) {
  const inputId = id ?? props.name;
  return (
    <div className={styles.field}>
      <label className={styles.label} htmlFor={inputId}>
        {label}
      </label>
      <textarea
        id={inputId}
        className={`${styles.input} ${styles.textarea} ${error ? styles.invalid : ""}`}
        aria-invalid={error ? true : undefined}
        {...props}
      />
      {error && <p className={styles.error}>{error}</p>}
    </div>
  );
}
