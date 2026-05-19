import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { loadWechatHarnessCases } from "@/lib/wechat-harness-data";
import WechatHarnessClient from "./WechatHarnessClient";

// /wechat-harness is a dev-only mirror of the Learning Brain visible chain
// (see contracts/learner-state.md §wechat-harness wrapper). Backend already
// gates /api/v1/learning-brain/harness-* via _qa_enabled(); this page-level
// gate mirrors that contract so the page itself returns 404 (not just empty
// data) outside of intended dev surfaces — defense-in-depth single authority.
//
// force-dynamic prevents Next.js from baking the gate decision at build time
// from the build host's env; the gate is evaluated per request.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "微信小程序影子测试 | 鲁班智考",
  description: "Replay mini-program rendering contracts in a Web test harness.",
};

const TRUTHY = new Set(["1", "true", "yes", "on"]);

function isWechatHarnessEnabled(): boolean {
  // Dev mode (`next dev`): always open — this is exactly when the harness
  // is meant to be used. NODE_ENV is set by Next.js itself.
  if (process.env.NODE_ENV !== "production") return true;

  // Production build (next build + next start, or deployed): require explicit
  // local env + flag, matching backend _qa_enabled() in
  // deeptutor/services/runtime_env.py / api/routers/learning_brain.py:154.
  const env = (
    process.env.DEEPTUTOR_ENV ??
    process.env.APP_ENV ??
    process.env.ENV ??
    process.env.ENVIRONMENT ??
    process.env.SERVICE_ENV ??
    ""
  )
    .trim()
    .toLowerCase();
  if (env !== "local") return false;

  const flag = (process.env.DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA ?? "")
    .trim()
    .toLowerCase();
  return TRUTHY.has(flag);
}

export default function WechatHarnessPage() {
  if (!isWechatHarnessEnabled()) {
    notFound();
  }
  const cases = loadWechatHarnessCases();
  return <WechatHarnessClient cases={cases} />;
}
