"""Polyv 视频签名下发（服务端签名，密钥不进客户端）。

背景：免费课详情页（yousenwebview host 页）播放 polyv 视频需要 {ts, sign}。
2026-06-15 commit c76ac0d4 把客户端硬编码密钥 md5 签名删掉、改成"读服务端下发签名"，
但佑森后端从未实现下发 → 视频播不了。本接口在 deeptutor 后端补上服务端签名（密钥
POLYV_SECRET_KEY 只在服务端），客户端取签名即可播放，密钥不再暴露到可反编译的小程序包。

签名算法必须与 polyv 旧客户端逐字节一致：sign = md5(secret + vid + ts)，ts=毫秒时间戳。
"""

from __future__ import annotations

import hashlib
import os
import time

from fastapi import Depends
from pydantic import BaseModel

from deeptutor.api._secure_router import public_router
from deeptutor.api.dependencies.rate_limit import route_rate_limit

router = public_router(reason="anonymous polyv video signature for pre-login free-course pages (rate-limited)")

# polyv 账号 secretkey。默认值兼容历史算法；生产应通过 env 覆盖并轮换。
_DEFAULT_POLYV_SECRET = "mnABa9XMn8"


def _polyv_secret() -> str:
    return str(os.getenv("POLYV_SECRET_KEY", "") or "").strip() or _DEFAULT_POLYV_SECRET


class PolyvSignResponse(BaseModel):
    vid: str
    ts: int
    sign: str


@router.get(
    "/sign",
    response_model=PolyvSignResponse,
    dependencies=[
        Depends(
            route_rate_limit(
                "polyv_sign",
                default_max_requests=60,
                default_window_seconds=60.0,
            )
        )
    ],
)
def polyv_sign(vid: str) -> PolyvSignResponse:
    """返回 polyv 播放签名。sign = md5(secret + vid + ts)，与旧客户端算法一致。"""
    ts = int(time.time() * 1000)
    secret = _polyv_secret()
    sign = hashlib.md5(f"{secret}{vid}{ts}".encode("utf-8")).hexdigest()
    return PolyvSignResponse(vid=vid, ts=ts, sign=sign)
