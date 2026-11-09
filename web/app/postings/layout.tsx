import ApplicantShell from "@/components/layout/ApplicantShell";

export default function PostingsLayout({ children }: LayoutProps<"/postings">) {
  return <ApplicantShell>{children}</ApplicantShell>;
}
