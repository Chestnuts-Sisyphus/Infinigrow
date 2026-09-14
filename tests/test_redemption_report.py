# -*- coding: utf-8 -*-
"""兑现率诚实呈现测试（T11/G6）：**无样本** ≠ 「0＝差」。

验收判据（可复跑）：两态各有测试——
  1. 没有执行者动过手 → 报告写「无样本」，并且**不出现**兑现率数字；
  2. 有执行者动过手 → 给真实兑现率与分桶，且**非样本行不进分母**。
"""
from __future__ import annotations

import json

from infinigrow.core.config import load_settings
from infinigrow.core.paths import REPO_ROOT, resolve_state
from infinigrow.engine.model import Observation, Prediction
from infinigrow.engine.reconcile import redemption_report, sampled
from infinigrow.engine.tick import run_tick


def _settings(tmp_path, subject=None):
    return load_settings(env={}, state_root=str(tmp_path / "state"),
                         repo_root=str(REPO_ROOT),
                         subject_root=str(subject or (tmp_path / "subject")))


def test_no_sample_is_not_zero():
    report = redemption_report([])
    assert report["判定"] == "无样本" and report["兑现率"] is None
    assert report["样本数"] == 0 and report["总行数"] == 0
    assert "不可计算" in report["说明"] and "不是 0" in report["说明"]


def test_mechanical_only_rows_are_not_samples(tmp_path):
    """机械拍的「打脸」行不算样本（那时候根本没有手在动）。"""
    rows = [{"redeemed": False, "sample": False, "sprout_id": "sp1-001-x",
             "predicted_edge": "判读", "actual_edge": None}]
    report = redemption_report(rows)
    assert report["判定"] == "无样本" and report["总行数"] == 1 and report["样本数"] == 0


def test_legacy_rows_without_the_field_are_not_samples():
    """v2.0 及更早的行没有 `sample` 字段 → 不当样本（那时候没有执行者通道）。"""
    assert sampled({"redeemed": True}) is False
    assert sampled({"redeemed": True, "sample": True}) is True
    assert sampled({"redeemed": True, "sample": "yes"}) is False
    assert redemption_report([{"redeemed": True}])["判定"] == "无样本"


def test_real_sample_gives_rate_and_buckets():
    rows = [
        {"redeemed": True, "sample": True, "sprout_id": "sp1-001-a",
         "predicted_edge": "判读", "actual_edge": "判读"},
        {"redeemed": False, "sample": True, "sprout_id": "sp2-002-b",
         "predicted_edge": "行动", "actual_edge": None},
        {"redeemed": False, "sample": False, "sprout_id": "sp3-003-c",
         "predicted_edge": "行动", "actual_edge": None},          # 不进分母
    ]
    report = redemption_report(rows)
    assert report["判定"] == "有样本" and report["样本数"] == 2
    assert report["兑现率"] == 0.5
    assert report["总行数"] == 3
    assert "非样本已排除" in report["说明"]


def test_tick_writes_sample_flag_accordingly(tmp_path):
    """真机两态：没有执行者的那拍写 sample=false；接上执行者后写 sample=true。"""
    subject = tmp_path / "subject"
    subject.mkdir()
    (subject / "notes.md").write_text("x", encoding="utf-8")
    settings = _settings(tmp_path, subject)
    preds = [Prediction("X", "大小", "1", tick=1, evidence="p1")]
    obs = [Observation("X", "大小", "2", "文件:x")]
    run_tick(settings=settings, tick=1, predictions=preds, observations=obs)   # 造出芽
    run_tick(settings=settings, tick=2, predictions=preds, observations=obs)   # 无执行者领题
    run_tick(settings=settings, tick=3, predictions=preds, observations=obs,
             llm=lambda prompt: "假执行者：不动手")                               # 有执行者
    layout = resolve_state(settings.state_root, settings.repo_root)
    rows = [json.loads(line) for line in
            layout.outcome_ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [r["sample"] for r in rows] == [False, True]
    report = redemption_report(rows)
    assert report["判定"] == "有样本" and report["样本数"] == 1 and report["总行数"] == 2


def test_report_renders_无样本_instead_of_zero(tmp_path):
    """对账报告里必须写「无样本」，不许写成 0 或「差」。"""
    subject = tmp_path / "subject"
    subject.mkdir()
    settings = _settings(tmp_path, subject)
    run_tick(settings=settings, tick=1,
             predictions=[Prediction("X", "大小", "1", tick=1, evidence="p1")],
             observations=[Observation("X", "大小", "2", "文件:x")])
    layout = resolve_state(settings.state_root, settings.repo_root)
    text = (layout.reconcile_dir / "reconcile-00001.md").read_text(encoding="utf-8")
    assert "判定：**无样本**" in text
    assert "不可计算" in text
    assert "兑现率：0" not in text
