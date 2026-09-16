# -*- coding: utf-8 -*-
"""芽源测试：N 差异 N 芽、零差异零芽、两个新入口（成熟链封顶／能力库未用）、
能力库读侧合并（M3）与提醒出口（M2）。"""
from infinigrow.engine.model import Diff, DiffKind, MATURITY_CAP, Sprout, SproutOrigin
from infinigrow.engine.sprout_sources import (LIBRARY_IDLE_TICKS, consumed_entries,
                                             entries_to_close, entry_mentioned,
                                             from_diffs, from_maturity_cap,
                                             from_unused_library, library_asks,
                                             library_entries, library_usage_updates)


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


# ---------------------------------------------------------------- M3：读侧合并与「已用」
def test_library_entries_collapse_by_name():
    """M3 的读侧：追加型账本按名字合并成**当前状态**（否则一条旧的未结案行会把出口
    重新打开、把「已用」读回旧值）。`created_tick` 取最早、`last_used_tick` 取最大。"""
    rows = [
        {"name": "主体/a.md", "created_tick": 10, "last_used_tick": 10,
         "source": "maturity-cap"},
        {"name": "主体/a.md", "last_used_tick": 40, "source": "trace"},
        {"name": "主体/b.md", "created_tick": 20, "last_used_tick": 20},
    ]
    entries = library_entries(rows)
    assert entries["主体/a.md"]["created_tick"] == 10
    assert entries["主体/a.md"]["last_used_tick"] == 40
    assert entries["主体/a.md"]["source"] == "maturity-cap"     # 来源取创建那一条
    assert entries["主体/b.md"]["last_used_tick"] == 20
    assert library_entries(entries)["主体/a.md"] == entries["主体/a.md"]   # 幂等


def test_library_entries_take_the_last_closure():
    rows = [{"name": "x", "created_tick": 1, "last_used_tick": 1},
            {"name": "x", "closed_tick": 9, "closed_by": "asked-out",
             "closure_pointer": "留痕:traces/tick-00009.md"},
            {"name": "x", "last_used_tick": 12}]
    entry = library_entries(rows)["x"]
    assert entry["closed_tick"] == 9
    assert entry["closure_pointer"].endswith("tick-00009.md")
    assert entry["last_used_tick"] == 12                       # 结案后仍如实记最近使用


def test_from_unused_library_skips_closed_entries():
    """M2 的出口判据读侧：**已结案的不再产芽**（哪怕账本里还有旧的未结案行）。"""
    rows = [{"name": "旧条目", "created_tick": 0, "last_used_tick": 0},
            {"name": "旧条目", "closed_tick": 5, "closed_by": "asked-out",
             "closure_pointer": "留痕:x"}]
    assert from_unused_library(rows, "", tick=LIBRARY_IDLE_TICKS + 50) == []


def test_from_unused_library_gate_reads_executor_output_text():
    """M3②：这道闸的输入是**执行者留痕输出**（不是差异账的 `note`）。"""
    rows = [{"name": "主体/journal/0002-20260914.md", "created_tick": 0,
             "last_used_tick": 0}]
    tick = LIBRARY_IDLE_TICKS + 5
    assert len(from_unused_library(rows, "本轮动了 journal/0002-20260914.md", tick)) == 0
    assert len(from_unused_library(rows, "本轮做了别的", tick)) == 1


def test_entry_mentioned_accepts_both_forms_but_dir_only_in_full():
    """M3 的命中判据：全名与主体内相对写法都认（实测相对写法才有命中）；
    目录对象只认全名（`journal/` 这种短串在任何提到目录的话里都会命中＝噪声）。"""
    assert entry_mentioned("写了 主体/journal/0322-20260916.md", "主体/journal/0322-20260916.md")
    assert entry_mentioned("写了 journal/0322-20260916.md", "主体/journal/0322-20260916.md")
    assert entry_mentioned("动了 主体/journal/", "主体/journal/")
    assert not entry_mentioned("动了 journal/ 这个目录", "主体/journal/")
    assert not entry_mentioned("", "主体/journal/0322-20260916.md")


def test_library_usage_updates_mark_used_and_skip_closed():
    """M3①：留痕命中 → 写一条**更新行**（`last_used_tick` 的真实更新方）。
    已结案的条目不更新（出口是永久的，别再给它续命）。"""
    entries = library_entries([
        {"name": "主体/a.md", "created_tick": 1, "last_used_tick": 1},
        {"name": "主体/b.md", "created_tick": 1, "last_used_tick": 1},
        {"name": "主体/c.md", "created_tick": 1, "last_used_tick": 1},
        {"name": "主体/c.md", "closed_tick": 3, "closed_by": "asked-out"},
    ])
    rows = library_usage_updates(entries, "动了 主体/a.md 与 c.md：主体/c.md", tick=9,
                                 pointer="留痕:traces/tick-00009.md")
    assert [r["name"] for r in rows] == ["主体/a.md"]           # c 已结案 → 不更新
    assert rows[0]["last_used_tick"] == 9
    assert rows[0]["source"] == "trace"


def test_library_asks_sums_leads_across_active_and_frozen():
    asked = library_asks([
        Sprout(id="l1", obj="A", dimension="可用性", pointer="p",
               origin=SproutOrigin.LIBRARY_UNUSED, created_tick=1, leads=2),
        Sprout(id="l2", obj="A", dimension="可用性", pointer="p",
               origin=SproutOrigin.LIBRARY_UNUSED, created_tick=2, leads=1),
        Sprout(id="s1", obj="A", dimension="存在性", pointer="p",
               origin=SproutOrigin.DIFF, created_tick=2, leads=3),   # 非库芽不算
    ])
    assert asked == {"A": 3}


def test_entries_to_close_needs_three_asks_and_no_consumption():
    """M2（G2 的根）：问满 N＝连领上限 3 次仍无消费 → 结案（带结案指针）；
    被消费过的条目不算「没人理」，问不满也不结案。"""
    sprout = Sprout(id="l1", obj="A", dimension="可用性", pointer="p",
                    origin=SproutOrigin.LIBRARY_UNUSED, created_tick=1, leads=3,
                    last_lead_tick=7)
    entries = library_entries([{"name": "A", "created_tick": 1, "last_used_tick": 1}])
    rows = entries_to_close(entries, [sprout], tick=20, lead_limit=3)
    assert [r["name"] for r in rows] == ["A"]
    assert rows[0]["closed_tick"] == 20 and rows[0]["asked"] == 3
    assert rows[0]["closure_pointer"] == "留痕:traces/tick-00007.md"   # 指向最后一次被问

    # 未满 3 次 → 不结案
    assert entries_to_close(entries, [replace_leads(sprout, 2)], tick=20, lead_limit=3) == []
    # 已被消费（last_used_tick 晚于创建）→ 不结案（问到了答案，不是没人理）
    used = library_entries([{"name": "A", "created_tick": 1, "last_used_tick": 5}])
    assert entries_to_close(used, [sprout], tick=20, lead_limit=3) == []
    # 已结案 → 不重复结案
    closed = library_entries([{"name": "A", "created_tick": 1, "last_used_tick": 1},
                              {"name": "A", "closed_tick": 4, "closed_by": "asked-out"}])
    assert entries_to_close(closed, [sprout], tick=20, lead_limit=3) == []


def replace_leads(sprout, leads):
    """造一根只改连领计数的孪生芽（dataclass 非 frozen，直接改副本字段即可）。"""
    from dataclasses import replace as _replace
    return _replace(sprout, leads=leads)


def test_consumed_entries_marks_used_after_creation():
    entries = library_entries([
        {"name": "A", "created_tick": 3, "last_used_tick": 3},          # 只创建过
        {"name": "B", "created_tick": 3, "last_used_tick": 8},          # 后来被用过
    ])
    assert consumed_entries(entries) == {"B"}
