import WorkspaceFrame from "./WorkspaceFrame";
import { resolveBrandCopy } from "@/lib/brand";

const { brandName } = resolveBrandCopy();

export default function WorkspaceLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return <WorkspaceFrame brandName={brandName}>{children}</WorkspaceFrame>;
}
