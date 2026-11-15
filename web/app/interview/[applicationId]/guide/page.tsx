import { notFound } from "next/navigation";
import { Suspense } from "react";
import GuideView from "@/components/interview/GuideView";
import ApplicantShell from "@/components/layout/ApplicantShell";

type Props = PageProps<"/interview/[applicationId]/guide">;

async function Guide({ params }: { params: Props["params"] }) {
  const id = Number((await params).applicationId);
  if (!Number.isInteger(id)) notFound();
  return <GuideView applicationId={id} />;
}

// 화면 22 AI 화상 면접 안내사항 (지원자)
export default function GuidePage(props: Props) {
  return (
    <ApplicantShell>
      <Suspense>
        <Guide params={props.params} />
      </Suspense>
    </ApplicantShell>
  );
}
