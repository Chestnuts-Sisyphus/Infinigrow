# -*- coding: utf-8 -*-
"""拍循环：一拍 = 取题 → 动手 → 对账 → 生芽 → 记账（＋心跳）。

三条 v1 现场换来的纪律，在 v2 里是**结构保证**而不是注释约定：

1. **执行会话不自产芽**：本模块**没有任何**「登记新芽候选」的入口；芽只从
   `sprout_sources`（差异／封顶／未用）来，而这三源全部读账本。想加自造芽，
   得先改这个模块——那就不是「顺手」能发生的事了。
2. **报告文件名带拍号 + 会话互斥**：v1 出过「同秒覆盖丢报告」「两个会话同时跑把
   成熟链连加两级」。这里：报告名 `reconcile-<拍号>.md`（同拍重的写＝同一个文件，
   不会互相盖），并用 `locks/` 下的独占锁串行化；拿不到锁＝本拍跳过（幂等，不报错）。
3. **成熟链同拍最多 +1**：步进函数显式写死 `+1` 上限，并把「单拍跳到顶」当异常拒绝。
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Sequence

from ..core.config import Settings, load_settings
from ..core.encoding import harden_stdio
from ..core.paths import StateLayout, guard, resolve_state
from ..ledger.store import LedgerError, append_jsonl, read_jsonl, write_work_file
from . import sprout_sources
from .model import (Diff, DiffKind, MATURITY_CAP, Observation, OutcomeRecord,
                    Prediction, Sprout)
from .org_trigger import should_run_org_session
from .reconcile import diff_summary, reconcile
from .sprout_queue import SproutQueue

TICK_STATUS_MARK = "consecutive_failures"
LOCK_STALE_SECONDS = 900          # 15 分钟＝一拍超时上限量级；超过即视为死锁可清
ORG_DUE_FILE = "org-due.json"     # 组织段到期提示（工作文件，每拍覆写）


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
    new_sprouts: list[str] = field(default_factory=list)
    outcomes: list[OutcomeRecord] = field(default_factory=list)
    org_decision: Optional[dict] = None      # 本拍算出的「该不该跑组织会话」
    notes: list[str] = field(default_factory=list)

    @property
    def diff_summary(self) -> dict:
        return diff_summary(self.diffs)

    def as_dict(self) -> dict:
        return {
            "tick": self.tick, "rc": self.rc, "skipped": self.skipped,
            "topic_sprout": self.topic_sprout,
            "diffs": self.diff_summary,
            "new_sprouts": self.new_sprouts,
            "outcomes": [o.as_record() for o in self.outcomes],
            "org_decision": self.org_decision,
            "notes": self.notes,
        }


# --------------------------------------------------------------------- 心跳
def read_tick_status(layout: StateLayout) -> dict:
    if not layout.tick_status.is_file():
        return {"consecutive_failures": 0, "last_rc": 0, "last_time": "", "last_note": "",
                "tick": 0}
    try:
        return json.loads(layout.tick_status.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        # 心跳文件坏掉＝园丁的断流判据失效；不静默吞，返回带标记的兜底并让调用方看见
        return {"consecutive_failures": 0, "last_rc": 0, "last_time": "", "tick": 0,
                "last_note": "心跳文件不可解析：%r" % exc}


def record_tick_result(layout: StateLayout, rc: int, tick: int, note: str = "") -> int:
    """落心跳：rc==0 归零，否则连续失败 +1。写不进去抛 `TickHeartbeatError`。

    心跳里记**引擎身份**（版本 ＋ 提交号）：定规是「引擎必须是最新版才准运转」，
    那么每一拍都必须能回答「这是哪个版本的引擎跑的」——否则升级之后，
    历史读数属于哪一版就说不清了（账本只记 tick 数字是不够的）。
    """
    from ..core.build_info import engine_identity
    status = read_tick_status(layout)
    failures = 0 if rc == 0 else int(status.get("consecutive_failures", 0)) + 1
    ident = engine_identity()
    payload = {
        TICK_STATUS_MARK: failures,
        "last_rc": rc,
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
    """独占锁：拿不到返回 None（本拍跳过）。陈旧锁（超过 `LOCK_STALE_SECONDS`）自动清。"""
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
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None                              # 竞态：另一个会话刚拿到 → 本拍跳过
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("tick=%d pid=%d\n" % (tick, os.getpid()))
    return lock


def release_lock(lock: Optional[Path]) -> None:
    if lock is not None and lock.exists():
        try:
            lock.unlink()
        except OSError:
            pass


# --------------------------------------------------------------------- 机械侧
def observe_state(layout: StateLayout) -> list[Observation]:
    """机械观测：把状态目录里的**可查事实**读成 W回（不执行任何命令）。"""
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
    """默认 B猜：本拍**不动**的对象保持不变（可对账的承诺，不是心情）。"""
    preds = []
    for path in (layout.tick_status, layout.outcome_ledger, layout.maturity_chain):
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


def evaluate_outcome(sprout: Sprout, diffs: Sequence[Diff], tick: int) -> OutcomeRecord:
    """领做后的兑现判定（机械）：该对象该维度的差异真消＝兑现；仍错＝打脸。"""
    mine = [d for d in diffs if d.key == sprout.key]
    redeemed = any(d.kind == DiffKind.OK for d in mine)
    actual = sprout.predicted_edge if redeemed else None
    return OutcomeRecord(sprout_id=sprout.id, predicted_edge=sprout.predicted_edge,
                         actual_edge=actual, redeemed=redeemed,
                         pointer=sprout.pointer, tick=tick)


def write_reconcile_report(layout: StateLayout, result: TickResult) -> Path:
    """写对账报告：**文件名带拍号**（同拍重跑＝同一个文件，不会互相覆盖）。"""
    from ..core.build_info import engine_label
    path = layout.reconcile_dir / ("reconcile-%05d.md" % result.tick)
    guard(path, layout.root)
    lines = ["# 对账报告 · 拍 %d" % result.tick, "",
             "- 引擎：%s" % engine_label(),
             "- 本拍取题：%s" % (result.topic_sprout or "（无芽可领）"),
             "- 差异总览：%s" % json.dumps(result.diff_summary, ensure_ascii=False), ""]
    for d in result.diffs:
        lines.append("- `%s` | %s | %s | 预期=%s | 实际=%s | 指针=%s"
                     % (d.kind.value, d.obj, d.dimension, d.expected, d.actual,
                        d.evidence or "（缺）"))
    if result.new_sprouts:
        lines += ["", "## 本拍新生芽", ""] + ["- `%s`" % s for s in result.new_sprouts]
    if result.outcomes:
        lines += ["", "## 兑现判定", ""] + [
            "- `%s` 预测边=%s 实际边=%s → %s"
            % (o.sprout_id, o.predicted_edge.value if o.predicted_edge else "无",
               o.actual_edge.value if o.actual_edge else "无",
               "兑现" if o.redeemed else "打脸") for o in result.outcomes]
    write_work_file(path, "\n".join(lines), layout.root,
                    require_markers=("# 对账报告",))
    return path


# --------------------------------------------------------------------- 主循环
def run_tick(settings: Optional[Settings] = None,
             state_root: Optional[str] = None,
             tick: Optional[int] = None,
             predictions: Optional[Sequence[Prediction]] = None,
             observations: Optional[Sequence[Observation]] = None,
             llm: Optional[Callable[[str], str]] = None,
             probe: bool = False) -> TickResult:
    """跑一拍。

    `llm=None`（默认）＝**机械拍**：零 token，只做机械观测与对账——冷启动验收、
    CI、以及「只想看机制转不转」时都用它。给了 `llm`（可调用：提示词→输出）才烧认知。

    `probe=True` 时额外把三个芽源的判定明细打进 notes（排查用，不改行为）。
    """
    harden_stdio()
    cfg = settings or load_settings(state_root=state_root)
    layout = resolve_state(cfg.state_root or state_root, cfg.repo_root, create=True)

    status = read_tick_status(layout)
    this_tick = tick if tick is not None else int(status.get("tick", 0)) + 1

    lock = acquire_lock(layout, this_tick)
    if lock is None:
        return TickResult(tick=this_tick, rc=0, skipped=True,
                          notes=["另一个会话在跑：本拍跳过（幂等，不覆盖他人产物）"])
    try:
        return _run_tick_locked(cfg, layout, this_tick, predictions, observations, llm, probe)
    finally:
        release_lock(lock)


def _run_tick_locked(cfg: Settings, layout: StateLayout, tick: int,
                     predictions, observations, llm, probe: bool) -> TickResult:
    result = TickResult(tick=tick)
    queue = SproutQueue(cap=cfg.queue_cap, lead_limit=cfg.lead_limit,
                        cold_start_ticks=cfg.cold_start_ticks)
    queue = SproutQueue.load(layout.sprouts, layout.frozen_sprouts,
                             cap=cfg.queue_cap, lead_limit=cfg.lead_limit,
                             cold_start_ticks=cfg.cold_start_ticks)

    topic = queue.take_topic(tick)
    result.topic_sprout = topic.id if topic else None
    if topic:
        queue.mark_lead(topic, tick)

    # 干活（LLM 段可选：不给 llm 就是机械拍，零 token）
    if llm is not None and topic is not None:
        prompt = _topic_prompt(topic)
        result.notes.append("LLM 段完成：%s" % ("有输出" if llm(prompt) else "空输出"))

    preds = list(predictions) if predictions is not None else predict_unchanged(layout, tick)
    obs = list(observations) if observations is not None else observe_state(layout)
    diffs = reconcile(preds, obs, tick)
    result.diffs = diffs

    # 记账：差异账（追加型，all rows，包括「预测内对」——被验证也是事实）
    for d in diffs:
        append_jsonl(layout.diff_ledger, d.as_record(), layout.root)

    # 成熟链：本拍被证实（预测内对）的对象 +1 步（同拍最多 +1）
    steps = maturity_of(layout)
    capped_now = []
    for d in diffs:
        if d.kind == DiffKind.OK:
            _, hit_cap = record_maturity(layout, d.obj, tick, steps)
            if hit_cap:
                capped_now.append(d.obj)

    # 芽源①：差异对账（N 差异 N 芽；无指针不成芽）
    new = sprout_sources.from_diffs(diffs, tick)
    # 芽源②：成熟链封顶（本拍恰好到顶的对象）
    known = [s.obj for s in queue.sprouts]
    new += sprout_sources.from_maturity_cap(
        [{"obj": o, "step": MATURITY_CAP, "tick": tick} for o in capped_now], tick,
        known_objects=known, start_seq=len(new) + 1)
    # 芽源③：能力库长期未用（读账本，判据＝具体状态：拍差 ≥ 阈值且本拍留痕未出现）
    liuhen = "\n".join(r.get("note", "") for r in read_jsonl(layout.diff_ledger)[-20:])
    new += sprout_sources.from_unused_library(
        read_jsonl(layout.library), liuhen, tick,
        known_objects=known + [s.obj for s in new], start_seq=len(new) + 1)

    for s in new:
        action, evicted = queue.add(s)
        result.new_sprouts.append("%s(%s)" % (s.id, action))
        if probe:
            result.notes.append("芽源=%s 对象=%s 维度=%s 动作=%s"
                                % (s.origin.value, s.obj, s.dimension, action))
        if evicted is not None and probe:
            result.notes.append("队列超限 → 冻结：%s" % evicted.id)

    # 兑现判定（本拍领过的芽）
    if topic is not None:
        outcome = evaluate_outcome(topic, diffs, tick)
        append_jsonl(layout.outcome_ledger, outcome.as_record(), layout.root)
        result.outcomes.append(outcome)

    queue.save(layout.sprouts, layout.frozen_sprouts, layout.root)
    report = write_reconcile_report(layout, result)
    result.notes.append("对账报告：%s" % report.name)

    # 组织段到期提示：**拍循环自己查判据**，不把「该看语义层了」留给外部调度器。
    # 上一代的 P0 根因之一就是「语义判断段没有调度入口」——诊断产出后没人回灌、就地过期。
    # 语义：这里只**提示**（写 org-due.json 并进本拍结果），不代跑 LLM 段、也不写尝试账
    # （尝试账＝「真跑过」，写了会误触 30 分钟冷却闸）。
    decision = should_run_org_session(layout, tick, gap=cfg.org_gap_ticks)
    result.org_decision = decision.as_dict()
    write_org_due(layout, result, decision)

    result.rc = 0
    record_tick_result(layout, result.rc, tick)
    return result


def write_org_due(layout: StateLayout, result: TickResult, decision) -> Path:
    """把「组织会话是否到期」落成可人读、可机读的一个小件（每拍覆写，工作文件）。"""
    path = layout.root / ORG_DUE_FILE
    guard(path, layout.root)
    lines = ["{", '  "tick": %d,' % result.tick,
             '  "should_run_org": %s,' % ("true" if decision.should_run else "false"),
             '  "reason": %s' % json.dumps(decision.reason, ensure_ascii=False),
             "}"]
    write_work_file(path, "\n".join(lines), layout.root,
                    require_markers=("should_run_org",))
    return path


def _topic_prompt(sprout: Sprout) -> str:
    """把芽拼成给执行会话的题面（题面里只含**差异本身**，不含「顺便再造根芽」这类指令）。"""
    return ("本拍题面（来源：%s）\n对象：%s\n维度：%s\n差异指针：%s\n"
            "要求：动手前先写下你对本对象的预期（B猜），动手后由对账判对错；"
            "不要登记新芽——芽由对账产出。" % (sprout.origin.value, sprout.obj,
                                          sprout.dimension, sprout.pointer))
