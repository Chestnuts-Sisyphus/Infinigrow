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
