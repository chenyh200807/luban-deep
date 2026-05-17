/* eslint-disable i18n/no-literal-ui-text -- Chinese-only invite application page. */
import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { ClipboardCheck, Home, Mail, MessageSquareText } from "lucide-react";
import { InviteApplicationForm } from "../InviteApplicationForm";

export const metadata: Metadata = {
  title: "填写鲁班智考内测申请",
  description: "填写鲁班智考 AI 陪考教练内测申请，提交手机、邮箱、备考阶段和真实学习痛点。",
};

export default function InviteTestApplyPage() {
  return (
    <div
      lang="zh-CN"
      className="h-screen touch-manipulation overflow-y-auto overflow-x-hidden bg-[#080c18] text-white selection:bg-[#5bbcff] selection:text-[#04111d]"
    >
      <header className="sticky top-0 z-40 border-b border-white/[0.08] bg-[#080c18]/[0.82] backdrop-blur-xl">
        <nav
          aria-label="鲁班智考内测申请导航"
          className="mx-auto flex min-h-16 max-w-7xl items-center justify-between gap-4 px-5 py-3 sm:px-8"
        >
          <Link
            href="/intro"
            aria-label="返回鲁班智考首页"
            className="flex min-w-0 items-center gap-3 rounded-full focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#5bbcff]"
          >
            <Image
              src="/images/logo-white.png"
              alt="鲁班智考"
              width={124}
              height={40}
              priority
              className="h-9 w-auto"
            />
          </Link>
          <div className="flex items-center gap-2">
            <Link
              href="/intro"
              className="inline-flex items-center gap-2 rounded-full border border-white/[0.12] bg-white/[0.06] px-4 py-2 text-sm font-bold text-white/[0.74] transition-colors hover:bg-white/[0.10] hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#5bbcff]"
            >
              <Home className="h-4 w-4" aria-hidden="true" />
              返回首页
            </Link>
            <Link
              href="/invite-test"
              className="hidden rounded-full border border-white/[0.12] bg-white/[0.06] px-4 py-2 text-sm font-bold text-white/[0.74] transition-colors hover:bg-white/[0.10] hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#5bbcff] sm:inline-flex"
            >
              内测介绍
            </Link>
          </div>
        </nav>
      </header>

      <main className="mx-auto grid max-w-7xl gap-8 px-5 py-10 sm:px-8 lg:grid-cols-[0.74fr_1.26fr] lg:gap-10 lg:py-24">
        <aside className="lg:sticky lg:top-28 lg:self-start">
          <div className="inline-flex items-center gap-3 rounded-full border border-white/[0.12] bg-white/[0.06] px-4 py-2 text-sm font-bold text-white/[0.72]">
            <ClipboardCheck className="h-4 w-4 text-[#66b6ff]" aria-hidden="true" />
            内测申请表
          </div>
          <h1 className="mt-6 text-balance text-4xl font-black leading-tight tracking-normal text-white sm:text-6xl lg:mt-8">
            申请加入
            <span className="block text-[#66b6ff]">AI 陪考教练内测</span>
          </h1>
          <p className="mt-6 max-w-xl text-pretty text-base leading-8 text-white/[0.62]">
            这里单独收集内测筛选信息。我们会根据备考阶段、真实痛点、可测试时间和回访意愿，邀请更适合首批体验的学员。
          </p>

          <div className="mt-10 hidden gap-5 lg:grid">
            <div className="rounded-[1.35rem] border border-white/10 bg-white/[0.055] p-5">
              <Mail className="h-6 w-6 text-[#66b6ff]" aria-hidden="true" />
              <h2 className="mt-5 text-2xl font-black tracking-normal text-white">邮箱为必填</h2>
              <p className="mt-3 text-sm leading-7 text-white/[0.58]">
                用于发送内测通知、体验说明和后续回访安排，不会作为公开注册承诺。
              </p>
            </div>
            <div className="rounded-[1.35rem] border border-white/10 bg-white/[0.055] p-5">
              <MessageSquareText className="h-6 w-6 text-[#66b6ff]" aria-hidden="true" />
              <h2 className="mt-5 text-2xl font-black tracking-normal text-white">通过后进入小程序体验</h2>
              <p className="mt-3 text-sm leading-7 text-white/[0.58]">
                可以提前准备一道最近做错的建筑实务选择题，或一段案例题作答，用于体验陪考教练批改。
              </p>
            </div>
          </div>
        </aside>

        <InviteApplicationForm sourcePage="invite-test-apply" />
      </main>
    </div>
  );
}
