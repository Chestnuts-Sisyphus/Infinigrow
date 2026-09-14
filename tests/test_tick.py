# -*- coding: utf-8 -*-
"""拍循环测试：心跳、互斥、报告拍号、成熟链 +1 护栏、封顶生芽、端到端空仓跑。"""
import json
from dataclasses import replace

import pytest

from infinigrow.core.paths import resolve_state
from infinigrow.core.config import load_settings
from infinigrow.engine.model import Observation, Prediction
from infinigrow.engine.tick import (LOCK_STALE_SECONDS, TickHeartbeatError, acquire_lock,
                                    advance_maturity, record_tick_result, release_lock,
                                    run_tick)


def _settings(tmp_path, repo_root):
    return load_settings(env={}, state_root=str(tmp_path / "state"), repo_root=str(repo_root))


def test_run_tick_creates_state_and_increments(tmp_path, settings):
    first = run_tick(settings=settings)
    second = run_tick(settings=settings)
    assert (first.tick, second.tick) == (1, 2)
    assert first.rc == 0
    layout = resolve_state(settings.state_root, settings.repo_root)
    assert layout.tick_status.is_file()
    assert json.loads(layout.tick_status.read_text(encoding="utf-8"))["tick"] == 2


def test_heartbeat_counts_failures_and_is_loud_on_write_error(tmp_path, settings):
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    assert record_tick_result(layout, 1, tick=1) == 1
    assert record_tick_result(layout, 1, tick=2) == 2
    assert record_tick_result(layout, 0, tick=3) == 0
    # 写不进去必须响亮（不能静默：园丁的断流判据靠它）。
    # 造法：把状态根指到一个**已存在的同名文件**上——目录建不出来，写盘必失败。
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")
    broken = replace(layout, root=blocker, tick_status=blocker / "tick_status.json")
    with pytest.raises(TickHeartbeatError):
        record_tick_result(broken, 0, tick=4)


def test_report_filename_carries_tick_number(tmp_path, settings):
    run_tick(settings=settings)
    run_tick(settings=settings)
    layout = resolve_state(settings.state_root, settings.repo_root)
    names = sorted(p.name for p in layout.reconcile_dir.glob("reconcile-*.md"))
    assert names == ["reconcile-00001.md", "reconcile-00002.md"]     # 同名不会互相覆盖


def test_lock_serialises_sessions(tmp_path, settings):
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    first = acquire_lock(layout, tick=1)
    assert first is not None
    assert acquire_lock(layout, tick=1) is None                     # 第二个会话拿不到
    release_lock(first)
    assert acquire_lock(layout, tick=2) is not None                 # 释放后可再拿


def test_stale_lock_cleared(tmp_path, settings):
    import os
    import time
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    lock = acquire_lock(layout, tick=1)
    old = time.time() - (LOCK_STALE_SECONDS + 10)
    os.utime(lock, (old, old))
    assert acquire_lock(layout, tick=2) is not None                 # 陈旧锁＝死锁，自动清


def test_tick_skips_when_locked(tmp_path, settings):
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    held = acquire_lock(layout, tick=1)
    try:
        result = run_tick(settings=settings)
        assert result.skipped is True and result.rc == 0            # 幂等跳过，不报错
    finally:
        release_lock(held)


def test_maturity_step_advances_at_most_one_per_tick():
    assert advance_maturity(0) == 1
    assert advance_maturity(3) == 4
    assert advance_maturity(4) == 4          # 封顶即止，不会跳到 5
    with pytest.raises(ValueError):
        advance_maturity(-1)


def test_maturity_never_jumps_two_in_one_tick(tmp_path, settings):
    run_tick(settings=settings)
    run_tick(settings=settings)
    layout = resolve_state(settings.state_root, settings.repo_root)
    steps: dict[str, list[int]] = {}
    for line in layout.maturity_chain.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        steps.setdefault(rec["obj"], []).append(rec["step"])
    for obj, seq in steps.items():
        for a, b in zip(seq, seq[1:], strict=False):
            assert b - a <= 1, "对象 %s 出现单拍连跳：%s" % (obj, seq)   # T11 护栏


def test_cap_produces_application_sprout(tmp_path, settings):
    """对象爬到第 4 步的那一拍，必须出现「开应用面」芽（T10-① 真机判据）。"""
    for _ in range(5):
        run_tick(settings=settings)
    layout = resolve_state(settings.state_root, settings.repo_root)
    origins = set()
    for line in layout.sprouts.read_text(encoding="utf-8").splitlines():
        origins.add(json.loads(line)["origin"])
    assert "成熟链封顶" in origins
    assert "差异对账" in origins


def test_tick_uses_supplied_predictions_and_observations(tmp_path, settings):
    """给出显式 B猜/W回：完全确定性的路径（CI 与复跑用）。"""
    result = run_tick(settings=settings,
                      predictions=[Prediction("X", "大小", "10", tick=1, evidence="p1")],
                      observations=[Observation("X", "大小", "20", "文件:x")])
    assert result.diff_summary["by_kind"] == {"预测内错": 1}
    assert len(result.new_sprouts) == 1


def test_zero_diff_produces_no_sprout(tmp_path, settings):
    """零差异零芽：完全一致的预测与观测 → 一根芽都不生。"""
    result = run_tick(settings=settings,
                      predictions=[Prediction("X", "大小", "10", tick=1, evidence="p1")],
                      observations=[Observation("X", "大小", "10", "文件:x")])
    assert result.diff_summary["by_kind"] == {"预测内对": 1}
    assert result.new_sprouts == []


def test_no_self_sprout_api_exists():
    """结构保证：引擎里**没有**「执行会话登记新芽」的入口（T9 的实现层证据）。"""
    import infinigrow.engine.tick as tick_mod
    exported = vars(tick_mod)
    forbidden = [n for n in exported if "自造" in n or "candidate_sprout" in n
                 or "dispatch_sprout" in n]
    assert forbidden == []
