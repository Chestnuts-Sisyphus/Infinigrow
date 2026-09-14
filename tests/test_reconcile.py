# -*- coding: utf-8 -*-
"""对账协议测试：四类差异、指针强制、待补指针超时。"""
from infinigrow.engine.model import DiffKind, Observation, Prediction
from infinigrow.engine.reconcile import (POINTER_GRACE_TICKS, diff_summary, pending_pointer,
                                        rate_table, reconcile, redemption_rate)


def test_four_kinds():
    preds = [
        Prediction("A", "大小", "10", tick=1, evidence="留痕:1"),
        Prediction("B", "大小", "10", tick=1, evidence="留痕:2"),
        Prediction("C", "大小", "10", tick=1, evidence="留痕:3"),
    ]
    obs = [
        Observation("A", "大小", "10", "文件:a"),      # 预测内对
        Observation("B", "大小", "12", "文件:b"),      # 预测内错
        Observation("D", "大小", "5", "文件:d"),       # 预测外发现
    ]
    diffs = reconcile(preds, obs, tick=1)
    kinds = sorted(d.kind.value for d in diffs)
    assert kinds == sorted(["预测内对", "预测内错", "预测未执行", "预测外发现"])
    assert diff_summary(diffs)["spawning"] == 3        # 「预测内对」不产芽


def test_pointer_enforced():
    """无证据指针的差异**不成芽**（拒收≠丢弃：进待补区）。"""
    diffs = reconcile([Prediction("A", "大小", "10", tick=1, evidence="")],
                      [Observation("A", "大小", "12", "")], tick=1)
    assert len(diffs) == 1 and diffs[0].kind == DiffKind.WRONG
    assert diffs[0].spawns is False


def test_pending_pointer_after_grace():
    pred = Prediction("A", "大小", "10", tick=1, evidence="")
    assert pending_pointer([pred], tick=1 + POINTER_GRACE_TICKS - 1) == []
    late = pending_pointer([pred], tick=1 + POINTER_GRACE_TICKS)
    assert len(late) == 1 and late[0].actual == "（指针缺失）"
    assert late[0].spawns is False                      # 指针仍缺 → 交组织会话补


def test_second_reconcile_can_confirm():
    """消解后重跑对账：差异变「预测内对」→ 这是兑现判定的机械入口。"""
    obs = [Observation("A", "大小", "12", "文件:a")]
    first = reconcile([Prediction("A", "大小", "10", tick=1, evidence="p1")], obs, tick=1)
    assert first[0].kind == DiffKind.WRONG
    second = reconcile([Prediction("A", "大小", "12", tick=2, evidence="p2")], obs, tick=2)
    assert second[0].kind == DiffKind.OK


def test_redemption_rate_is_recomputed():
    records = [
        {"sprout_id": "s1", "predicted_edge": "判读", "actual_edge": "判读", "redeemed": True},
        {"sprout_id": "s1", "predicted_edge": "判读", "actual_edge": None, "redeemed": False},
    ]
    assert redemption_rate(records) == 0.5
    assert redemption_rate([]) == 0.0                    # 无样本不假装有数据
    table = rate_table(records)
    assert table["总记录"] == 2
