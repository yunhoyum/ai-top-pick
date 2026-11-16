import { notFound } from "next/navigation";
import { Suspense } from "react";
import RankingView from "@/components/evaluation/RankingView";

type Props = PageProps<"/admin/postings/[postingId]/interview/ranking">;

async function Ranking({ params }: { params: Props["params"] }) {
  const { postingId } = await params;
  const id = Number(postingId);
  if (!Number.isInteger(id)) notFound();
  return <RankingView postingId={id} stage="interview" />;
}

// 화면 27 면접 지원자 순위 (ADM-029)
export default function InterviewRankingPage(props: Props) {
  return (
    <Suspense>
      <Ranking params={props.params} />
    </Suspense>
  );
}
