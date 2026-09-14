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


def test_repeated_same_value_in_one_domain_does_not_grow_the_queue():
    state = DomainState()
    first = state.gate([_diff("主体/a.md", actual="10")], tick=1)
    assert len(first.kept) == 1 and not first.absorbed
    state.claim("主体/a.md", "字节数", "sp-1", "10", tick=1)

    second = state.gate([_diff("主体/b.md", actual="10")], tick=2)   # 同域同量、同值
    assert second.kept == [] and len(second.absorbed) == 1
    claim = state.claims[encode("主体", "字节数")]
    assert claim.absorbed == 1 and claim.sprout_id == "sp-1"

    third = state.gate([_diff("主体/c.md", actual="10")], tick=3)
    assert third.kept == [] and state.claims[encode("主体", "字节数")].absorbed == 2


def test_new_quantity_unfreezes_the_domain():
    state = DomainState()
    state.gate([_diff("主体/a.md", actual="10")], tick=1)
    state.claim("主体/a.md", "字节数", "sp-1", "10", tick=1)
    gate = state.gate([_diff("主体/b.md", actual="42")], tick=2)     # 新的量
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
