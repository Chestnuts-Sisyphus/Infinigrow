# -*- coding: utf-8 -*-
"""组织会话（LLM 段）触发判据——**具体状态判据，不用「频率高」这类归纳**。

放在 `engine/` 而不是 `scheduler/`，是因为**拍循环本身必须查它**：
上一代引擎的 P0 根因之一就是「语义判断段一直没有调度入口」——诊断报告产出后没人回灌，
就地过期。判据若只存在于外部调度器里，拍循环就看不见「我该看语义层了」，
同一个洞会以另一种形式重开。`scheduler/triggers.py` 只是它的对外门面（给外部调度器用）。

触发条件（任一成立即触发，冷却闸在后）：

| # | 条件 | 判据形态 |
|---|---|---|
| ① | 从未跑过 LLM 组织段 | 账本无记录（具体状态：记录数＝0） |
| ② | 距上次 LLM 段拍号差 ≥ `gap` | 拍号差（整数比较，不是「大概多久」） |
| ③ | 存在待补指针差异 | 具体状态：待补指针条目数 > 0 |
| ④ | 本拍零差异且已连续 `zero_gap` 拍 | 需要的是**具体计数**：连续零差异拍数 ≥ 阈值 |

冷却闸：距上次 LLM 段**机械时间戳**不足 `cooldown_min` 分钟 → 不触发
（硬约束：断流/节流类判据一律用机械时间戳，不用模型留痕时间）。
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from ..core.paths import StateLayout
from ..ledger.store import append_jsonl, read_jsonl

DEFAULT_GAP_TICKS = 5
DEFAULT_COOLDOWN_MIN = 30
DEFAULT_ZERO_GAP = 10

#: 组织段尝试账（记录「什么时候试过」，条件②与冷却闸都读它）
ORG_LEDGER = "org-llm.jsonl"


@dataclass
class OrgTriggerDecision:
    should_run: bool
    reason: str
    criteria: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"should_run": self.should_run, "reason": self.reason, "criteria": self.criteria}


def _last_org_record(records: Sequence[dict]) -> Optional[dict]:
    return records[-1] if records else None


def _parse_stamp(text: str) -> Optional[_dt.datetime]:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return _dt.datetime.strptime(str(text).strip(), fmt)
        except (ValueError, TypeError):
            continue
    return None


def org_ledger_path(layout: StateLayout) -> Path:
    return layout.root / ORG_LEDGER


def should_run_org_session(layout: StateLayout, tick: int,
                           now: Optional[_dt.datetime] = None,
                           gap: int = DEFAULT_GAP_TICKS,
                           cooldown_min: int = DEFAULT_COOLDOWN_MIN,
                           zero_gap: int = DEFAULT_ZERO_GAP) -> OrgTriggerDecision:
    """读账本 → 判定（纯函数，除读账本外无副作用；便于单测与复跑）。"""
    tries = read_jsonl(org_ledger_path(layout))
    last = _last_org_record(tries)
    diffs = read_jsonl(layout.diff_ledger)
    pending = [d for d in diffs if not d.get("evidence") and d.get("spawns") is False]
    zero_streak = 0
    for rec in reversed(diffs):
        if rec.get("kind") == "预测内对":
            zero_streak += 1
        elif rec.get("kind") in ("预测内错", "预测外发现", "预测未执行"):
            break

    criteria = {
        "从未跑过": last is None,
        "距上次拍号差": None if last is None else tick - int(last.get("tick") or 0),
        "待补指针": len(pending),
        "连续预测内对拍数": zero_streak,
        "上次时间戳": None if last is None else last.get("time"),
    }

    if last is None:
        return OrgTriggerDecision(True, "①从未跑过 LLM 组织段（账本 0 条）", criteria)

    now = now or _dt.datetime.now()
    stamp = _parse_stamp(last.get("time", ""))
    if stamp is not None and (now - stamp).total_seconds() < cooldown_min * 60:
        return OrgTriggerDecision(False, "冷却闸：距上次 LLM 段不足 %d 分钟" % cooldown_min,
                                  criteria)

    last_tick = int(last.get("tick") or 0)
    if tick - last_tick >= gap:
        return OrgTriggerDecision(True, "②空窗补跑：距上次拍号差 %d ≥ %d"
                                  % (tick - last_tick, gap), criteria)
    if pending:
        return OrgTriggerDecision(True, "③待补指针差异 %d 条" % len(pending), criteria)
    if zero_streak >= zero_gap:
        return OrgTriggerDecision(True, "④连续 %d 拍零差异（该看语义层了）" % zero_streak,
                                  criteria)
    return OrgTriggerDecision(False, "无条件成立：空窗 %s < %d，待补指针 0"
                              % (criteria["距上次拍号差"], gap), criteria)


def record_org_session(layout: StateLayout, tick: int, note: str = "") -> None:
    """记一次 LLM 组织段**尝试**（含拍号与机械时间戳——缺了拍号，条件②就永远推不出来）。"""
    append_jsonl(org_ledger_path(layout),
                 {"tick": tick, "time": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                  "note": note}, layout.root)


def cadence_seconds(minutes: int) -> int:
    """把「每 N 分钟一拍」换算成秒（机械量，供外部调度器读）。"""
    if minutes <= 0:
        raise ValueError("间隔必须是正整数分钟")
    return minutes * 60


def files_touched_since(root: Path, stamp: float) -> list[str]:
    """列出某时刻之后被改过的文件（供「最近在动什么」类具体判据复用）。"""
    out = []
    for p in sorted(Path(root).rglob("*")):
        if p.is_file() and p.stat().st_mtime > stamp:
            out.append(p.name)
    return out
