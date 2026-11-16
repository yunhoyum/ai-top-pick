import { notFound } from "next/navigation";
import { Suspense } from "react";
import ReportView from "@/components/evaluation/ReportView";

type Props = PageProps<"/admin/postings/[postingId]/interview/applications/[applicationId]/report">;

async function Report({ params }: { params: Props["params"] }) {
  const { postingId, applicationId } = await params;
  const posting = Number(postingId);
  const application = Number(applicationId);
  if (!Number.isInteger(posting) || !Number.isInteger(application)) notFound();
  return <ReportView postingId={posting} applicationId={application} stage="interview" />;
}

// 화면 28 면접 전형 결과 보고서 (ADM-027)
export default function InterviewReportPage(props: Props) {
  return (
    <Suspense>
      <Report params={props.params} />
    </Suspense>
  );
}
