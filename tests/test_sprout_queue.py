# -*- coding: utf-8 -*-
"""芽队列纪律：合并、上限冻结、连领上限、冷启动随机化 vs 字典序。"""
from infinigrow.engine.model import Sprout, SproutOrigin
from infinigrow.engine.sprout_queue import SproutQueue


def _sprout(sid, obj, dim="大小", tick=1, long_task=False):
    return Sprout(id=sid, obj=obj, dimension=dim, pointer="p", origin=SproutOrigin.DIFF,
                  created_tick=tick, long_task=long_task)


def test_same_object_dimension_replaced_not_stacked():
    """同对象同维度＝一根芽（新顶旧）——v1「186/221 根同族」的病根就在这。"""
    q = SproutQueue(cap=50)
    q.add(_sprout("s1", "A"))
    action, _ = q.add(_sprout("s2", "A"))
    assert action == "replaced"
    assert len(q.sprouts) == 1 and q.sprouts[0].id == "s2"


def test_duplicate_id_ignored():
    q = SproutQueue(cap=50)
    q.add(_sprout("s1", "A"))
    action, _ = q.add(_sprout("s1", "B", dim="别的"))
    assert action == "duplicate" and len(q.sprouts) == 1


def test_cap_freezes_oldest():
    q = SproutQueue(cap=3)
    for i in range(5):
        q.add(_sprout("s%d" % i, "obj%d" % i, tick=i))
    assert len(q.sprouts) == 3
    assert [s.id for s in q.frozen] == ["s0", "s1"]
    assert len(q.frozen) == 2                            # 冻结≠删除


def test_lead_limit_and_long_task_exemption():
    q = SproutQueue(cap=10, lead_limit=3)
    s = _sprout("s1", "A")
    q.add(s)
    for _ in range(3):
        q.mark_lead(s, 1)
    assert q.eligible(2) == []                           # 连领 3 拍 → 本拍不可领
    q.add(_sprout("s2", "B", long_task=True))
    assert [x.id for x in q.eligible(2)] == ["s2"]       # 长任务豁免


def test_cold_start_is_reproducible_then_lexicographic():
    q = SproutQueue(cap=10, cold_start_ticks=5)
    for name in ("c", "a", "b"):
        q.add(_sprout("s-" + name, name))
    picks = [q.take_topic(3).id for _ in range(5)]
    assert len(set(picks)) == 1                          # 同拍号 → 同选择（可复跑）
    assert q.take_topic(9).id == "s-a"                   # 冷启动之后：字典序


def test_revive_from_frozen():
    q = SproutQueue(cap=2)
    q.add(_sprout("s1", "A", tick=1))
    q.add(_sprout("s2", "B", tick=2))
    q.add(_sprout("s3", "C", tick=3))
    assert [s.id for s in q.frozen] == ["s1"]
    moved = q.frozen[0]
    q.revive(moved, tick=4)
    assert "s1" in {s.id for s in q.sprouts}                 # 挂起≠死亡：回活跃队列
    assert moved.created_tick == 4 and moved.leads == 0     # 重新点亮＝刷新年龄与连领计数
    assert q.frozen and q.frozen[0].id != "s1"               # 被挤出的换成别人


def test_summary_counts_by_origin():
    q = SproutQueue(cap=10)
    q.add(_sprout("s1", "A"))
    assert q.summary()["by_origin"] == {"差异对账": 1}
