import { notFound } from "next/navigation";
import { Suspense } from "react";
import DoneView from "@/components/interview/DoneView";
import ApplicantShell from "@/components/layout/ApplicantShell";

type Props = PageProps<"/interview/[applicationId]/done">;

async function Done({ params, searchParams }: { params: Props["params"]; searchParams: Props["searchParams"] }) {
  const id = Number((await params).applicationId);
  if (!Number.isInteger(id)) notFound();
  const { answered, ended } = await searchParams;
  const count = Number(answered);
  return (
    <DoneView
      applicationId={id}
      answered={Number.isInteger(count) ? count : null}
      endedAt={typeof ended === "string" ? ended : null}
    />
  );
}

// 화면 25 면접 종료 안내 (지원자)
export default function DonePage(props: Props) {
  return (
    <ApplicantShell>
      <Suspense>
        <Done params={props.params} searchParams={props.searchParams} />
      </Suspense>
    </ApplicantShell>
  );
}
