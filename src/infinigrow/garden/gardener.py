# -*- coding: utf-8 -*-
"""机械园丁（零 token，免疫系统）。

看护四件事：**死锁**（陈旧锁）、**断流**（机械时间戳）、**失败升级**（拍失败与
**执行者失败分开计**）、**账本体检 ＋ 轮转**（只移动不删，保语义）。

为什么执行者失败要单独有一条旗：机械拍跑得成、执行者起不来，是两种病。
上一代最贵的教训是「静默失败」——环境坏了、通道坏了，账上什么也看不出来。
"""
from __future__ import annotations

import datetime as _dt
import time
from dataclasses import dataclass, field
from typing import Optional

from ..core.config import Settings, load_settings
from ..core.paths import StateLayout, guard, resolve_state
from ..engine.tick import LOCK_STALE_SECONDS, read_tick_status
from ..ledger.rotation import rotate_all
from ..ledger.store import ledger_stats, write_work_file

#: 断流阈值（小时）：最后一拍超过这么久没更新 → 致命旗
STALE_HOURS = 12
#: 连续失败升级阈值（拍）
FAIL_ESCALATE = 3
#: 执行者连续失败升级阈值（次）——与拍失败分开，因为故障位置不同
EXECUTOR_FAIL_ESCALATE = 3
#: 状态完整性要求存在的文件
REQUIRED_FILES = ("tick_status.json",)


@dataclass
class GardenerReport:
    fatal: bool = False
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    cleared_locks: list[str] = field(default_factory=list)
    rotated: list[dict] = field(default_factory=list)
    ledger_stats: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"fatal": self.fatal, "flags": self.flags, "notes": self.notes,
                "cleared_locks": self.cleared_locks, "rotated": self.rotated,
                "ledger_stats": self.ledger_stats}


def _hours_since(stamp: str, now: Optional[_dt.datetime] = None) -> Optional[float]:
    """机械时间戳差：解析失败返回 None（不猜、不用模型自述兜底）。"""
    if not stamp:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            t = _dt.datetime.strptime(stamp.strip(), fmt)
        except ValueError:
            continue
        now = now or _dt.datetime.now()
        return (now - t).total_seconds() / 3600.0
    return None


def run_gardener(settings: Optional[Settings] = None,
                 state_root: Optional[str] = None,
                 now: Optional[_dt.datetime] = None,
                 write_alert: bool = True) -> GardenerReport:
    cfg = settings or load_settings(state_root=state_root)
    layout = resolve_state(cfg.state_root or state_root, cfg.repo_root, create=True)
    report = GardenerReport()

    # 1) 死锁扫描（判据＝mtime 年龄）
    if layout.locks_dir.is_dir():
        for lock in sorted(layout.locks_dir.glob("*.lock")):
            age = time.time() - lock.stat().st_mtime
            if age > LOCK_STALE_SECONDS:
                try:
                    lock.unlink()
                    report.cleared_locks.append(lock.name)
                except OSError as exc:
                    report.flags.append("锁清理失败 %s：%s" % (lock.name, exc))
    report.notes.append("死锁扫描：清理 %d 个陈旧锁" % len(report.cleared_locks))

    # 2) 断流（机械时间戳）
    status = read_tick_status(layout)
    hours = _hours_since(status.get("last_time", ""), now)
    if hours is None:
        report.notes.append("断流检查：无有效时间戳（尚未跑过拍）——不置旗")
    elif hours > STALE_HOURS:
        report.fatal = True
        report.flags.append("断流：最后一拍距今 %.1f 小时（阈值 %d）" % (hours, STALE_HOURS))
    else:
        report.notes.append("断流检查：最后一拍距今 %.1f 小时（正常）" % hours)

    # 3) 连续失败升级（拍失败 ＋ **执行者失败**分开计：故障位置不同）
    failures = int(status.get("consecutive_failures", 0) or 0)
    if failures >= FAIL_ESCALATE:
        report.fatal = True
        report.flags.append("连续失败 %d 拍（阈值 %d）" % (failures, FAIL_ESCALATE))
    else:
        report.notes.append("失败计数：%d（正常）" % failures)

    executor_failures = int(status.get("consecutive_executor_failures", 0) or 0)
    if executor_failures >= EXECUTOR_FAIL_ESCALATE:
        report.fatal = True
        report.flags.append("执行者连续失败 %d 次（阈值 %d；最后 rc=%s）"
                            % (executor_failures, EXECUTOR_FAIL_ESCALATE,
                               status.get("last_executor_rc")))
    else:
        report.notes.append("执行者失败计数：%d（正常）" % executor_failures)

    # 4) 完整性 + 账本体检
    for name in REQUIRED_FILES:
        p = layout.root / name
        if not p.is_file():
            report.notes.append("完整性：%s 尚未生成（首次运行正常）" % name)
    for ledger in (layout.diff_ledger, layout.outcome_ledger, layout.maturity_chain,
                   layout.library):
        stats = ledger_stats(ledger)
        report.ledger_stats[ledger.name] = stats
        if stats["bad_lines"]:
            report.flags.append("账本坏行：%s 有 %d 行" % (ledger.name, stats["bad_lines"]))

    # 5) 账本轮转（只移动不删；阈值是配置项，园丁每次跑顺手做一次）
    if cfg.rotate_max_bytes > 0:
        report.rotated = rotate_all(layout, max_bytes=cfg.rotate_max_bytes,
                                    keep_tail=cfg.rotate_keep_tail)
        if report.rotated:
            report.notes.append("账本轮转：%s"
                                % "、".join("%s→%s(移 %d 行)"
                                           % (r["name"], r["archive"], r["moved"])
                                           for r in report.rotated))
        else:
            report.notes.append("账本轮转：无账本超阈值（%d 字节）"
                                % cfg.rotate_max_bytes)

    if write_alert:
        _write_alert(layout, report, status)
    return report


def _write_alert(layout: StateLayout, report: GardenerReport, status: dict) -> None:
    """把致命旗落到 `state/ALERT.md`（无致命旗＝写「正常」一行，也便于人一眼确认）。

    走 `ledger/store.write_work_file`（原子替换 ＋ 越界守卫），而不是这里自己写盘：
    人读的警报面只有一处，写盘纪律也只有一条路（静态规则 R8 守这条）。
    """
    path = layout.root / "ALERT.md"
    guard(path, layout.root)
    stamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if report.fatal:
        lines = ["# 引擎警报（%s）" % stamp, "", "**需要人看一眼**：", ""]
        lines += ["- %s" % f for f in report.flags]
    else:
        lines = ["# 引擎正常（%s）" % stamp, "", "- 无致命旗",
                 "- 最后一拍：%s" % (status.get("last_time") or "（尚未跑过）")]
    lines += ["", "## 体检明细", ""] + ["- %s" % n for n in report.notes]
    write_work_file(path, "\n".join(lines) + "\n", layout.root,
                    require_markers=("# 引擎",))
