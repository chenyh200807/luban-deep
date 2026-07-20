"""luban_lesson 域共享夹具。

2026-07-20 补题批后 40 个 practice 包全部完成人审签发(supply_ready=True),
仓库里不再存在真实的 pending/未签发包。fail-closed 契约测试(未签发=默认拒发)
改用本文件的**合成 pending 夹具**继续守约:取真实已签 authority 深拷贝,把全部
review 重置为 pending/无签名,再经 ``validate_practice_authority`` 复验——保证
合成态仍是编译管道可能产出的合法世界态,而不是"专供测试的假形状"。
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Callable

import pytest

import deeptutor.services.luban_lesson.practice_html as practice_html
import deeptutor.services.luban_lesson.read_model as read_model


def pendingized_authority(authority: dict[str, Any]) -> dict[str, Any]:
    """把一份已签发 v3 authority 变成"全题 pending/未签名"的合法合成态。

    只重置治理层(review/eligible/revoked);题目内容 identity(content_sha256、
    projection_receipt)不变——与真实"编译完成、人审未过"的世界态同形。
    """
    pending = copy.deepcopy(authority)
    for item in pending["items"]:
        item["review"] = practice_html._default_review(item["content_sha256"])
        item["eligible"] = False
        item["revoked"] = False
        item["revocation_refs"] = []
    for surface in pending["surfaces"]:
        surface["eligible_variant_ids"] = []
    # 合成态必须通过与生产 load 相同的 validator——防夹具自身腐化。
    return practice_html.validate_practice_authority(
        pending, expected_pack=pending["pack_id"]
    )


@pytest.fixture
def pendingize_pack(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[str], dict[str, Any]]:
    """让指定 pack 的 compiled authority 以"未签发(pending)"世界态被消费。

    只拦截 manifest 注册路径的读取(``authority_path is None``);显式 sidecar
    直读(tamper 类测试)不受影响。同时补丁 ``practice_html`` 与 ``read_model``
    两个消费命名空间(read_model 以 from-import 绑定了同名符号)。返回
    pendingized authority 供测试直接断言。
    """
    real_load = practice_html.load_compiled_practice

    def _install(pack_id: str) -> dict[str, Any]:
        target = str(pack_id or "").strip().upper()
        canonical = real_load(target)
        assert canonical is not None, f"{target} 未登记 compiled authority"
        pending = pendingized_authority(canonical)

        def fake(
            pid: str, *, authority_path: Path | None = None
        ) -> dict[str, Any] | None:
            if authority_path is None and str(pid or "").strip().upper() == target:
                # 仍走一次真实 load(digest/公开投影 sha 校验)再替换治理层。
                value = real_load(pid)
                if value is None:
                    return None
                return pendingized_authority(value)
            return real_load(pid, authority_path=authority_path)

        monkeypatch.setattr(practice_html, "load_compiled_practice", fake)
        monkeypatch.setattr(read_model, "load_compiled_practice", fake)
        return pending

    return _install
