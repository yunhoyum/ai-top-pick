import { notFound } from "next/navigation";
import { Suspense } from "react";
import PostingInfoForm from "@/components/posting/PostingInfoForm";

type Props = PageProps<"/admin/postings/[postingId]/edit/[step]">;

async function EditStep({ params }: { params: Props["params"] }) {
  const { postingId, step } = await params;
  const id = Number(postingId);
  // 지금은 1단계(공고 정보)만 있다. 나머지 단계는 화면이 만들어지면 추가한다
  if (step !== "info" || !Number.isInteger(id)) notFound();
  return <PostingInfoForm postingId={id} />;
}

// 화면 04~09 공고 등록·수정 단계 (경로의 step: info, doc-items, ...)
export default function EditPostingStepPage(props: Props) {
  return (
    <Suspense>
      <EditStep params={props.params} />
    </Suspense>
  );
}
