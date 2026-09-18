# -*- coding: utf-8 -*-
"""芽队列纪律：合并、上限冻结、连领上限、冷启动随机化 vs 字典序。"""
from infinigrow.engine.model import Diff, DiffKind, Sprout, SproutOrigin
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


def test_replace_inherits_the_older_birth_tick():
    """N61/A1：同键「新顶旧」时**继承旧芽的出生拍**——问题的年龄属于问题，不属于记录行。

    真机现场：`sp0326-001` 出生 326、到 338 才拿到取题位；期间组织会话每 3 拍重提一次，
    每次重提都把它的年龄刷回当前拍（在取题序里永远排在新芽位置）。
    """
    q = SproutQueue(cap=50)
    q.add(_sprout("s1", "A", tick=10))
    q.add(_sprout("s2", "A", tick=90))
    assert q.sprouts[0].created_tick == 10          # 继承更早的那个（min）
    assert q.sprouts[0].id == "s2"                  # 记录行仍是新的（账本按 id 留痕）


def test_replace_does_not_move_the_order_key_earlier():
    """合并后的 `order_key` **不得比它替换掉的那根更靠前**（否则就是动了排序＝K15 领域）。

    口径：`order_key` 排的是 `last_lead_tick`（最久未碰优先）——旧芽被领过（leads=1），
    合并时若不带走这条记录、只继承出生拍，合并芽就会插到旧芽**前面**去。
    """
    q = SproutQueue(cap=50)
    old = _sprout("s1", "A", tick=10)
    q.add(old)
    q.mark_lead(old, tick=60)                       # 旧芽被领做过一次（last_lead=60, leads=1）
    before = q.order_key(q.sprouts[0])
    q.add(_sprout("s2", "A", tick=90))              # 同键重提（新顶旧）
    merged = q.sprouts[0]
    after = q.order_key(merged)
    assert merged.created_tick == 10
    assert merged.last_lead_tick == 60               # 被碰时刻一并继承 → 排序不前移
    assert after[:2] == before[:2] and after >= before          # 不前移


def test_replace_keeps_the_touch_record_but_not_the_lead_budget():
    """连领**预算**是记录行的（不继承），但「最后一次被碰的时刻」跟着问题走。

    为什么不继承 `leads`：继承了就等于「同一差异问满 3 次后被永久判死」——重现的差异
    再也做不了，这是没人要的语义变更。`last_lead_tick` 必须带走，否则合并芽会比它替换掉的
    那根更靠前（＝动了排序）。
    """
    q = SproutQueue(cap=50, lead_limit=3)
    old = _sprout("s1", "A", tick=10)
    q.add(old)
    for t in (20, 30, 40):
        q.mark_lead(old, t)                          # 旧行问满 3 次
    assert q.eligible(50) == []
    q.add(_sprout("s2", "A", tick=90))               # 同键重提（新顶旧）
    merged = q.sprouts[0]
    assert merged.created_tick == 10                 # 年龄继承
    assert merged.last_lead_tick == 40               # 被碰时刻继承（排序不前移）
    assert merged.leads == 0                         # 预算不继承：新行照旧拿自己的
    assert len(q.eligible(50)) == 1                  # 重现的差异仍可被做（改造前的行为）


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


def test_review_frozen_relights_live_diffs_and_records_reason():
    """冻结区重看（T4/A5）：差异仍以**未消解**形态出现 → 重新点亮；
    否则如实记录「未点亮＋原因」——不许静默躺着，也不许无差别全复活。"""
    q = SproutQueue(cap=2)
    q.add(_sprout("s1", "A", tick=1))
    q.add(_sprout("s2", "B", tick=2))
    q.add(_sprout("s3", "C", tick=3))
    assert len(q.frozen) == 1                                # s1 被挤出

    # 本拍差异：A×存在性 仍以「预测未执行」出现（未消解）→ s1 应被重新点亮
    diffs = [Diff(DiffKind.NOT_EXECUTED, "A", "大小", "存在", "（无）", "p", tick=4)]
    notes = q.review_frozen(diffs, tick=4)
    assert any("重新点亮 s1" in n for n in notes)
    assert "s1" in {s.id for s in q.sprouts}

    # 差异已消解/未重现 → 记录「未点亮＋原因」，冻结区保持原样
    notes2 = q.review_frozen([], tick=5)
    assert any("未点亮" in n and "差异已消解或未重现" in n for n in notes2)
    assert [s.id for s in q.frozen] == ["s2"]          # s2 被 s1 复活挤出，差异未重现→仍冻结

    # 重亮上限：冻结 3 根、差异全活着 → 本拍最多重亮 max_relight 根，其余记原因
    q2 = SproutQueue(cap=2)
    for i in range(5):
        q2.add(_sprout("x%d" % i, "obj%d" % i, tick=i))
    live = [Diff(DiffKind.WRONG, "obj%d" % i, "大小", "1", "2", "p", tick=6)
            for i in range(3)]
    notes3 = q2.review_frozen(live, tick=6, max_relight=2)
    relit = [n for n in notes3 if "重新点亮" in n]
    capped = [n for n in notes3 if "重亮已达上限" in n]
    assert len(relit) == 2 and len(capped) == 1


def test_summary_counts_by_origin():
    q = SproutQueue(cap=10)
    q.add(_sprout("s1", "A"))
    assert q.summary()["by_origin"] == {"差异对账": 1}


def test_ordering_is_not_biased_by_id_prefix():
    """取题顺序不许被「芽源前缀」支配（T12 现场演练抓到的真坑）。

    判据是**具体状态**：一根**更早出生**的差异芽（`sp*`）与一根**更晚出生**的
    封顶芽（`cap*`）同时在队列里时，先取到的是更早出生的那根——
    纯按 ID 字典序取题时 `cap` < `sp`，封顶芽会永远插队，把主芽源（差异）饿死。
    """
    q = SproutQueue(cap=50, lead_limit=3, cold_start_ticks=0)
    earlier = Sprout(id="sp0010-001-subject_growth_md", obj="主体/growth-1.md",
                     dimension="存在性", pointer="p", origin=SproutOrigin.DIFF,
                     created_tick=10)
    later = Sprout(id="cap0011-001-state_json", obj="state.json", dimension="应用面",
                   pointer="p", origin=SproutOrigin.MATURITY_CAP, created_tick=11)
    q.add(later)
    q.add(earlier)
    assert q.take_topic(tick=12).id == earlier.id         # 更早出生的先做

    q.mark_lead(earlier, 12)                              # 被碰过 → 让位给最久没碰的
    assert q.take_topic(tick=13).id == later.id

    assert q.order_key(earlier) == q.order_key(earlier)   # 全可复现（不引入随机）
    assert q.order_key(earlier) != q.order_key(later)


# ---------------------------------------------------------------- N48：去重含冻结区 + 重问
def test_known_objects_includes_frozen_zone():
    """M1（N48 真凶修复）：去重集合必须**含冻结区**——「挂起≠死亡」。

    现场（可复跑）：只扫活跃队列时，能力库 91 条条目**全部**已有芽，却每拍再立 ~36 根
    （被挤出的对象下一拍又被当成「没生过」）→ 上限 50 的队列被占满、主芽源「差异对账」
    自 tick 189 起零取题。合并律的完整形态是「同对象同维度只有一根芽，**活跃或冻结里都算**」。
    """
    q = SproutQueue(cap=2)
    q.add(_sprout("s1", "A", tick=1))
    q.add(_sprout("s2", "B", tick=2))
    q.add(_sprout("s3", "C", tick=3))          # s1 被挤出到冻结区
    assert [s.id for s in q.frozen] == ["s1"]
    known = q.known_objects(tick=4, requestion_ticks=10_000)
    assert {"A", "B", "C"} <= known            # 冻结里的 A 照样算「已生」


def test_frozen_sprout_is_reasked_after_requestion_ticks():
    """M4（G9）：冻结**不是永久封存**——冻结满 `requestion_ticks` 拍且未被点亮 →
    不再拦它（允许重新立芽）；没满 → 继续拦（刚问过的不重复问）。"""
    q = SproutQueue(cap=1)
    q.add(_sprout("s1", "A", tick=1))
    q.add(_sprout("s2", "B", tick=2))          # s1 在拍 2 被冻结（frozen_tick=2）
    assert q.frozen[0].frozen_tick == 2        # 冻结时刻是机械记录，不靠猜
    assert "A" in q.known_objects(tick=100, requestion_ticks=300)      # 未满年限 → 拦
    assert "A" not in q.known_objects(tick=302, requestion_ticks=300)  # 满 300 拍 → 放行


def test_requestion_uses_the_newest_freeze_of_that_object():
    """重问判据取「该对象全部冻结芽里**最新的那次冻结**」——否则积压的旧冻结芽会在同一拍
    把同一批对象全部放行（一次洪泛，等于把 N48 请回来）。"""
    q = SproutQueue(cap=10)
    old = _sprout("lib0001-001-A", "A", tick=1)
    fresh = _sprout("lib0100-001-A", "A", tick=100)
    q.frozen.extend([old, fresh])
    old.frozen_tick, fresh.frozen_tick = 1, 100
    assert "A" in q.known_objects(tick=350, requestion_ticks=300)   # 最新一次冻结只过去 250 拍


def test_old_frozen_rows_without_frozen_tick_fall_back_to_created_tick():
    """升级前的旧行没有 `frozen_tick` → 回退到 `created_tick`（不假装它刚冻结）。"""
    q = SproutQueue(cap=10)
    legacy = _sprout("lib0005-001-A", "A", tick=5)          # frozen_tick 缺省 None
    q.frozen.append(legacy)
    assert legacy.frozen_tick is None
    assert "A" not in q.known_objects(tick=400, requestion_ticks=300)


def test_freeze_moves_active_sprout_to_frozen_and_frees_the_slot():
    """M2 的退场动作：条目结案/消费后，它在队的芽**只移动**进冻结区（不删）。"""
    q = SproutQueue(cap=10)
    s = _sprout("lib0001-001-A", "A")
    q.add(s)
    assert q.freeze(s, tick=7) is True
    assert q.sprouts == [] and [x.id for x in q.frozen] == ["lib0001-001-A"]
    assert q.frozen[0].frozen_tick == 7
    assert q.freeze(_sprout("lib9999-001-Z", "Z"), tick=8) is False    # 不在队 → 不动别人


def test_revive_clears_frozen_tick_and_refreshes_age():
    """重新点亮（挂起≠死亡的另一半）：回活跃队列、清连领计数、**清冻结时刻**。"""
    q = SproutQueue(cap=1)
    q.add(_sprout("s1", "A", tick=1))
    q.add(_sprout("s2", "B", tick=2))
    s1 = q.frozen[0]
    q.revive(s1, tick=9)
    assert s1.frozen_tick is None and s1.created_tick == 9 and s1.leads == 0


def test_long_task_is_reserved_and_has_no_writer():
    """K16：`long_task` 豁免连领上限＝**登记为预留**，引擎里不许有写入方。

    为什么必须钉住：这条豁免是「连领上限」的唯一后门。没有写入方它是死的（现状是有意决定），
    但后门一旦被人顺手接上，就等于执行会话给自己发免死金牌——违反「每根芽最多连领 3 拍」
    那条由事故换来的约束。接线需要先定「什么算长任务」的机械判据（设计决策），
    不许通过悄悄加一个 `long_task=True` 来既成事实。
    """
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "src" / "infinigrow"
    writer = re.compile(r"long_task\s*=\s*True|\[\s*['\"]long_task['\"]\s*\]\s*=")
    offenders = [p.relative_to(src).as_posix() for p in sorted(src.rglob("*.py"))
                 if p.name != "model.py" and writer.search(p.read_text(encoding="utf-8"))]
    assert offenders == [], "有人给预留字段加了写入方：%s" % offenders

    # 预留的行为本身是活的（旧行读得进来）：带标记才豁免，不带就照守上限
    q = SproutQueue(cap=10, lead_limit=1)
    plain, long_one = _sprout("s1", "A"), _sprout("s2", "B", long_task=True)
    for s in (plain, long_one):
        s.leads = 1
        q.add(s)
    assert [s.id for s in q.eligible(5)] == ["s2"]
