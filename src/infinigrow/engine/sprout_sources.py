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

**提醒必须有出口（N48 的根因修复）**：③能力库未用问的是「可用性」——那是**机械层读不到**
的语义维度（兑现账只能如实标 `verifiable=False`，已 240 行）→ 若它既没有「做完」的定义、
又不能结案，就是一条**永真、可无限重生**的提醒，会把队列占满、把能做完的差异芽饿死
（实测：主芽源自 tick 189 起零取题）。本模块给出的两条出口：

- **消费**（`mark_library_usage`）：条目名在**执行者留痕输出**里命中 → `last_used_tick` 更新
  （M3：这个字段此前只在创建那一拍写一次，此后没有任何更新方 → 「闲置 ≥20 拍」永久为真）；
- **结案**（`entries_to_close`）：条目被问满上限（复用连领上限 N＝3 次）仍无消费 →
  写明 `closed_tick` 与结案指针（指向最后一次被问的留痕）→ 该条目**移出候选池**
  （已结案的不再产芽）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Sequence

from .model import (COUNT_DIMENSIONS, Diff, DiffKind, Edge, MATURITY_CAP, Sprout,
                    SproutOrigin, forward_delta, parse_delta)
from .subject import DIR_OBJECT_SUFFIX, SUBJECT_PREFIX

#: 能力库条目「长期未用」的拍数阈值（具体状态判据，不是「频率高」式归纳）
LIBRARY_IDLE_TICKS = 20

#: 能力库账本里的一次「消费」写入（M3）：来源标记写进账本行，可复查是谁更新的
LIBRARY_USAGE_SOURCE = "trace"

#: 结案原因标记（M2）
CLOSED_BY_ASKED_OUT = "asked-out"


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
            expected_value=_carry_expected(d),
        ))
        seq += 1
    return out


def _carry_expected(diff: Diff) -> Optional[str]:
    """芽**带着**产出它的那个预期（N43 修正：绝对值 → 差额）。

    - `预测未执行`（承诺在先、现实没读到）：原样带走——「存在」这类名义目标没有快照问题；
    - 计数型维度的**前向目标**（预期 > 实际）：带走**差额**（`+N`）而不是绝对值——
      绝对值是提议那一拍的快照，等芽被领到时现实早已走过它（实测：提议拍写「文件数＝97」，
      领做时已 103 → 永远判打脸）；差额在领做那一拍按当时现实重新锚定
      （`engine/tick.resolve_relative_predictions`），目标不会过期；
    - 其余（含 `预测内错` 且预期 < 实际＝现实已超过预期）：不带——
      把旧值当目标派回去等于让执行者把现实改回错的样子（实测踩到过：文件数从 1 变 2
      是生长，却派了一根「改回 1」的芽）。
    """
    if diff.kind == DiffKind.NOT_EXECUTED:
        return diff.expected
    if diff.dimension not in COUNT_DIMENSIONS:
        return None
    delta = parse_delta(diff.expected)          # 已经是差额写法 → 原样带走
    if delta is not None:
        return diff.expected
    delta = forward_delta(diff.expected, diff.actual)
    return "+%d" % delta if delta else None


def _predict_edge(diff: Diff) -> Optional[Edge]:
    """增益预测（事前选边）：按差异类型给结构先验，权重由兑现账事后校准。

    预测对象必须**现实可查**（能写进预测清单、能对账打脸），所以这里的取值是枚举值
    而不是自由文本。
    """
    if diff.kind == DiffKind.UNPREDICTED:
        return Edge.READ          # 现实给了新东西而没预测到 → 先看懂（判读）
    if diff.kind == DiffKind.NOT_EXECUTED:
        return Edge.ACT           # 说要做的没做 → 先把动作落成现实变化（行动）
    if _is_forward_target(diff):
        return Edge.ACT           # 「该再长一格」同样是动作型的活（N43）
    return Edge.PRINCIPLE         # 预测内错 → 多半要从已有认知推新认知（原理）


def _is_forward_target(diff: Diff) -> bool:
    """这根差异是不是「现实还没长到预期」的前向目标（计数型维度，N43）。"""
    return (diff.dimension in COUNT_DIMENSIONS
            and (parse_delta(diff.expected) is not None
                 or forward_delta(diff.expected, diff.actual) is not None))


#: 固化边（cap 芽）的**应用证据件**目录（Q2/A3）：证据件落在主体里的这个相对目录下。
APP_EVIDENCE_DIR = "app"

#: 固化边的**维度名**（cap 芽的 dimension）——判别的另一个锚（芽源之外）。
APP_EDGE_DIMENSION = "应用面"

#: 证据件**缺失归因**的三类桶名（G2）。文档（双语 `mechanism.md`）与 `status`／报告同一套名字，
#: 由 `tests/test_mechanism_docs.py` 钉住：改桶名而不同步文案，测试即红。
EVIDENCE_MISS_BUCKETS = ("自述已写未落地", "命名漂移", "未自述写入")


def app_evidence_path(obj: str, tick: int) -> str:
    """证据件相对路径的**纯函数**：`app/<拍号4位>-<对象名>.md`（对象名按 Q2 约定清洗）。

    与 `app_evidence_relpath` 同源（后者就是包一层芽对象转字符串）；单独提出来是给
    R8/A9 的**合规率**读数用的——它只有账本行（`outcomes.jsonl` 的 `obj`＋`tick`），
    没有芽对象，但路径必须和引擎当初给执行者的**同一个**，读数才可对账。
    """
    obj = str(obj or "")
    if obj.startswith(SUBJECT_PREFIX):
        obj = obj[len(SUBJECT_PREFIX):]
    safe = obj.replace("\\", "/").strip("/").replace("/", "_")
    if not safe:
        safe = "主体"
    if not safe.endswith(".md"):
        safe += ".md"
    return "%s/%04d-%s" % (APP_EVIDENCE_DIR, tick, safe)


def app_evidence_relpath(sprout: Sprout, tick: int) -> str:
    """固化边（cap 芽）本拍的**应用证据件相对路径**：`app/<拍号4位>-<对象名>.md`。

    「应用面」原先是一条**永远不可机械对账**的边（A3/N60）：cap 芽累计 160 次领做、
    `verifiable=true` **0 条**，而它占着取题位的一大块（最近 30 拍 24/31）——
    兑现率的分子因此系统性缺一角。修法是把「应用发生了」变成一件**在主体里留下痕迹**的事：
    执行者做完这一手，就在约定路径留一份证据件；引擎按**它的存在性**机械对账。

    命名由**引擎**规定（不是让执行者发挥），因为要机械可判：

    - 拍号段＝**领做拍**（这一手动作发生在哪一拍），4 位补零，与芽 ID 的拍号段同源；
    - 对象名＝芽对象的相对路径，`/` 换成 `_`（避免子目录层级把证据件散进别的目录里）；
    - 固定 `.md` 后缀（目录对象如 `主体/journal/` → `主体_journal.md`）。

    例：芽 `cap0380-001-主体_journal_0376-20260916`、领做拍 438 →
    `app/0438-journal_0376-20260916.md`。
    """
    return app_evidence_path(str(sprout.obj or ""), tick)


def app_evidence_compliance(rows: Sequence[dict], subject_root, tick_from: int = 0,
                            traces_dir=None) -> dict:
    """**证据件合规率**（R8/A9）：窗口内 cap 领做行里，真有证据件的比例。

    此前只能人肉数 `app/` 目录（且对不上账本行）；这条读数把「应有证据件的行」与
    「证据件真实存在」在**同一个路径函数**（`app_evidence_path`）上对账：
    存在＝这一手应用真的落地了（与 Q2 的证据边同一口径；只按存在性判，不看内容——
    内容质量归语义层）。缺失样例最多列 5 份，报告可复核。

    **缺失归因（G2）**：给了 `traces_dir` 就按该拍留痕的**自述动作**把缺失分成三类——
    「自述已写未落地」（自述写了约定路径、文件却不在）／「命名漂移」（自述写到别的名字，
    连拍号差 1 也算，必须被抓住而不是混进「没做」）／「未自述写入」（没给目录、没留痕、
    或那一拍根本没自述写 `app/`）。来历是活体取证：拍 676 与 679 的题面逐字给了约定路径、
    留痕里执行者也自述写了**同一个路径**、rc=0，主体里却没有这份文件——那既不是命名问题
    也不是「没做」，而是动作没落地。没有这一类读数时，「命名错配把假打脸送进分母」只能靠
    人肉读留痕，而上一次就是这么读错的。归因**只解释缺失，不改分子分母**（兑现率算法不动）。
    """
    from .reconcile import trace_write_paths

    base = Path(subject_root)
    total = present = 0
    missing: list[str] = []
    attr: dict[str, int] = {}
    drift: list[str] = []
    prefix = APP_EVIDENCE_DIR + "/"
    for rec in rows:
        if not str(rec.get("sprout_id") or "").startswith("cap"):
            continue
        try:
            t = int(rec.get("tick"))
        except (TypeError, ValueError):
            continue
        if t < tick_from:
            continue
        rel = app_evidence_path(str(rec.get("obj") or ""), t)
        total += 1
        if (base / rel).is_file():
            present += 1
            continue
        missing.append(rel)
        if traces_dir is None:
            continue
        if not attr:
            attr = {name: 0 for name in EVIDENCE_MISS_BUCKETS}
        declared = trace_write_paths(traces_dir, t)
        if rel in declared:
            attr["自述已写未落地"] += 1
            continue
        other = [d for d in declared if d.startswith(prefix)]
        if other:
            attr["命名漂移"] += 1
            if len(drift) < 5:
                drift.append("应有 %s ← 自述写 %s" % (rel, other[0]))
        else:
            attr["未自述写入"] += 1
    return {"窗口起拍": tick_from, "cap 领做": total, "证据件存在": present,
            "合规率": (present / total) if total else None, "缺失样例": missing[:5],
            "缺失归因": attr, "命名漂移样例": drift}


def frozen_requestion_eta(entries, frozen_rows: Sequence[dict], active_objs: Iterable[str],
                          tick: int, requestion_ticks: int = 300) -> dict:
    """重问闸的**最早可重问拍**（R5/A4，引擎口径；与观测层 drill ④ 同源）。

    闸只对**候选池里的条目**会响：候选池＝库账本里**未结案且未消费**的条目；
    池内某对象**不在活跃队列**、且它最新一根冻结芽已冻满 `requestion_ticks` 拍 →
    那一刻它才从去重闸（M1「挂起≠死亡」）里放出来、可以重新立芽。
    返回最早那一拍（含对象与冻结拍，可复核）。池里没有「冻结且不活跃」的条目 →
    返回 `最早可重问拍=None`（这一刻闸不会响——不是 0，不是「还差 0」的假警报）。
    """
    active = set(active_objs or ())
    newest: dict[str, int] = {}
    for rec in frozen_rows:
        at = rec.get("frozen_tick")
        if at is None:
            at = rec.get("created_tick") or 0
        obj = str(rec.get("obj") or "")
        if obj:
            newest[obj] = max(newest.get(obj, at), at)
    open_rows = [e for e in entries.values()
                 if e.get("closed_tick") is None
                 and int(e.get("last_used_tick") or 0) <= int(e.get("created_tick") or 0)]
    blocked = sorted((newest[e["name"]] + requestion_ticks, e["name"], newest[e["name"]])
                     for e in open_rows
                     if e["name"] not in active and e["name"] in newest)
    if not blocked:
        return {"冻结待重问": 0, "最早可重问对象": None, "该对象冻结于": None,
                "最早可重问拍": None, "还差拍数": None}
    first, who, at = blocked[0]
    return {"冻结待重问": len(blocked), "最早可重问对象": who, "该对象冻结于": at,
            "最早可重问拍": first, "还差拍数": max(0, first - int(tick or 0))}


def app_evidence_object(sprout: Sprout, tick: int) -> str:
    """证据件的**对账空间对象名**（`主体/app/0438-journal_0376-20260916.md`）。

    与 `app_evidence_relpath` 同源：前者给执行者看（相对路径），后者进预测/观测
    （对象命名空间）。两者只差 `主体/` 前缀这一层，不各说各话。
    """
    return SUBJECT_PREFIX + app_evidence_relpath(sprout, tick)


def is_app_edge(sprout: Sprout) -> bool:
    """这根芽是不是**固化边**（成熟链封顶 → 应用面）——Q2 的证据件只对这类芽要求。"""
    return (getattr(sprout, "origin", None) == SproutOrigin.MATURITY_CAP
            or str(getattr(sprout, "dimension", "")) == APP_EDGE_DIMENSION)


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
    """③能力库条目长期未消费 → 芽「为何未用／在别域是否成立」。

    判据全是**具体状态**：该条目的 `last_used_tick` 与当前拍号之差 ≥ `idle_ticks`，
    且最近执行者留痕里没有出现该条目名（M3②：这道闸原先读的是**差异账最后 20 行的
    `note`**——实测那串文本总长 19 个字符，闸从不生效；现在读的是执行者留痕输出）。
    **已结案的条目不再产芽**（M2：提醒的出口）——读的是合并后的当前状态，
    不会因为账本里还留着一条旧的「未结案」行而重新开口。

    不设「使用频率」式阈值（那是归纳，不是状态）。
    """
    known = set(known_objects)
    out: list[Sprout] = []
    seq = start_seq
    for name, entry in library_entries(library_records).items():
        if not name or name in known:
            continue
        if entry.get("closed_tick") is not None:
            continue                            # 已结案：出口是永久的（不再产芽）
        last_used = entry.get("last_used_tick") or entry.get("created_tick") or 0
        if tick - last_used < idle_ticks:
            continue
        if entry_mentioned(liuhen_text, name):
            continue                            # 最近留痕里出现过 → 不算未用
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


# --------------------------------------------------------------------- 能力库读侧（M2/M3）
def library_entries(records: Iterable[dict]) -> dict[str, dict]:
    """能力库账本（追加型） → **每个名字一条当前状态**（名字 → 条目）。

    为什么要有这一层：`library.jsonl` 是追加型账本，同一条目会有多次写入——创建、
    M3 的「留痕命中＝已用」更新、M2 的结案。若逐行读，一条**旧的**未结案行会把
    出口重新打开（结案失效）；`last_used_tick` 也会被旧行读回旧值（「本拍用过」白写）。
    所以读侧统一走这里合并：

    - `created_tick` 取**最早**（条目什么时候进库的）；
    - `last_used_tick` 取**最大**（最近一次被消费）；
    - `closed_*`（`closed_tick`/`closure_pointer`/`closed_by`）取**最后一次**写入。

    与轮转侧同源：`ledger/rotation.py` 对状态型账本也是「每个键保留最新一行」。
    **幂等**：把已经合并过的条目（名字 → 条目 的映射，或条目本身）再喂进来，结果不变。
    """
    source = records.values() if isinstance(records, dict) else records
    entries: dict[str, dict] = {}
    for rec in source:
        if not isinstance(rec, dict):
            continue
        name = str(rec.get("name") or "")
        if not name:
            continue
        entry = entries.setdefault(name, {"name": name, "created_tick": None,
                                          "last_used_tick": None, "closed_tick": None,
                                          "closure_pointer": "", "closed_by": "",
                                          "source": ""})
        created = rec.get("created_tick")
        if isinstance(created, int) and (entry["created_tick"] is None
                                         or created < entry["created_tick"]):
            entry["created_tick"] = created
        used = rec.get("last_used_tick")
        if isinstance(used, int) and (entry["last_used_tick"] is None
                                      or used > entry["last_used_tick"]):
            entry["last_used_tick"] = used
        closed = rec.get("closed_tick")
        if isinstance(closed, int):
            entry["closed_tick"] = closed
            entry["closure_pointer"] = str(rec.get("closure_pointer") or "")
            entry["closed_by"] = str(rec.get("closed_by") or "")
        if not entry["source"] and rec.get("source"):
            entry["source"] = str(rec["source"])
    for entry in entries.values():
        if entry["created_tick"] is None:
            entry["created_tick"] = entry["last_used_tick"] or 0
        if entry["last_used_tick"] is None:
            entry["last_used_tick"] = entry["created_tick"]
    return entries


def entry_mentioned(text: str, name: str) -> bool:
    """条目名是否出现在给定文本里（M3 的机械判据：「留痕里命中该对象」＝已用）。

    两种写法都认：

    - **全名**（`主体/journal/0322-20260916.md`）——引擎对账空间里的写法；
    - **主体内相对写法**（`journal/0322-20260916.md`）——执行者在主体根里动手时的写法。
      实测：留痕输出里全名命中 0 次、相对写法命中 5 次——只认全名等于这条判据永不触发。

    目录对象（名字以 `/` 结尾）**只认全名**：`journal/` 这种相对写法在任何一句提到
    主体目录的话里都会命中，那不是「用过这个能力」，是噪声（判据宁窄而准，不宽而吵）。
    """
    if not text or not name:
        return False
    if name in text:
        return True
    if name.endswith(DIR_OBJECT_SUFFIX) or not name.startswith(SUBJECT_PREFIX):
        return False
    return name[len(SUBJECT_PREFIX):] in text


def library_usage_updates(entries: Iterable[dict], text: str, tick: int,
                          pointer: str) -> list[dict]:
    """M3①：**留痕命中 → 记为已用**。返回要追加进能力库账本的更新行。

    这是 `last_used_tick` 的**真实更新方**——此前它只在创建那一拍写一次，此后没有任何
    更新方，「闲置 ≥20 拍」对每条条目**永久为真**（N48-1：一条永真的提醒）。
    已结案的条目不更新（出口是永久的，别再给它续命）。
    """
    out: list[dict] = []
    for entry in (entries.values() if isinstance(entries, dict) else entries):
        name = entry.get("name") or ""
        if not name or entry.get("closed_tick") is not None:
            continue
        if not entry_mentioned(text, name):
            continue
        out.append({"name": name, "last_used_tick": tick,
                    "source": LIBRARY_USAGE_SOURCE, "usage_pointer": pointer})
    return out


def library_asks(sprouts: Iterable[Sprout]) -> dict[str, int]:
    """每个库条目**累计被问过几次**＝它名下库芽的 `leads` 之和（活跃 ∪ 冻结都算）。

    为什么用「累计」而不是「当前这根芽的 leads」：问过就是问过——一根被挤出到冻结区的
    芽（leads=1）与它的后继（leads=2）合起来是三次，那是同一个条目被问了三次。
    """
    asked: dict[str, int] = {}
    for s in sprouts:
        if s.origin != SproutOrigin.LIBRARY_UNUSED:
            continue
        asked[s.obj] = asked.get(s.obj, 0) + int(s.leads or 0)
    return asked


def library_last_lead(sprouts: Iterable[Sprout]) -> dict[str, int]:
    """每个库条目**最后一次被问**发生在哪一拍（结案指针指向那一拍的留痕）。"""
    last: dict[str, int] = {}
    for s in sprouts:
        if s.origin != SproutOrigin.LIBRARY_UNUSED or not s.last_lead_tick:
            continue
        last[s.obj] = max(last.get(s.obj, 0), int(s.last_lead_tick))
    return last


def entries_to_close(entries, sprouts: Iterable[Sprout], tick: int,
                     lead_limit: int) -> list[dict]:
    """M2：**给提醒一个出口**——哪些库条目该结案（问满上限仍无消费）。

    判据（三条，全是具体状态）：

    1. 条目**未结案**（没有 `closed_tick`）；
    2. 它名下的库芽（活跃 ∪ 冻结）`leads` 之和 ≥ `lead_limit`（复用既有连领上限 N＝3）；
    3. 期间**没有被消费**：`last_used_tick` 不晚于条目创建（M3 的留痕命中会更新它）。

    返回要追加进能力库账本的结案行：`closed_tick` ＋ 结案指针（**指向最后一次被问的那份
    执行者留痕**——「为什么没用上／别域是否成立」的答复原文在那里，机械层不代替它下结论）
    ＋ 累计问次数（可复查为什么结案）。
    """
    asked = library_asks(sprouts)
    last_lead = library_last_lead(sprouts)
    rows: list[dict] = []
    for entry in (entries.values() if isinstance(entries, dict) else entries):
        name = entry.get("name") or ""
        if not name or entry.get("closed_tick") is not None:
            continue
        count = asked.get(name, 0)
        if count < lead_limit:
            continue
        created = entry.get("created_tick") or 0
        consumed = int(entry.get("last_used_tick") or 0) > int(created)
        if consumed:
            continue                    # 被消费过＝问到了答案，不是「没人理」
        lead = last_lead.get(name, 0)
        pointer = ("留痕:traces/tick-%05d.md" % lead) if lead else "能力库:%s(无留痕指针)" % name
        rows.append({"name": name, "closed_tick": tick, "closed_by": CLOSED_BY_ASKED_OUT,
                     "asked": count, "closure_pointer": pointer})
    return rows


def consumed_entries(entries) -> set[str]:
    """已被消费的条目名（M3：留痕命中 → `last_used_tick` 晚于创建）。

    与结案对称：一个提醒要么**被消费**（问题答完了），要么**被结案**（问满了没人答）
    ——两条出口都让它不再占取题位。这里只回答「哪些条目已消费」，
    退场动作（只移动进冻结区）由调用方按同一套队列纪律执行。
    """
    consumed = set()
    for entry in (entries.values() if isinstance(entries, dict) else entries):
        name = entry.get("name") or ""
        if not name:
            continue
        if int(entry.get("last_used_tick") or 0) > int(entry.get("created_tick") or 0):
            consumed.add(name)
    return consumed


def library_pool_summary(entries, tick: int = 0,
                         idle_ticks: int = LIBRARY_IDLE_TICKS,
                         known_objects: Iterable[str] = ()) -> dict:
    """能力库候选池组成（N62/A8）：**未结案且未消费 N／已结案 M／已消费 K**。

    为什么要有这条读数（[已证明] 现场）：M2 的两条出口落地后库芽全部退场，「能力库未用」
    这条提醒渠道**完全静默**——而静默有两种含义，在状态面上长得一模一样：

    | 含义 | 期望读数 |
    |---|---|
    | **预期**（问题都有结论了，或还不到该问的时候） | 候选池 0 条，或 N 条全被挡住 |
    | **故障**（渠道死了：产芽逻辑不工作） | **本可出芽**的条数 > 0 却长期不出芽 |

    没有这条读数，「渠道安静」与「渠道断了」分不开（这就是 N48 修根留下的可观测性缺口）。

    分类判据（互斥，按出口优先级：结案 > 消费 > 在池）：
    条目 `closed_tick` 有值 → 已结案；否则 `last_used_tick > created_tick` → 已消费；
    否则 → 未结案且未消费（**候选池**＝`from_unused_library` 的输入）。
    候选池再按**两道闸**分开（与 `from_unused_library` 的判据同源）：

    - `重问冷却中`：该对象已有芽（活跃 ∪ 冻结）→ 去重闸会跳过（M1：挂起≠死亡）；
    - `未到闲置阈值`：`tick − 末次使用 < idle_ticks` → 还算「最近用过」；
    - `本可出芽`：两道闸都没挡——**这一条 > 0 而库里长期不出芽，才是渠道故障的证据**。
    """
    known = set(known_objects)
    rows = list(entries.values() if isinstance(entries, dict) else entries)
    closed = consumed = 0
    open_rows: list[dict] = []
    for entry in rows:
        name = entry.get("name") or ""
        if not name:
            continue
        if entry.get("closed_tick") is not None:
            closed += 1
        elif int(entry.get("last_used_tick") or 0) > int(entry.get("created_tick") or 0):
            consumed += 1
        else:
            open_rows.append(entry)
    idle = [tick - int(e.get("last_used_tick") or e.get("created_tick") or 0)
            for e in open_rows]
    # 两道闸各自计数（一条可以同时被两道挡），`本可出芽`＝两道都没挡的条数
    # ——只有它 > 0 才是「渠道该出芽却没出芽」的证据。
    cooled = too_young = ready = 0
    for entry, age in zip(open_rows, idle, strict=True):
        in_cooldown = (entry.get("name") or "") in known
        young = age < idle_ticks
        cooled += 1 if in_cooldown else 0
        too_young += 1 if young else 0
        ready += 1 if not in_cooldown and not young else 0
    if not open_rows:
        verdict = "静默＝预期（候选池已空：结案 %d／消费 %d）" % (closed, consumed)
    elif ready > 0:
        verdict = ("本可出芽 %d 条（重问冷却挡 %d／未到闲置阈值 %d）"
                   "——若后续该出芽却不出，即渠道故障" % (ready, cooled, too_young))
    else:
        verdict = ("静默＝预期：%d 条待问但全被挡（重问冷却 %d／未到闲置阈值 %d）"
                   % (len(open_rows), cooled, too_young))
    return {"总条目": closed + consumed + len(open_rows),
            "未结案未消费": len(open_rows), "已结案": closed, "已消费": consumed,
            "重问冷却中": cooled, "未到闲置阈值": too_young, "本可出芽": ready,
            "最早闲置拍数": max(idle) if idle else None, "闲置阈值": idle_ticks,
            "判定": verdict}
