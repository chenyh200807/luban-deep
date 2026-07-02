"""微信小程序订阅消息发送（双轮设计 v3.2 §9-D12「明天见」推送的服务端半边）。

Authority 边界（single-authority，不建第二权威）：
- ``access_token`` 唯一来源 = 注入的 ``access_token_provider``（复用
  ``MemberConsoleService._get_wechat_access_token`` 的 stable_token 缓存，
  本模块绝不自取 token）。
- 模板 ID 唯一来源 = env（``TEMPLATE_ENV_KEYS``）；owner 在公众号后台申请模板后
  填入，未配置 = 链路建成前的合法状态。

降级契约（§9-D12：授权失败/未配置/上游失败一律退化为 App 内红点，不硬弹不阻断）：
本模块**永不 raise 到调用方主流程**——一切失败路径都折叠为结构化
``SendResult(status="degraded_red_dot", reason=...)``，消费侧据此渲染红点 +
英雄位文案。``sent`` 是唯一成功态。

Wiring 说明（防 unconsumed island）：本模块随交接时刻 UI 落地时由 spike 接线
（记录授权 → 次日到期时调用本函数）；在那之前不开 API endpoint。
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from typing import Any, Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)

_SEND_URL = "https://api.weixin.qq.com/cgi-bin/message/subscribe/send"

# 模板语义键 → env 键。新增推送类型 = 加一行（register-before-use：env 键即登记面）。
TEMPLATE_ENV_KEYS: dict[str, str] = {
    # 交接时刻授权的「明天这个考点换身皮再来考你一次」次日复测提醒
    "next_day_retest": "WECHAT_SUBSCRIBE_TMPL_NEXT_DAY_RETEST",
}

# 微信侧「用户拒绝/未授权」错误码（一次性订阅每发一条耗一次授权）
_ERR_USER_REFUSED = 43101


@dataclass(frozen=True)
class SendResult:
    status: str  # "sent" | "degraded_red_dot"
    reason: str = ""  # degraded 时的机器可读原因
    errcode: int = 0

    @property
    def sent(self) -> bool:
        return self.status == "sent"


def _degraded(reason: str, errcode: int = 0) -> SendResult:
    return SendResult(status="degraded_red_dot", reason=reason, errcode=errcode)


def resolve_template_id(template_key: str) -> str:
    env_key = TEMPLATE_ENV_KEYS.get(template_key, "")
    if not env_key:
        return ""
    return str(os.getenv(env_key) or "").strip()


async def send_subscribe_message(
    *,
    openid: str,
    template_key: str,
    data: dict[str, Any],
    access_token_provider: Callable[[], Awaitable[str]],
    page: str = "",
) -> SendResult:
    """发送一条订阅消息；任何失败都折叠为红点降级，绝不向上抛。

    ``data`` 形状须匹配 owner 申请到的模板字段（如 ``{"thing1": {"value": ...}}``）。
    """
    if template_key not in TEMPLATE_ENV_KEYS:
        # 未登记的模板语义键是编程错误而非运行时状态——这是唯一 raise 的入口校验
        raise ValueError(f"unregistered template_key: {template_key!r}")

    openid = str(openid or "").strip()
    if not openid:
        return _degraded("missing_openid")

    template_id = resolve_template_id(template_key)
    if not template_id:
        return _degraded("template_not_configured")

    try:
        access_token = await access_token_provider()
    except Exception:
        logger.warning("wechat_subscribe: access token unavailable", exc_info=True)
        return _degraded("access_token_unavailable")

    body: dict[str, Any] = {
        "touser": openid,
        "template_id": template_id,
        "data": data,
    }
    if page:
        body["page"] = page

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                _SEND_URL, params={"access_token": access_token}, json=body
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError:
        logger.warning("wechat_subscribe: upstream error", exc_info=True)
        return _degraded("upstream_error")

    errcode = int(payload.get("errcode") or 0)
    if errcode == 0:
        return SendResult(status="sent")
    if errcode == _ERR_USER_REFUSED:
        # 用户拒绝/授权额度耗尽：§9-D12 明确的合法降级路径，不是错误
        return _degraded("user_refused", errcode)
    logger.warning(
        "wechat_subscribe: send failed errcode=%s errmsg=%s",
        errcode,
        payload.get("errmsg"),
    )
    return _degraded(f"errcode_{errcode}", errcode)
