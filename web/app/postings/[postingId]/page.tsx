import { notFound } from "next/navigation";
import { Suspense } from "react";
import PublicPostingDetailView from "@/components/applicant/PublicPostingDetailView";

type Props = PageProps<"/postings/[postingId]">;

async function Detail({ params }: { params: Props["params"] }) {
  const { postingId } = await params;
  const id = Number(postingId);
  if (!Number.isInteger(id)) notFound();
  return <PublicPostingDetailView postingId={id} />;
}

// 화면 11-1 채용공고 상세 (지원자)
export default function PostingDetailPage(props: Props) {
  return (
    <Suspense>
      <Detail params={props.params} />
    </Suspense>
  );
}
