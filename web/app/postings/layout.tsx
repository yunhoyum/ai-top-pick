import ApplicantHeader from "@/components/layout/ApplicantHeader";
import styles from "./layout.module.css";

// 지원자 화면 틀. 비로그인도 볼 수 있다
export default function PostingsLayout({ children }: LayoutProps<"/postings">) {
  return (
    <div className={styles.shell}>
      <ApplicantHeader />
      <main className={styles.main}>{children}</main>
    </div>
  );
}
