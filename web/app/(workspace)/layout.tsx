import WorkspaceFrame from "./WorkspaceFrame";

const brandName = process.env.NEXT_PUBLIC_APP_BRAND_NAME || "鲁班智考";

export default function WorkspaceLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return <WorkspaceFrame brandName={brandName}>{children}</WorkspaceFrame>;
}
