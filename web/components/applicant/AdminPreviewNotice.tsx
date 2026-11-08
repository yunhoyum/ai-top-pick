import styles from "./AdminPreviewNotice.module.css";

// 관리자는 자기 공고가 지원자에게 어떻게 보이는지 확인하러 지원자 화면에 들어온다. 지원자 화면 맨 위에 알린다
export default function AdminPreviewNotice() {
  return <p className={styles.notice}>지원자가 지원할 화면입니다.</p>;
}
