# -*- coding: utf-8 -*-
"""对账协议：B猜（预测清单）× W回（现实回答）→ 差异点清单。

四类差异（只此四类）：

| 类型 | 判据 | 产芽 |
|---|---|---|
| 预测内错 | 预期态变 ≠ 实际态变 | ✅ |
| 预测内对 | 预期 = 实际 | ❌（计入被验证） |
| 预测外发现 | 实际有、预测没提 | ✅ |
| 预测未执行 | 预测写了没做 | ✅ |

**逐项对齐、指针强制、便宜判等**三条是「不靠模型理解力」的机械保证：
对齐按 (对象, 维度) 机械匹配；每个差异点必须带证据指针，无指针进「待补指针」区，
超时未补＝「指针缺失」差异＝照样产芽（拒收≠丢弃）。
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence

from .model import Diff, DiffKind, Observation, Prediction

#: 待补指针的宽限拍数（超时＝指针缺失差异，产芽）
POINTER_GRACE_TICKS = 5


def _index(observations: Iterable[Observation]) -> dict[tuple[str, str], Observation]:
    """按 (对象, 维度) 建索引；同键多次出现＝同一维度被写了两遍，后者覆盖（并可见）。"""
    out: dict[tuple[str, str], Observation] = {}
    for obs in observations:
        out[obs.key] = obs
    return out


def reconcile(predictions: Sequence[Prediction], observations: Sequence[Observation],
              tick: int) -> list[Diff]:
    """逐项对账 → 差异点清单（保持预测顺序，末尾追加「预测外发现」）。

    机械判等：`expected == actual` 即判「对」。数值/状态型可直接比；
    事件型或意图区的语义冲突不在这里判（那是组织会话的语义判断段，判断进账可被打脸）。
    """
    index = _index(observations)
    diffs: list[Diff] = []
    matched: set[tuple[str, str]] = set()

    for pred in predictions:
        obs = index.get(pred.key)
        if obs is None:
            diffs.append(Diff(DiffKind.NOT_EXECUTED, pred.obj, pred.dimension,
                              pred.expected, "（无现实侧记录）", pred.evidence, tick))
            continue
        matched.add(pred.key)
        if obs.actual != pred.expected:
            diffs.append(Diff(DiffKind.WRONG, pred.obj, pred.dimension,
                              pred.expected, obs.actual, obs.evidence or pred.evidence, tick))
        else:
            diffs.append(Diff(DiffKind.OK, pred.obj, pred.dimension,
                              pred.expected, obs.actual, obs.evidence, tick))

    for obs in observations:
        if obs.key not in matched:
            diffs.append(Diff(DiffKind.UNPREDICTED, obs.obj, obs.dimension,
                              "（预测未提）", obs.actual, obs.evidence, tick))
    return diffs


def pending_pointer(predictions: Sequence[Prediction], tick: int,
                    grace: int = POINTER_GRACE_TICKS) -> list[Diff]:
    """超时未补指针的预测项 → 「指针缺失」差异（自愈：拒收不等于丢弃）。"""
    out = []
    for pred in predictions:
        if pred.evidence:
            continue
        if pred.tick is not None and tick - pred.tick >= grace:
            out.append(Diff(DiffKind.WRONG, pred.obj, pred.dimension, pred.expected,
                            "（指针缺失）", "", tick))
    return out


def diff_summary(diffs: Iterable[Diff]) -> dict:
    """对账汇总（供报告与园丁抽查用；计数按类型，不按「感觉」）。"""
    out: dict[str, int] = {}
    spawn = 0
    for d in diffs:
        out[d.kind.value] = out.get(d.kind.value, 0) + 1
        spawn += 1 if d.spawns else 0
    return {"total": sum(out.values()), "by_kind": out, "spawning": spawn}


def redemption_rate(records: Iterable, bucket: Optional[tuple] = None) -> float:
    """兑现率**现算**（不存缓存、不手工维护）。

    - `bucket=None` → 全局兑现率；
    - 给了桶（对象域 × 预测边 × 实际边）→ 该桶兑现率。
    分母为 0 时返回 0.0 并**不假装有数据**（调用方据此区分「没样本」与「全打脸」）。
    """
    rows = list(records)
    if bucket is not None:
        rows = [r for r in rows if _bucket(r) == bucket]
    if not rows:
        return 0.0
    hit = sum(1 for r in rows if _redeemed(r))
    return hit / len(rows)


def _redeemed(record) -> bool:
    return bool(record.get("redeemed")) if isinstance(record, dict) else bool(record.redeemed)


def _bucket(record) -> tuple:
    if not isinstance(record, dict):
        return record.bucket()
    return (str(record.get("sprout_id", "")).split("-")[0],
            record.get("predicted_edge") or "无",
            record.get("actual_edge") or "无")


def rate_table(records: Iterable) -> dict:
    """按桶列出兑现率（生芽会话引用的就是这张表；桶是机械锚，不可换名）。"""
    rows = list(records)
    buckets: dict[tuple, int] = {}
    for r in rows:
        buckets[_bucket(r)] = buckets.get(_bucket(r), 0) + 1
    return {"总记录": len(rows),
            "桶": {" × ".join(map(str, k)): {"n": n, "兑现率": redemption_rate(rows, k)}
                   for k, n in sorted(buckets.items(), key=lambda kv: str(kv[0]))}}
