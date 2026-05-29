"""
backfill_phone_identity.py
==========================
把 external_auth/users.json 里的手机号补写进 Supabase DB。

每个 external_auth 用户条目结构：
    {
        "user_6508": {
            "id": "<UUID>",          ← canonical_uid，用于 wallet/用户表
            "phone": "13288620794",  ← 已 normalize 的 11 位手机号
            "username": "user_6508",
            "password_hash": "...",
            "created_at": "..."
        }
    }

写入目标：
    1. public.user_identity_aliases  alias_type='phone', alias_value=<phone>, user_id=<uuid>
    2. public.users.phone            WHERE id=<uuid> AND phone IS NULL

用法（在阿里云服务器上执行）：
    python scripts/backfill_phone_identity.py
    python scripts/backfill_phone_identity.py --users-file /app/data/user/external_auth/users.json
    python scripts/backfill_phone_identity.py --dry-run          # 只打印，不写库
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_USERS_FILES = [
    Path("/app/data/user/external_auth/users.json"),
    Path("/root/luban/.storage/users.json"),
]


# ──────────────────────────────────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────────────────────────────────

def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, TypeError):
        return False


def _normalize_phone(value: Any) -> str:
    """取后 11 位数字（与 external_auth.py normalize_external_phone 保持一致）。"""
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[-11:] if len(digits) >= 11 else ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────────────────
# 读取 external_auth/users.json
# ──────────────────────────────────────────────────────────────────────────────

def _find_users_file(override: str | None) -> Path:
    if override:
        p = Path(override)
        if not p.exists():
            sys.exit(f"ERROR: 指定的 users 文件不存在: {p}")
        return p
    for candidate in _DEFAULT_USERS_FILES:
        if candidate.exists():
            return candidate
    sys.exit(
        f"ERROR: 找不到 external_auth users 文件，默认位置：\n"
        + "\n".join(f"  {p}" for p in _DEFAULT_USERS_FILES)
        + "\n请用 --users-file 参数指定路径。"
    )


def load_external_auth_users(path: Path) -> dict[str, dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        sys.exit(f"ERROR: 读取 {path} 失败: {exc}")
    if not isinstance(raw, dict):
        sys.exit(f"ERROR: {path} 格式错误，期望 JSON object")
    return raw


def collect_phone_rows(users: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    """
    返回可写入 DB 的行列表，每行包含：
        username, canonical_uid, phone
    仅包含有手机号且 id 是合法 UUID 的用户。
    """
    rows: list[dict[str, str]] = []
    skipped_no_phone = 0
    skipped_no_uuid = 0

    for username, user_data in users.items():
        if not isinstance(user_data, dict):
            continue

        canonical_uid = _normalize_text(user_data.get("id"))
        phone = _normalize_phone(user_data.get("phone"))

        if not phone:
            skipped_no_phone += 1
            continue

        if not _is_uuid(canonical_uid):
            logger.warning("跳过 %s：id 不是合法 UUID（%s）", username, canonical_uid or "空")
            skipped_no_uuid += 1
            continue

        rows.append({
            "username": username,
            "canonical_uid": canonical_uid,
            "phone": phone,
        })

    logger.info(
        "external_auth 用户总数: %d | 有手机号且 UUID 正常: %d | 无手机号: %d | UUID 异常: %d",
        len(users),
        len(rows),
        skipped_no_phone,
        skipped_no_uuid,
    )
    return rows


# ──────────────────────────────────────────────────────────────────────────────
# 写 DB
# ──────────────────────────────────────────────────────────────────────────────

_UPSERT_ALIAS_SQL = """
INSERT INTO public.user_identity_aliases
    (alias_type, alias_value, user_id, source, confidence, verified_at)
VALUES (%s, %s, %s::uuid, %s, %s, %s)
ON CONFLICT (alias_type, alias_value) DO UPDATE SET
    user_id     = EXCLUDED.user_id,
    confidence  = EXCLUDED.confidence,
    verified_at = EXCLUDED.verified_at,
    updated_at  = now()
"""

_UPDATE_USERS_PHONE_SQL = """
UPDATE public.users
SET phone = %s
WHERE id = %s
  AND (phone IS NULL OR phone = '')
"""


def _get_connection(db_url: str):
    """返回 psycopg 或 psycopg2 连接（优先 psycopg3）。"""
    try:
        import psycopg
        return psycopg.connect(db_url, connect_timeout=10), False
    except ImportError:
        pass
    try:
        import psycopg2
        return psycopg2.connect(db_url, connect_timeout=10), True
    except ImportError:
        sys.exit("ERROR: 需要安装 psycopg 或 psycopg2：pip install psycopg[binary] 或 pip install psycopg2-binary")


def run_backfill(
    rows: list[dict[str, str]],
    *,
    db_url: str,
    dry_run: bool,
) -> None:
    now = _now_iso()
    alias_upserted = 0
    users_updated = 0

    if dry_run:
        logger.info("=== DRY RUN 模式，不写入任何数据 ===")
        for row in rows:
            logger.info(
                "[DRY RUN] alias: phone=%s → uuid=%s (%s)",
                row["phone"], row["canonical_uid"], row["username"],
            )
        return

    conn, is_psycopg2 = _get_connection(db_url)
    try:
        cur = conn.cursor()

        for row in rows:
            phone = row["phone"]
            canonical_uid = row["canonical_uid"]
            username = row["username"]

            # 1. user_identity_aliases
            try:
                cur.execute(
                    _UPSERT_ALIAS_SQL,
                    ("phone", phone, canonical_uid, "phone_backfill", 1.0, now),
                )
                alias_upserted += 1
            except Exception as exc:
                logger.warning("alias upsert 失败 username=%s phone=%s: %s", username, phone, exc)
                conn.rollback()
                continue

            # 2. users.phone（仅补空字段，不覆盖已有值）
            try:
                cur.execute(_UPDATE_USERS_PHONE_SQL, (phone, canonical_uid))
                if cur.rowcount and cur.rowcount > 0:
                    users_updated += 1
            except Exception as exc:
                logger.warning("users.phone 更新失败 username=%s uuid=%s: %s", username, canonical_uid, exc)

            if not is_psycopg2:
                conn.commit()
            else:
                conn.commit()

            logger.info(
                "✓ %s  phone=%s  uuid=%s",
                username, phone, canonical_uid,
            )

    finally:
        conn.close()

    logger.info(
        "\n完成：alias 写入 %d 条，users.phone 补写 %d 条（共 %d 个用户）",
        alias_upserted, users_updated, len(rows),
    )


# ──────────────────────────────────────────────────────────────────────────────
# 验证：执行后从 DB 读取确认
# ──────────────────────────────────────────────────────────────────────────────

def verify_results(rows: list[dict[str, str]], *, db_url: str) -> None:
    if not rows:
        return
    conn, _ = _get_connection(db_url)
    try:
        cur = conn.cursor()
        phones = tuple(r["phone"] for r in rows)
        cur.execute(
            "SELECT alias_value, user_id::text, source, verified_at "
            "FROM public.user_identity_aliases "
            "WHERE alias_type = 'phone' AND alias_value = ANY(%s::text[])",
            (list(phones),),
        )
        found = cur.fetchall()
    finally:
        conn.close()

    logger.info("\n=== 验证：DB 中确认存在的 phone alias 记录 ===")
    for row in found:
        logger.info("  phone=%-14s  uuid=%s  source=%s", row[0], row[1], row[2])
    missing = set(phones) - {r[0] for r in found}
    if missing:
        logger.warning("以下手机号未写入 DB：%s", ", ".join(sorted(missing)))
    else:
        logger.info("全部 %d 条手机号验证通过 ✓", len(rows))


# ──────────────────────────────────────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="补写 external_auth 用户手机号到 Supabase DB")
    parser.add_argument(
        "--users-file",
        default=None,
        help="external_auth users.json 路径（默认自动探测）",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Postgres 连接串（默认读 DB_URL 环境变量）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印计划，不写 DB",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="写入后跳过验证查询",
    )
    args = parser.parse_args()

    db_url = _normalize_text(args.db_url or os.getenv("DB_URL") or os.getenv("DATABASE_URL"))
    if not db_url and not args.dry_run:
        sys.exit("ERROR: 请设置 DB_URL 环境变量或用 --db-url 参数指定数据库连接串")

    users_file = _find_users_file(args.users_file)
    logger.info("读取 users 文件：%s", users_file)

    users = load_external_auth_users(users_file)
    rows = collect_phone_rows(users)

    if not rows:
        logger.info("没有需要补写的用户，退出。")
        return

    run_backfill(rows, db_url=db_url, dry_run=args.dry_run)

    if not args.dry_run and not args.no_verify:
        verify_results(rows, db_url=db_url)


if __name__ == "__main__":
    main()
