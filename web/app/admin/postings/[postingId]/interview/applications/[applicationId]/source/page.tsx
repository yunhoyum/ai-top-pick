import { notFound } from "next/navigation";
import { Suspense } from "react";
import InterviewSourceView from "@/components/evaluation/InterviewSourceView";

type Props = PageProps<"/admin/postings/[postingId]/interview/applications/[applicationId]/source">;

async function Source({ params }: { params: Props["params"] }) {
  const { postingId, applicationId } = await params;
  const posting = Number(postingId);
  const application = Number(applicationId);
  if (!Number.isInteger(posting) || !Number.isInteger(application)) notFound();
  return <InterviewSourceView postingId={posting} applicationId={application} />;
}

// 화면 29 지원자 자료 원본 (면접, ADM-028)
export default function InterviewSourcePage(props: Props) {
  return (
    <Suspense>
      <Source params={props.params} />
    </Suspense>
  );
}
