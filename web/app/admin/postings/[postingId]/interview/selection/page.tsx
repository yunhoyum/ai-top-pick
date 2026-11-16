import { notFound } from "next/navigation";
import { Suspense } from "react";
import SelectionView from "@/components/evaluation/SelectionView";

type Props = PageProps<"/admin/postings/[postingId]/interview/selection">;

async function Selection({ params }: { params: Props["params"] }) {
  const { postingId } = await params;
  const id = Number(postingId);
  if (!Number.isInteger(id)) notFound();
  return <SelectionView postingId={id} stage="interview" />;
}

// 화면 30 면접 전형 합격자 선정 (ADM-031)
export default function InterviewSelectionPage(props: Props) {
  return (
    <Suspense>
      <Selection params={props.params} />
    </Suspense>
  );
}
