import styles from "./NumberInput.module.css";

type NumberInputProps = {
  id: string;
  // 입력 중인 값. 빈 문자열은 아직 입력하지 않은 상태다 (0과 구분한다)
  value: string;
  // 값 뒤에 붙는 단위 (%, 개, 초)
  unit: string;
  onValueChange: (value: string) => void;
  error?: string;
  // 입력할 수 있는 최대 자릿수
  maxDigits?: number;
};

// 0 이상의 정수만 받는 입력칸 (Figma Number). 숫자가 아닌 글자는 입력되지 않는다
export default function NumberInput({ id, value, unit, onValueChange, error, maxDigits = 9 }: NumberInputProps) {
  function onChange(raw: string) {
    const digits = raw.replace(/\D/g, "").slice(0, maxDigits);
    // 앞의 0은 지운다 ("007" → "7")
    onValueChange(digits === "" ? "" : String(Number(digits)));
  }

  return (
    <div className={styles.wrap}>
      <div className={`${styles.box} ${error ? styles.invalid : ""}`}>
        <input
          id={id}
          className={styles.input}
          inputMode="numeric"
          autoComplete="off"
          placeholder="0"
          aria-invalid={error ? true : undefined}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
        <span className={styles.unit}>{unit}</span>
      </div>
      {error && <p className={styles.error}>{error}</p>}
    </div>
  );
}
