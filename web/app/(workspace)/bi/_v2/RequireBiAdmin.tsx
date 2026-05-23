/* eslint-disable i18n/no-literal-ui-text */
"use client";

import { Lock, ShieldAlert } from "lucide-react";
import { type ReactNode } from "react";
import { useBiAdminIdentity, type BiAdminIdentity } from "./useBiAdminIdentity";

export type RequireBiAdminProps = {
  // children 必接收已认证的 admin identity；未认证或非 admin 时 children 不会渲染。
  children: (identity: BiAdminIdentity & { authenticated: true; isAdmin: true }) => ReactNode;
  // 兜底 fallback：未登录或权限不足时显示的内容。默认 LoginPrompt / NotAdminPrompt。
  unauthenticated?: ReactNode;
  notAdmin?: ReactNode;
};

// Single cross-cutting boundary for BI Admin access. Replaces the per-panel
// `if (!identity.authenticated)` scatter (Round 2 reviewer 找出的 6 处重复)。
// Children only render when identity is fully authenticated AND admin. This
// means every panel below the boundary can assume identity.actorId is real,
// removing the "fabricate audit with actor='unauthenticated'" footgun.
export function RequireBiAdmin({ children, unauthenticated, notAdmin }: RequireBiAdminProps) {
  const identity = useBiAdminIdentity();

  if (!identity.authenticated) {
    return <>{unauthenticated ?? <UnauthenticatedView />}</>;
  }
  if (!identity.isAdmin) {
    return <>{notAdmin ?? <NotAdminView identity={identity} />}</>;
  }

  // TypeScript 收窄到 authenticated:true & isAdmin:true 的 identity。
  return <>{children(identity as BiAdminIdentity & { authenticated: true; isAdmin: true })}</>;
}

function UnauthenticatedView() {
  return (
    <div
      className="mx-auto flex max-w-2xl flex-col items-start gap-3 rounded-md border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800"
      role="alert"
    >
      <div className="flex items-center gap-2 font-semibold">
        <Lock className="h-4 w-4" aria-hidden /> BI 后台需 admin 登录
      </div>
      <p className="text-xs leading-relaxed">
        BI 会员经营后台是 admin-only 工作区。当前会话未携带 BI Admin token。请通过
        <code className="mx-1 rounded bg-white px-1 py-0.5 font-mono text-[11px]">bi-admin-auth</code>
        模块登录后访问，所有写动作（备注 / 跟进 / audit）均会绑定真实 actor_id 写入服务端。
      </p>
      <p className="text-[11px] text-rose-700">
        开发环境无 admin session 时 BI v2 仅展示该提示页；不会渲染任何 panel，也不会发起
        admin API 请求（避免 audit 漂移 / actor 伪造 / 截图被误读为生产数据）。
      </p>
    </div>
  );
}

function NotAdminView({ identity }: { identity: BiAdminIdentity }) {
  return (
    <div
      className="mx-auto flex max-w-2xl flex-col items-start gap-3 rounded-md border border-amber-200 bg-amber-50 p-6 text-sm text-amber-800"
      role="alert"
    >
      <div className="flex items-center gap-2 font-semibold">
        <ShieldAlert className="h-4 w-4" aria-hidden /> 当前账号权限不足
      </div>
      <p className="text-xs">
        当前账号 <code className="font-mono">{identity.actorId}</code> 已认证但非 admin。
        BI 后台仅 admin 可见；请使用 admin 账号登录或联系运维授予权限。
      </p>
    </div>
  );
}
