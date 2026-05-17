import WorkspaceSidebar from "@/components/sidebar/WorkspaceSidebar";
import { UnifiedChatProvider } from "@/context/UnifiedChatContext";
import { BarChart3, MessageSquare } from "lucide-react";
import Image from "next/image";
import Link from "next/link";

const brandName = process.env.NEXT_PUBLIC_APP_BRAND_NAME || "鲁班智考";

export default function WorkspaceLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <UnifiedChatProvider>
      <div className="flex h-screen overflow-hidden">
        <div className="hidden md:block">
          <WorkspaceSidebar />
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-12 shrink-0 items-center justify-between border-b border-[var(--border)]/70 bg-[var(--secondary)] px-4 md:hidden">
            <Link href="/" className="flex items-center gap-2">
              <Image
                src="/logo-ver2.png"
                alt={brandName}
                width={491}
                height={346}
                style={{ width: "auto", height: 20 }}
              />
              <span className="text-[15px] font-semibold tracking-tight text-[var(--foreground)]">
                {brandName}
              </span>
            </Link>
            <nav className="flex items-center gap-1">
              <Link
                href="/"
                className="rounded-lg p-2 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--background)]/60 hover:text-[var(--foreground)]"
                aria-label="Chat"
              >
                <MessageSquare size={17} strokeWidth={1.8} />
              </Link>
              <Link
                href="/bi"
                className="rounded-lg p-2 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--background)]/60 hover:text-[var(--foreground)]"
                aria-label="BI"
              >
                <BarChart3 size={17} strokeWidth={1.8} />
              </Link>
            </nav>
          </header>
          <main className="min-w-0 flex-1 overflow-hidden bg-[var(--background)]">{children}</main>
        </div>
      </div>
    </UnifiedChatProvider>
  );
}
