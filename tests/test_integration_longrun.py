# -*- coding: utf-8 -*-
"""长跑集成测试：连跑多拍，验证**队列纪律与报告完整性在时间维度上成立**。

单拍测试证明不了的事，这里证明：

- 队列真的会在上限处**封顶并冻结**（不是「理论上会」）——这正是「原地打转」的刹车；
- 对账报告**拍号无缺口**（T11 的验收判据：连跑多拍，工作目录报告拍号无缺口）；
- 成熟链**没有单拍连跳**（跑长一点也守得住）；
- 心跳拍号与报告拍号一致（失败可见的前提）。
"""
from __future__ import annotations

import json

from infinigrow.core.config import load_settings
from infinigrow.core.paths import REPO_ROOT, resolve_state
from infinigrow.engine.model import Observation, Prediction
from infinigrow.engine.tick import run_tick


def _settings(tmp_path, state="state"):
    return load_settings(env={}, state_root=str(tmp_path / state), repo_root=str(REPO_ROOT))


def test_reports_have_no_tick_gaps_over_60_ticks(tmp_path):
    """连跑 60 拍：报告名带拍号，拍号**一个不缺口**（同秒覆盖病的机械化判据）。"""
    settings = _settings(tmp_path)
    for _ in range(60):
        assert run_tick(settings=settings).rc == 0
    layout = resolve_state(settings.state_root, settings.repo_root)
    names = sorted(p.name for p in layout.reconcile_dir.glob("reconcile-*.md"))
    assert names == ["reconcile-%05d.md" % i for i in range(1, 61)]
    status = json.loads(layout.tick_status.read_text(encoding="utf-8"))
    assert status["tick"] == 60 and status["consecutive_failures"] == 0


def test_queue_caps_and_freezes_under_pressure(tmp_path):
    """压力下队列封顶并冻结：每拍 10 个**互不相同**的对象（模拟「差异源源不断」）。"""
    settings = _settings(tmp_path, "pressure")
    for tick in range(1, 7):                       # 6 拍 × 10 根 = 60 根，上限 50
        preds, obs = [], []
        for j in range(10):
            obj = "X%02d-%02d" % (tick, j)
            preds.append(Prediction(obj, "大小", "1", tick=tick, evidence="p:%s" % obj))
            obs.append(Observation(obj, "大小", "2", "文件:%s" % obj))
        result = run_tick(settings=settings, tick=tick, predictions=preds, observations=obs)
        assert result.diff_summary["by_kind"] == {"预测内错": 10}    # 每拍 10 差异 → 10 芽

    layout = resolve_state(settings.state_root, settings.repo_root)
    active = [json.loads(line) for line in
              layout.sprouts.read_text(encoding="utf-8").splitlines() if line.strip()]
    frozen = [json.loads(line) for line in
              layout.frozen_sprouts.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(active) == settings.queue_cap == 50
    assert len(frozen) == 10                                     # 只动队列，账本全留
    # 账本一行不少：6 拍 × 10 条差异全部在账上（冻结/顶替都不清账）
    diff_lines = [line for line in layout.diff_ledger.read_text(encoding="utf-8").splitlines()
                  if line.strip()]
    assert len(diff_lines) == 60


def test_maturity_never_jumps_over_long_run(tmp_path):
    settings = _settings(tmp_path, "longrun")
    for _ in range(25):
        run_tick(settings=settings)
    layout = resolve_state(settings.state_root, settings.repo_root)
    steps: dict[str, list[int]] = {}
    for line in layout.maturity_chain.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        steps.setdefault(rec["obj"], []).append(rec["step"])
    assert steps, "长跑后成熟链应有记录"
    for obj, seq in steps.items():
        assert seq == sorted(seq), "成熟链倒退：%s" % obj
        for a, b in zip(seq, seq[1:], strict=False):
            assert b - a <= 1, "对象 %s 单拍连跳：%s" % (obj, seq)
        assert max(seq) <= 4, "成熟链越界：%s" % obj


def test_no_duplicate_object_dimension_in_queue(tmp_path):
    """同对象同维度＝一根芽：连跑 30 拍后队列里不许出现重复键（原地打转的病根）。"""
    settings = _settings(tmp_path, "dedupe")
    for tick in range(1, 31):
        preds = [Prediction("SAME", "字节数", "1", tick=tick, evidence="p")]
        obs = [Observation("SAME", "字节数", str(tick), "文件:x")]
        run_tick(settings=settings, tick=tick, predictions=preds, observations=obs)
    layout = resolve_state(settings.state_root, settings.repo_root)
    keys = [(json.loads(line)["obj"], json.loads(line)["dimension"]) for line in
            layout.sprouts.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(keys) == len(set(keys)) == 1
