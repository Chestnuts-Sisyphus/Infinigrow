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

import re

from pathlib import Path
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

#: 执行者留痕里「本轮输出没被解析」的**自述标记**（适配器打的诚实行；引擎只按字面标记分类，
#: 不替它解释语义）。为什么要有这一类：实测（2026-09-17，拍 449）模型回了带 `actions` 的
#: JSON，但**开头少了 `{"`** → 适配器 `extract_json` 失败 → 整条回复（含写入动作）被丢弃，
#: 引擎这一拍如实记打脸——那一条打脸的**真实原因**既不是「提议过期」也不是「没做」，
#: 而是**动作没落地**。按「提议过期」算它，就是把执行者侧的解析故障记成提议的账。
EXECUTOR_UNPARSED_MARKS = ("留痕说明：", "不是 JSON")

#: 留痕里「执行者输出」那一段的标题（`executor.write_trace` 的固定版式）
TRACE_OUTPUT_HEADING = "## 输出（原样）"

#: 自述动作的机械形态：适配器解析出的 `{"op": ..., "path": ...}`
_TRACE_ACTION_RX = re.compile(r'"op"\s*:\s*"[^"]*"\s*,\s*"path"\s*:\s*"([^"]+)"')


def trace_write_paths(traces_dir, tick) -> list[str]:
    """本拍留痕**输出段**里执行者自述的写入路径（缺留痕/没给目录 → 空表，不猜）。

    为什么只读输出段：约定路径本来就被引擎**逐字写进题面**，扫全文会把引擎自己的话
    当成执行者的自述——那等于用同一个字符串给自己作证，归因就失去意义。
    留痕是工作文件（同拍重跑覆盖），所以它说的就是**最后那一次**动作。
    """
    if traces_dir is None:
        return []
    path = Path(str(traces_dir)) / ("tick-%05d.md" % int(tick))
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    start = text.find(TRACE_OUTPUT_HEADING)
    if start < 0:
        return []
    return [m.group(1).replace("\\", "/").lstrip("./")
            for m in _TRACE_ACTION_RX.finditer(text[start:])]


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


def executor_output_unparsed(traces_dir, tick: int,
                             marks: Iterable[str] = EXECUTOR_UNPARSED_MARKS) -> bool:
    """这一拍的执行者留痕里有没有「本轮输出没被解析」的自述标记（缺留痕 → False，不猜）。

    引擎只按**字面标记**分类，不替适配器解释语义：标记在 → 这一拍的动作**可能压根没落地**
    （适配器把整条回复当最终留痕处理了），那条打脸就不该记到「提议过期」的账上。
    """
    if traces_dir is None:
        return False
    path = Path(str(traces_dir)) / ("tick-%05d.md" % int(tick))
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(mark in text for mark in marks)


def executor_tick_failures(rows) -> dict:
    """按拍聚合**执行者退出码**：只收「该拍每次 tick 类调用都没成功返回」的拍。

    为什么要有第二条执行者侧证据：留痕的「输出未解析」标记只覆盖**解析失败**那一种
    （适配器把整条回复当最终留痕）；执行者**非零退出／超时**时留痕里没有那个标记，
    于是那条打脸会被芽龄规则判成「真没做」——把执行者侧的失败记在主体的账上
    （真机拍 723：`executor.jsonl` 一行 rc=1、usage=unknown、note「非零退出（stderr 见留痕）」）。

    三条边界都为了**不替主体开脱**：① 同拍只要有一次 rc=0 且未超时的尝试，动作就可能已落地
    （重试成功的形态），不算；② 组织段调用（`kind` 非 `tick`）与这根芽无关，不算；
    ③ 没给账本（旧调用形态／空状态根）→ 空表，不猜。
    """
    ok_ticks = set()
    failed: dict = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("kind") or "tick") != "tick":
            continue
        tick = int(row.get("tick") or 0)
        timed_out = bool(row.get("timed_out"))
        code = int(row.get("rc") or 0)
        if code == 0 and not timed_out:
            ok_ticks.add(tick)
            continue
        info = failed.setdefault(tick, {"rc": code, "timed_out": timed_out, "attempts": 0})
        info["attempts"] += 1
    return {t: v for t, v in failed.items() if t not in ok_ticks}


def executor_side_loss(traces_dir, tick_now: int, window: int = 10) -> dict:
    """**执行者侧损耗**读数（R2/N69）：最近 `window` 拍里，几份留痕带「输出未解析」标记。

    判据与打脸归因的「执行者侧未落地」**同源**（同一个字面标记 `EXECUTOR_UNPARSED_MARKS`、
    同一份留痕读法），只是这里不看兑现账——它回答的是「这段时间执行者自己丢了几次动作」，
    与丢在哪根芽上无关。为什么要有这条读数：适配器在**另一条线**（不在本仓库写权内），
    修复需要另行拍板；在拍板之前，损耗必须**长期可见**（否则「修不修」只能靠回忆）。
    缺留痕的拍不计入分母（零样本不冒充通过；`比例=None` 就是「这段时间没有可数的留痕」）。
    """
    if traces_dir is None:
        return {"窗口": window, "留痕": 0, "回退": 0, "比例": None}
    base = Path(str(traces_dir))
    total = hit = 0
    for t in range(max(0, int(tick_now) - window + 1), int(tick_now) + 1):
        path = base / ("tick-%05d.md" % t)
        if not path.is_file():
            continue
        total += 1
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(mark in text for mark in EXECUTOR_UNPARSED_MARKS):
            hit += 1
    return {"窗口": window, "留痕": total, "回退": hit,
            "比例": (hit / total) if total else None}


def redemption_attribution(records: Iterable, tick_from: Optional[int] = None,
                           stale_after: int = STALE_LEAD_TICKS,
                           traces_dir=None, executor_rows=None) -> dict:
    """领做与兑现的**分桶归因**（M10/B2/B3；可复跑的命令形态）。

    三件事一次说清，全部机械可判：

    1. **谁在领做**：按芽源前缀（`sp`／`cap`／`lib`）数领做次数，并各报
       「可对账／不可对账」——固化边（`cap*`）占了多少取题位，是 B4/A3 的核心读数；
    2. **兑现与打脸**：可对账样本行里，兑现多少、打脸多少；
    3. **打脸归因**：把打脸行分开——
       - **执行者侧未落地**（两条执行者侧证据任一成立）：给了 `traces_dir` 且该拍留痕带
         「输出未解析」标记；或给了 `executor_rows`（`state/executor.jsonl` 的行）且该拍
         **每次** tick 调用都非零退出／超时。动作可能压根没执行，**先别记提议的账**
         （实测拍 449：模型回了带 `actions` 的 JSON 但开头少了 `{"` → 适配器解析失败 →
         整条回复含写入动作被丢弃；实测拍 723：rc=1、usage=unknown、留痕里却没有解析标记）；
       - **提议过期**：领做时芽龄 ≥ `stale_after`（默认 30 拍）——这条提议做出来时看的是
         30 拍前的现实，而引擎在领做时**不会重新校验前提**（判据只锚 `(对象, 维度)`）。
         这是**机械代理·待证**：它说的是「前提老」，**没有**证明「提议内容已失效」，
         因此只在两条执行者侧证据都不成立时才落到这个桶；
       - **真没做**：芽龄 < 阈值，且两条执行者侧证据都不成立——提议是新的，现实没被满足。

    **证明等级**：分桶与芽龄是 [已证明]（全部读账本现算）；「提议过期」是
    [归纳待证] 的**归因代理**（措辞按代理呈现，不外推成结论）。「执行者侧未落地」则是
    [已证明]：留痕的字面标记由适配器自己打，退出码／超时由引擎逐次记进 `executor.jsonl`。

    `tick_from` 给了就只看该拍及之后的领做行（长窗口复验收口用同一个函数复跑）。
    `executor_rows` 不给（旧调用形态）→ 只看留痕标记，行为与从前一致。
    归因**只动打脸行的分组**，不改分子分母（可对账样本／兑现／打脸计数与兑现率口径不变）。
    """
    rows = [r for r in records if isinstance(r, dict)]
    if tick_from is not None:
        rows = [r for r in rows if int(r.get("tick") or 0) >= tick_from]
    tick_now = max((int(r.get("tick") or 0) for r in rows), default=0)

    leads: dict[str, int] = {}
    by_source: dict[str, dict] = {}
    stale_rows: list[dict] = []
    undone_rows: list[dict] = []
    unparsed_rows: list[dict] = []
    undone_ages: list[int] = []
    exec_fail = executor_tick_failures(executor_rows)
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
        unparsed = executor_output_unparsed(traces_dir, tick)
        side = exec_fail.get(tick)
        if unparsed or side is not None:
            evidence = []
            if unparsed:
                evidence.append("留痕「输出未解析」标记")
            if side is not None:
                evidence.append("该拍 %d 次 tick 调用全部非零退出/超时" % side["attempts"])
                item["执行者退出码"] = side["rc"]
                item["执行者超时"] = side["timed_out"]
            item["依据"] = "＋".join(evidence)
            unparsed_rows.append(item)
        elif age is not None and age >= stale_after:
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
            "执行者侧未落地": {"n": len(unparsed_rows), "行": unparsed_rows,
                              "说明": ("该拍留痕带「输出未解析」标记，或该拍每次 tick 调用都"
                                       "非零退出/超时（`state/executor.jsonl` 的 rc/timed_out）："
                                       "动作可能没执行（[已证明] 的两条执行者侧证据，见 "
                                       "`executor_output_unparsed`／`executor_tick_failures`）")},
            "提议过期": {"n": len(stale_rows), "阈值拍": stale_after,
                         "行": stale_rows,
                         "说明": "领做时芽龄 ≥ 阈值：提议的前提已老（机械代理·待证，"
                                 "仅在执行者侧两条证据都不成立时才落此桶）"},
            "真没做": {"n": len(undone_rows), "行": undone_rows,
                       "芽龄中位数": (sorted(undone_ages)[len(undone_ages) // 2]
                                      if undone_ages else None),
                       "说明": "领做时芽龄 < 阈值，且该拍既无「输出未解析」标记、"
                               "也不是执行者调用全失败"},
        },
        "说明": ("按芽源前缀分桶现算；「不可对账」＝该维度机械层读不到（读不到≠打脸），"
                 "固化边（cap*）的取题位占比＝ 按芽源.cap.领做 ÷ 领做.总。"
                 "打脸归因先查执行者侧证据（留痕标记／该拍调用全失败），"
                 "都不成立才按「领做时芽龄」分提议过期与真没做；"
                 "归因只动打脸行的分组，分子分母不变。"),
    }

