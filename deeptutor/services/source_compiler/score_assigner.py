"""按经验反推的踩点给分逻辑给案例采分点赋分(分值引擎)。

规则来源与验证见 `docs/数据盘点/2026-06-16-给分逻辑(分值引擎基础).md`:
从 431 个真实采分点(5 年佑森解析,已独立复核)反推;留一年交叉验证 73% exact /
MAE 0.215(改进版:列举吸收小题余额)。

authority = `engine_rule_derived` —— **非官方阅卷分值**。用途:
  1. 给生成题/变题的采分点赋分(主用途,生成器自控结构,实际优于盲推);
  2. 缺真值年份的"引擎估计默认值"(明确标注非真值)。
真题有真实分值时优先用真值(查表),本引擎只在无真值时赋分。

纯函数,无外部依赖、不写任何 authority、不冒充 official。若未来被生产 runtime 消费
(如喂 learner truth),须先 register-before-use 并保持 authority=engine_rule_derived。
"""
from __future__ import annotations

from typing import Any, Sequence

AUTHORITY = "engine_rule_derived"
JUDGE_RULE = "min(Σ命中采分点×分值, 小题满分) 封顶"

# 常见分值粒度(吸附用),来自真题分布:1.0 主力,0.5/2/3/4/5 次之
_SNAP_GRID = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0)
_LIST_TYPE = "列举"
# 非列举单元型:每个单元默认 1.0 分(留一验证中 80% 命中)
_UNIT_TYPES = {"计算步骤", "计算结果", "判断", "改错", "程序", "措施", "分类"}


def _snap(value: float) -> float:
    """把分值吸附到最近的常见粒度。"""
    return min(_SNAP_GRID, key=lambda v: abs(v - value))


def default_sub_q_total(n_points: int) -> float:
    """无指定小题满分时按采分点数粗估(R2:真题小题满分 3-7 为主)。"""
    if n_points <= 2:
        return 3.0
    if n_points <= 4:
        return 5.0
    if n_points <= 6:
        return 6.0
    return 7.0


def assign_scores(
    points: Sequence[dict[str, Any]],
    sub_q_total: float | None = None,
) -> dict[str, Any]:
    """给一道小题的采分点列表赋分(验证过的改进版逻辑)。

    points: 每项是 dict,至少含 ``type``(point_type:列举/计算步骤/判断/改错/程序/措施/计算结果/分类)。
    sub_q_total: 小题满分;None 时按采分点数取默认(``default_sub_q_total``)。

    返回 ``{sub_q_total, scores:[每点分值], judge_rule, authority}``。

    规则:
      - R5 单元数 > 小题满分 → 每单元 0.5(项多塞小满分);
      - 否则非列举每单元 1.0;列举吸收"小题满分 − 非列举已占"的余额(多列举平分);
      - 判分按 ``judge`` 封顶。
    """
    pts = list(points)
    n = len(pts)
    if n == 0:
        return {
            "sub_q_total": float(sub_q_total or 0.0),
            "scores": [],
            "judge_rule": JUDGE_RULE,
            "authority": AUTHORITY,
        }

    total = float(sub_q_total) if sub_q_total is not None else default_sub_q_total(n)
    types = [str(p.get("type", "")) for p in pts]

    if n > total:  # R5
        scores: list[float] = [0.5] * n
    else:
        scores = [0.0] * n
        lie_idx = [i for i, t in enumerate(types) if t == _LIST_TYPE]
        non_lie_idx = [i for i in range(n) if i not in lie_idx]
        for i in non_lie_idx:
            scores[i] = 1.0
        remainder = total - len(non_lie_idx) * 1.0
        if lie_idx:
            each = _snap(remainder / len(lie_idx)) if remainder > 0 else 1.0
            each = each if each > 0 else 1.0
            for i in lie_idx:
                scores[i] = each
        else:
            # 无列举且非列举单元少于满分:踩点池可 < 满分,保持 1.0(不强行抬)
            for i in non_lie_idx:
                if scores[i] == 0.0:
                    scores[i] = 1.0

    return {
        "sub_q_total": total,
        "scores": scores,
        "judge_rule": JUDGE_RULE,
        "authority": AUTHORITY,
    }


def judge(
    point_scores: Sequence[float],
    hit_mask: Sequence[bool],
    sub_q_total: float,
) -> float:
    """R7 封顶判分:小题得分 = min(Σ命中采分点×分值, 小题满分)。"""
    earned = sum(s for s, hit in zip(point_scores, hit_mask) if hit)
    return min(round(earned, 2), float(sub_q_total))
