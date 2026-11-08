import type { SelectHTMLAttributes } from "react";
import styles from "./Field.module.css";

type SelectFieldProps = SelectHTMLAttributes<HTMLSelectElement> & {
  label: string;
  placeholder: string;
  options: string[];
  error?: string;
};

export default function SelectField({ label, placeholder, options, error, id, ...props }: SelectFieldProps) {
  const inputId = id ?? props.name;
  return (
    <div className={styles.field}>
      <label className={styles.label} htmlFor={inputId}>
        {label}
      </label>
      <select
        id={inputId}
        className={`${styles.input} ${styles.select} ${error ? styles.invalid : ""}`}
        aria-invalid={error ? true : undefined}
        {...props}
      >
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
      {error && <p className={styles.error}>{error}</p>}
    </div>
  );
}
