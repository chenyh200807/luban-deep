"""鲁班站点卡 lesson viewmodel——投影门（双轮 v3.2 §7）的第一个 runtime 消费者。

Thin 投影层（§3 所有权表）：本模块**只读投影、零生成**——
- 签发真值唯一来源 = `_pack_manifest.json`（manifest 绿灯 =
  ``published ∧ jury_clean ∧ not explicitly_barred_default_entry``，fail-closed：
  不在绿灯集合的 pack 与不存在的 pack 同样不可见，防未签发内容泄漏）；
- 变体池只报数量与 sha（runtime 抽取归复测链路，本模块不展开题面）；
  且**只认签发池**（双 fail-closed）：bank ``status=="signed"`` 且
  ``source_pack_sha256`` 与 manifest 该 pack 的 ``content_sha256`` 一致——
  candidate 未签发/pack 正文修订后的旧变体，一律与 bank 缺失同形不可见
  （签发动作 = ``docs/原始数据/考点原料/promote_variant_bank.py``，人闸）；
- 视频后 forward 由 ``practice_html`` 只读 publisher 从 finished 编译的
  非公开 authority sidecar；客户端投影剥离答案，review 仍只认上述 signed bank；
- 讲懂卡 URL = 业务托管基址（env ``LUBAN_LESSON_CARD_BASE``）+ pack slug 约定，
  卡产物按压缩预研 0.39MB 口径产出并开 Content-Encoding（托管侧职责）；
- ``content_sha256`` 仍表示 pack Markdown；lesson 与 practice 各用自己的发布/源摘要
  做 URL cache-bust，禁止一个 bundle SHA 同时代表两种内容事实。

学习证据边界（防第四 builder）：本模块**不写任何学习证据**。课后练统一走
``luban_retest_completion.v1`` → ``RetestWritebackService``（forward 非 promoting），
档位③走判分链路；学-evidence
（lesson_viewed）唯一 writer = ``learner_state/lesson_evidence.py``（经
``lesson_progress`` 路由，融合计划 §2.1）——本投影模块仍零写入。
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from deeptutor.services.luban_lesson.practice_html import (
    PracticeHtmlInvalid,
    is_compiled_practice_pack,
    load_compiled_practice,
    project_compiled_practice,
)

_REPO = Path(__file__).resolve().parents[3]
_MANIFEST_PATH = (
    _REPO / "docs" / "原始数据" / "考点原料" / "成品" / "_pack_manifest.json"
)
_VARIANT_BANK_TEMPLATE = "_{pack_id}_variant_bank.v0.json"
_CARD_BASE_ENV = "LUBAN_LESSON_CARD_BASE"
_PUBLIC_PREVIEW_ROOT = _REPO / "web" / "public" / "luban-preview"
_LESSON_PAGE_NAME = re.compile(r"^lesson(?P<episode>[2-9][0-9]*)?\.html$")


class LessonNotAvailable(Exception):
    """pack 不存在或未过投影门——两者对外同形（fail-closed，不泄漏未签发存在性）。"""


# manifest 模块级缓存(照 pack_lifecycle_projection 的 (mtime_ns, size) 模式,
# 病B-3):命中零解析;产物更新(stat 键变)自动失效;失败(缺文件/损坏)
# fail-closed 且**不缓存**——修好文件后同进程下次调用即恢复。
_MANIFEST_CACHE: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}
_MANIFEST_UNAVAILABLE: dict[str, Any] = {"projection_green": [], "packs": []}
_LESSON_FILE_SHA_CACHE: dict[str, tuple[tuple[int, int], str]] = {}


def _load_manifest(manifest_path: Path | None = None) -> dict[str, Any]:
    path = manifest_path or _MANIFEST_PATH
    try:
        stat = path.stat()
        stat_key = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        # manifest 缺失 = 供给面不可用，整体 fail-closed
        return dict(_MANIFEST_UNAVAILABLE)
    cache_key = str(path)
    cached = _MANIFEST_CACHE.get(cache_key)
    if cached is not None and cached[0] == stat_key:
        return cached[1]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(_MANIFEST_UNAVAILABLE)
    _MANIFEST_CACHE[cache_key] = (stat_key, manifest)
    return manifest


def _compiled_practice_meta(pack_id: str) -> dict[str, str]:
    try:
        authority = load_compiled_practice(pack_id)
    except PracticeHtmlInvalid:
        return {}
    if authority is None:
        return {}
    return {
        "practice_sha": str(authority.get("source_bundle_sha256") or ""),
        "lesson_sha": str(authority.get("published_lesson_sha256") or ""),
    }


def _lesson_url(
    pack_id: str, *, lesson_file: str = "lesson.html", bundle_sha: str = ""
) -> str:
    """某个已发布讲解页面的托管 URL。

    ``lesson_file`` 只由 ``_published_lesson_pages`` 生成，不能从客户端直通；
    这样 ``lesson2.html``/``lesson3.html`` 是教学集的真实入口，而非字符串猜测。
    """
    base = str(os.getenv(_CARD_BASE_ENV) or "").strip().rstrip("/")
    if not base:
        return ""  # 托管未配置：viewmodel 仍可用（练档数据不依赖卡），客户端按无卡降级
    if bundle_sha:
        return f"{base}/{pack_id.lower()}/{lesson_file}?v={bundle_sha}"
    return f"{base}/{pack_id.lower()}/{lesson_file}"


def _card_url(pack_id: str, *, bundle_sha: str = "") -> str:
    """兼容默认首集的既有消费方。"""
    return _lesson_url(pack_id, bundle_sha=bundle_sha)


def _published_lesson_pages(pack_id: str) -> list[Path]:
    """从已发布页确定性枚举同一考点的教学集。

    站点注册表/publisher 是发布映射的唯一 writer；运行时只读其实际输出。
    只接受无缺口的 ``lesson.html``、``lesson2.html``、``lesson3.html`` …序列：
    少任意一集或出现未知文件名均不把后续页面暴露给学习端。
    """
    station_dir = _PUBLIC_PREVIEW_ROOT / str(pack_id or "").strip().lower()
    try:
        candidates = list(station_dir.glob("lesson*.html"))
    except OSError:
        return []
    indexed: dict[int, Path] = {}
    for path in candidates:
        match = _LESSON_PAGE_NAME.fullmatch(path.name)
        if match is None:
            return []
        index = int(match.group("episode") or "1")
        if index in indexed:
            return []
        indexed[index] = path
    if not indexed:
        return []
    expected = list(range(1, max(indexed) + 1))
    if sorted(indexed) != expected:
        return []
    return [indexed[index] for index in expected]


def _lesson_page_sha(path: Path) -> str:
    """页面级缓存摘要；内容页变更即失效，避免列表请求反复读 74 份 HTML。"""
    try:
        stat = path.stat()
    except OSError:
        return ""
    cache_key = str(path)
    stat_key = (stat.st_mtime_ns, stat.st_size)
    cached = _LESSON_FILE_SHA_CACHE.get(cache_key)
    if cached is not None and cached[0] == stat_key:
        return cached[1]
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""
    _LESSON_FILE_SHA_CACHE[cache_key] = (stat_key, digest)
    return digest


def _episode_label(index: int, total: int) -> str:
    if total == 1:
        return "完整讲解"
    if total == 2:
        return "上集" if index == 1 else "下集"
    if total == 3:
        return ("上集", "中集", "下集")[index - 1]
    return f"第 {index} 集"


def _teaching_points_for_lesson(lesson: dict[str, Any]) -> list[dict[str, Any]]:
    """一个 pack 的已发布教学集投影（零写入、零第二份目录）。"""
    if not lesson.get("card_hosted"):
        return []
    pages = _published_lesson_pages(str(lesson.get("pack_id") or ""))
    total = len(pages)
    if not total:
        return []
    points: list[dict[str, Any]] = []
    for index, page in enumerate(pages, start=1):
        page_sha = _lesson_page_sha(page)
        if not page_sha:
            return []  # 任一页不可读 = 整个教学集不完整，fail-closed
        label = _episode_label(index, total)
        pack_id = str(lesson["pack_id"])
        points.append(
            {
                "teaching_point_id": f"{pack_id}:lesson:{index}",
                "pack_id": pack_id,
                "title": str(lesson.get("title") or ""),
                "episode_index": index,
                "episode_total": total,
                "episode_label": label,
                "lesson_file": page.name,
                "card_url": _lesson_url(
                    pack_id, lesson_file=page.name, bundle_sha=page_sha
                ),
            }
        )
    return points


def _practice_card_url(pack_id: str, *, bundle_sha: str = "") -> str:
    """已编译随堂练成品的托管 URL；没有成品练习的 pack 不猜路径。"""
    if not bundle_sha:
        return ""
    base = str(os.getenv(_CARD_BASE_ENV) or "").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}/{pack_id.lower()}/practice.html?v={bundle_sha}"


_BANK_CACHE: dict[tuple[str, int], Any] = {}


def _load_signed_bank(
    pack_id: str,
    manifest_dir: Path,
    expected_sha: str,
    filename_template: str = _VARIANT_BANK_TEMPLATE,
) -> dict[str, Any] | None:
    """供给池签发闸（双 fail-closed，所有 bank 读取的唯一入口——含考点卡池，
    ``concept_cards.py`` 传自己的 ``filename_template`` 复用同一闸，禁分叉第二 loader）。

    只放行 ``status=="signed"`` 且 ``source_pack_sha256`` == manifest 该 pack
    ``content_sha256`` 的 bank；candidate 未签发、pack 正文修订后的 sha 漂移、
    文件缺失/损坏，一律返回 None（对外与 bank 缺失同形，不泄漏未签发存在性）。
    """
    path = manifest_dir / filename_template.format(pack_id=pack_id)
    # 读缓存(2026-07-12 性能): (path, mtime) 键——文件一变即失效, 语义与直读
    # 逐字节等价; 每请求扫 37+ 个 bank JSON 的重复磁盘解析是复习/学情面
    # 的主要读放大源。缓存的是解析后的 bank 原对象(下游只读投影, 不改写)。
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return None
    cache_key = (str(path), mtime)
    cached = _BANK_CACHE.get(cache_key)
    if cached is not None:
        bank = cached
    else:
        try:
            bank = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        # 单文件单版本: 清掉同路径旧mtime条目再入缓存(防无界增长)
        for key in [k for k in _BANK_CACHE if k[0] == str(path)]:
            _BANK_CACHE.pop(key, None)
        _BANK_CACHE[cache_key] = bank
    if not isinstance(bank, dict):
        return None
    if str(bank.get("status") or "") != "signed":
        return None  # candidate/未知状态 = 未签发，不可直通真实考生
    expected_sha = str(expected_sha or "").strip()
    if not expected_sha or str(bank.get("source_pack_sha256") or "") != expected_sha:
        return None  # pack 正文已修订（或 manifest 无 sha），旧变体失效
    return bank


def _variant_summary(
    pack_id: str, manifest_dir: Path, expected_sha: str
) -> dict[str, Any]:
    bank = _load_signed_bank(pack_id, manifest_dir, expected_sha)
    if bank is None:
        return {"available": False, "count": 0}
    variants = bank.get("variants") or []
    return {
        "available": bool(variants),
        "count": len(variants),
        "bank_status": "signed",
        "source_pack_sha256": str(bank.get("source_pack_sha256") or ""),
    }


def list_all_pack_ids(*, manifest_path: Path | None = None) -> list[str]:
    """manifest pack 全集（pack_id 排序，非 manifest 登记序；消费者当集合用）
    ——生命周期投影「未学」态的枚举范围
    （考点全集来自当前 manifest，不由客户端镜像固定数量）。
    只读 manifest，绿灯与否不影响「未学」枚举（锁定站也如实是未学）。"""
    manifest = _load_manifest(manifest_path)
    return sorted(
        str(pack.get("pack_id") or "").strip()
        for pack in manifest.get("packs") or []
        if str(pack.get("pack_id") or "").strip()
    )


def list_green_lessons(*, manifest_path: Path | None = None) -> list[dict[str, Any]]:
    """绿灯站点列表投影（地图/路线消费）；只含绿灯包，锁定站的露脸文案归上层。

    ``retest_available`` = manifest 登记的 compiled finished 供给或 signed 变体池真值
    （各自复用唯一 loader/签发闸，不建第二判定）——供学习页按真实供给
    路由/降级，不对空池站渲染练不了的按钮。
    """
    manifest = _load_manifest(manifest_path)
    green = set(manifest.get("projection_green") or [])
    manifest_dir = (manifest_path or _MANIFEST_PATH).parent
    rows = []
    for pack in manifest.get("packs") or []:
        if pack.get("pack_id") not in green:
            continue
        rows.append(
            {
                "pack_id": pack["pack_id"],
                "title": str(pack.get("title") or ""),
                "content_sha256": str(pack.get("content_sha256") or ""),
                # 托管真值来自 manifest 对 lesson.html 的确定性扫描；路线绿灯与可播放分开。
                "card_hosted": bool(pack.get("card_hosted")),
                "retest_available": bool(
                    manifest_path is None
                    and _compiled_practice_meta(str(pack["pack_id"]))
                )
                or _variant_summary(
                    str(pack["pack_id"]),
                    manifest_dir,
                    str(pack.get("content_sha256") or ""),
                )["available"],
            }
        )
    rows = sorted(rows, key=lambda r: r["pack_id"])
    # 集数是发布产物的只读投影，不改写 manifest 的 pack 生命周期真值。
    if manifest_path is None:
        for row in rows:
            row["teaching_episode_count"] = len(
                _published_lesson_pages(str(row["pack_id"]))
            )
    return rows


def list_teaching_points(*, manifest_path: Path | None = None) -> list[dict[str, Any]]:
    """可独立播放的教学集列表。

    ``pack_universe`` 仍是完整考点/进度范围；本函数只回答“当前已发布多少集
    视频”。它从发布输出的连续 ``lesson*.html`` 序列投影，既不把 74 集伪装为
    74 个练习包，也不保存一张需要人工同步的 episode 清单。
    """
    if manifest_path is not None:
        # 临时 manifest 没有配套发布根，不能拿主仓静态页替它猜教学集。
        return []
    points: list[dict[str, Any]] = []
    for lesson in list_green_lessons():
        points.extend(_teaching_points_for_lesson(lesson))
    return points


def build_lesson_viewmodel(
    pack_id: str, *, episode_index: int = 1, manifest_path: Path | None = None
) -> dict[str, Any]:
    """单站 viewmodel；不过投影门一律 LessonNotAvailable（fail-closed）。"""
    pack_id = str(pack_id or "").strip().upper()
    manifest = _load_manifest(manifest_path)
    green = set(manifest.get("projection_green") or [])
    if pack_id not in green:
        raise LessonNotAvailable(pack_id)
    pack = next(
        (p for p in manifest.get("packs") or [] if p.get("pack_id") == pack_id),
        None,
    )
    if pack is None:  # manifest 自身不一致也 fail-closed
        raise LessonNotAvailable(pack_id)
    manifest_dir = (manifest_path or _MANIFEST_PATH).parent
    try:
        episode_index = int(episode_index)
    except (TypeError, ValueError):
        episode_index = 1
    if episode_index < 1:
        raise LessonNotAvailable(pack_id)

    practice_meta = _compiled_practice_meta(pack_id) if manifest_path is None else {}
    practice_sha = practice_meta.get("practice_sha", "")
    lesson_sha = practice_meta.get("lesson_sha", "")
    pages = _published_lesson_pages(pack_id) if manifest_path is None else []
    if episode_index > 1 and (not pages or episode_index > len(pages)):
        raise LessonNotAvailable(pack_id)
    selected_page = pages[episode_index - 1] if pages else None
    selected_lesson_sha = (
        # 首集继续使用 compiled sidecar 的发布摘要，保持既有 URL 缓存语义；
        # 其余集使用自己 HTML 的摘要，绝不借首集版本号。
        lesson_sha
        if episode_index == 1 and lesson_sha
        else _lesson_page_sha(selected_page)
        if selected_page is not None
        else ""
    )
    episode_total = len(pages) if pages else 1
    episode_label = _episode_label(episode_index, episode_total)
    return {
        "pack_id": pack_id,
        "title": str(pack.get("title") or ""),
        "content_sha256": str(pack.get("content_sha256") or ""),
        # card_hosted=manifest 确定性扫描(web/public/luban-preview/<id>/lesson.html 实存);
        # 非 hosted 站不发 URL——防 web-view 打开 404(部署探针实证 22/28 站无卡)
        "card_url": (
            _lesson_url(
                pack_id,
                lesson_file=selected_page.name if selected_page is not None else "lesson.html",
                bundle_sha=selected_lesson_sha,
            )
            if pack.get("card_hosted")
            else ""
        ),
        # 页面级教学集元数据只用于播放/展示；学习证据、练习、掌握仍归 pack。
        "teaching_episode": {
            "index": episode_index,
            "total": episode_total,
            "label": episode_label,
        },
        # finished 随堂练的托管副本；客户端不再从 lesson URL 猜路径。
        "practice_url": (
            _practice_card_url(pack_id, bundle_sha=practice_sha)
            if pack.get("card_hosted")
            else ""
        ),
        "practice_surface": {
            "available": bool(pack.get("card_hosted") and practice_sha),
            "kind": "compiled_html" if practice_sha else "",
            "question_count": 5 if practice_sha else 0,
            "completion_contract": (
                "luban_retest_completion.v1" if practice_sha else ""
            ),
        },
        "variant_retest": _variant_summary(
            pack_id, manifest_dir, str(pack.get("content_sha256") or "")
        ),
        # 证据写入路径声明（客户端按此接线，防第四 builder）：
        "evidence_channels": {
            "practice_completion": "luban_retest_completion.v1",
            "full_answer": "case_grading",  # 档位③（判分内核链路）
        },
    }


def _forward_rule_group_spread(
    core: list[dict[str, Any]], seed: int, limit: int
) -> list[dict[str, Any]]:
    """正向轻练选序：确定性广度优先 round-robin 覆盖不同 ``rule_group``——
    对刚学完的 pack 先各考法采样一题、再回填（学习轮"先广后深"）。

    与复测的扁平轮换的唯一差别是**选序**：纯签发池内确定性重排，零生成、
    零新供给（不派生任何题面字段，§8 红线）。组间顺序与组内起点均由 ``seed``
    确定性散列派生（多端幂等）；组间按轮次交错；题数 ≤ 核心变体数（耗尽即止）。

    红队修复（2026-07-10 owner 实测抓获"全同答案 session"）：旧实现对**所有组
    施加同一个** ``(seed + round_idx) % len`` 偏移，而变体池按"每组对齐序"生成
    （组内第 0 位=完整/正确情形），于是 limit ≤ 组数时 5 题全取自同一"位置列"
    = 单一 expected_ok（实测 forward 全同率 17.2%，seed 奇偶直接翻全对/全错）。
    现改为**每组独立散列偏移** + 组序进 seed（第 1 题不再永远同一考法）。
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for variant in core:
        groups.setdefault(str(variant.get("rule_group") or ""), []).append(variant)

    def _h(tag: str, key: str) -> int:
        digest = hashlib.sha256(f"{seed}:{tag}:{key}".encode("utf-8")).hexdigest()
        return int(digest[:12], 16)

    keys = sorted(groups.keys(), key=lambda k: _h("g", k))  # 组序确定性洗牌
    interleaved: list[dict[str, Any]] = []
    round_idx = 0
    while any(round_idx < len(groups[k]) for k in keys):
        for k in keys:
            members = groups[k]
            if round_idx < len(members):
                interleaved.append(members[(_h("o", k) + round_idx) % len(members)])
        round_idx += 1
    return interleaved[: min(limit, len(core))]


def build_retest_items(
    pack_id: str,
    *,
    user_id: str,
    day_index: int,
    limit: int = 5,
    mode: str = "review",
    practice_surface: str = "",
    manifest_path: Path | None = None,
) -> list[dict[str, Any]]:
    """练习题面投影——runtime 只读编译产物，绝不在线生成。

    两种模式共用同一 endpoint、selection identity 与 completion writer：
    - ``mode="review"``（默认，复习轮换皮复测）：跨天扁平确定性轮换，同一用户
      同一天取同一切片（多端幂等，§9-D3）；跨天按 ``day_index``（服务端本地日，
      §9-D2）前进，池耗尽自动回绕复用旧变体（产能降级预案①，绝不 runtime 现编）。
    - ``mode="forward"``：已编译 pack 读 finished HTML 固定五题投影
      （不下发正确项）；``practice_surface`` 只能选 manifest 登记的成品面。
      证据仍由 RetestWritebackService server-rescore 且 non-promoting。

    signed variant 分支只发核心变体（extension=false）；对外投影字段
    {variant_id, rule_group, surface, expected_ok, correct_statement, anchor}——
    绝不派生 scoring_point 文本 / exam_refs / chapter（变体池无此供给=不臆造）。

    ``textbook``（可选字段）= **同 pack** 签发考点卡 bank 按 ``anchor == point_id``
    精确 join 出的教材原文并排卡 {quote, label, page_num}。这不是派生/生成——
    quote 逐字来自已签发考点卡（同一 ``_load_signed_bank`` 双闸），坐标系同为
    kc: 锚。join 不中 / 卡池未签发 → 字段缺省（fail-closed，前端有原文才亮）。
    跨包借 quote 红线不适用：只 join 自己 pack 的卡池。

    签发闸（双 fail-closed）：只从 ``status=="signed"`` 且 sha 锚定当前 pack
    正文的 bank 抽取——不满足与 bank 缺失同形返回 ``[]``（既有降级）。
    """
    vm = build_lesson_viewmodel(pack_id, manifest_path=manifest_path)
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode == "forward" and manifest_path is None:
        try:
            compiled = project_compiled_practice(
                vm["pack_id"],
                expected_pack_sha256=vm["content_sha256"],
                surface_id=practice_surface,
            )
        except PracticeHtmlInvalid:
            compiled = None
        if compiled is not None:
            # 成品面是固定五题，不能用 limit 截短后仍签发完成凭证。
            return compiled
        if is_compiled_practice_pack(vm["pack_id"]):
            return []  # compiled 内容损坏/SHA 漂移时禁回退第二套 signed-variant 题面
    if not vm["variant_retest"]["available"]:
        return []
    manifest_dir = (manifest_path or _MANIFEST_PATH).parent
    bank = _load_signed_bank(vm["pack_id"], manifest_dir, vm["content_sha256"])
    if bank is None:
        return []
    blocked = _variant_blocklist(manifest_dir)
    core = [
        v
        for v in bank.get("variants") or []
        if not v.get("extension") and str(v.get("variant_id") or "") not in blocked
    ]
    if not core:
        return []
    limit = max(1, min(int(limit), 10))
    # seed = 高熵确定性散列(红队修复: 旧 sum(ord)+day_index 在千级用户上碰撞 58%,
    # 且 user/day 在整数轴上混叠——char-sum 差 1 的两人错一天拿同卷)。
    # 同 (user, day) 仍幂等(§9-D3 多端一致)。
    seed = int(
        hashlib.sha256(f"{user_id}:{int(day_index)}".encode("utf-8")).hexdigest()[:12],
        16,
    )
    if normalized_mode == "forward":
        ordered = _forward_rule_group_spread(core, seed, len(core))
    else:
        start = seed % len(core)
        ordered = [core[(start + i) % len(core)] for i in range(len(core))]
    picked = _balance_expected_ok(_diversify_skeletons(ordered, limit), seed, limit)
    textbook_by_point = _textbook_quote_index(
        vm["pack_id"], manifest_dir, vm["content_sha256"]
    )
    rows: list[dict[str, Any]] = []
    for v in picked:
        row: dict[str, Any] = {
            "variant_id": v["variant_id"],
            "rule_group": v["rule_group"],
            "surface": v["surface"],
            "expected_ok": bool(v["expected_ok"]),
            "correct_statement": v["correct_statement"],
            "anchor": v["anchor"],
        }
        textbook = textbook_by_point.get(str(v.get("anchor") or ""))
        if textbook:
            row["textbook"] = textbook
        rows.append(row)
    return rows


_VARIANT_BLOCKLIST_FILE = "_variant_blocklist.json"


def _variant_blocklist(manifest_dir: Path) -> set[str]:
    """对抗面板 A 级停发变体清单（serve 侧过滤, 签发 bank 原样不动）。

    2026-07-11 变体 statement 验尸：9 条 A 级门道语句（旧真题官答与 2026 新
    规范教材冲突为主——地下防水四级/超灌0.8~1.0m/钢丝网保留/变形缝依据等）
    波及 40 变体。救活 = 教研按 2026 教材口径修 pack 后重签并从清单移除。
    缺文件 = 空集（不改变既有行为）。"""
    path = manifest_dir / _VARIANT_BLOCKLIST_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set()
    except Exception:
        return set()  # 清单损坏时不放大故障(保守: 不过滤, 由测试盯格式)
    return {
        str(item.get("variant_id") or "")
        for item in data.get("variants") or []
        if item.get("variant_id")
    }


_SKELETON_ENTITY_RE = re.compile(r"「[^」]*」")
_SKELETON_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _surface_skeleton(surface: str) -> str:
    """题面句式骨架(实体挖空+数字归一)——同骨架=用户眼中的"同一句换词"。"""
    text = _SKELETON_ENTITY_RE.sub("「X」", str(surface or ""))
    return _SKELETON_NUM_RE.sub("N", text)


def _diversify_skeletons(
    ordered: list[dict[str, Any]], limit: int
) -> list[dict[str, Any]]:
    """同场次句式骨架去重(owner 2026-07-11"老用户马上腻"拍板的呈现层修复):

    实测 A01 B-basis 组 16 变体仅 4 种骨架——一场 5 题里出现两道"同句换词"
    即产生敷衍感。骨架未见的题排前, 重复骨架的退后作回填(小池不空窗)。
    保持 ordered 相对原序(forward 考法广度/review 轮换语义不变), 纯确定性。
    ``limit`` 仅语义提示(截取仍在 _balance_expected_ok), 此处全量重排。"""
    fresh: list[dict[str, Any]] = []
    seen: set[str] = set()
    rest: list[dict[str, Any]] = []
    for v in ordered:
        sk = _surface_skeleton(str(v.get("surface") or ""))
        if sk in seen:
            rest.append(v)
            continue
        seen.add(sk)
        fresh.append(v)
    return fresh + rest


def retest_pool_meta(
    pack_id: str, *, manifest_path: Path | None = None
) -> dict[str, Any]:
    """题池元信息(呈现层"换皮是刻意设计"的证据): 核心题数/考法数——签发真值
    派生, 停发清单已剔除。供 retest 页 hero/收据展示题池规模与收集感。"""
    try:
        vm = build_lesson_viewmodel(pack_id, manifest_path=manifest_path)
    except LessonNotAvailable:
        return {"core_total": 0, "rule_groups_total": 0}
    manifest_dir = (manifest_path or _MANIFEST_PATH).parent
    bank = _load_signed_bank(vm["pack_id"], manifest_dir, vm["content_sha256"])
    if bank is None:
        return {"core_total": 0, "rule_groups_total": 0}
    blocked = _variant_blocklist(manifest_dir)
    core = [
        v for v in bank.get("variants") or []
        if not v.get("extension") and str(v.get("variant_id") or "") not in blocked
    ]
    return {
        "core_total": len(core),
        "rule_groups_total": len({str(v.get("rule_group") or "") for v in core}),
    }


def _balance_expected_ok(
    ordered: list[dict[str, Any]], seed: int, limit: int
) -> list[dict[str, Any]]:
    """答案模式防泄露（选题层能修的那一半；句式泄露归编译端内容工单）。

    owner 实测抓到"整场点'不妥当'全对"。此前选题完全不看 ``expected_ok``，
    可能送出整组同答案的 session。最小干预收口（不做硬配平——硬配平会挤掉
    forward 的考法广度契约，且会过度复曝少数类变体）：

    - **防全同**：送出的题全为同一答案类、且池子里存在对偶类时，把末位
      确定性换成剩余序列中最早的对偶题（仅此一换，广度语义基本不动）；
      单类池如实全送，不臆造对偶。
    - **顺序确定性洗牌**：按 (seed, variant_id) 稳定散列重排出题序，杀掉
      次序 tell；同 (user, day) 仍幂等（§9-D3 多端一致），跨用户/跨日不可预测。
    """
    picked = list(ordered[: min(limit, len(ordered))])
    if len(picked) >= 2:
        classes = {bool(v.get("expected_ok")) for v in picked}
        if len(classes) == 1:
            uniform = classes.pop()
            swap_in = next(
                (
                    v
                    for v in ordered[len(picked):]
                    if bool(v.get("expected_ok")) != uniform
                ),
                None,
            )
            if swap_in is not None:
                picked[-1] = swap_in
    picked.sort(
        key=lambda v: hashlib.sha256(
            f"{seed}:{v.get('variant_id')}".encode("utf-8")
        ).hexdigest()
    )
    return picked


_CONCEPT_CARD_BANK_TEMPLATE = "_{pack_id}_concept_card_bank.v0.json"


def _textbook_quote_index(
    pack_id: str, manifest_dir: Path, expected_sha: str
) -> dict[str, dict[str, Any]]:
    """同 pack 签发考点卡 → {point_id: 教材原文并排卡}（retest join 用）。

    quote/label 逐字透传签发卡字段（zero 生成）；卡池未签发/缺失 → 空 index
    （fail-closed，retest 不带 textbook 字段照常工作）。
    """
    bank = _load_signed_bank(
        pack_id,
        manifest_dir,
        expected_sha,
        filename_template=_CONCEPT_CARD_BANK_TEMPLATE,
    )
    if bank is None:
        return {}
    index: dict[str, dict[str, Any]] = {}
    for card in bank.get("cards") or []:
        point_id = str(card.get("point_id") or "").strip()
        quote = str(card.get("quote") or "").strip()
        if not point_id or not quote:
            continue
        source_ref = card.get("source_ref") or {}
        page_num = source_ref.get("page_num") if isinstance(source_ref, dict) else None
        index[point_id] = {
            "quote": quote,
            "label": str(card.get("front") or ""),
            "page_num": page_num if isinstance(page_num, int) else None,
        }
    return index
