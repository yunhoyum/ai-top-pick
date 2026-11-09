import ApplicantHeader from "./ApplicantHeader";
import styles from "./ApplicantShell.module.css";

// 지원자 화면 틀 (채용공고, 지원서, 내 지원 현황 공통). 비로그인도 쓰는 화면이 있어 로그인 확인은 각 화면이 한다
export default function ApplicantShell({ children }: { children: React.ReactNode }) {
  return (
    <div className={styles.shell}>
      <ApplicantHeader />
      <main className={styles.main}>{children}</main>
    </div>
  );
}
