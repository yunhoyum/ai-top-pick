import { Suspense } from "react";
import AdminShell from "@/components/layout/AdminShell";

// 관리자 화면 공통: 로그인과 역할을 확인하고 사이드바를 보여준다
export default function AdminLayout({ children }: LayoutProps<"/admin">) {
  return (
    <Suspense>
      <AdminShell>{children}</AdminShell>
    </Suspense>
  );
}
