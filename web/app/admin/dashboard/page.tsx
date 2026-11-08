import { Suspense } from "react";
import DashboardView from "@/components/dashboard/DashboardView";

// 화면 03 대시보드 (관리자). 로그인하면 가장 먼저 보이는 화면이다
export default function DashboardPage() {
  return (
    <Suspense>
      <DashboardView />
    </Suspense>
  );
}
