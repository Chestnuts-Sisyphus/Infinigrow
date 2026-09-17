# -*- coding: utf-8 -*-
"""拍循环：一拍 = 取题 → 动手 → 对账 → 生芽 → 记账（＋心跳）。

一拍的**顺序**是机制的一部分（顺序错了，「对账」就成了自说自话）：

```
    1  组织会话（可选：从 B猜/留痕/W回 里找语义差异、写规划预测）   ← 需要执行者通道
    2  定 B猜（默认「不变」（主体+自身状态）；组织会话的规划值覆盖它）
    3  取题（从芽队列按纪律取一根）
    4  动手（执行者：提示词经 stdin 进、stdout 出；不给执行者＝机械拍）
    5  W回（**动手之后**再读现实一次）
    6  对账 → 差异四类 → 域饱和闸 → 生芽
    7  记账：差异账/兑现账/成熟链/执行者账/域状态 ＋ 对账报告 ＋ 心跳
```

第 5 步在动手**之后**，这是「行动」边能被对账的前提：动手前读的现实证明不了动手的效果。

四条从 v1 现场换来的纪律，在 v2 里是**结构保证**而不是注释约定：

1. **执行会话不自产芽**：本模块**没有任何**「登记新芽候选」的入口；芽只从
   `sprout_sources`（差异／封顶／未用）与**组织会话**来，两者都读账本。想加自造芽，
   得先改这个模块——那就不是「顺手」能发生的事了。
2. **报告文件名带拍号 + 会话互斥**：v1 出过「同秒覆盖丢报告」「两个会话同时跑把
   成熟链连加两级」。这里：报告名 `reconcile-<拍号>.md`，`locks/` 独占锁串行化，
   拿不到锁＝本拍跳过（幂等，不报错）。
3. **成熟链同拍最多 +1**：步进函数显式写死 `+1` 上限，并把「单拍跳到顶」当异常拒绝。
4. **机械拍零外部调用**：不给执行者时不加载执行者模块、不起任何子进程
   （`tests/test_coldstart.py::test_cold_start_zero_token` 守着这条）。
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

from ..core.config import Settings, load_settings
from ..core.encoding import harden_stdio, read_text
from ..core.paths import StateLayout, guard, resolve_state
from ..ledger.store import (LedgerError, append_jsonl, create_exclusive, read_jsonl,
                            write_work_file)
from . import sprout_sources
from . import subject as subject_mod
from .domain_saturation import DomainState, value_at_freeze
from .model import (Diff, DiffKind, MATURITY_CAP, Observation, OutcomeRecord,
                    Prediction, Sprout, SproutOrigin, parse_delta)
from .org_trigger import should_run_org_session
from .reconcile import diff_summary, pending_pointer, reconcile, redemption_report
from .sprout_queue import SproutQueue

TICK_STATUS_MARK = "consecutive_failures"
LOCK_STALE_SECONDS = 900          # 15 分钟＝一拍超时上限量级；超过即视为死锁可清
ORG_DUE_FILE = "org-due.json"     # 组织段到期提示（工作文件，每拍覆写）
TICK_PROMPT_FILE = "tick.md"      # 执行会话提示词（机制正本的一部分，**真被发出去**）
PROMPT_INPUT_MAX_CHARS = 6000     # 题面+预测块的规模上限（提示词要有界）

#: 留痕里「输出段」的起始标记（M3②：「本拍用过」这道闸只读输出，不读提示词——
#: 提示词的题面里点着对象名，把它也算进来，任何被问过的条目都会被读成「做过」）
TRACE_OUTPUT_MARK = "## 输出（原样）"
#: 「最近用过」这道闸看最近几份**执行者**留痕（组织会话的留痕是「提议」，不是「动手」）
TRACE_GATE_FILES = 5
#: 执行者留痕的文件名前缀（与 `engine/executor.py` 的 KIND_TICK 同值；此处不导入那个模块，
#: 保持「机械拍连执行者模块都不加载」这条结构性质）
TRACE_TICK_GLOB = "tick-*.md"

#: 差异来源标记（账本里区分机械对账与组织会话）
SOURCE_MECHANICAL = "mechanical"

# 用途标签（与 engine/executor.py 的常量同值；此处**不导入**那个模块，
# 保持「机械拍连执行者模块都不加载」这条结构性质）
KIND_TICK = "tick"
KIND_ORG = "org-session"


class TickHeartbeatError(RuntimeError):
    """心跳写不进去（园丁的断流判据上游）——必须响亮，不许静默。"""


@dataclass
class TickResult:
    """一拍的结果（机械可读；调用方与测试都只认这个对象）。"""

    tick: int
    rc: int = 0
    skipped: bool = False
    topic_sprout: Optional[str] = None
    diffs: list[Diff] = field(default_factory=list)
    outcomes: list[OutcomeRecord] = field(default_factory=list)
    new_sprouts: list[str] = field(default_factory=list)
    org_decision: Optional[dict] = None      # 本拍算出的「该不该跑组织会话」
    notes: list[str] = field(default_factory=list)
    # v2.1（运转线）：主体 / 执行者 / 组织会话 / 域饱和 / 兑现 的读数落点
    subject: dict = field(default_factory=dict)
    executor: Optional[dict] = None
    executor_state: str = "absent"      # absent（未接）｜no_ticket（接了但本拍无芽可领）｜ran（调用了）
    org: Optional[dict] = None
    domain: dict = field(default_factory=dict)
    predictions: dict = field(default_factory=dict)
    act_caused: list[str] = field(default_factory=list)   # 本拍动作自己造成的读数变化
    #: 能力库提醒的出口动作（M2 结案／M3 消费退场）——本拍做了什么都落这里，可复查
    library: dict = field(default_factory=dict)

    def executor_line(self) -> str:
        """执行者一行字（**三种状态分开说**：未接 ≠ 接了但没活干 ≠ 跑过了）。"""
        if self.executor:
            return self.executor["label"]
        if self.executor_state == "no_ticket":
            return "（已接执行者；本拍无芽可领 → 未调用，零 token）"
        return "（未接执行者：机械拍，零 token）"

    @property
    def diff_summary(self) -> dict:
        return diff_summary(self.diffs)

    def as_dict(self) -> dict:
        return {
            "tick": self.tick, "rc": self.rc, "skipped": self.skipped,
            "topic_sprout": self.topic_sprout,
            "diffs": self.diff_summary,
            "outcomes": [o.as_record() for o in self.outcomes],
            "new_sprouts": self.new_sprouts,
            "org_decision": self.org_decision,
            "subject": self.subject, "executor": self.executor,
            "executor_state": self.executor_state,
            "org": self.org, "domain": self.domain, "predictions": self.predictions,
            "act_caused": self.act_caused, "notes": self.notes,
            "library": self.library,
        }


# --------------------------------------------------------------------- 心跳
def read_tick_status(layout: StateLayout) -> dict:
    if not layout.tick_status.is_file():
        return {"consecutive_failures": 0, "consecutive_executor_failures": 0,
                "last_rc": 0, "last_executor_rc": None, "last_time": "", "last_note": "",
                "tick": 0}
    try:
        return json.loads(layout.tick_status.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        # 心跳文件坏掉＝园丁的断流判据失效；不静默吞，返回带标记的兜底并让调用方看见
        return {"consecutive_failures": 0, "consecutive_executor_failures": 0,
                "last_rc": 0, "last_executor_rc": None, "last_time": "", "tick": 0,
                "last_note": "心跳文件不可解析：%r" % exc}


def current_tick(layout: StateLayout) -> tuple[int, str]:
    """本拍该用哪个拍号：**优先心跳；心跳不可读时从账本恢复**。

    踩过的坑（实测）：心跳文件在某一瞬读不出时（并发/文件系统抖动/写到一半被杀），
    旧实现静默回退成 `tick=0` → 本拍编号回到 1 → 报告 `reconcile-00001.md` 被**同名覆写**，
    账本里拍号也出现跳变（现场：账本跨拍 1-16，心跳却是 2）。

    所以：心跳读不出来就**从账本反推**（取 diffs/outcomes/maturity/executor 里的最大拍号 +1），
    并把这件事写成可见说明——静默重置比报错危险得多。

    另一个同样危险的情形（v2.2.1 后真机复见）：心跳**可读**但拍号**落后于账本最大拍号**
    （序列倒退——现场：账本跨拍 1-16，心跳却是 4）。这是旧事故留下的余波：
    心跳没坏，恢复逻辑只守「不可读」一种触发，于是新序列 4、5、6… 会**逐一覆写**旧报告
    `reconcile-00004..00016.md`。所以只要「心跳拍号 < 账本最大拍号」就同样恢复，
    不许把拍号序列接回已经被账本占用的区间。
    """
    status = read_tick_status(layout)
    note = str(status.get("last_note") or "")
    tick = int(status.get("tick") or 0)
    heartbeat_broken = tick <= 0 or note.startswith("心跳文件不可解析")
    recovered = 0
    for path in (layout.diff_ledger, layout.outcome_ledger, layout.maturity_chain,
                 layout.executor_ledger):
        for rec in read_jsonl(path):
            value = rec.get("tick")
            if isinstance(value, int) and value > recovered:
                recovered = value
    if recovered and (heartbeat_broken or tick < recovered):
        if heartbeat_broken:
            why = ("心跳不可读（%s），已从账本恢复：本拍按拍 %d 起算（账本最大拍号 %d）"
                   % (note or "原因未知", recovered + 1, recovered))
        else:
            why = ("心跳拍号 %d 落后于账本最大拍号 %d（序列倒退），已从账本恢复："
                   "本拍按拍 %d 起算" % (tick, recovered, recovered + 1))
        return recovered + 1, why
    return tick + 1, ""


def record_tick_result(layout: StateLayout, rc: int, tick: int, note: str = "",
                       executor_rc: Optional[int] = None,
                       no_ticket: bool = False) -> int:
    """落心跳：rc==0 归零，否则连续失败 +1。写不进去抛 `TickHeartbeatError`。

    心跳里记**引擎身份**（版本 ＋ 提交号）：定规是「引擎必须是最新版才准运转」，
    那么每一拍都必须能回答「这是哪个版本的引擎跑的」——否则升级之后，
    历史读数属于哪一版就说不清了（账本只记 tick 数字是不够的）。

    另记**执行者连续失败**（与拍失败分开计）：机械拍跑得成、执行者起不来，
    这是两种病；混在一个计数里，园丁的告警就指不出是哪儿坏了。
    本拍没调执行者（`executor_rc=None`）时**保留原计数**（没调用不算失败，也不算成功）。

    `no_ticket`（K3）：本拍**接了执行者但无芽可领**（执行者没有被调用）——
    连续 N 拍这样＝**空转**（引擎在烧时间不生长），园丁据此出「不生长」告警旗。
    机械拍（没接执行者）不算：零 token 本来就是它的预期，不叫空转。
    """
    from ..core.build_info import engine_identity
    status = read_tick_status(layout)
    failures = 0 if rc == 0 else int(status.get("consecutive_failures", 0)) + 1
    executor_failures = int(status.get("consecutive_executor_failures", 0) or 0)
    if executor_rc is not None:
        executor_failures = 0 if executor_rc == 0 else executor_failures + 1
    stall = int(status.get("no_ticket_streak", 0) or 0)
    stall = stall + 1 if no_ticket else 0
    ident = engine_identity()
    payload = {
        TICK_STATUS_MARK: failures,
        "consecutive_executor_failures": executor_failures,
        "no_ticket_streak": stall,
        "last_rc": rc,
        "last_executor_rc": executor_rc,
        "last_time": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_note": note,
        "tick": tick,
        "engine_version": ident["version"],
        "engine_commit": ident["commit"],
    }
    try:
        write_work_file(layout.tick_status,
                        json.dumps(payload, ensure_ascii=False, indent=2),
                        layout.root, require_markers=(TICK_STATUS_MARK,))
    except (LedgerError, OSError, PermissionError) as exc:
        raise TickHeartbeatError("心跳写失败（园丁断流判据将停止更新）：%s" % exc) from exc
    return failures


# --------------------------------------------------------------------- 互斥
def acquire_lock(layout: StateLayout, tick: int) -> Optional[Path]:
    """独占锁：拿不到返回 None（本拍跳过）。陈旧锁（超过 `LOCK_STALE_SECONDS`）自动清。

    创建动作走 `ledger/store.create_exclusive`（原子独占创建是**写盘能力**的一种，
    收在 store 层里 —— cli/engine 里不再各自拼系统调用，越界守卫就只可能漏在 store 里）。
    """
    guard(layout.locks_dir, layout.root)
    layout.locks_dir.mkdir(parents=True, exist_ok=True)
    lock = layout.locks_dir / "tick.lock"
    if lock.exists():
        age = time.time() - lock.stat().st_mtime
        if age > LOCK_STALE_SECONDS:
            try:
                lock.unlink()                    # 陈旧锁＝死锁，清掉（可复跑、幂等）
            except OSError:
                return None
        else:
            return None
    try:
        created = create_exclusive(lock, "tick=%d pid=%d\n" % (tick, os.getpid()),
                                   layout.root)
    except LedgerError:
        return None
    return lock if created else None              # 竞态：另一个会话刚拿到 → 本拍跳过


def release_lock(lock: Optional[Path]) -> None:
    if lock is not None and lock.exists():
        try:
            lock.unlink()
        except OSError:
            pass


# --------------------------------------------------------------------- 机械侧
def observe_state(layout: StateLayout) -> list[Observation]:
    """机械观测**引擎自身状态**：把状态目录里的可查事实读成 W回（不起子进程）。

    ⚠ 默认**不进对账**（见 `run_tick` 里默认预测/观测只用主体）：这些文件是引擎
    自己写的——每一拍都会因为自己的记账而变，把它们当「差异」等于让引擎给自己
    派活（实测：每拍凭空长出 3 根「diffs.jsonl/sprouts.jsonl/library.jsonl 字节数」
    的芽，执行者无法也不该去动引擎状态）。引擎自身健康由**园丁**看护
    （断流/锁/失败计数/轮转），那是另一条线。
    保留这个函数：显式调用与测试要用「看自己」这条读数时它仍然可用。
    """
    objects = [layout.tick_status, layout.diff_ledger, layout.outcome_ledger,
               layout.maturity_chain, layout.sprouts, layout.library]
    out = []
    for path in objects:
        exists = path.is_file()
        size = path.stat().st_size if exists else 0
        out.append(Observation(obj=path.name, dimension="字节数", actual=str(size),
                               evidence="文件:%s" % path.name))
    return out


def predict_unchanged(layout: StateLayout, tick: int) -> list[Prediction]:
    """默认 B猜（引擎自身状态）：本拍这些对象保持不变。

    与 `observe_state` 对称（同对象同维度）——不对称会制造假差异：只观测不预测＝
    每拍「预测外发现」，只预测不观测＝每拍「预测未执行」。两者都是凭空生芽。
    """
    preds = []
    for path in (layout.tick_status, layout.diff_ledger, layout.outcome_ledger,
                 layout.maturity_chain, layout.sprouts, layout.library):
        size = path.stat().st_size if path.is_file() else 0
        preds.append(Prediction(obj=path.name, dimension="字节数", expected=str(size),
                                tick=tick, evidence="预测:%s@拍%d" % (path.name, tick)))
    return preds


def advance_maturity(current_step: int) -> int:
    """成熟链步进：**同拍最多 +1**（T11 连跳护栏；封顶即止）。"""
    if current_step < 0:
        raise ValueError("成熟链步不能为负：%s" % current_step)
    if current_step >= MATURITY_CAP:
        return MATURITY_CAP
    return current_step + 1


def maturity_of(layout: StateLayout) -> dict[str, int]:
    """现算每个对象当前成熟链步（读账本，取最新一行；不缓存、不手工维护）。"""
    steps: dict[str, int] = {}
    for rec in read_jsonl(layout.maturity_chain):
        obj, step = rec.get("obj"), rec.get("step")
        if obj and isinstance(step, int):
            steps[obj] = step
    return steps


def record_maturity(layout: StateLayout, obj: str, tick: int,
                    steps: dict[str, int]) -> tuple[int, bool]:
    """把某对象推进一格并落账。返回 (新步, 是否本拍恰好封顶)。"""
    current = steps.get(obj, 0)
    new_step = advance_maturity(current)
    capped_now = new_step == MATURITY_CAP and current < MATURITY_CAP
    append_jsonl(layout.maturity_chain,
                 {"obj": obj, "step": new_step, "tick": tick, "tick_at_cap": capped_now},
                 layout.root)
    steps[obj] = new_step
    return new_step, capped_now


def evaluate_outcome(sprout: Sprout, diffs: Sequence[Diff], tick: int,
                     sampled: bool = True,
                     observable_keys: Optional[Sequence[tuple[str, str]]] = None,
                     ) -> OutcomeRecord:
    """领做后的兑现判定（机械）：该对象该维度的差异真消＝兑现；仍错＝打脸。

    `sampled`＝这一拍**真有东西动过手**（执行者跑过）。没有执行者的一拍里
    兑现账会写 `sample=false`：机械拍不做语义判断也不产出真实生长，
    把它的「打脸」当业绩读，就是把仪表盘当引擎（G6 的病灶）。
    """
    mine = [d for d in diffs if d.key == sprout.key]
    redeemed = any(d.kind == DiffKind.OK for d in mine)
    actual = sprout.predicted_edge if redeemed else None
    # 可对账性：机械层本拍读得到这个 (对象, 维度) 吗？读不到的（例如「应用面」这类
    # 语义维度的芽）**永远**判不出兑现——把它们算进兑现率就是把「读不到」说成「打脸」，
    # 那是结构性假数字。如实标 `verifiable=False`，并让兑现率把它们排除在分母外。
    verifiable = True
    if observable_keys is not None:
        verifiable = tuple(sprout.key) in set(map(tuple, observable_keys))
    return OutcomeRecord(sprout_id=sprout.id, predicted_edge=sprout.predicted_edge,
                         actual_edge=actual, redeemed=redeemed,
                         pointer=sprout.pointer, tick=tick, sampled=sampled,
                         verifiable=verifiable, obj=sprout.obj)


# --------------------------------------------------------------------- 提示词
def resolve_relative_predictions(preds: Sequence[Prediction],
                                 readings: Optional[dict] = None) -> list[Prediction]:
    """把 B猜里的**差额预期**（`+N`）按**动手前**的现实锚定成绝对值（N43）。

    差额预期＝「在动手前的读数上再推进 N」（组织会话提议「往 journal/ 里再长一格」时
    写的就是它）。为什么不在提议时写死绝对数字：提议拍 ≠ 创建拍（K7 的拍号段＝
    **创建**拍），写死等于把一个会过期的快照当承诺——等芽被领到时现实早已走过它。

    - 锚不上（该量本拍读不到 / 读数不是整数）→ **原样保留**：不做假装可对账的承诺，
      对账会如实记成未执行；机械层读不到的量本来就不该被算进兑现率（`verifiable`）。
    - 不是差额写法的预测原样返回（默认预测全是绝对值，走这条）。
    """
    readings = readings if readings is not None else {}
    out: list[Prediction] = []
    for item in preds:
        delta = parse_delta(item.expected)
        if delta is None:
            out.append(item)
            continue
        current = readings.get(item.key)
        try:
            base = int(str(current).strip())
        except (TypeError, ValueError):
            out.append(item)                       # 读不到 → 锚不上，原样保留
            continue
        out.append(replace(item, expected=str(base + delta)))
    return out


def build_tick_prompt(settings: Settings, layout: StateLayout, tick: int,
                      sprout: Optional[Sprout], predictions: Sequence[Prediction],
                      subject_root: Path, facts: Optional[dict] = None) -> str:
    """执行会话提示词＝机制提示词原文 ＋ 本拍题面 ＋ 本拍事实 ＋ 本拍 B猜（承诺）。

    提示词文件**真被发出去**（不是只写在文档里给静态规则检查）：机制改了、提示词没改，
    执行者那边立刻就能看出来——这是 R2 同源校验之外的第二道现实约束。

    把 B猜 给执行者，是这条通道的关键：B猜是**事前承诺**，执行者的活是让现实满足它，
    兑现账判的正是这一条。不给它，任何真动手的一拍都会被判成「预测内错」——
    那说明的不是「干错了」，而是「没预测」。

    `facts`＝**机械事实摘录**（拍号／差异概览／队列／兑现率／主体读数）。为什么要有它：
    执行者若只拿到一句题面，写出来的留痕只能是空话；给它账本里**真实存在**的数字，
    它才可能写出可核对的东西——而「真实」的标准由引擎给，不由它自述。
    """
    prompt_path = settings.prompts_path() / TICK_PROMPT_FILE
    if not prompt_path.is_file():
        raise FileNotFoundError("执行会话提示词缺失：%s" % TICK_PROMPT_FILE)
    base = read_text(prompt_path)
    lines = [
        "",
        "---",
        "",
        "## 本拍题面（机器填，勿改）",
        "",
        "- 拍号：%d" % tick,
        "- 状态根名：%s" % layout.root.name,
        "- 主体根名：%s" % subject_mod.subject_leaf(subject_root),
        "- 主体对象命名：`%s<相对路径>`" % subject_mod.SUBJECT_PREFIX,
        "",
    ]
    if sprout is not None:
        lines += [
            "### 本拍要消解的差异（领到的芽）",
            "",
            "- 芽 ID：`%s`" % sprout.id,
            "- 芽源：%s" % sprout.origin.value,
            "- 对象：%s｜维度：%s" % (sprout.obj, sprout.dimension),
            "- 差异指针：%s" % (sprout.pointer or "（缺）"),
            "- 增益预测（事前选的边）：%s"
            % (sprout.predicted_edge.value if sprout.predicted_edge else "（无）"),
            "",
        ]
    else:
        lines += ["### 本拍没有芽可领", "",
                  "队列里没有可领的芽。**不要**为了有活干而自己造题：",
                  "芽是预测差异的产物（零差异零芽）。本拍可以只留痕说明「无事可做」。", ""]
    if facts:
        lines += ["### 本拍事实（机械摘录；引用它时照抄，不要加工成结论）", ""]
        lines += ["- %s" % item for item in facts.get("lines", [])]
        lines.append("")
    lines += ["### 本拍 B猜（引擎已记录；你要让现实满足它们）", ""]
    if predictions:
        lines += ["- `%s`｜%s｜预期=%s｜指针=%s"
                  % (p.obj, p.dimension, p.expected, p.evidence or "（缺）")
                  for p in predictions]
    else:
        lines += ["（本拍没有预测）"]
    lines += [
        "",
        "### 输出与留痕",
        "",
        "- 你的 stdout 会**原样**落进 `state/traces/`（这一拍的留痕），stderr 同路。",
        "- 要报告用量就单独打一行：`IG_USAGE {\"input_tokens\": 0, \"cost_usd\": 0}`",
        "  （不写＝账本里记 null：引擎不拿输出长度冒充 token 数）。",
        "- 返回值非 0＝这一拍记为**执行者失败**（可见、进告警计数），但不会因此丢账。",
    ]
    text = base + "\n".join(lines)
    if len(text) > PROMPT_INPUT_MAX_CHARS + len(base):
        text = text[:PROMPT_INPUT_MAX_CHARS + len(base)] + "\n（题面过长，已截断）\n"
    return text


def tick_facts(layout: StateLayout, queue: SproutQueue, tick: int,
               topic: Optional[Sprout], subject_root: Path) -> dict:
    """组一段**机械事实摘录**给执行者（每个数字都能在账本/主体里查到）。

    只用引擎自己记账得到的东西：拍号、队列读数、最近差异概览、兑现率判定、主体读数。
    刻意不写「最近表现不错」这类判断——事实由引擎给，判断留给执行者（并由对账判对错）。
    """
    recent = read_jsonl(layout.diff_ledger)[-30:]
    by_kind: dict[str, int] = {}
    for rec in recent:
        key = str(rec.get("kind"))
        by_kind[key] = by_kind.get(key, 0) + 1
    redemption = redemption_report(read_jsonl(layout.outcome_ledger))
    snapshot = subject_mod.subject_snapshot(subject_root, tick)
    summary = queue.summary()
    lines = [
        "拍号 %d（引擎：%s）" % (tick, _engine_label()),
        "队列：活跃 %d／冻结 %d（芽源分布 %s）"
        % (summary["active"], summary["frozen"],
           json.dumps(summary["by_origin"], ensure_ascii=False)),
        "本拍领到的芽：%s" % (topic.id if topic else "（无）"),
        "最近 30 行差异账按类型：%s" % json.dumps(by_kind, ensure_ascii=False),
        "兑现账：%s（样本 %d／共 %d 行）"
        % (redemption["判定"], redemption["样本数"], redemption["总行数"]),
        "主体读数：文件 %d 个（真实总数，不受观测上限影响）／观测 %d 个／共 %d 字节"
        % (snapshot["file_count"], snapshot.get("observed_files", len(snapshot["files"])),
           snapshot["total_bytes"]),
    ]
    if snapshot["files"]:
        lines.append("主体文件：%s"
                     % "、".join("%s(%d 字节)" % (f["name"], f["bytes"])
                                 for f in snapshot["files"][:20]))
    else:
        lines.append("主体文件：（空）")
    lines.append("可对账对象（本拍会读到的现存对象×维度；数量上限 %d）：%s"
                 % (snapshot["file_limit"],
                    "、".join("%s×%s" % (o, dim) for o, dim in _observable_keys(snapshot))
                    or "（无）"))
    lines.append("要提议**新建**主体内的文件：直接对它下预测（预期=存在）——"
                 "现实侧读不到它会记成「预测未执行」，照样产芽（这是合法的提议路径）。")
    return {"lines": lines}


def _observable_keys(snapshot: dict) -> list[tuple[str, str]]:
    """主体快照 → 明早会对账的 (对象, 维度) 清单（与 `observe_subject` 对称）。"""
    leaf = snapshot["root_name"]
    keys = [(leaf, "存在性"), (leaf, "文件数")]
    for item in snapshot.get("dirs", []):
        keys.append((subject_mod.subject_dir_object(item["name"]), "文件数"))
    for item in snapshot["files"]:
        obj = subject_mod.subject_object(item["name"])
        keys += [(obj, "存在性"), (obj, "字节数")]
    return keys


def recent_trace_output(layout: StateLayout, files: int = TRACE_GATE_FILES) -> str:
    """最近几份**执行者**留痕的「输出段」原文（M3②：「本拍用过」这道闸的输入）。

    此前这道闸读的是**差异账最后 20 行的 `note`**——实测那串文本总长 19 个字符，
    闸从不生效（N48-2）。现在读留痕输出：

    - **只读输出段**（`## 输出（原样）` 之后）：留痕里还有提示词，题面点名了对象——
      把提示词也算进来，任何被问过的条目都会被读成「做过」，闸就白设了；
    - **只读执行者留痕**（`tick-*.md`）：组织会话的留痕是「提议」不是「动手」，
      提议里提到某个对象不等于它被用过；
    - 读不到/没留痕 → 空串（不猜）。
    """
    traces = getattr(layout, "traces_dir", None)
    if traces is None or not Path(traces).is_dir():
        return ""
    paths = [p for p in Path(traces).glob(TRACE_TICK_GLOB) if p.is_file()]
    if not paths:
        return ""
    try:
        paths.sort(key=lambda p: p.stat().st_mtime)
    except OSError:
        paths.sort()
    chunks: list[str] = []
    for path in paths[-max(1, files):]:
        try:
            text = read_text(path)
        except OSError:
            continue
        idx = text.find(TRACE_OUTPUT_MARK)
        chunks.append(text[idx:] if idx >= 0 else "")
    return "\n".join(chunks)


def augment_observations(observations: Sequence[Observation],
                         predictions: Sequence[Prediction],
                         subject_root: Path) -> list[Observation]:
    """**定键补观测**（M7/N45）：对**预测里出现过的键**补一条观测，只读这些键。

    治的是「观测边界造成的假差异」：观测与默认预测都取「mtime 最新 N 个」，
    主体新增一个文件会把边界上的文件挤出观测名额 → 那一拍它既没被观测、又被预测
    「不变」→ 对账记成「预测未执行」（它其实存在，实测 8 行：拍 267/271/272/274/290/302/306/311）。

    边界纪律不变：补观测**只针对预测里出现过的键**（该集合本来就因为有界预测而有界），
    不扩大观测面、不去扫整个主体；真的缺失仍如实记成「预测未执行」（拒收≠丢弃）。
    """
    known = {o.key for o in observations}
    out = list(observations)
    for pred in predictions:
        if pred.key in known:
            continue
        extra = subject_mod.observe_object(subject_root, pred.obj, pred.dimension)
        if extra is None:
            continue
        known.add(extra.key)
        out.append(extra)
    return out


def exit_library_reminders(layout: StateLayout, queue: SproutQueue, entries: dict,
                           tick: int, lead_limit: int) -> dict:
    """能力库提醒的**出口**（M2 结案 ＋ M3 消费退场）——「提醒」必须能结束。

    - **结案**（M2）：条目被问满上限（复用连领上限 N＝3）仍无消费 → 写 `closed_tick`
      ＋结案指针（指向最后一次被问的留痕；「为什么没用上／别域是否成立」的答复原文在那里）
      → 该条目移出候选池（`from_unused_library` 不再为它产芽）；
    - **消费退场**（M3）：条目被消费（留痕命中 → `last_used_tick` 更新）→ 问题答完了，
      在队芽同样退场——否则同一根芽还会被再问两次，白烧两轮。

    两条出口都**只移动不删**：在队的库芽进冻结区（挂起，可被重看/重问）。
    `entries` 是本拍合并后的能力库视图（读侧唯一入口），本函数就地更新它，
    调用方同一拍内后续读到的就是最新状态。
    """
    closed = sprout_sources.entries_to_close(entries, queue.sprouts + queue.frozen,
                                             tick, lead_limit)
    for row in closed:
        append_jsonl(layout.library, row, layout.root)
        entry = entries.get(row["name"])
        if entry is not None:                       # 本拍内即刻生效（不再产芽/不再更新）
            entry["closed_tick"] = tick
            entry["closed_by"] = row["closed_by"]
            entry["closure_pointer"] = row["closure_pointer"]
    closed_names = {row["name"] for row in closed}
    consumed = sprout_sources.consumed_entries(entries)
    retired_close: list[str] = []
    retired_consumed: list[str] = []
    for sprout in list(queue.sprouts):
        if sprout.origin != SproutOrigin.LIBRARY_UNUSED:
            continue
        if sprout.obj in closed_names:
            if queue.freeze(sprout, tick):
                retired_close.append(sprout.id)
        elif sprout.obj in consumed:
            if queue.freeze(sprout, tick):
                retired_consumed.append(sprout.id)
    return {"closed": sorted(closed_names), "consumed": sorted(consumed),
            "retired_by_close": retired_close,
            "retired_by_consumption": retired_consumed}


def _engine_label() -> str:
    """引擎身份一行字（延迟导入，避免 import 期循环）。"""
    from ..core.build_info import engine_label
    return engine_label()


def _make_runner(settings: Settings, layout: StateLayout, subject_root: Path, tick: int,
                 kind: str, executor_cmd: str, callable_fn):
    """造执行者 runner。**延迟导入执行者模块**：机械拍连它都不加载。

    工作目录刻意是**仓库根**（不是主体根）：命令照你在仓库里的写法解析
    （`python tools/xxx.py` 这类相对路径要能直接用），而「该动手的地方」由
    `IG_SUBJECT_ROOT` 环境变量给执行者——两者分工明确，不靠猜。
    """
    command = (executor_cmd or "").strip()
    if not command and callable_fn is None:
        return None
    from . import executor as exec_mod
    return exec_mod.make_runner(
        command=command, callable_fn=callable_fn, tick=tick, kind=kind,
        cwd=settings.repo_path, state_root=layout.root, subject_root=subject_root,
        timeout_s=settings.executor_timeout_s, model=settings.llm_model)


# --------------------------------------------------------------------- 报告
def _redemption_lines(layout: StateLayout,
                      known_objects: Optional[Sequence[str]] = None) -> list[str]:
    """兑现率段（**诚实呈现**：无样本就说无样本，不说 0，不说「差」）。"""
    report = redemption_report(read_jsonl(layout.outcome_ledger))
    lines = ["## 兑现率（现算，不存缓存）", "",
             "- 判定：**%s**（样本 %d 条／兑现账共 %d 行；其中不可对账 %d 行，不计入）"
             % (report["判定"], report["样本数"], report["总行数"],
                report.get("不可对账", 0)),
             "- 说明：%s" % report["说明"]]
    if report.get("兑现率") is not None:
        lines.append("- 兑现率：%.2f" % report["兑现率"])
        for bucket, stat in report["分桶"].items():
            lines.append("  - 桶 %s：n=%d 兑现率=%.2f"
                         % (bucket, stat["n"], stat["兑现率"]))
    cap = report.get("固化边") or {}
    if cap.get("n"):
        lines.append("- 固化边（应用面，不可机械验证）：%d 条，单独列出：%s"
                     % (cap["n"], "、".join(cap.get("单独列出") or [])[:160]))
    # N62/A8：能力库候选池组成——「提醒渠道安静」是预期还是故障，报告里也要能判。
    from .sprout_sources import library_entries, library_pool_summary
    try:
        tick_now = int(read_tick_status(layout).get("tick") or 0)
    except (OSError, ValueError, json.JSONDecodeError):
        tick_now = 0
    pool = library_pool_summary(library_entries(read_jsonl(layout.library)), tick_now,
                                known_objects=known_objects or ())
    lines.append("- 能力库候选池：未结案且未消费 %d 条／已结案 %d 条／已消费 %d 条"
                 "（总 %d 条；本可出芽 %d，重问冷却挡 %d／未到闲置阈值 %d）"
                 % (pool["未结案未消费"], pool["已结案"], pool["已消费"],
                    pool["总条目"], pool["本可出芽"], pool["重问冷却中"],
                    pool["未到闲置阈值"]))
    lines.append("- 能力库渠道判定：%s" % pool["判定"])
    return lines


def _short_names(names: Optional[Sequence[str]], limit: int = 6) -> str:
    """把一长串条目名压成一行可读摘要（报告是给人看的，别把 40 个名字全铺上去）。"""
    items = list(names or [])
    if not items:
        return ""
    head = "、".join(items[:limit])
    return "（%s%s）" % (head, " 等 %d 条" % len(items) if len(items) > limit else "")


def write_reconcile_report(layout: StateLayout, result: TickResult,
                           known_objects: Optional[Iterable[str]] = None) -> Path:
    """写对账报告：**文件名带拍号**（同拍重跑＝同一个文件，不会互相覆盖）。"""
    from ..core.build_info import engine_label
    path = layout.reconcile_dir / ("reconcile-%05d.md" % result.tick)
    guard(path, layout.root)
    lines = ["# 对账报告 · 拍 %d" % result.tick, "",
             "- 引擎：%s" % engine_label(),
             "- 本拍取题：%s" % (result.topic_sprout or "（无芽可领）"),
             "- 本拍 B猜：%s" % json.dumps(result.predictions, ensure_ascii=False),
             "- 执行者：%s" % result.executor_line(),
             "- 组织会话：%s" % ((result.org or {}).get("summary") or "（未跑）"),
             "- 主体：%s" % json.dumps(result.subject, ensure_ascii=False),
             "- 域饱和：%s" % json.dumps(result.domain, ensure_ascii=False),
             "- 本拍动作造成的读数变化（入账、不派芽）：%s"
             % (json.dumps(result.act_caused, ensure_ascii=False) or "（无）"),
             "- 能力库出口（M2 结案／M3 消费）：结案 %d 条%s｜在队芽退场 %d 根（结案 %d／消费 %d）"
             % (len(result.library.get("closed") or []),
                _short_names(result.library.get("closed")),
                len(result.library.get("retired_by_close") or [])
                + len(result.library.get("retired_by_consumption") or []),
                len(result.library.get("retired_by_close") or []),
                len(result.library.get("retired_by_consumption") or [])),
             "- 差异总览：%s" % json.dumps(result.diff_summary, ensure_ascii=False), ""]
    if result.diffs:
        lines += ["## 差异点（机械对账）", ""]
        for d in result.diffs:
            lines.append("- `%s` | %s | %s | 预期=%s | 实际=%s | 指针=%s"
                         % (d.kind.value, d.obj, d.dimension, d.expected, d.actual,
                            d.evidence or "（缺）"))
        lines.append("")
    if result.org and result.org.get("findings"):
        lines += ["## 组织会话发现（语义判断，进账可被打脸）", ""]
        lines += ["- %s" % f for f in result.org["findings"]] + [""]
    if result.new_sprouts:
        lines += ["## 本拍新生芽", ""] + ["- `%s`" % s for s in result.new_sprouts] + [""]
    lines += _redemption_lines(layout, known_objects)
    if result.outcomes:
        lines += ["", "## 兑现判定（本拍领过的芽）", ""] + [
            "- `%s` 预测边=%s 实际边=%s → %s%s%s"
            % (o.sprout_id, o.predicted_edge.value if o.predicted_edge else "无",
               o.actual_edge.value if o.actual_edge else "无",
               "兑现" if o.redeemed else "打脸",
               "" if o.sampled else "（无样本：本拍没有执行者动手）",
               "" if o.verifiable else "（不可对账：该维度机械层读不到）")
            for o in result.outcomes]
    write_work_file(path, "\n".join(lines), layout.root,
                    require_markers=("# 对账报告",))
    return path


def write_org_due(layout: StateLayout, result: TickResult, decision) -> Path:
    """把「组织会话是否到期」落成可人读、可机读的一个小件（每拍覆写，工作文件）。"""
    path = layout.root / ORG_DUE_FILE
    guard(path, layout.root)
    org = result.org or {}
    payload = {
        "tick": result.tick,
        "should_run_org": bool(decision.should_run),
        "reason": decision.reason,
        "executor": bool(result.executor is not None),
        "ran_this_tick": bool(org.get("ran")),
        "org_summary": org.get("summary") or "",
        "criteria": decision.criteria,
    }
    write_work_file(path, json.dumps(payload, ensure_ascii=False, indent=2),
                    layout.root, require_markers=("should_run_org",))
    return path


# --------------------------------------------------------------------- 主循环
def run_tick(settings: Optional[Settings] = None,
             state_root: Optional[str] = None,
             tick: Optional[int] = None,
             predictions: Optional[Sequence[Prediction]] = None,
             observations: Optional[Sequence[Observation]] = None,
             llm: Optional[Callable[[str], str]] = None,
             probe: bool = False,
             executor: Optional[str] = None,
             org_session: bool = True) -> TickResult:
    """跑一拍。

    - `executor=None` 且 `llm=None`（默认）＝**机械拍**：零 token、零凭据、不起子进程，
      只做机械观测与对账——冷启动验收、CI、以及「只想看机制转不转」时都用它。
    - `executor="命令"`（或配置 `IG_EXECUTOR`）＝**接上执行者**：题面与 B猜经 stdin 进、
      stdout 出，输出落留痕、调用落账（成功／失败／超时／空输出都是可见事实）。
    - `llm=可调用`＝进程内执行者（嵌入与测试用），与命令行走同一条记账路径。

    `probe=True` 时额外把芽源判定明细打进 notes（排查用，不改行为）。
    """
    harden_stdio()
    cfg = settings or load_settings(state_root=state_root)
    layout = resolve_state(cfg.state_root or state_root, cfg.repo_root, create=True)

    recovered_note = ""
    if tick is not None:
        this_tick = tick
    else:
        this_tick, recovered_note = current_tick(layout)

    lock = acquire_lock(layout, this_tick)
    if lock is None:
        return TickResult(tick=this_tick, rc=0, skipped=True,
                          notes=["另一个会话在跑：本拍跳过（幂等，不覆盖他人产物）"])
    try:
        result = _run_tick_locked(cfg, layout, this_tick, predictions, observations, llm,
                                 probe, executor, org_session)
    finally:
        release_lock(lock)
    if recovered_note:
        result.notes.insert(0, recovered_note)          # 异常要显眼，不许静默
        record_tick_result(layout, result.rc, this_tick, note=recovered_note,
                           executor_rc=(result.executor or {}).get("rc"),
                           no_ticket=result.executor_state == "no_ticket")
    return result


def _run_tick_locked(cfg: Settings, layout: StateLayout, tick: int,
                     predictions, observations, llm, probe: bool,
                     executor_cmd: Optional[str], org_enabled: bool) -> TickResult:
    result = TickResult(tick=tick)
    subject_root = cfg.subject_path()
    queue = SproutQueue.load(layout.sprouts, layout.frozen_sprouts,
                             cap=cfg.queue_cap, lead_limit=cfg.lead_limit,
                             cold_start_ticks=cfg.cold_start_ticks)
    domains = DomainState.load(layout.domains)
    # 能力库的**合并视图**（M2/M3 的读侧唯一入口）：追加型账本按名字合并成当前状态
    # （创建 / 消费更新 / 结案都写新行；逐行读会让结案失效、把「已用」读回旧值）
    lib_entries = sprout_sources.library_entries(read_jsonl(layout.library))
    command = (executor_cmd if executor_cmd is not None else cfg.executor_command())

    # 1) 组织会话（可选）：从 B猜/留痕/W回 里找语义差异、写规划预测。
    #    生芽权在这一层——但**只从差异生**（零差异零芽），执行会话依旧不能自产芽。
    org_run = None
    if org_enabled:
        runner_org = _make_runner(cfg, layout, subject_root, tick, KIND_ORG, command, llm)
        if runner_org is not None:
            decision_pre = should_run_org_session(layout, tick, gap=cfg.org_gap_ticks,
                                                  cooldown_min=cfg.org_cooldown_min)
            if decision_pre.should_run:
                from . import org_session as org_mod
                org_run = org_mod.run_org_session(
                    settings=cfg, layout=layout, tick=tick, subject_root=subject_root,
                    queue=queue, domains=domains, runner=runner_org)
                result.org = {"ran": True, "summary": org_run.summary(),
                              "findings": ["%s | %s | %s | 指针=%s"
                                           % (f.kind.value, f.obj, f.dimension,
                                              f.pointer or "（缺）")
                                           for f in org_run.findings],
                              "sprouts": org_run.sprouts,
                              "predictions": len(org_run.predictions),
                              "parse_error": org_run.parse_error,
                              "trace": org_run.trace.name if org_run.trace else ""}
                result.notes.append("组织会话：%s" % org_run.summary())
                # N58：把「组织会话此刻看到的清单」存成锚点——它下一次跑时，
                # 「本拍现实变化」块比的就是「自上次组织会话以来」（它缺席期间的全部变化）。
                # 窗口＝1 拍时，组织会话（每 3~5 拍才跑一次）天然错过其余几拍的变化。
                write_work_file(layout.subject_org_anchor,
                                json.dumps(subject_mod.subject_snapshot(subject_root, tick),
                                           ensure_ascii=False, indent=2),
                                layout.root, require_markers=("root_name",))

    # 2) B猜：默认「主体保持不变」＋ 组织会话的规划值覆盖。
    #    刻意**不把引擎自身状态**放进默认预测/观测：那些文件是引擎自己写的，
    #    每拍都会因自己的记账而变——当差异读就是自己给自己派活（实测每拍 3 根假芽）。
    caller_supplied_predictions = predictions is not None
    if caller_supplied_predictions:
        preds = list(predictions)
        planned = 0
    else:
        defaults = subject_mod.predict_subject_unchanged(subject_root, tick)
        planned = len(org_run.predictions) if org_run else 0
        preds = (subject_mod.merge_predictions(defaults, org_run.predictions)
                 if org_run else defaults)
    before_act = subject_mod.subject_readings(subject_root)
    # **动手前快照**（N55/K14）：它有两个用处——①组织会话锚点缺失时的回退窗口；
    # ②排查「那一手动作造成了什么」（动手前 vs 动手后，步 8 那份）。
    write_work_file(layout.subject_before_snapshot,
                    json.dumps(subject_mod.subject_snapshot(subject_root, tick),
                               ensure_ascii=False, indent=2),
                    layout.root, require_markers=("root_name",))
    result.predictions = {"total": len(preds), "planned": planned}

    # 3) 取题
    topic = queue.take_topic(tick)
    result.topic_sprout = topic.id if topic else None
    if topic:
        queue.mark_lead(topic, tick)
        # 把**这株芽自己带的预期**并进本拍 B猜：它是引擎当初的承诺（「该对象该维度
        # 应当成立」）。不并进来，执行者真把差异消解了也会被记成「预测外发现→打脸」
        # ——实测踩到过：题面要求在、它建好了，兑现账却记打脸。
        # 只在**默认路径**下这么做：调用方显式给了 predictions 时，那份 B猜就是全部
        # （测试与嵌入要的是「完全确定」，不该被引擎偷偷加一条）。
        if topic.expected_value and caller_supplied_predictions is False:
            preds = [p for p in preds if p.key != topic.key] + [
                Prediction(obj=topic.obj, dimension=topic.dimension,
                           expected=topic.expected_value, tick=tick,
                           evidence="芽承诺:%s" % (topic.pointer or topic.id))]
            result.predictions["topic_expectation"] = topic.expected_value
            result.predictions["total"] = len(preds)

    # 2b) **差额预期锚定**（N43）：`+N` 型的承诺（组织会话的提议、芽带的增量目标）
    #     在**动手前**的读数上锚成绝对值——锚的是「再推进 N」，不是提议那一拍的快照。
    #     放在取题之后：领到的芽自带的预期（上面那段）也走同一条锚定，不留特例。
    preds = resolve_relative_predictions(preds, before_act)
    result.predictions["total"] = len(preds)

    # 4) 动手（执行者通道；不给执行者＝机械拍，不烧认知）
    runner = _make_runner(cfg, layout, subject_root, tick, KIND_TICK, command, llm)
    call = None
    if runner is not None and topic is not None:
        from . import executor as exec_mod
        try:
            prompt = build_tick_prompt(cfg, layout, tick, topic, preds, subject_root,
                                       facts=tick_facts(layout, queue, tick, topic,
                                                        subject_root))
        except FileNotFoundError as exc:
            result.notes.append("提示词缺失，本拍未动手：%s" % exc)
        else:
            call = runner(prompt)
            exec_mod.record_executor_run(layout, call)
            exec_mod.write_trace(layout, call, prompt, subject_root)
            result.executor = {"label": call.label(), "rc": call.rc, "ok": call.ok,
                               "timed_out": call.timed_out, "usage": call.usage,
                               "trace": "%s-%05d.md" % (call.kind, call.tick)}
            result.notes.append("执行者：%s" % call.label())
            result.executor_state = "ran"
            # M3①：**留痕命中 → 记为已用**——`last_used_tick` 的真实更新方。
            # 此前它只在创建那一拍写一次，此后没有任何更新方 →「闲置 ≥20 拍」永久为真
            # （N48-1：一条永真的提醒）。只扫**执行者输出**：题面里点着对象名，
            # 把提示词也算进来就成了自证（任何被问过的条目都会立刻「已用」）。
            usage_rows = sprout_sources.library_usage_updates(
                lib_entries, call.output, tick,
                "留痕:traces/%s-%05d.md" % (call.kind, call.tick))
            for row in usage_rows:
                append_jsonl(layout.library, row, layout.root)
                entry = lib_entries.get(row["name"])
                if entry is not None:               # 同一拍内后续判据读到最新状态
                    entry["last_used_tick"] = max(int(entry.get("last_used_tick") or 0),
                                                  tick)
            if usage_rows:
                names = [row["name"] for row in usage_rows]
                result.library["consumed_this_tick"] = names
                result.notes.append("能力库消费（留痕命中）：%s" % "、".join(names))
    elif runner is not None:
        result.executor_state = "no_ticket"
        result.notes.append("无芽可领：本拍未调执行者（不硬造活干）")

    # 5) W回：**动手之后**再读现实（动手前读的现实证明不了动手的效果）。
    #    与预测对称：默认只读**主体**（引擎自身状态由园丁看护，不进对账）。
    if observations is not None:
        obs = list(observations)
    else:
        obs = subject_mod.observe_subject(subject_root)
        # M7：**定键补观测**——预测里出现过的键若被观测名额挤出去，补一条（只读这些键）。
        # 不补的话，新增文件会把边界文件挤出观测面 → 它被记成「预测未执行」（它其实存在）。
        obs = augment_observations(obs, preds, subject_root)
    diffs = reconcile(preds, obs, tick)

    # 待补指针超时（T4/A6）：差异账里 `pending_pointer=True` 的条目超过宽限拍数
    # → 生成「指针缺失」差异并**照样产芽**（机制正本：超时未补＝照样产芽）。
    # 此前 `reconcile.pending_pointer()` 只有实现没有调用方——待补指针只登记、永不处理。
    # 判据（具体状态）：条目 `tick` 距今 ≥ 宽限拍数，且该 (对象, 维度) 尚未产出过
    # `pointer_missing` 差异（去重：同一待补条目不重复产）。
    pointer_timeout_keys: set[tuple[str, str]] = set()
    pending_rows = [r for r in read_jsonl(layout.diff_ledger) if r.get("pending_pointer")]
    done_keys = {(r.get("obj"), r.get("dimension"))
                 for r in read_jsonl(layout.diff_ledger) if r.get("pointer_missing")}
    pp_preds = [Prediction(obj=str(r.get("obj", "")),
                           dimension=str(r.get("dimension", "")),
                           expected=r.get("expected", ""), tick=r.get("tick"),
                           evidence="")
                for r in pending_rows
                if (r.get("obj"), r.get("dimension")) not in done_keys]
    for d in pending_pointer(pp_preds, tick):
        # 「指针缺失」差异的指针＝超时这一机械事实本身（无指针不成芽的纪律不变）
        fixed = replace(d, evidence="待补指针超时@拍%d" % d.tick)
        pointer_timeout_keys.add((fixed.obj, fixed.dimension))
        diffs.append(fixed)
        result.notes.append("待补指针超时（指针缺失）产芽：%s×%s" % (fixed.obj, fixed.dimension))

    # 6) 差异 → 域饱和闸 → 生芽；差异**全部入账**（被吸收的也记，事实不许隐藏）
    # 哪些键的变化是**本拍动作自己造成的**：动手前后各读一次主体，差值即动作的直接后果。
    # 这些差异记账、进报告——但**不派芽**：它们已经被那一手动作消解了，
    # 派回去就是让执行者去「处理自己刚造成的结果」（实测：它只能拒绝，白烧一轮）。
    act_caused = set()
    after_act = {}
    if call is not None:
        after_act = subject_mod.subject_readings(subject_root)
        act_caused = {k for k, v in after_act.items() if before_act.get(k) != v}
        act_caused |= {k for k in before_act if k not in after_act}
    spawnable = [d for d in diffs if d.key not in act_caused]

    # 已耗尽的芽（连领满上限且非长任务，永不再被领）＝域占用的「无人认领」信号：
    # 域饱和闸据此释放僵尸占用（N41 死锁修复 K1——存在性维度不再靠「产出新量」解冻）。
    exhausted_ids = {s.id for s in queue.sprouts
                     if not s.long_task and s.leads >= queue.lead_limit}
    gate = domains.gate(spawnable, tick, exhausted_sprout_ids=exhausted_ids)
    absorbed_keys = {(d.obj, d.dimension, d.actual) for d in gate.absorbed}
    for d in diffs:
        record = d.as_record()
        record["source"] = SOURCE_MECHANICAL
        if d.key in act_caused:
            record["act_caused"] = True
        if (d.obj, d.dimension, d.actual) in absorbed_keys:
            record["absorbed_by_domain"] = True
        if d.key in pointer_timeout_keys:
            record["source"] = "pointer-timeout"
            record["pointer_missing"] = True
        append_jsonl(layout.diff_ledger, record, layout.root)
    result.diffs = diffs
    result.act_caused = sorted("%s×%s" % k for k in act_caused)

    # 成熟链：本拍被证实（预测内对）的对象 +1 步（**同拍最多 +1**）。
    # 逐**对象**去重再推进：一个对象在同一拍可能有多条被证实的差异（例如主体的
    # 存在性 + 字节数），逐条推进会让它一拍 +2——那正是「同拍最多 +1」要挡的事。
    steps = maturity_of(layout)
    capped_now, advanced = [], []
    for d in diffs:
        if d.kind != DiffKind.OK or d.obj in advanced:
            continue
        advanced.append(d.obj)
        _, hit_cap = record_maturity(layout, d.obj, tick, steps)
        if hit_cap:
            capped_now.append(d.obj)

    # 能力库**写入方**（T3/A4）：对象本拍封顶 → 写一条「可复用认知」。
    # 此前 `library.jsonl` 没有任何写入方 → 芽源③（能力库未用）是死路径，永不产芽。
    # 语义：封顶＝已固化（同一类输入不再烧认知）→ 值得拿到别域验证；此后若连续
    # `LIBRARY_IDLE_TICKS` 拍未被留痕消费，`from_unused_library` 才生「为何未用」的芽。
    for o in capped_now:
        append_jsonl(layout.library, {
            "name": o, "created_tick": tick, "last_used_tick": tick,
            "source": "maturity-cap",
        }, layout.root)

    new = sprout_sources.from_diffs(gate.kept, tick)
    # **既生对象集合**（M1）＝活跃 ∪ 冻结里已有它的芽（「同对象同维度只有一根芽，挂起≠死亡」）；
    # M4：某对象最近一根芽也已冻结满 `frozen_requestion_ticks` 拍且没被点亮 → 不再拦它。
    # 此前只扫活跃队列：被挤出的同一对象下一拍又被当「没生过」重新立芽——实测每拍 ~36 根，
    # 把上限 50 的队列占满、主芽源（差异对账）自 tick 189 起零取题（N48 的真凶）。
    known = sorted(queue.known_objects(tick, cfg.frozen_requestion_ticks))
    new += sprout_sources.from_maturity_cap(
        [{"obj": o, "step": MATURITY_CAP, "tick": tick} for o in capped_now], tick,
        known_objects=known, start_seq=len(new) + 1)
    # M3②：「本拍用过」这道闸改读**执行者留痕输出**（最近 `TRACE_GATE_FILES` 份），
    # 不再读差异账的 `note`（实测那串文本总长 19 个字符，闸从不生效）。
    liuhen = recent_trace_output(layout)
    new += sprout_sources.from_unused_library(
        read_jsonl(layout.library), liuhen, tick,
        known_objects=known + [s.obj for s in new], start_seq=len(new) + 1)

    for s in new:
        action, evicted = queue.add(s, tick)
        if s.origin.value == "差异对账":
            value = value_at_freeze(gate.kept, s.obj, s.dimension)
            if value != "":
                from .domain_saturation import domain_key as _dkey, encode as _dencode
                domains.claim(s.obj, s.dimension, s.id, value, tick, s.pointer,
                              absorbed=gate.absorbed_by_key.get(
                                  _dencode(*_dkey(s.obj, s.dimension)), 0))
        result.new_sprouts.append("%s(%s)" % (s.id, action))
        if probe:
            result.notes.append("芽源=%s 对象=%s 维度=%s 动作=%s"
                                % (s.origin.value, s.obj, s.dimension, action))
        if evicted is not None and probe:
            result.notes.append("队列超限 → 冻结：%s" % evicted.id)

    # 6b) 能力库提醒的**出口**（M2 结案／M3 消费退场）：一个提醒要么被消费、要么被结案，
    #     两条出口都让它在队的芽退场（只移动进冻结区）——「可用性」读不到兑现，
    #     没有出口它就是一条永真、可无限重生的提醒（N48 的根）。
    result.library.update(exit_library_reminders(layout, queue, lib_entries, tick,
                                                 cfg.lead_limit))
    if result.library.get("closed"):
        result.notes.append("能力库结案 %d 条：%s"
                            % (len(result.library["closed"]),
                               "、".join(result.library["closed"][:6])))
    if result.library.get("retired_by_close") or result.library.get("retired_by_consumption"):
        result.notes.append("能力库在队芽退场：结案 %d 根／消费 %d 根"
                            % (len(result.library.get("retired_by_close") or []),
                               len(result.library.get("retired_by_consumption") or [])))

    # 域占用同步（芽被消解 / 已不在队列 / 持有者已耗尽 → 释放该域，允许再立一根）。
    # exhausted_ids 同上：存量僵尸占用（持有者耗尽）在此自愈，不删任何文件。
    released = domains.sync([s.id for s in queue.sprouts + queue.frozen],
                            [(d.obj, d.dimension) for d in diffs if d.kind == DiffKind.OK],
                            tick, exhausted_sprout_ids=exhausted_ids)
    result.domain = {"占用": len(domains.claims), "本拍吸收": len(gate.absorbed),
                     "本拍放行": len(gate.kept), "本拍释放": released}
    domains.save(layout)

    # 7) 兑现判定（本拍领过的芽）＋ 账
    if topic is not None:
        # 可对账键集＝本拍 W回 **实际读到的**那些 (对象, 维度)
        # （默认路径下就是主体读数；调用方显式给观测时就是显式那几个）。
        outcome = evaluate_outcome(topic, diffs, tick, sampled=call is not None,
                                   observable_keys=[o.key for o in obs])
        append_jsonl(layout.outcome_ledger, outcome.as_record(), layout.root)
        result.outcomes.append(outcome)

    # 7b) 冻结区重看（T4/A5）：每 `frozen_review_every` 拍给冻结芽「重新点亮」的机会。
    #     此前该配置项无人调用——冻结区一旦被挤满就永不重看。
    if tick % cfg.frozen_review_every == 0 and queue.frozen:
        for note in queue.review_frozen(diffs, tick):
            result.notes.append(note)

    queue.save(layout.sprouts, layout.frozen_sprouts, layout.root)

    # 8) 主体快照（只记目录名与相对名，不落绝对路径）
    snapshot = subject_mod.subject_snapshot(subject_root, tick)
    result.subject = {k: snapshot[k] for k in ("root_name", "exists", "file_count",
                                              "total_bytes")}
    write_work_file(layout.subject_snapshot,
                    json.dumps(snapshot, ensure_ascii=False, indent=2),
                    layout.root, require_markers=("root_name",))

    report = write_reconcile_report(
        layout, result,
        known_objects=queue.known_objects(tick, cfg.frozen_requestion_ticks))
    result.notes.append("对账报告：%s" % report.name)

    # 组织段到期提示：**拍循环自己查判据**，不把「该看语义层了」留给外部调度器。
    # 上一代的 P0 根因之一就是「语义判断段没有调度入口」——诊断产出后没人回灌、就地过期。
    decision = should_run_org_session(layout, tick, gap=cfg.org_gap_ticks,
                                      cooldown_min=cfg.org_cooldown_min)
    result.org_decision = decision.as_dict()
    write_org_due(layout, result, decision)

    result.rc = 0
    record_tick_result(layout, result.rc, tick,
                       executor_rc=(call.rc if call is not None else None),
                       no_ticket=result.executor_state == "no_ticket")
    return result
