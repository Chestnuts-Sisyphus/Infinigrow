# -*- coding: utf-8 -*-
"""组织段触发判据测试：**拍循环自己必须查它**（上一代 P0 根因的回归闸）。

上一代引擎的病：语义判断段的判据/工具都写好了，但没有任何调度器调用它，
诊断报告产出后没人回灌、就地过期。这里把「拍循环查判据」做成可断言的事实。

判据一律是**具体状态**（账本条数、拍号差、待补指针数、连续零差异拍数），
没有一条是「频率高」式归纳。
"""
from __future__ import annotations

import datetime as _dt
import json

from infinigrow.core.config import load_settings
from infinigrow.core.paths import REPO_ROOT, resolve_state
from infinigrow.engine.model import Observation, Prediction
from infinigrow.engine.org_trigger import (DEFAULT_COOLDOWN_MIN, DEFAULT_GAP_TICKS,
                                           org_ledger_path, record_org_session,
                                           should_run_org_session)
from infinigrow.engine.tick import ORG_DUE_FILE, run_tick
from infinigrow.ledger.store import append_jsonl


def _settings(tmp_path, name="state"):
    return load_settings(env={}, state_root=str(tmp_path / name), repo_root=str(REPO_ROOT))


def test_first_tick_says_org_is_due_and_persists_it(tmp_path):
    """第一次跑（组织段从未跑过）→ 判据①触发，且这一判定**落在盘上**。"""
    settings = _settings(tmp_path)
    result = run_tick(settings=settings)
    assert result.org_decision is not None
    assert result.org_decision["should_run"] is True
    assert "从未跑过" in result.org_decision["reason"]

    layout = resolve_state(settings.state_root, settings.repo_root)
    due = json.loads((layout.root / ORG_DUE_FILE).read_text(encoding="utf-8"))
    assert due["should_run_org"] is True and due["tick"] == 1


def test_cooldown_blocks_after_a_real_attempt(tmp_path):
    """刚跑过组织段（机械时间戳在冷却窗内）→ 不触发：冷却闸认时间不认心情。"""
    settings = _settings(tmp_path, "cooldown")
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    record_org_session(layout, tick=1, note="手工跑过一次")
    decision = should_run_org_session(layout, tick=2)
    assert decision.should_run is False
    assert "冷却闸" in decision.reason
    assert decision.criteria["距上次拍号差"] == 1


def test_gap_criterion_fires_with_concrete_tick_difference(tmp_path):
    """空窗补跑：距上次拍号差 ≥ gap → 触发（整数比较，具体状态）。"""
    settings = _settings(tmp_path, "gap")
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    old = (_dt.datetime.now() - _dt.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    # 直接写一条「很久以前跑过」的尝试记录（含机械时间戳与拍号）
    append_jsonl(org_ledger_path(layout),
                 {"tick": 3, "time": old, "note": "历史尝试"}, layout.root)
    assert should_run_org_session(layout, tick=3 + DEFAULT_GAP_TICKS - 1).should_run is False
    fired = should_run_org_session(layout, tick=3 + DEFAULT_GAP_TICKS)
    assert fired.should_run is True and "空窗补跑" in fired.reason
    assert fired.criteria["距上次拍号差"] == DEFAULT_GAP_TICKS


def test_pending_pointer_criterion(tmp_path):
    """待补指针差异 > 0 → 触发（具体状态：条数）。

    造数要点：时间戳取「1 小时前」——**过了冷却闸（30 分钟）但拍号差仍小于 gap（5）**，
    这样才轮得到第三条判据发言。（次序是设计：冷却闸先于空窗闸，与真机行为一致。）
    """
    settings = _settings(tmp_path, "pending")
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    warm = (_dt.datetime.now() - _dt.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    append_jsonl(org_ledger_path(layout), {"tick": 9, "time": warm}, layout.root)
    append_jsonl(layout.diff_ledger,
                 {"kind": "预测内错", "obj": "X", "dimension": "大小",
                  "evidence": "", "spawns": False, "tick": 9}, layout.root)
    decision = should_run_org_session(layout, tick=10)
    assert decision.should_run is True and "待补指针" in decision.reason
    assert decision.criteria["待补指针"] == 1


def test_zero_diff_streak_criterion(tmp_path):
    """连续零差异（具体计数）≥ 阈值 → 触发：工程上「安静得可疑」是要看的信号。

    **单位要报对（N56）**：阈值数的是**差异账的行数**（一拍几十行），所以读数里
    同时给出「行数」与它覆盖的「拍数」——原先叫「连续 N 拍」却数行，报出来的
    「86 拍」其实是 86 行 ≈ 2 拍（在报数时说假话）。
    """
    settings = _settings(tmp_path, "zero")
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    warm = (_dt.datetime.now() - _dt.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    append_jsonl(org_ledger_path(layout), {"tick": 20, "time": warm}, layout.root)
    for i in range(10):
        append_jsonl(layout.diff_ledger,
                     {"kind": "预测内对", "obj": "X", "dimension": "字节数",
                      "evidence": "文件:x", "spawns": False, "tick": 21 + i}, layout.root)
    decision = should_run_org_session(layout, tick=21)
    assert decision.should_run is True and "零差异" in decision.reason
    assert decision.criteria["连续预测内对行数"] == 10
    assert decision.criteria["连续零差异拍数"] == 10        # 这 10 行来自 10 个不同拍
    assert "约 10 拍" in decision.reason


def test_decision_is_recomputed_every_tick(tmp_path):
    """每拍都重算并覆写提示件（不是「设一次就忘」）。"""
    settings = _settings(tmp_path, "recompute")
    for tick in (1, 2, 3):
        run_tick(settings=settings, tick=tick,
                 predictions=[Prediction("X", "大小", "1", tick=tick, evidence="p")],
                 observations=[Observation("X", "大小", "2", "文件:x")])
    layout = resolve_state(settings.state_root, settings.repo_root)
    due = json.loads((layout.root / ORG_DUE_FILE).read_text(encoding="utf-8"))
    assert due["tick"] == 3
    assert DEFAULT_COOLDOWN_MIN > 0        # 冷却闸存在（默认值有明确来源）
