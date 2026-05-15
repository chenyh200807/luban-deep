import type { Metadata } from "next";

import InviteTestPage from "./InviteTestPage";

export const metadata: Metadata = {
  title: "鲁班智考 AI 建筑实务内测申请",
  description: "面向佑森建筑实务学员的申请制 AI 学习助手内测入口。",
};

export default function Page() {
  return <InviteTestPage />;
}
