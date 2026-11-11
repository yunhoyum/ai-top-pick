import { notFound } from "next/navigation";
import { Suspense } from "react";
import RankingView from "@/components/evaluation/RankingView";

type Props = PageProps<"/admin/postings/[postingId]/document/ranking">;

async function Ranking({ params }: { params: Props["params"] }) {
  const { postingId } = await params;
  const id = Number(postingId);
  if (!Number.isInteger(id)) notFound();
  return <RankingView postingId={id} />;
}

// 화면 17 서류 지원자 순위 (ADM-023)
export default function DocumentRankingPage(props: Props) {
  return (
    <Suspense>
      <Ranking params={props.params} />
    </Suspense>
  );
}
