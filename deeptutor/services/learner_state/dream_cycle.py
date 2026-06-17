"""Learning Brain dream cycle（gbrain 式夜间巩固）。

哲学（gbrain）：与其让 agent 在聊天 turn 里拼命重算画像，不如跑一个 24/7
后台循环做 ingest/enrich/consolidate——把全量历史合成结果持久化成投影缓存，
turn 内只读缓存。

单一权威边界：
- 合成只经 ``service.synthesize_learning_truth``（learning_synthesis 是唯一
  合成权威），本模块不计算任何新事实；
- 持久化与 canonical 促升门控（G4 cohort / 授权 flag）全部在 service 与
  canonical_truth_policy 内生效，本模块不绕过；
- 本模块只回答三件事：何时跑（interval）、跑哪些用户（候选枚举 + 生产
  cohort 限定）、跑成什么样（report）。

默认关（``LUBAN_LEARNING_BRAIN_DREAM_CYCLE_ENABLED`` fail-closed），生产
环境候选用户限定在 G4 canonical cohort 内，与现有授权门保持同一边界。
"""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from deeptutor.logging import get_logger
from deeptutor.services.config.env_store import get_env_store
from deeptutor.services.learner_state.canonical_truth_policy import (
    canonical_truth_production_write_cohort_allowed,
)
from deeptutor.services.learner_state.worker_file_lock import try_exclusive_file_lock
from deeptutor.services.runtime_env import env_flag, is_production_environment

DREAM_CYCLE_ENABLED_FLAG = "LUBAN_LEARNING_BRAIN_DREAM_CYCLE_ENABLED"
DREAM_CYCLE_INTERVAL_HOURS_ENV = "LUBAN_LEARNING_BRAIN_DREAM_CYCLE_INTERVAL_HOURS"
DREAM_CYCLE_DEFAULT_INTERVAL_HOURS = 24.0
DREAM_CYCLE_WATERMARK_FILENAME = ".dream_cycle_last_run"
DREAM_CYCLE_LOCK_FILENAME = ".dream_cycle.lock"

logger = get_logger("LearningBrainDreamCycle")


class LearningBrainDreamCycle:
    """对有学习证据的用户做全量历史合成并持久化投影缓存的夜间巩固器。"""

    def __init__(self, service: Any, *, state_dir: Path | None = None) -> None:
        self._service = service
        # state_dir 给定时：watermark 持久化到文件（跨 worker / 跨重启共享），
        # 并用同目录的文件锁保证多 worker 只有一个实际执行者。
        self._state_dir = Path(state_dir) if state_dir is not None else None
        self._last_run_at: float | None = None
        self._last_report: dict[str, Any] = {}

    @property
    def last_report(self) -> dict[str, Any]:
        return dict(self._last_report)

    def enabled(self) -> bool:
        return env_flag(DREAM_CYCLE_ENABLED_FLAG, default=False)

    def interval_seconds(self) -> float:
        raw = get_env_store().get(
            DREAM_CYCLE_INTERVAL_HOURS_ENV,
            str(DREAM_CYCLE_DEFAULT_INTERVAL_HOURS),
        )
        try:
            hours = float(raw)
        except (TypeError, ValueError):
            hours = DREAM_CYCLE_DEFAULT_INTERVAL_HOURS
        if hours <= 0:
            hours = DREAM_CYCLE_DEFAULT_INTERVAL_HOURS
        return hours * 3600.0

    def due(self, *, now: float) -> bool:
        last_run = self._read_watermark()
        if last_run is None:
            return True
        return (now - last_run) >= self.interval_seconds()

    def _read_watermark(self) -> float | None:
        if self._state_dir is None:
            return self._last_run_at
        path = self._state_dir / DREAM_CYCLE_WATERMARK_FILENAME
        try:
            return float(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return self._last_run_at

    def _write_watermark(self, now: float) -> None:
        # 有意先更新内存：文件写失败时本进程退化为内存节流（仍按 interval），
        # 若反序则持续写失败会变成每个 tick 重跑——比对等降级更糟。
        self._last_run_at = now
        if self._state_dir is None:
            return
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            (self._state_dir / DREAM_CYCLE_WATERMARK_FILENAME).write_text(
                f"{now}\n", encoding="utf-8"
            )
        except OSError:  # watermark 写失败只退化为本进程内存语义，不中断巩固
            logger.warning("dream cycle watermark write failed", exc_info=True)

    def run_once(self, *, now: float | None = None, force: bool = False) -> dict[str, Any]:
        current = time.time() if now is None else float(now)
        if not self.enabled():
            return {"ran": False, "reason": "disabled"}
        if not force and not self.due(now=current):
            return {"ran": False, "reason": "not_due"}
        if self._state_dir is not None:
            with try_exclusive_file_lock(self._state_dir / DREAM_CYCLE_LOCK_FILENAME) as acquired:
                if not acquired:
                    return {"ran": False, "reason": "lock_held"}
                # 拿锁后重读 watermark：并发的另一个 worker 可能刚跑完。
                if not force and not self.due(now=current):
                    return {"ran": False, "reason": "not_due"}
                return self._consolidate_all(now=current, force=force)
        return self._consolidate_all(now=current, force=force)

    def _consolidate_all(self, *, now: float, force: bool) -> dict[str, Any]:
        # force 在此只用于 report.reason 标注；due/锁判定都在调用方完成。
        user_ids = self._candidate_user_ids()
        consolidated: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for user_id in user_ids:
            if not self._user_allowed(user_id):
                skipped.append({"user_id": user_id, "reason": "production_cohort_required"})
                continue
            try:
                result = self._service.synthesize_learning_truth(
                    user_id,
                    dry_run=False,
                    event_limit=None,
                )
            except Exception as exc:  # noqa: BLE001 — 单用户失败必须隔离
                logger.warning(f"dream cycle synthesis failed: user_id={user_id} error={exc}")
                errors.append({"user_id": user_id, "error": str(exc)})
                continue
            promotion = (
                dict(result.get("canonical_truth_promotion") or {})
                if isinstance(result, dict)
                else {}
            )
            consolidated.append({
                "user_id": user_id,
                "promotion_reason": str(promotion.get("reason") or ""),
            })

        self._write_watermark(now)
        report = {
            "ran": True,
            "reason": "due" if not force else "forced",
            "user_count": len(user_ids),
            "consolidated": consolidated,
            "skipped": skipped,
            "errors": errors,
        }
        self._last_report = report
        logger.info(
            f"dream cycle completed: users={len(user_ids)} consolidated={len(consolidated)} "
            f"skipped={len(skipped)} errors={len(errors)}"
        )
        return report

    def _candidate_user_ids(self) -> list[str]:
        lister = getattr(self._service, "list_local_memory_event_user_ids", None)
        if not callable(lister):
            return []
        try:
            return [str(item) for item in list(lister() or []) if str(item or "").strip()]
        except Exception:  # noqa: BLE001 — 枚举失败不让循环崩
            logger.warning("dream cycle user enumeration failed", exc_info=True)
            return []

    def _user_allowed(self, user_id: str) -> bool:
        if is_production_environment():
            return canonical_truth_production_write_cohort_allowed(user_id)
        return True


__all__ = [
    "DREAM_CYCLE_DEFAULT_INTERVAL_HOURS",
    "DREAM_CYCLE_ENABLED_FLAG",
    "DREAM_CYCLE_INTERVAL_HOURS_ENV",
    "LearningBrainDreamCycle",
]
