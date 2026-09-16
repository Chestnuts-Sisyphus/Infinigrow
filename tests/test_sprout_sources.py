# -*- coding: utf-8 -*-
"""芽源测试：N 差异 N 芽、零差异零芽、两个新入口（成熟链封顶／能力库未用）。"""
from infinigrow.engine.model import (Diff, DiffKind, MATURITY_CAP, SproutOrigin)
from infinigrow.engine.sprout_sources import (LIBRARY_IDLE_TICKS, from_diffs,
                                             from_maturity_cap, from_unused_library)


def _diff(obj="A", dim="大小", kind=DiffKind.WRONG, evidence="留痕:1"):
    return Diff(kind, obj, dim, "10", "12", evidence, 7)


def test_n_diffs_n_sprouts():
    diffs = [_diff("A"), _diff("B"), _diff("C"), _diff("D", kind=DiffKind.OK)]
    sprouts = from_diffs(diffs, tick=7)
    assert len(sprouts) == 3                             # 「预测内对」不生芽
    assert all(s.origin == SproutOrigin.DIFF for s in sprouts)
    assert len({s.id for s in sprouts}) == 3


def test_zero_diff_zero_sprout():
    assert from_diffs([], tick=7) == []
    assert from_diffs([_diff(kind=DiffKind.OK)], tick=7) == []


def test_no_pointer_no_sprout():
    assert from_diffs([_diff(evidence="")], tick=7) == []


def test_maturity_cap_source():
    """①封顶 → 芽「开应用面」；只认**本拍恰好**到顶（具体状态，不是「最近经常」）。"""
    records = [
        {"obj": "X", "step": MATURITY_CAP, "tick": 7},          # 本拍到顶 → 生芽
        {"obj": "Y", "step": MATURITY_CAP, "tick": 3},          # 早先到顶 → 不生
        {"obj": "Z", "step": 2, "tick": 7},                     # 没到顶 → 不生
    ]
    sprouts = from_maturity_cap(records, tick=7)
    assert [s.obj for s in sprouts] == ["X"]
    assert sprouts[0].origin == SproutOrigin.MATURITY_CAP
    assert sprouts[0].dimension == "应用面"
    assert sprouts[0].pointer                                  # 指针强制


def test_maturity_cap_dedupes_known():
    records = [{"obj": "X", "step": MATURITY_CAP, "tick": 7}]
    assert from_maturity_cap(records, tick=7, known_objects=["X"]) == []


def test_library_unused_source():
    """②长期未用 → 芽「为何未用／别域是否成立」；判据全是具体状态。"""
    tick = LIBRARY_IDLE_TICKS + 5
    records = [
        {"name": "旧条目", "last_used_tick": 0},                # 闲置超阈值 → 生芽
        {"name": "新条目", "last_used_tick": tick - 1},          # 刚用过 → 不生
        {"name": "本拍用过", "last_used_tick": 0},               # 闲置够久但本拍留痕出现 → 不生
    ]
    sprouts = from_unused_library(records, liuhen_text="本轮动了 本拍用过 这个对象",
                                  tick=tick)
    assert [s.obj for s in sprouts] == ["旧条目"]
    assert sprouts[0].origin == SproutOrigin.LIBRARY_UNUSED
    assert sprouts[0].dimension == "可用性"


def test_library_unused_respects_known():
    records = [{"name": "旧条目", "last_used_tick": 0}]
    assert from_unused_library(records, "", tick=LIBRARY_IDLE_TICKS + 1,
                               known_objects=["旧条目"]) == []


# ---------------------------------------------------------------- N43 前向目标
def test_forward_target_carries_delta_not_snapshot():
    """N43：计数型**前向目标**（预期 > 实际）随芽带走的是**差额**（`+1`），不是绝对值。

    绝对值＝提议那一拍的快照，等芽被领到时现实早已走过它（实测：提议拍写「文件数＝97」，
    领做时已 103 → 永远判打脸）；差额在领做那一拍按当时现实重新锚定。
    边预测＝行动（这是一手要落成现实变化的活，不是「推新认知」）。
    """
    diff = Diff(DiffKind.WRONG, "主体/journal/", "文件数", "97", "96", "指针:提议", 7)
    sprout = from_diffs([diff], tick=7)[0]
    assert sprout.expected_value == "+1"
    assert sprout.predicted_edge.value == "行动"


def test_forward_target_never_reverts_reality():
    """N43 的反面（不许回归）：现实**已经超过**预期（预期 < 实际）→ 不带预期。

    这是当时踩到的坑：文件数 1→2 是生长，却派了一根「改回 1」的芽。
    """
    diff = Diff(DiffKind.WRONG, "主体/n.md", "文件数", "1", "2", "指针:旧", 7)
    sprout = from_diffs([diff], tick=7)[0]
    assert sprout.expected_value is None
    assert sprout.predicted_edge.value == "原理"


def test_delta_form_is_carried_as_is_on_any_dimension():
    """差额写法（`+N`）原样带走——组织会话提议「再长一格」走的就是这条。"""
    diff = Diff(DiffKind.WRONG, "主体/journal/", "文件数", "+1", "96", "指针:提议", 7)
    assert from_diffs([diff], tick=7)[0].expected_value == "+1"


def test_not_executed_still_carries_its_nominal_expectation():
    """回归：`预测未执行` 仍按原样带名义预期（「存在」这类没有快照问题）。"""
    diff = Diff(DiffKind.NOT_EXECUTED, "主体/x.md", "存在性", "存在", "（无现实侧记录）",
                "提议:新建", 7)
    assert from_diffs([diff], tick=7)[0].expected_value == "存在"
