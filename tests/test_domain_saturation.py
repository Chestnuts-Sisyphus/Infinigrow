# -*- coding: utf-8 -*-
"""域饱和判据测试（T7/G8）：同一「对象域 × 标准可验证量」只养一根未完成芽。

验收判据（可复跑）：
  1. 构造**同域重复差异**（同样的量）→ 队列**不增长**（差异照旧入账，只是不立新芽）；
  2. **新量出现**才解冻（同样的域与量，但 actual 变了 → 允许再立一根）；
  3. 芽被**消解**（本拍对账为「预测内对」）或**已不在队列** → 释放该域；
  4. 无路径的对象**自成域**（＝退化成既有的「同对象同维度合并」，不误伤旧行为）。
"""
from __future__ import annotations

from infinigrow.core.config import load_settings
from infinigrow.core.paths import REPO_ROOT, resolve_state
from infinigrow.engine.domain_saturation import DomainState, domain_key, encode
from infinigrow.engine.model import Diff, DiffKind
from infinigrow.engine.sprout_queue import SproutQueue
from infinigrow.engine.tick import run_tick


def _diff(obj, dimension="字节数", actual="10", kind=DiffKind.WRONG, tick=1, evidence="p"):
    return Diff(kind=kind, obj=obj, dimension=dimension, expected="9", actual=actual,
                evidence=evidence, tick=tick)


def test_domain_key_rule():
    assert domain_key("主体/growth-1.md", "字节数") == ("主体", "字节数")
    assert domain_key("主体/sub/a.md", "字节数") == ("主体/sub", "字节数")
    assert domain_key("tick_status.json", "字节数") == ("tick_status.json", "字节数")


def test_same_object_same_value_in_one_domain_does_not_grow_the_queue():
    """同一对象同一量反复出现 → 不增长（合并律保留）。

    K1 语义更新：域饱和的粒度从「同域」收到「同对象」——**不同对象＝不同的问题**，
    各自放行（解冻④）；同对象同量同值才是真正的复述，仍被吸收。
    """
    state = DomainState()
    first = state.gate([_diff("主体/a.md", actual="10")], tick=1)
    assert len(first.kept) == 1 and not first.absorbed
    state.claim("主体/a.md", "字节数", "sp-1", "10", tick=1)

    second = state.gate([_diff("主体/a.md", actual="10")], tick=2)   # 同对象、同值
    assert second.kept == [] and len(second.absorbed) == 1
    claim = state.claims[encode("主体", "字节数")]
    assert claim.absorbed == 1 and claim.sprout_id == "sp-1"

    third = state.gate([_diff("主体/a.md", actual="10")], tick=3)
    assert third.kept == [] and state.claims[encode("主体", "字节数")].absorbed == 2


def test_different_object_in_same_domain_releases_and_grows():
    """K1 解冻④：同域同量、**对象不同**＝新问题 → 放行并释放旧占用（不再永久吸收）。"""
    state = DomainState()
    state.gate([_diff("主体/a.md", actual="10")], tick=1)
    state.claim("主体/a.md", "字节数", "sp-1", "10", tick=1)
    gate = state.gate([_diff("主体/b.md", actual="10")], tick=2)     # 对象不同
    assert len(gate.kept) == 1 and not gate.absorbed
    assert any("对象" in r for r in gate.released)


def test_new_quantity_unfreezes_the_domain():
    state = DomainState()
    state.gate([_diff("主体/a.md", actual="10")], tick=1)
    state.claim("主体/a.md", "字节数", "sp-1", "10", tick=1)
    gate = state.gate([_diff("主体/a.md", actual="42")], tick=2)     # 同一对象、新的量
    assert len(gate.kept) == 1 and not gate.absorbed
    assert gate.released and "产出新量" in gate.released[0]


def test_other_dimension_is_a_different_quota():
    state = DomainState()
    state.gate([_diff("主体/a.md", actual="10")], tick=1)
    state.claim("主体/a.md", "字节数", "sp-1", "10", tick=1)
    gate = state.gate([_diff("主体/b.md", dimension="存在性", actual="缺失")], tick=2)
    assert len(gate.kept) == 1                                       # 另一把量，另一份额度


def test_release_on_resolved_and_on_missing_sprout():
    state = DomainState()
    state.claim("主体/a.md", "字节数", "sp-1", "10", tick=1)          # 域 主体
    state.claim("别的域/b.md", "字节数", "sp-2", "7", tick=1)         # 域 别的域
    released = state.sync(live_sprout_ids=["sp-1"],                  # sp-2 不在队列里了
                          ok_keys=[("主体/a.md", "字节数")],          # sp-1 被消解
                          tick=5)
    assert len(released) == 2 and state.claims == {}
    assert any("已消解" in r for r in released) and any("不在队列" in r for r in released)


def test_sync_keeps_live_and_unresolved_claims():
    """冻结区里的芽也算「未完成」：不释放（挂起≠死亡）。"""
    state = DomainState()
    state.claim("主体/a.md", "字节数", "sp-1", "10", tick=1)
    released = state.sync(live_sprout_ids=["sp-1"], ok_keys=[], tick=5)
    assert released == [] and len(state.claims) == 1


def test_objects_without_path_are_their_own_domain():
    """无 `/` 的对象自成域：与既有「同对象同维度合并」同效，不误伤旧行为。"""
    state = DomainState()
    state.gate([_diff("tick_status.json", actual="10")], tick=1)
    state.claim("tick_status.json", "字节数", "sp-1", "10", tick=1)
    same = state.gate([_diff("tick_status.json", actual="10")], tick=2)
    assert same.kept == [] and len(same.absorbed) == 1
    other = state.gate([_diff("outcomes.jsonl", actual="10")], tick=2)
    assert len(other.kept) == 1                                      # 另一个对象=另一个域


def test_state_file_round_trip_and_bad_file_is_empty(tmp_path):
    from infinigrow.core.config import load_settings as _ls
    settings = _ls(env={}, state_root=str(tmp_path / "state"), repo_root=str(REPO_ROOT))
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    state = DomainState()
    state.claim("主体/a.md", "字节数", "sp-1", "10", tick=1)
    state.save(layout)
    reloaded = DomainState.load(layout.domains)
    assert reloaded.as_dict() == state.as_dict()
    layout.domains.write_text("{ 坏文件", encoding="utf-8")
    assert DomainState.load(layout.domains).claims == {}             # 坏文件＝空状态，不抛


def test_tick_records_absorbed_diffs_without_hiding_them(tmp_path):
    """被吸收的差异**照旧入账**（打标 `absorbed_by_domain`）：配额不是隐藏。"""
    settings = load_settings(env={}, state_root=str(tmp_path / "state"),
                             repo_root=str(REPO_ROOT),
                             subject_root=str(tmp_path / "subject"))
    from infinigrow.engine.model import Observation, Prediction
    preds = [Prediction("主体/a.md", "字节数", "1", tick=1, evidence="p:主体/a.md"),
             Prediction("主体/b.md", "字节数", "1", tick=1, evidence="p:主体/b.md")]
    obs = [Observation("主体/a.md", "字节数", "9", "主体:a.md"),
           Observation("主体/b.md", "字节数", "9", "主体:b.md")]
    result = run_tick(settings=settings, tick=1, predictions=preds, observations=obs)
    assert len(result.new_sprouts) == 1                              # 同域同量只立一根

    layout = resolve_state(settings.state_root, settings.repo_root)
    rows = [line for line in layout.diff_ledger.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    assert len(rows) == 2                                            # 两条差异都在账上
    absorbed = [row for row in rows if '"absorbed_by_domain": true' in row]
    assert len(absorbed) == 1
    queue = SproutQueue.load(layout.sprouts, layout.frozen_sprouts)
    assert len(queue.sprouts) == 1


# ---------------------------------------------------------------- K1 N41 死锁修复
def test_different_object_in_same_domain_is_new_quantity():
    """解冻④：同域同量、**对象不同**＝另一个问题，不再被旧占用吸收。

    N41 死锁的核心：`存在性` 维度的 actual 是有穷枚举，同一对象几乎不会「产出新量」；
    若占用还记着旧对象，新对象（如 journal 下一篇）会被永久吸收。修法＝对象不同即放行。
    """
    state = DomainState()
    state.gate([_diff("主体/journal/0071-20260914.md", dimension="存在性",
                      actual="存在")], tick=1)
    state.claim("主体/journal/0071-20260914.md", "存在性", "sp-1",
                "存在", tick=1)

    gate = state.gate([_diff("主体/journal/0086-20260915.md", dimension="存在性",
                             actual="存在")], tick=2)
    assert len(gate.kept) == 1 and not gate.absorbed                # 放行，不再吸收
    assert any("对象" in r and "占用对象" in r for r in gate.released)
    assert encode("主体/journal", "存在性") not in state.claims       # 旧占用已释放


def test_exhausted_holder_releases_the_domain():
    """解冻③：持有者芽已耗尽（连领满上限且非长任务）→ 占用释放、差异放行。

    N41 的另一半：占用归一根 `leads=3` 的芽，它永不再被领，但占用仍挂着——
    新差异只能被吸收。修法＝耗尽即释放（立芽后占用登记给新芽）。
    """
    state = DomainState()
    state.gate([_diff("主体/a.md", actual="10")], tick=1)
    state.claim("主体/a.md", "字节数", "sp-1", "10", tick=1)

    gate = state.gate([_diff("主体/a.md", actual="10")], tick=2,
                      exhausted_sprout_ids={"sp-1"})
    assert len(gate.kept) == 1 and not gate.absorbed
    assert any("已耗尽" in r for r in gate.released)
    assert encode("主体", "字节数") not in state.claims


def test_sync_self_heals_exhausted_zombie_claims():
    """存量自愈：持有者还在队列但**已耗尽**（连领满上限）的僵尸占用在 sync 时释放。"""
    state = DomainState()
    state.claim("主体/a.md", "字节数", "sp-dead", "10", tick=1)       # 僵尸占用（持有者在队列但耗尽）
    state.claim("别的域/b.md", "字节数", "sp-live", "7", tick=1)      # 活占用（不同域，互不覆盖）
    released = state.sync(live_sprout_ids=["sp-dead", "sp-live"], ok_keys=[],
                          tick=5, exhausted_sprout_ids={"sp-dead"})
    assert len(released) == 1 and "已耗尽" in released[0]
    assert "sp-dead" not in {c.sprout_id for c in state.claims.values()}
    assert state.claims[encode("别的域", "字节数")].sprout_id == "sp-live"   # 活占用保留
