import styles from "./RoleTabs.module.css";

export type Role = "관리자" | "지원자";
const ROLES: Role[] = ["관리자", "지원자"];

// 관리자/지원자 선택 탭 (로그인 01, 회원가입 02)
export default function RoleTabs({ value, onChange }: { value: Role; onChange: (role: Role) => void }) {
  return (
    <div className={styles.segmented} role="group" aria-label="역할 선택">
      {ROLES.map((r) => (
        <button
          key={r}
          type="button"
          className={`${styles.segment} ${value === r ? styles.active : ""}`}
          aria-pressed={value === r}
          onClick={() => onChange(r)}
        >
          {r}
        </button>
      ))}
    </div>
  );
}
