import { notFound } from "next/navigation";
import { Suspense } from "react";
import CompanyQuestionsForm from "@/components/posting/CompanyQuestionsForm";
import DocCriteriaForm from "@/components/posting/DocCriteriaForm";
import DocItemsForm from "@/components/posting/DocItemsForm";
import InterviewCriteriaForm from "@/components/posting/InterviewCriteriaForm";
import PostingInfoForm from "@/components/posting/PostingInfoForm";

type Props = PageProps<"/admin/postings/[postingId]/edit/[step]">;

async function EditStep({ params }: { params: Props["params"] }) {
  const { postingId, step } = await params;
  const id = Number(postingId);
  // 지금은 1~5단계(공고 정보, 서류 문항, 서류 평가기준, 면접 평가기준, 기업 질문)만 있다. 나머지 단계는 화면이 만들어지면 추가한다
  if (!Number.isInteger(id)) notFound();
  if (step === "info") return <PostingInfoForm postingId={id} />;
  if (step === "doc-items") return <DocItemsForm postingId={id} />;
  if (step === "doc-criteria") return <DocCriteriaForm postingId={id} />;
  if (step === "interview-criteria") return <InterviewCriteriaForm postingId={id} />;
  if (step === "company-questions") return <CompanyQuestionsForm postingId={id} />;
  notFound();
}

// 화면 04~09 공고 등록·수정 단계 (경로의 step: info, doc-items, ...)
export default function EditPostingStepPage(props: Props) {
  return (
    <Suspense>
      <EditStep params={props.params} />
    </Suspense>
  );
}
