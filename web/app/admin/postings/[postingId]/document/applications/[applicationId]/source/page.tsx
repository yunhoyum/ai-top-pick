import { notFound } from "next/navigation";
import { Suspense } from "react";
import SourceView from "@/components/evaluation/SourceView";

type Props = PageProps<"/admin/postings/[postingId]/document/applications/[applicationId]/source">;

async function Source({ params }: { params: Props["params"] }) {
  const { postingId, applicationId } = await params;
  const posting = Number(postingId);
  const application = Number(applicationId);
  if (!Number.isInteger(posting) || !Number.isInteger(application)) notFound();
  return <SourceView postingId={posting} applicationId={application} />;
}

// 화면 19 지원자 자료 원본 (ADM-022)
export default function DocumentSourcePage(props: Props) {
  return (
    <Suspense>
      <Source params={props.params} />
    </Suspense>
  );
}
