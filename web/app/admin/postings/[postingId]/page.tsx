import { notFound } from "next/navigation";
import { Suspense } from "react";
import PostingDetailView from "@/components/posting/detail/PostingDetailView";

type Props = PageProps<"/admin/postings/[postingId]">;

async function Detail({ params }: { params: Props["params"] }) {
  const { postingId } = await params;
  const id = Number(postingId);
  if (!Number.isInteger(id)) notFound();
  return <PostingDetailView postingId={id} />;
}

// 화면 11 채용공고 상세 (관리자)
export default function PostingDetailPage(props: Props) {
  return (
    <Suspense>
      <Detail params={props.params} />
    </Suspense>
  );
}
