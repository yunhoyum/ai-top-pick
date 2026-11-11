import { notFound } from "next/navigation";
import { Suspense } from "react";
import ReportView from "@/components/evaluation/ReportView";

type Props = PageProps<"/admin/postings/[postingId]/document/applications/[applicationId]/report">;

async function Report({ params }: { params: Props["params"] }) {
  const { postingId, applicationId } = await params;
  const posting = Number(postingId);
  const application = Number(applicationId);
  if (!Number.isInteger(posting) || !Number.isInteger(application)) notFound();
  return <ReportView postingId={posting} applicationId={application} />;
}

// 화면 18 서류 전형 결과 보고서 (ADM-021)
export default function DocumentReportPage(props: Props) {
  return (
    <Suspense>
      <Report params={props.params} />
    </Suspense>
  );
}
