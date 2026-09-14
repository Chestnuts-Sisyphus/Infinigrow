# -*- coding: utf-8 -*-
"""调度层：什么时候该跑 LLM 组织段/拍。判据只认「具体状态」，不认「频率高」。

**判据实现不在这里**——单一事实源是 `engine/org_trigger.py`（因为**拍循环本身必须查它**，
上一代正是因为「语义判断段没有调度入口」而让诊断就地过期）。
本模块是**对外门面**：给外部调度器（计划任务/看护脚本）用的稳定入口，
将来若判据要挪窝，外部调用方不受影响。
"""
from ..engine.org_trigger import (DEFAULT_COOLDOWN_MIN, DEFAULT_GAP_TICKS,  # noqa: F401
                                 DEFAULT_ZERO_GAP, OrgTriggerDecision, cadence_seconds,
                                 files_touched_since, org_ledger_path, record_org_session,
                                 should_run_org_session)

__all__ = [
    "OrgTriggerDecision", "should_run_org_session", "record_org_session",
    "org_ledger_path", "cadence_seconds", "files_touched_since",
    "DEFAULT_GAP_TICKS", "DEFAULT_COOLDOWN_MIN", "DEFAULT_ZERO_GAP",
]
