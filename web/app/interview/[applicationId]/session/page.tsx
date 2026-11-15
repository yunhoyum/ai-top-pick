import { notFound } from "next/navigation";
import { Suspense } from "react";
import SessionView from "@/components/interview/SessionView";

type Props = PageProps<"/interview/[applicationId]/session">;

async function Session({ params, searchParams }: { params: Props["params"]; searchParams: Props["searchParams"] }) {
  const id = Number((await params).applicationId);
  const sessionId = Number((await searchParams).session);
  if (!Number.isInteger(id) || !Number.isInteger(sessionId)) notFound();
  return <SessionView applicationId={id} sessionId={sessionId} />;
}

// 화면 24 화상 면접 화면 (지원자). 지원자 머리글 대신 면접 막대(Interview Bar)를 쓴다
export default function SessionPage(props: Props) {
  return (
    <Suspense>
      <Session params={props.params} searchParams={props.searchParams} />
    </Suspense>
  );
}
