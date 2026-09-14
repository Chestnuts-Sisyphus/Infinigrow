# -*- coding: utf-8 -*-
"""对账协议测试：四类差异、指针强制、待补指针超时。"""
from infinigrow.engine.model import DiffKind, Observation, Prediction
from infinigrow.engine.reconcile import (POINTER_GRACE_TICKS, diff_summary, pending_pointer,
                                        rate_table, reconcile, redemption_rate,
                                        redemption_report)


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


def test_cap_rows_are_listed_separately_and_excluded_from_rate():
    """T6/A7：cap*（固化边/应用面）行**单独列出**，不进兑现率分母，也不算打脸。"""
    records = [
        # 两根可对账的样本行（真兑现）
        {"sprout_id": "sp0001-001-x", "predicted_edge": "判读",
         "actual_edge": "判读", "redeemed": True, "sample": True, "verifiable": True},
        {"sprout_id": "sp0002-001-y", "predicted_edge": "行动",
         "actual_edge": "行动", "redeemed": True, "sample": True, "verifiable": True},
        # 一根 cap 行（不可对账：应用面）——不该影响兑现率
        {"sprout_id": "cap0007-001-z", "predicted_edge": "固化",
         "actual_edge": None, "redeemed": False, "sample": True, "verifiable": False},
        # 一根 cap 行但 verifiable=True（旧行默认）→ 非样本（没有 sample 字段）不进分母
        {"sprout_id": "cap0008-001-w", "predicted_edge": "固化",
         "actual_edge": None, "redeemed": False},
    ]
    report = redemption_report(records)
    assert report["兑现率"] == 1.0                       # 2/2，cap 不进分母
    assert report["不可对账"] == 1                       # 只有那根 verifiable=False
    assert report["固化边"]["n"] == 1
    assert report["固化边"]["单独列出"] == ["cap0007-001-z"]
    # 无样本时 cap 也照常单独列出
    report2 = redemption_report([
        {"sprout_id": "cap0009-001-q", "predicted_edge": "固化",
         "actual_edge": None, "redeemed": False, "sample": False, "verifiable": False},
    ])
    assert report2["判定"] == "无样本" and report2["固化边"]["n"] == 1


def test_buckets_are_object_domain_edge_actual_edge():
    """T7/A8：桶＝**对象域 × 预测边 × 实际边**（与机制正本措辞一致）。

    分桶维度是**对象域**（对象名里最后一段 `/` 之前；无 `/` 者自成域），
    不再是芽 ID 前缀（旧口径把「芽源前缀+拍号」当桶，与文档说的对象域对不上）。
    """
    records = [
        {"sprout_id": "sp0001-001-主体_notes", "obj": "主体/notes.md",
         "predicted_edge": "判读", "actual_edge": "判读", "redeemed": True,
         "sample": True},
        {"sprout_id": "sp0001-002-主体_notes", "obj": "主体/notes.md",
         "predicted_edge": "判读", "actual_edge": "行动", "redeemed": False,
         "sample": True},
        {"sprout_id": "sp0001-003-subject", "obj": "subject",
         "predicted_edge": "判读", "actual_edge": "判读", "redeemed": True,
         "sample": True},
    ]
    table = rate_table(records)
    buckets = table["桶"]
    assert "主体 × 判读 × 判读" in buckets
    assert buckets["主体 × 判读 × 判读"]["n"] == 1
    assert "subject × 判读 × 判读" in buckets and buckets["subject × 判读 × 判读"]["n"] == 1
    assert "主体 × 判读 × 行动" in buckets                     # 不同实际边＝不同桶
    assert redemption_rate(records, ("主体", "判读", "判读")) == 1.0
    assert redemption_rate(records, ("主体", "判读", "行动")) == 0.0
    # 旧行（无 obj 字段）→ 「（无对象）」桶，如实不猜
    old = [{"sprout_id": "sp0001-001-x", "predicted_edge": "判读",
            "actual_edge": "判读", "redeemed": True, "sample": True}]
    assert "（无对象） × 判读 × 判读" in rate_table(old)["桶"]
