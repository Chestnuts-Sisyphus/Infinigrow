# -*- coding: utf-8 -*-
"""园丁测试（K3/A4）：连续「无芽可领」→ ALERT 出「不生长/空转」旗。

验收判据（可复跑）：
  1. 心跳里 `no_ticket_streak` ≥ 阈值（默认 12）→ ALERT 含「不生长」旗；
  2. 低于阈值 → 不置旗（note 里可见计数在累积）；
  3. 恢复正常（streak 归零）→ 旗平息；
  4. 与断流（时间戳）／失败（rc 计数）三条线**互不覆盖**（各自独立置旗）。
"""
from __future__ import annotations

import datetime as _dt
import json

from infinigrow.core.config import load_settings
from infinigrow.core.paths import REPO_ROOT, resolve_state
from infinigrow.garden.gardener import run_gardener


def _now() -> str:
    """当前时刻（机械来源）。夹具**不许**写死时间戳：写死会让「断流」判据随真实时间
    慢慢变红（实测：夹具写 2026-09-15 12:00，到 09-16 就成了「距今 32.5 小时」，
    一个与用例无关的断流旗把断言打红）。要测断流线就显式传一个过期时间戳。"""
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _settings(tmp_path, stall_alert_ticks=12):
    return load_settings(env={}, state_root=str(tmp_path / "state"),
                         repo_root=str(REPO_ROOT), stall_alert_ticks=stall_alert_ticks)


def _write_heartbeat(layout, streak=0, tick=100, last_time=None):
    payload = {
        "consecutive_failures": 0, "consecutive_executor_failures": 0,
        "no_ticket_streak": streak, "last_rc": 0, "last_executor_rc": None,
        "last_time": last_time or _now(), "last_note": "", "tick": tick,
        "engine_version": "2.2.4", "engine_commit": "test",
    }
    layout.tick_status.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                  encoding="utf-8")


def test_stall_above_threshold_raises_no_growth_flag(tmp_path):
    settings = _settings(tmp_path)
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    _write_heartbeat(layout, streak=12)                    # 连续 12 拍无芽可领
    report = run_gardener(settings=settings, write_alert=True)
    assert report.fatal
    assert any("不生长" in f and "空转" in f for f in report.flags)
    alert = layout.root.joinpath("ALERT.md").read_text(encoding="utf-8")
    assert "不生长" in alert and "空转" in alert


def test_stall_below_threshold_not_fatal(tmp_path):
    settings = _settings(tmp_path)
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    _write_heartbeat(layout, streak=3)                     # 才 3 拍，未达阈值
    report = run_gardener(settings=settings, write_alert=True)
    assert not report.fatal
    assert any("空转计数：3" in n for n in report.notes)
    alert = layout.root.joinpath("ALERT.md").read_text(encoding="utf-8")
    assert "引擎正常" in alert                             # 不误报


def test_stall_resets_when_growth_resumes(tmp_path):
    settings = _settings(tmp_path)
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    _write_heartbeat(layout, streak=0)                     # streak 归零＝恢复生长
    report = run_gardener(settings=settings, write_alert=True)
    assert not report.fatal
    assert any("空转计数：0" in n for n in report.notes)
    alert = layout.root.joinpath("ALERT.md").read_text(encoding="utf-8")
    assert "引擎正常" in alert


def test_stall_threshold_is_configurable(tmp_path):
    settings = _settings(tmp_path, stall_alert_ticks=4)
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    _write_heartbeat(layout, streak=4)
    report = run_gardener(settings=settings, write_alert=True)
    assert report.fatal and any("空转" in f for f in report.flags)


def test_stale_heartbeat_raises_stall_flag(tmp_path):
    """断流线（机械时间戳）单独成立：过期时间戳 → 断流旗（与空转/失败两条线独立）。

    时间戳**相对当前时刻**算（13 小时前 > 阈值 12），不写死日期——写死＝这个用例
    自己会过期（见 `_now` 的注释）。
    """
    settings = _settings(tmp_path)
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    stale = (_dt.datetime.now() - _dt.timedelta(hours=13)).strftime("%Y-%m-%d %H:%M:%S")
    _write_heartbeat(layout, streak=0, last_time=stale)     # 空转计数为 0：只有断流该置旗
    report = run_gardener(settings=settings, write_alert=True)
    assert report.fatal
    assert any("断流" in f for f in report.flags)
    assert not any("不生长" in f for f in report.flags)      # 不误报空转


def test_no_growth_and_executor_failure_are_separate_flags(tmp_path):
    """空转（无芽可领）与执行者失败是两条独立旗——不互相掩盖。"""
    settings = _settings(tmp_path)
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    payload = {
        "consecutive_failures": 0, "consecutive_executor_failures": 5,
        "no_ticket_streak": 13, "last_rc": 0, "last_executor_rc": 1,
        "last_time": _now(), "last_note": "", "tick": 100,
        "engine_version": "2.2.4", "engine_commit": "test",
    }
    layout.tick_status.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    report = run_gardener(settings=settings, write_alert=True)
    texts = " ".join(report.flags)
    assert "执行者连续失败" in texts and "不生长" in texts      # 两旗都在
