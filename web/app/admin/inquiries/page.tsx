import { Suspense } from "react";
import InquiriesView from "@/components/inquiry/InquiriesView";

// 화면 26 문의·예외 처리 (관리자, ADM-026·041)
export default function InquiriesPage() {
  return (
    <Suspense>
      <InquiriesView />
    </Suspense>
  );
}
