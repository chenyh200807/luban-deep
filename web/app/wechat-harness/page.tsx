import type { Metadata } from "next";

import { loadWechatHarnessCases } from "@/lib/wechat-harness-data";
import WechatHarnessClient from "./WechatHarnessClient";

export const metadata: Metadata = {
  title: "微信小程序影子测试 | 鲁班智考",
  description: "Replay mini-program rendering contracts in a Web test harness.",
};

export default function WechatHarnessPage() {
  const cases = loadWechatHarnessCases();
  return <WechatHarnessClient cases={cases} />;
}

