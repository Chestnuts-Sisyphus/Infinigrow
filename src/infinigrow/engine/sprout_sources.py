# -*- coding: utf-8 -*-
"""芽源：**只有三个**，全部由账本机械判定，执行会话一律不自产芽。

| 芽源 | 判据（机械、可查） | 芽题面 |
|---|---|---|
| 差异对账 | 对账产出的差异点，且带证据指针 | 消解这个差异 |
| 成熟链封顶 | 对象爬到成熟链第 4 步（已固化） | 基于它开应用面 |
| 能力库未用 | 库条目连续 N 拍未在留痕里被消费 | 为何未用／在别域是否成立 |

**后两条是 v2 新增的现实入口**：v1 的芽源只有「差异」一条，
差异被消解完后队列只剩执行会话自造的复述芽（实测 221 根里 186 根同族、题面逐字相同，
引擎原地打转直到被人工叫停）。补两个入口＝给引擎**第二条、第三条通向现实的路**，
但生芽权仍在账本侧（组织会话），执行会话依旧不能自产芽。

「零差异零芽」是硬律：没有差异、没有封顶、没有未用条目 → 本拍不产芽。
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence

from .model import (Diff, Edge, MATURITY_CAP, Sprout, SproutOrigin)

#: 能力库条目「长期未用」的拍数阈值（具体状态判据，不是「频率高」式归纳）
LIBRARY_IDLE_TICKS = 20


def _sprout_id(prefix: str, obj: str, dimension: str, tick: int, seq: int) -> str:
    """芽 ID：前缀-拍号-序号（可读、可排序、可复查；字典序取题直接可用）。"""
    safe_obj = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in obj)[:24]
    return "%s%04d-%03d-%s" % (prefix, tick, seq, safe_obj)


def from_diffs(diffs: Sequence[Diff], tick: int, start_seq: int = 1) -> list[Sprout]:
    """差异 → 芽（N 差异 N 芽）。无指针的差异**不成芽**（进待补区，超时另算）。"""
    out: list[Sprout] = []
    seq = start_seq
    for d in diffs:
        if not d.spawns:
            continue
        predicted = _predict_edge(d)
        out.append(Sprout(
            id=_sprout_id("sp", d.obj, d.dimension, tick, seq),
            obj=d.obj, dimension=d.dimension,
            pointer=d.evidence, origin=SproutOrigin.DIFF, created_tick=tick,
            predicted_edge=predicted, maturity_step=None,
        ))
        seq += 1
    return out


def _predict_edge(diff: Diff) -> Optional[Edge]:
    """增益预测（事前选边）：按差异类型给结构先验，权重由兑现账事后校准。

    预测对象必须**现实可查**（能写进预测清单、能对账打脸），所以这里的取值是枚举值
    而不是自由文本。
    """
    from .model import DiffKind
    if diff.kind == DiffKind.UNPREDICTED:
        return Edge.READ          # 现实给了新东西而没预测到 → 先看懂（判读）
    if diff.kind == DiffKind.NOT_EXECUTED:
        return Edge.ACT           # 说要做的没做 → 先把动作落成现实变化（行动）
    return Edge.PRINCIPLE         # 预测内错 → 多半要从已有认知推新认知（原理）


def from_maturity_cap(maturity_records: Iterable[dict], tick: int,
                      known_objects: Iterable[str] = (),
                      start_seq: int = 1) -> list[Sprout]:
    """①成熟链封顶 → 芽「基于它开应用面」。

    `maturity_records` 形如 `{"obj": ..., "step": 4, "tick": ...}`（成熟链账本行）。
    只对**本拍恰好到达封顶**的对象生芽（`reached_tick == tick`）——这是具体状态判据，
    不是「最近经常封顶」式归纳；已经在别处登记过的对象由调用方用 `known_objects` 去重。
    """
    known = set(known_objects)
    out: list[Sprout] = []
    seq = start_seq
    for rec in maturity_records:
        obj = rec.get("obj")
        if not obj or obj in known:
            continue
        if rec.get("step") != MATURITY_CAP or rec.get("tick") != tick:
            continue
        out.append(Sprout(
            id=_sprout_id("cap", obj, "应用面", tick, seq),
            obj=obj, dimension="应用面",
            pointer="成熟链:%s@拍%d" % (obj, tick),
            origin=SproutOrigin.MATURITY_CAP, created_tick=tick,
            predicted_edge=Edge.SOLIDIFY,      # 已固化 → 预测「固化」会被再确认/扩展
            maturity_step=MATURITY_CAP,
        ))
        seq += 1
    return out


def from_unused_library(library_records: Iterable[dict], liuhen_text: str, tick: int,
                        idle_ticks: int = LIBRARY_IDLE_TICKS,
                        known_objects: Iterable[str] = (),
                        start_seq: int = 1) -> list[Sprout]:
    """②能力库条目长期未消费 → 芽「为何未用／在别域是否成立」。

    判据全是**具体状态**：该条目的 `last_used_tick` 与当前拍号之差 ≥ `idle_ticks`，
    且本拍留痕里没有出现该条目名。不设「使用频率」式阈值（那是归纳，不是状态）。
    """
    known = set(known_objects)
    out: list[Sprout] = []
    seq = start_seq
    for rec in library_records:
        name = rec.get("name")
        if not name or name in known:
            continue
        last_used = rec.get("last_used_tick", rec.get("created_tick", 0)) or 0
        if tick - last_used < idle_ticks:
            continue
        if name in (liuhen_text or ""):
            continue                            # 本拍用过 → 不算未用
        out.append(Sprout(
            id=_sprout_id("lib", name, "可用性", tick, seq),
            obj=name, dimension="可用性",
            pointer="能力库:%s(末次使用拍%s)" % (name, last_used),
            origin=SproutOrigin.LIBRARY_UNUSED, created_tick=tick,
            predicted_edge=Edge.PRINCIPLE,      # 「在别域是否成立」＝原理边的异域验证
            maturity_step=None,
        ))
        seq += 1
    return out
