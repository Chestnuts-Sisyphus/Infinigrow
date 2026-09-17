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
    obj = str(record.get("obj", ""))
    domain = obj.rsplit("/", 1)[0] if "/" in obj else obj
    return (domain or "（无对象）",
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


def verifiable(record) -> bool:
    """这一行是不是**可对账**的：该芽的维度机械层读得到吗？（读不到就不该判它打脸）

    默认 True（旧行没有这个字段）。`verifiable=False` 的那类（例如「应用面」这类
    语义维度）**永远**判不出兑现——把它们算进兑现率就是把「读不到」说成「打脸」。
    """
    if isinstance(record, dict):
        return record.get("verifiable") is not False
    return bool(getattr(record, "verifiable", True))


def sampled(record) -> bool:
    """这一行是不是**样本**：那一拍有执行者真动过手（`sample` 字段）。

    旧行（v2.0 及更早）没有这个字段 → 视为**非样本**：那时候根本没有执行者通道，
    那些「全打脸」记录是机械拍的产物，不该混进兑现率的分母。
    """
    if isinstance(record, dict):
        return record.get("sample") is True
    return bool(getattr(record, "sampled", False))


def redemption_report(records: Iterable) -> dict:
    """兑现率的**诚实呈现**（T11/G6）：无样本就说「无样本」，不说 0，更不说「差」。

    两种状态必须能被机器与人都一眼分清：

    | 状态 | 判定 | 含义 |
    |---|---|---|
    | 没有执行者动过手 | `无样本` | 兑现率**不可计算**（不是 0，也不是差） |
    | 有执行者动过手 | `有样本` | 给真实兑现率与分桶 |

    分母只数样本行；`总行数` 一并报出，便于看出「有没有被静默丢样本」。

    **固化边单独列出**（T6/A7）：`cap*`（成熟链封顶→开应用面）的维度「应用面」是
    语义维度，机械层读不到 → 兑现判不出。它们**单独列出**（`固化边` 字段），
    不进兑现率分母，也不算「打脸」——那是「读不到」，不是「错了」。
    占取题位是刻意的：封顶芽驱动执行者把已固化能力**应用到别域**（一个真动作）。

    **Q2/A3 之后**：接了**证据边**的 cap 行（`verifiable=true`）走正常口径——
    证据件存在＝应用发生（`evaluate_outcome` 的 `evidence_key`），进分母、可兑现可打脸；
    只有**没接证据边**的行（旧账、不带题面的调用）才落进下面这个桶。
    所以「固化边」条数**下降**正是这条边被接上的读数。
    """
    rows = list(records)
    checkable = [r for r in rows if verifiable(r)]
    samples = [r for r in checkable if sampled(r)]
    unverifiable = len(rows) - len(checkable)
    cap_rows = [r for r in rows
                if str(r.get("sprout_id", "")).startswith("cap") and not verifiable(r)]
    cap_bucket = {"单独列出": [str(r.get("sprout_id")) for r in cap_rows],
                  "n": len(cap_rows),
                  "说明": "固化边（应用面）**未接证据边**的行：不可机械验证，单独列出，"
                          "不计入兑现率分母，也不算打脸；接了证据边的 cap 行已按存在性对账，"
                          "在正常样本里（Q2/A3）"}
    if not samples:
        return {"判定": "无样本", "样本数": 0, "总行数": len(rows), "兑现率": None,
                "分桶": {}, "不可对账": unverifiable, "固化边": cap_bucket,
                "说明": ("本状态根还没有「执行者动过手且该维度机械层读得到」的拍："
                         "机械拍不做语义判断、也不产出真实生长，所以兑现率**不可计算**"
                         "（不是 0，也不是差）。接上执行者后自动开始积累样本。"
                         "（另有 %d 行因为维度读不到而不计入：读不到 ≠ 打脸。）"
                         % unverifiable)}
    hit = sum(1 for r in samples if _redeemed(r))
    buckets: dict[tuple, int] = {}
    for r in samples:
        buckets[_bucket(r)] = buckets.get(_bucket(r), 0) + 1
    return {"判定": "有样本", "样本数": len(samples), "总行数": len(rows),
            "不可对账": unverifiable, "固化边": cap_bucket,
            "兑现率": hit / len(samples),
            "分桶": {" × ".join(map(str, k)): {"n": n, "兑现率": redemption_rate(samples, k)}
                     for k, n in sorted(buckets.items(), key=lambda kv: str(kv[0]))},
            "说明": ("按「对象域 × 预测边 × 实际边」分桶现算；分母只含**可对账的样本行**"
                     "（%d 行非样本已排除：那些拍里没有执行者动手；"
                     "%d 行不可对账已排除：该维度机械层读不到，读不到≠打脸；"
                     "固化边 %d 行单独列出）。"
                     % (len(rows) - len(samples) - unverifiable, unverifiable,
                        len(cap_rows)))}


#: 「提议过期」的机械阈值（拍）：领做时芽龄 ≥ 这个数，就说这条提议的**前提**太老了。
STALE_LEAD_TICKS = 30


def sprout_prefix(sprout_id) -> str:
    """芽 ID 的**芽源前缀**（`sp0326-001-…` → `sp`；`cap0380-001-…` → `cap`）。

    前缀是 `sprout_sources` 里写死的机械锚（sp＝差异／cap＝成熟链封顶／lib＝能力库未用），
    不换名、不猜——兑现账里没有单独的「芽源」字段，前缀就是它。
    """
    text = str(sprout_id or "")
    out = []
    for ch in text:
        if ch.isdigit():
            break
        out.append(ch)
    return "".join(out) or "（无前缀）"


def sprout_created_tick(sprout_id) -> Optional[int]:
    """从芽 ID 里取**出生拍**（`sp0326-001-…` → 326）。取不到 → None（不猜）。

    ID 的拍号段是 `sprout_sources._sprout_id` 写死的格式（`<前缀><拍号4位>-<序号>-<对象>`），
    所以「第一段连续数字」就是创建拍——这是机械锚，不是解析模型自述。
    """
    text = str(sprout_id or "")
    digits = ""
    for ch in text:
        if ch.isdigit():
            digits += ch
            continue
        if digits:
            break
    if len(digits) < 4:
        return None
    return int(digits[:4])


def redemption_attribution(records: Iterable, tick_from: Optional[int] = None,
                           stale_after: int = STALE_LEAD_TICKS) -> dict:
    """领做与兑现的**分桶归因**（M10/B2/B3；可复跑的命令形态）。

    三件事一次说清，全部机械可判：

    1. **谁在领做**：按芽源前缀（`sp`／`cap`／`lib`）数领做次数，并各报
       「可对账／不可对账」——固化边（`cap*`）占了多少取题位，是 B4/A3 的核心读数；
    2. **兑现与打脸**：可对账样本行里，兑现多少、打脸多少；
    3. **打脸归因**：把打脸行按**领做时的芽龄**分开——
       `等待拍数 = 领做拍 − 出生拍`（出生拍取自芽 ID 的拍号段，机械可判）。
       芽龄 ≥ `stale_after`（默认 30 拍）→ **提议过期**：这条提议做出来时看的是
       30 拍前的现实，而引擎在领做时**不会重新校验前提**（判据只锚 `(对象, 维度)`），
       所以「前提已经过期」是这条打脸的**机械代理**，不是替它开脱；
       芽龄 < 阈值 → **真没做**（提议是新的，执行者拿到了题面却没让现实满足它）。

    **证明等级**：分桶与芽龄是 [已证明]（全部读账本现算）；「提议过期」是
    [归纳待证] 的**归因代理**——它说的是「前提老」，不是「提议内容本身已失效」
    （后者是语义判断，机械层不代替它下结论）。报数只说这两桶各几条 + 原始芽龄。

    `tick_from` 给了就只看该拍及之后的领做行（长窗口复验收口用同一个函数复跑）。
    """
    rows = [r for r in records if isinstance(r, dict)]
    if tick_from is not None:
        rows = [r for r in rows if int(r.get("tick") or 0) >= tick_from]
    tick_now = max((int(r.get("tick") or 0) for r in rows), default=0)

    leads: dict[str, int] = {}
    by_source: dict[str, dict] = {}
    stale_rows: list[dict] = []
    undone_rows: list[dict] = []
    undone_ages: list[int] = []
    for r in rows:
        prefix = sprout_prefix(r.get("sprout_id"))
        leads[prefix] = leads.get(prefix, 0) + 1
        stat = by_source.setdefault(prefix, {"领做": 0, "可对账": 0, "兑现": 0,
                                             "打脸": 0, "不可对账": 0})
        stat["领做"] += 1
        if not verifiable(r):
            stat["不可对账"] += 1
            continue
        stat["可对账"] += 1
        if _redeemed(r):
            stat["兑现"] += 1
            continue
        stat["打脸"] += 1
        created = sprout_created_tick(r.get("sprout_id"))
        tick = int(r.get("tick") or 0)
        age = None if created is None else max(0, tick - created)
        item = {"sprout_id": r.get("sprout_id"), "tick": tick,
                "出生拍": created, "等待拍数": age}
        if age is not None and age >= stale_after:
            stale_rows.append(item)
        else:
            undone_rows.append(item)
            if age is not None:
                undone_ages.append(age)

    checkable = sum(s["可对账"] for s in by_source.values())
    redeemed = sum(s["兑现"] for s in by_source.values())
    failed = sum(s["打脸"] for s in by_source.values())
    unverifiable = sum(s["不可对账"] for s in by_source.values())
    return {
        "窗口": {"起拍": (min((int(r.get("tick") or 0) for r in rows), default=None)
                          if rows else None),
                 "止拍": tick_now or None, "行数": len(rows)},
        "领做": {"总": len(rows), "按前缀": leads},
        "按芽源": by_source,
        "可对账样本": checkable, "兑现": redeemed, "打脸": failed,
        "不可对账": unverifiable,
        "打脸归因": {
            "提议过期": {"n": len(stale_rows), "阈值拍": stale_after,
                         "行": stale_rows,
                         "说明": "领做时芽龄 ≥ 阈值：提议的前提已老（机械代理，[归纳待证]）"},
            "真没做": {"n": len(undone_rows), "行": undone_rows,
                       "芽龄中位数": (sorted(undone_ages)[len(undone_ages) // 2]
                                      if undone_ages else None),
                       "说明": "领做时芽龄 < 阈值：提议是新的，现实没被满足"},
        },
        "说明": ("按芽源前缀分桶现算；「不可对账」＝该维度机械层读不到（读不到≠打脸），"
                 "固化边（cap*）的取题位占比＝ 按芽源.cap.领做 ÷ 领做.总。"
                 "打脸归因按「领做时芽龄」机械分桶（出生拍取自芽 ID 拍号段）。"),
    }

