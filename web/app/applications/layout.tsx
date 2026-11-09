import ApplicantShell from "@/components/layout/ApplicantShell";

export default function ApplicationsLayout({ children }: LayoutProps<"/applications">) {
  return <ApplicantShell>{children}</ApplicantShell>;
}
