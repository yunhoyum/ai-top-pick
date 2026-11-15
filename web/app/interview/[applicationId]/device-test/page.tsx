import { notFound } from "next/navigation";
import { Suspense } from "react";
import DeviceTestView from "@/components/interview/DeviceTestView";
import ApplicantShell from "@/components/layout/ApplicantShell";

type Props = PageProps<"/interview/[applicationId]/device-test">;

async function DeviceTest({ params }: { params: Props["params"] }) {
  const id = Number((await params).applicationId);
  if (!Number.isInteger(id)) notFound();
  return <DeviceTestView applicationId={id} />;
}

// 화면 23 화상 면접 기술적 테스트 (지원자)
export default function DeviceTestPage(props: Props) {
  return (
    <ApplicantShell>
      <Suspense>
        <DeviceTest params={props.params} />
      </Suspense>
    </ApplicantShell>
  );
}
