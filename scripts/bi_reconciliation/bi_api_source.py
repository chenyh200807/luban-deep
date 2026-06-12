"""取数器①：BI API 实拍（X-Metrics-Token，只读）。

路径 DSL：`endpoint:dot.path`，列表选择器 `list[key=value]`。
解析失败一律返回 (None, reason)——降级也是证据，不抛异常。
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from deeptutor.services.bi_metrics import BI_METRICS
from scripts.bi_reconciliation.mapping import METRIC_MAPPINGS
from scripts.bi_reconciliation.types import SOURCE_BI_API, SourceReading

BI_ENDPOINTS = ("overview", "cost", "members", "anomalies")


def _get_with_retry(client: httpx.Client, url: str, params: dict[str, Any], attempts: int = 3) -> httpx.Response:
    """瞬时 5xx 重试（test2 实测偶发 502）；4xx 不重试直接抛。"""
    last: httpx.Response | None = None
    for attempt in range(attempts):
        resp = client.get(url, params=params)
        if resp.status_code < 500:
            resp.raise_for_status()
            return resp
        last = resp
        time.sleep(1.5 * (attempt + 1))
    assert last is not None
    last.raise_for_status()
    return last


def fetch_bi_payloads(base_url: str, metrics_token: str, window_days: int = 7) -> dict[str, Any]:
    """在线抓取（live run 用）；离线测试不调用此函数。窗口参数名为 days（int）。"""
    headers = {"X-Metrics-Token": metrics_token}
    out: dict[str, Any] = {}
    with httpx.Client(base_url=base_url, headers=headers, timeout=30, trust_env=False) as client:
        for ep in BI_ENDPOINTS:
            resp = _get_with_retry(client, f"/api/v1/bi/{ep}", {"days": window_days})
            out[ep] = resp.json()
    return out


def _resolve(payload: Any, locator: str) -> tuple[float | None, str]:
    """沿 dot path 取值；段形如 `key` 或 `listkey[k=v]`。返回 (value, reason)。"""
    if payload is None:
        return None, "endpoint_payload_missing"
    node: Any = payload
    for seg in locator.split("."):
        selector = None
        if "[" in seg and seg.endswith("]"):
            seg, _, rest = seg.partition("[")
            selector = rest[:-1]
        if seg:
            if not isinstance(node, dict) or seg not in node:
                return None, f"path_not_found:{seg}"
            node = node[seg]
        if selector is not None:
            key, _, expected = selector.partition("=")
            if not isinstance(node, list):
                return None, f"not_a_list:{seg}"
            matches = [x for x in node if isinstance(x, dict) and str(x.get(key)) == expected]
            if not matches:
                return None, f"selector_no_match:{selector}"
            node = matches[0]
    if node is None:
        return None, "value_is_null"
    if isinstance(node, bool) or not isinstance(node, (int, float, str)):
        return None, f"non_scalar:{type(node).__name__}"
    if isinstance(node, str):
        stripped = node.strip().rstrip("%")
        try:
            return float(stripped), ""
        except ValueError:
            return None, f"non_numeric_string:{node[:40]}"
    return float(node), ""


def extract_bi_readings(payloads: dict[str, Any], window_days: int) -> list[SourceReading]:
    readings: list[SourceReading] = []
    for m in METRIC_MAPPINGS:
        if not m.bi_api_path:
            continue
        endpoint, _, locator = m.bi_api_path.partition(":")
        value, reason = _resolve(payloads.get(endpoint), locator)
        meta: dict[str, Any] = {"path": m.bi_api_path}
        if value is None:
            meta["reason"] = reason or "path_not_found"
        if m.metric_id == "total_cost_usd":
            cross, _ = _resolve(payloads.get("overview"), "summary.total_cost_usd")
            meta["overview_summary_total_cost_usd"] = cross
        readings.append(SourceReading(m.metric_id, SOURCE_BI_API, value, window_days, meta))
    return readings


def _collect_kpi_labels(payloads: dict[str, Any]) -> list[str]:
    """遍历各端点的 cards/kpis 数组收集 label 字段。"""
    labels: list[str] = []
    for payload in payloads.values():
        if not isinstance(payload, dict):
            continue
        candidates = list(payload.get("cards") or [])
        boss = payload.get("boss_workbench")
        if isinstance(boss, dict):
            candidates.extend(boss.get("kpis") or [])
        for item in candidates:
            if isinstance(item, dict) and isinstance(item.get("label"), str):
                labels.append(item["label"])
    return labels


def find_unregistered_labels(payloads: dict[str, Any]) -> list[str]:
    """payload KPI 标签中无法经注册表 label/label_aliases 解析的项——P2 收口清单。"""
    known: set[str] = set()
    for metric in BI_METRICS:
        known.add(metric.label)
        known.update(metric.label_aliases)
    return sorted(set(_collect_kpi_labels(payloads)) - known)
