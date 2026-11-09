import { notFound } from "next/navigation";
import { Suspense } from "react";
import ApplyView from "@/components/applicant/apply/ApplyView";

type Props = PageProps<"/postings/[postingId]/apply">;

async function Apply({ params }: { params: Props["params"] }) {
  const { postingId } = await params;
  const id = Number(postingId);
  if (!Number.isInteger(id)) notFound();
  return <ApplyView postingId={id} />;
}

// 화면 12~16 지원서 작성 (지원자)
export default function ApplyPage(props: Props) {
  return (
    <Suspense>
      <Apply params={props.params} />
    </Suspense>
  );
}
