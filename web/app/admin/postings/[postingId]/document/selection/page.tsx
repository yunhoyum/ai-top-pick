import { notFound } from "next/navigation";
import { Suspense } from "react";
import SelectionView from "@/components/evaluation/SelectionView";

type Props = PageProps<"/admin/postings/[postingId]/document/selection">;

async function Selection({ params }: { params: Props["params"] }) {
  const { postingId } = await params;
  const id = Number(postingId);
  if (!Number.isInteger(id)) notFound();
  return <SelectionView postingId={id} />;
}

// 화면 20 서류 전형 합격자 선정 (ADM-025)
export default function DocumentSelectionPage(props: Props) {
  return (
    <Suspense>
      <Selection params={props.params} />
    </Suspense>
  );
}
