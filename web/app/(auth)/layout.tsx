import AuthBrandPanel from "@/components/layout/AuthBrandPanel";
import styles from "./auth.module.css";

// 로그인(01)·회원가입(02) 공통: 왼쪽 브랜드 패널 + 오른쪽 폼
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={styles.layout}>
      <AuthBrandPanel />
      <main className={styles.formArea}>{children}</main>
    </div>
  );
}
