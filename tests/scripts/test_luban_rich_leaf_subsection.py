from __future__ import annotations

from scripts.luban_rich_leaf_subsection import (
    Subsection,
    leaf_name_core,
    slice_leaf_subsection,
)

# A real-shaped chunk: 门和窗基本构造要求, with numbered #### subsections.
_DOOR_WINDOW_MD = """### 1.2.4 门和窗基本构造要求

#### 1. 门窗构造要求

（1）门窗选用应根据建筑使用功能、节能要求综合确定。

#### 2. 门的设置规定

（1）门应开启方便、使用安全、坚固耐用。

#### 3. 窗的设置规定

（1）窗扇的开启形式应能保障使用安全。

#### 4. 天窗的设置规定

（1）采光天窗应采用防破碎坠落的透光材料。
"""


def test_core_strips_qualifier_and_enumerator() -> None:
    assert leaf_name_core("结构设计——圈梁") == "圈梁"
    assert leaf_name_core("4. 天窗的设置规定") == "天窗的设置规定"
    assert leaf_name_core("（1）门的设置规定") == "门的设置规定"


def test_distinct_subsection_per_leaf_under_same_chunk() -> None:
    """两个 leaf 共享一个 chunk 必须拿到各自不同的子段落 (编译单位=召回单位=leaf)。"""
    tianchuang = slice_leaf_subsection(_DOOR_WINDOW_MD, "天窗的设置规定", chunk_hosts_multiple_leaves=True)
    men = slice_leaf_subsection(_DOOR_WINDOW_MD, "门的设置规定", chunk_hosts_multiple_leaves=True)

    assert isinstance(tianchuang, Subsection)
    assert isinstance(men, Subsection)
    assert "采光天窗" in tianchuang.text
    assert "门应开启方便" in men.text
    # The decisive invariant: the two leaves no longer share content.
    assert tianchuang.text != men.text
    # 天窗 section must NOT bleed into 门 content and vice versa.
    assert "门应开启方便" not in tianchuang.text
    assert "采光天窗" not in men.text


def test_section_span_stops_at_next_sibling_heading() -> None:
    men = slice_leaf_subsection(_DOOR_WINDOW_MD, "门的设置规定", chunk_hosts_multiple_leaves=True)
    assert men is not None
    # 门 section stops before 窗 section.
    assert "窗扇的开启形式" not in men.text


def test_non_discriminative_name_abstains() -> None:
    """纯通用名 (建筑设计要求) 不能锚定子段落 -> 必须 abstain (None), 不许瞎切。"""
    md = "### 建筑设计要求\n\n建筑设计应符合相关规范。"
    assert slice_leaf_subsection(md, "建筑设计要求", chunk_hosts_multiple_leaves=True) is None


def test_ambiguous_multi_heading_abstains() -> None:
    """两个同名同级 heading -> 歧义 -> abstain。"""
    md = "#### 1. 门的设置规定\n\nA\n\n#### 2. 门的设置规定\n\nB\n"
    assert slice_leaf_subsection(md, "门的设置规定", chunk_hosts_multiple_leaves=True) is None


def test_multi_leaf_chunk_no_heading_match_abstains() -> None:
    """名字在 chunk 里找不到对应 heading 且 chunk 挂多 leaf -> abstain (不回退整 chunk)。"""
    md = "### 焊缝夹渣\n\n焊缝夹渣的成因与防治。"
    # leaf 名义是屋面防水, chunk 内容是焊缝夹渣 -> A 类误链 -> 必须 abstain
    assert slice_leaf_subsection(md, "屋面防水", chunk_hosts_multiple_leaves=True) is None


def test_no_heading_chunk_abstains_even_when_sole_leaf() -> None:
    """D blocker 收口: 无 heading 的 chunk 即使是 1:1 leaf↔chunk 也必须 abstain。
    "核心词出现在正文" 不能证明整 chunk 只讲这个 leaf — 回退整 chunk = 原始污染再现。
    单一规则: None always means quarantine, 两条 lane 一视同仁。"""
    md = "建筑分类按使用性质划分。民用建筑包括居住建筑和公共建筑。"
    assert slice_leaf_subsection(md, "建筑分类", chunk_hosts_multiple_leaves=False) is None
    assert slice_leaf_subsection(md, "建筑分类", chunk_hosts_multiple_leaves=True) is None


# ---------------------------------------------------------------------------
# v2 加严: substring false-positive (窗 vs 门窗 vs 天窗) — wrong-slice 防护
# ---------------------------------------------------------------------------


def test_substring_sibling_does_not_wrong_slice_window_vs_door_window() -> None:
    """窗的设置规定 不能切到 门窗构造要求 或 天窗的设置规定 的段落 (substring 陷阱)。"""
    sibs = ("门窗构造要求", "门的设置规定", "天窗的设置规定")
    win = slice_leaf_subsection(
        _DOOR_WINDOW_MD, "窗的设置规定", chunk_hosts_multiple_leaves=True, sibling_cores=sibs
    )
    assert win is not None
    assert "窗扇的开启形式" in win.text
    # must be ITS OWN section, not 门窗 / 天窗 / 门 content
    assert "门窗选用" not in win.text
    assert "采光天窗" not in win.text
    assert "门应开启方便" not in win.text


def test_tianchuang_is_not_shadowed_by_window_sibling() -> None:
    """天窗的设置规定 的 heading superstrings 窗的设置规定 — negative check 不能因此误杀。"""
    sibs = ("窗的设置规定", "门的设置规定", "门窗构造要求")
    tian = slice_leaf_subsection(
        _DOOR_WINDOW_MD, "天窗的设置规定", chunk_hosts_multiple_leaves=True, sibling_cores=sibs
    )
    assert tian is not None
    assert "采光天窗" in tian.text
    assert "窗扇的开启形式" not in tian.text  # 窗 section not bled in


_PARENT_CHILD_MD = """### 2) 混凝土的强度

混凝土强度是结构设计的重要依据。

#### (1) 混凝土立方体抗压强度

按国家标准制作边长 150mm 立方体试件测得抗压强度。
"""


def test_parent_leaf_keeps_only_preamble_not_child_subsection() -> None:
    """父 leaf (混凝土的强度) 拥有父标题, 但其子段属于 sibling (混凝土立方体抗压强度):
    父 leaf 只能拿 preamble, 不能吞掉子段 (否则把子段内容复制成 sibling 的污染)。"""
    parent = slice_leaf_subsection(
        _PARENT_CHILD_MD,
        "混凝土的强度",
        chunk_hosts_multiple_leaves=True,
        sibling_cores=("混凝土立方体抗压强度",),
    )
    child = slice_leaf_subsection(
        _PARENT_CHILD_MD,
        "混凝土立方体抗压强度",
        chunk_hosts_multiple_leaves=True,
        sibling_cores=("混凝土的强度",),
    )
    assert parent is not None and child is not None
    # parent keeps intro, NOT the child's body
    assert "结构设计的重要依据" in parent.text
    assert "立方体试件" not in parent.text
    # child keeps its own body
    assert "立方体试件" in child.text
    assert parent.text != child.text


def test_same_parent_heading_for_multiple_leaves_abstains() -> None:
    """3 个 leaf 都只能 reverse-match 同一个父标题且无各自子标题 -> 分不开 -> 全 abstain。"""
    md = "#### 劳动力结构特征\n\n按性别、年龄、技术等级划分。\n"
    sibs = ("劳动力结构特征：性别构成", "劳动力结构特征：年龄构成", "劳动力结构特征：技术等级构成")
    for name in sibs:
        others = tuple(s for s in sibs if s != name)
        assert (
            slice_leaf_subsection(md, name, chunk_hosts_multiple_leaves=True, sibling_cores=others)
            is None
        )


def test_safe_reverse_qualifier_tail_matches() -> None:
    """全站仪 (heading) 是 全站仪测量 (leaf) 的更简洁同义形式 -> 安全 reverse 命中。"""
    md = "### 全站仪\n\n全站仪是一种集测距、测角于一体的测量仪器。\n"
    sub = slice_leaf_subsection(md, "全站仪测量", chunk_hosts_multiple_leaves=False)
    assert sub is not None
    assert "测距" in sub.text


def test_negative_check_prevents_distinct_payload_wrong_slice() -> None:
    """关键: 切错但 payload 不同的情形 — fail-closed 指纹门(只抓相同 payload)抓不住,
    必须靠 slice 期 negative check + preamble 收缩在源头挡住。

    父 leaf 不能吞掉属于 sibling 的子段(吞了会产出一个与 sibling 不同、门看不见的
    错误 payload)。"""
    md = (
        "### 门和窗基本构造要求\n\n门窗章节总览。\n\n"
        "#### 门的设置规定\n\n（1）门应开启方便。\n\n"
        "#### 窗的设置规定\n\n（1）窗扇开启应保障安全。\n"
    )
    parent = slice_leaf_subsection(
        md, "门和窗基本构造要求", chunk_hosts_multiple_leaves=True,
        sibling_cores=("门的设置规定", "窗的设置规定"),
    )
    assert parent is not None
    # parent narrowed to preamble — must NOT swallow either child (each would be a
    # DISTINCT payload the identical-fingerprint gate could never catch).
    assert "门窗章节总览" in parent.text
    assert "门应开启方便" not in parent.text
    assert "窗扇开启应保障安全" not in parent.text


def test_lecture_lane_no_heading_quarantines_not_whole_chunk() -> None:
    """D blocker (Codex NO-GO): lecture lane 用 chunk_hosts_multiple_leaves=False
    调切分器。无 heading 但 core 命中正文时, 旧代码会回退整 chunk = 第二套宽松规则。
    收口后必须 abstain (None) -> 调用方 quarantine, 与 textbook lane 统一。"""
    # lecture chunk: leaf core (防火封堵) 在正文中出现, 但无任何 heading 可锚定。
    md = "防火封堵应在管道穿越楼板处设置。施工时需注意阻火圈安装方向与膨胀倍率。"
    assert slice_leaf_subsection(md, "防火封堵", chunk_hosts_multiple_leaves=False) is None


def test_lecture_lane_with_heading_still_slices() -> None:
    """收口不能误杀: lecture chunk 有真实 heading 锚定 leaf 时仍正常切出本段。"""
    md = "### 防火封堵\n\n防火封堵应在管道穿越楼板处设置, 注意膨胀倍率。\n"
    sub = slice_leaf_subsection(md, "防火封堵", chunk_hosts_multiple_leaves=False)
    assert sub is not None
    assert "膨胀倍率" in sub.text


def test_bold_heading_anchor_is_sliceable() -> None:
    """无 ATX 标题、只有加粗小标题的 chunk 也能被切 (放宽: bold 作为 heading 候选)。"""
    md = (
        "**（1）门窗节能施工材料复验要求**\n\n门窗复验应检查传热系数。\n\n"
        "**（2）墙体节能工程施工质量要求**\n\n墙体保温层应粘结牢固。\n"
    )
    sub = slice_leaf_subsection(
        md, "门窗节能施工材料复验要求", chunk_hosts_multiple_leaves=True,
        sibling_cores=("墙体节能工程施工质量要求",),
    )
    assert sub is not None
    assert "传热系数" in sub.text
    assert "墙体保温层" not in sub.text
