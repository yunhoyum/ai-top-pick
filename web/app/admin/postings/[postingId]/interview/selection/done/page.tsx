import { notFound } from "next/navigation";
import { Suspense } from "react";
import SelectionDoneView from "@/components/evaluation/SelectionDoneView";

type Props = PageProps<"/admin/postings/[postingId]/interview/selection/done">;

async function SelectionDone({ params }: { params: Props["params"] }) {
  const { postingId } = await params;
  const id = Number(postingId);
  if (!Number.isInteger(id)) notFound();
  return <SelectionDoneView postingId={id} stage="interview" />;
}

// 화면 30-1 면접 전형 합격자 확정 완료
export default function InterviewSelectionDonePage(props: Props) {
  return (
    <Suspense>
      <SelectionDone params={props.params} />
    </Suspense>
  );
}
