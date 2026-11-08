import styles from "./Badge.module.css";

export type BadgeTone = "navy" | "teal" | "gray" | "amber";

// 상태 배지 (Figma Badge: Navy, Teal, Gray, Amber)
export default function Badge({ tone = "navy", children }: { tone?: BadgeTone; children: React.ReactNode }) {
  return <span className={`${styles.badge} ${styles[tone]}`}>{children}</span>;
}
