# -*- coding: utf-8 -*-
"""超时预算闸：单次执行者超时 × 一拍最多调用次数，必须 < 计划任务的 ExecutionTimeLimit。

为什么锁这条（M10）：Windows 计划任务用 `-ExecutionTimeLimit` 给整次运行套一个墙，超过就
**中途杀掉**——留半截留痕、账本写一半、心跳停摆，而引擎自己毫不知情。本机一度带
`IG_EXECUTOR_TIMEOUT_S=600` 跑，`600×2≈20 分钟`已经贴着 ps1 里的 30 分钟上限，这个乘积
关系此前**没有任何测试**看护。这条用配置表的**默认值**（不读环境变量，保证确定性）现算，
把「调大超时/加调用次数却没同步抬高计划任务时限」这类改动挡在提交前。
"""
from __future__ import annotations

import re
from pathlib import Path

from infinigrow.core import config
from infinigrow.engine.tick import MAX_EXECUTOR_CALLS_PER_TICK

REPO = Path(__file__).resolve().parents[1]
PS1 = REPO / "tools" / "scheduled_task.ps1"

_LIMIT_RX = re.compile(
    r"-ExecutionTimeLimit\s+\(New-TimeSpan\s+-Minutes\s+(\d+)\)")


def _exec_limit_minutes() -> int:
    m = _LIMIT_RX.search(PS1.read_text(encoding="utf-8"))
    assert m, "scheduled_task.ps1 里读不到 -ExecutionTimeLimit (New-TimeSpan -Minutes N)"
    return int(m.group(1))


def _budget_ok(timeout_s: int, limit_minutes: int) -> bool:
    return timeout_s * MAX_EXECUTOR_CALLS_PER_TICK < limit_minutes * 60


def test_default_timeout_times_call_count_fits_the_schedule():
    timeout = config._default("executor_timeout_s")
    limit = _exec_limit_minutes()
    assert _budget_ok(timeout, limit), (
        "超时预算爆表：%ds × %d 次 = %ds ≥ 计划任务时限 %d 分钟（%ds）；"
        "要么调小 executor_timeout_s / 每拍调用数，要么抬高 scheduled_task.ps1 的时限"
        % (timeout, MAX_EXECUTOR_CALLS_PER_TICK, timeout * MAX_EXECUTOR_CALLS_PER_TICK,
           limit, limit * 60))


def test_the_gate_actually_bites():
    """反证：把超时抬到吃满时限，判据必须翻红——否则这条闸是空转的。"""
    limit = _exec_limit_minutes()
    per_call_limit = limit * 60 // MAX_EXECUTOR_CALLS_PER_TICK
    assert _budget_ok(per_call_limit - 1, limit)      # 刚好塞得下
    assert not _budget_ok(per_call_limit, limit)      # 等于时限＝会被中途杀，判红


def test_call_count_is_a_small_positive_bound():
    """每拍调用次数必须是可信的小整数（tick 动手 + 组织段各一次＝2）。"""
    assert MAX_EXECUTOR_CALLS_PER_TICK == 2
