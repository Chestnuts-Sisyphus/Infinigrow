# -*- coding: utf-8 -*-
"""拍循环测试：心跳、互斥、报告拍号、成熟链 +1 护栏、封顶生芽、端到端空仓跑、对称性。"""
import json
from dataclasses import replace

import pytest

from infinigrow.core.paths import REPO_ROOT, resolve_state
from infinigrow.core.config import load_settings
from infinigrow.engine.model import Observation, Prediction
from infinigrow.engine.tick import (LOCK_STALE_SECONDS, TickHeartbeatError, acquire_lock,
                                    advance_maturity, record_tick_result, release_lock,
                                    run_tick)


def _settings(tmp_path, repo_root):
    return load_settings(env={}, state_root=str(tmp_path / "state"), repo_root=str(repo_root))


def test_run_tick_creates_state_and_increments(tmp_path, settings):
    first = run_tick(settings=settings)
    second = run_tick(settings=settings)
    assert (first.tick, second.tick) == (1, 2)
    assert first.rc == 0
    layout = resolve_state(settings.state_root, settings.repo_root)
    assert layout.tick_status.is_file()
    assert json.loads(layout.tick_status.read_text(encoding="utf-8"))["tick"] == 2


def test_heartbeat_counts_failures_and_is_loud_on_write_error(tmp_path, settings):
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    assert record_tick_result(layout, 1, tick=1) == 1
    assert record_tick_result(layout, 1, tick=2) == 2
    assert record_tick_result(layout, 0, tick=3) == 0
    # 写不进去必须响亮（不能静默：园丁的断流判据靠它）。
    # 造法：把状态根指到一个**已存在的同名文件**上——目录建不出来，写盘必失败。
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")
    broken = replace(layout, root=blocker, tick_status=blocker / "tick_status.json")
    with pytest.raises(TickHeartbeatError):
        record_tick_result(broken, 0, tick=4)


def test_report_filename_carries_tick_number(tmp_path, settings):
    run_tick(settings=settings)
    run_tick(settings=settings)
    layout = resolve_state(settings.state_root, settings.repo_root)
    names = sorted(p.name for p in layout.reconcile_dir.glob("reconcile-*.md"))
    assert names == ["reconcile-00001.md", "reconcile-00002.md"]     # 同名不会互相覆盖


def test_lock_serialises_sessions(tmp_path, settings):
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    first = acquire_lock(layout, tick=1)
    assert first is not None
    assert acquire_lock(layout, tick=1) is None                     # 第二个会话拿不到
    release_lock(first)
    assert acquire_lock(layout, tick=2) is not None                 # 释放后可再拿


def test_stale_lock_cleared(tmp_path, settings):
    import os
    import time
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    lock = acquire_lock(layout, tick=1)
    old = time.time() - (LOCK_STALE_SECONDS + 10)
    os.utime(lock, (old, old))
    assert acquire_lock(layout, tick=2) is not None                 # 陈旧锁＝死锁，自动清


def test_tick_skips_when_locked(tmp_path, settings):
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    held = acquire_lock(layout, tick=1)
    try:
        result = run_tick(settings=settings)
        assert result.skipped is True and result.rc == 0            # 幂等跳过，不报错
    finally:
        release_lock(held)


def test_maturity_step_advances_at_most_one_per_tick():
    assert advance_maturity(0) == 1
    assert advance_maturity(3) == 4
    assert advance_maturity(4) == 4          # 封顶即止，不会跳到 5
    with pytest.raises(ValueError):
        advance_maturity(-1)


def test_maturity_never_jumps_two_in_one_tick(tmp_path, settings):
    run_tick(settings=settings)
    run_tick(settings=settings)
    layout = resolve_state(settings.state_root, settings.repo_root)
    steps: dict[str, list[int]] = {}
    for line in layout.maturity_chain.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        steps.setdefault(rec["obj"], []).append(rec["step"])
    for obj, seq in steps.items():
        for a, b in zip(seq, seq[1:], strict=False):
            assert b - a <= 1, "对象 %s 出现单拍连跳：%s" % (obj, seq)   # T11 护栏


def test_cap_produces_application_sprout(tmp_path, settings):
    """对象爬到第 4 步的那一拍，必须出现「开应用面」芽（T10-① 真机判据）。"""
    for _ in range(5):
        run_tick(settings=settings)
    layout = resolve_state(settings.state_root, settings.repo_root)
    origins = set()
    for line in layout.sprouts.read_text(encoding="utf-8").splitlines():
        origins.add(json.loads(line)["origin"])
    assert "成熟链封顶" in origins


def test_maturity_cap_writes_library_entry(tmp_path, settings):
    """对象封顶的那一拍，能力库必须出现**写入方**条目（T3/A4：芽源③不再是死路径）。

    现场：`library.jsonl` 过去没有任何写入方 → `from_unused_library` 读到的永远是空表，
    芽源③「能力库未用」永不产芽。现在封顶对象各写一条（含末次使用拍与来源），
    芽源③从此有现实的输入；条目名必须来自可对账对象（本拍封顶的那批）。
    """
    for _ in range(5):
        run_tick(settings=settings)
    layout = resolve_state(settings.state_root, settings.repo_root)
    rows = [json.loads(line) for line in
            layout.library.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows, "能力库应有封顶写入条目"
    for rec in rows:
        assert rec.get("source") == "maturity-cap"
        assert isinstance(rec.get("last_used_tick"), int)
        assert isinstance(rec.get("created_tick"), int)


def test_pending_pointer_timeout_produces_diff_and_named_report(tmp_path, settings):
    """待补指针超时（T4/A6）：差异账里 `pending_pointer=True` 的条目超过宽限拍数
    → 生成「指针缺失」差异并**照样产芽**；报告点名；且不重复产（同一待补条目不刷屏）。

    现场：`reconcile.pending_pointer()` 只有实现没有调用方——待补指针只登记、永不处理。
    """
    from infinigrow.engine.reconcile import POINTER_GRACE_TICKS
    from infinigrow.ledger.store import append_jsonl
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    append_jsonl(layout.diff_ledger, {
        "kind": "预测内错", "obj": "主体/ghost.md", "dimension": "存在性",
        "expected": "存在", "actual": "（指针缺失）", "evidence": "",
        "tick": 1, "spawns": False, "source": "org-session", "pending_pointer": True,
    }, layout.root)
    named = None
    for i in range(1, POINTER_GRACE_TICKS + 3):
        r = run_tick(settings=settings, tick=i)
        if any("待补指针超时" in n for n in r.notes):
            named = r
            break
    assert named is not None, "超时后报告必须点名「待补指针超时」"
    rows = [json.loads(line) for line in
            layout.diff_ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    missing = [r for r in rows if r.get("pointer_missing")]
    assert len(missing) == 1 and missing[0]["obj"] == "主体/ghost.md"
    # 只产一次：宽限之后再跑几拍，不重复产（去重判据＝已存在 pointer_missing 行）
    for i in range(POINTER_GRACE_TICKS + 3, POINTER_GRACE_TICKS + 6):
        run_tick(settings=settings, tick=i)
    rows2 = [json.loads(line) for line in
             layout.diff_ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len([r for r in rows2 if r.get("pointer_missing")]) == 1


def test_steady_subject_produces_no_spurious_diffs(tmp_path, settings):
    """**预测/观测必须对称**：主体没变的一拍不许凭空长出差异。

    踩过的坑：机械层观测 6 个自身状态文件、只预测其中 3 个 → 每拍 3 条
    「预测外发现」；主体观测到了每个文件的存在性、却不预测它 → 一拍一条
    「预测未执行」。两种都是**不对称造出来的假差异**，会让引擎给自己派无解的活。
    判据：连跑两拍、主体一个字节都不动 → 差异**只有**「预测内对」，
    且没有任何一条提到引擎自身的账本文件。
    """
    import datetime as _dt
    subject = tmp_path / "subject"
    subject.mkdir()
    (subject / "seed.md").write_text("seed", encoding="utf-8")
    settings = load_settings(env={}, state_root=str(tmp_path / "state"),
                             repo_root=str(REPO_ROOT), subject_root=str(subject))
    settings.cold_start_ticks = 0
    first = run_tick(settings=settings, tick=1)
    second = run_tick(settings=settings, tick=2)
    for result in (first, second):
        assert result.diff_summary["by_kind"].get("预测内错", 0) == 0
        assert result.diff_summary["by_kind"].get("预测外发现", 0) == 0
        assert result.diff_summary["by_kind"].get("预测未执行", 0) == 0
        assert result.new_sprouts == []
    assert second.diff_summary["by_kind"]["预测内对"] >= 4      # 根(2) + 文件(2)
    for diff in second.diffs:
        assert diff.obj not in ("diffs.jsonl", "sprouts.jsonl", "library.jsonl",
                                "tick_status.json", "outcomes.jsonl", "maturity.jsonl")
    assert _dt.datetime.now()           # 时间戳不是这里要断言的，只表明测试没被跳过


def test_maturity_advances_at_most_once_per_object_per_tick(tmp_path, settings):
    """同一对象同拍有多条被证实的差异（存在性＋字节数）→ 成熟链仍只 +1。"""
    subject = tmp_path / "subject"
    subject.mkdir()
    (subject / "a.md").write_text("x", encoding="utf-8")
    settings = load_settings(env={}, state_root=str(tmp_path / "state"),
                             repo_root=str(REPO_ROOT), subject_root=str(subject))
    for tick in (1, 2, 3):
        run_tick(settings=settings, tick=tick)
    layout = resolve_state(settings.state_root, settings.repo_root)
    steps: dict[str, list[int]] = {}
    for line in layout.maturity_chain.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        steps.setdefault(rec["obj"], []).append(rec["step"])
    for obj, seq in steps.items():
        for a, b in zip(seq, seq[1:], strict=False):
            assert b - a <= 1, "对象 %s 单拍连跳：%s" % (obj, seq)
    # 主体的那个文件对象应当每拍 +1（3 拍 → 至少到过第 3 步）
    file_steps = steps.get("主体/a.md") or []
    assert file_steps and max(file_steps) <= 3


def test_tick_uses_supplied_predictions_and_observations(tmp_path, settings):
    """给出显式 B猜/W回：完全确定性的路径（CI 与复跑用）。"""
    result = run_tick(settings=settings,
                      predictions=[Prediction("X", "大小", "10", tick=1, evidence="p1")],
                      observations=[Observation("X", "大小", "20", "文件:x")])
    assert result.diff_summary["by_kind"] == {"预测内错": 1}
    assert len(result.new_sprouts) == 1


def test_zero_diff_produces_no_sprout(tmp_path, settings):
    """零差异零芽：完全一致的预测与观测 → 一根芽都不生。"""
    result = run_tick(settings=settings,
                      predictions=[Prediction("X", "大小", "10", tick=1, evidence="p1")],
                      observations=[Observation("X", "大小", "10", "文件:x")])
    assert result.diff_summary["by_kind"] == {"预测内对": 1}
    assert result.new_sprouts == []


def test_no_self_sprout_api_exists():
    """结构保证：引擎里**没有**「执行会话登记新芽」的入口（T9 的实现层证据）。"""
    import infinigrow.engine.tick as tick_mod
    exported = vars(tick_mod)
    forbidden = [n for n in exported if "自造" in n or "candidate_sprout" in n
                 or "dispatch_sprout" in n]
    assert forbidden == []


def test_topic_expectation_is_merged_into_the_guess(tmp_path, settings):
    """领到的芽**带着的预期**要并进本拍 B猜——否则「真消解了」会被记成打脸。

    实测踩到过：题面要求某文件存在、执行者建好了，兑现账却记「打脸」——
    因为动手那一拍的预测清单里恰好没有这一条（它来自上一拍组织会话的承诺）。
    判据：造一根带预期的芽（预期来自「预测未执行」那一类：承诺在先、现实没读到）
    → 让这一拍的现实满足它 → 差异类型必须是「预测内对」，兑现判定必须是「兑现」。
    """
    from infinigrow.engine.sprout_queue import SproutQueue

    # 拍 1：只给预测、不给观测 → 「预测未执行」→ 芽带着预期「存在」
    run_tick(settings=settings,
             predictions=[Prediction("主体/x.md", "存在性", "存在", tick=1,
                                     evidence="p1")],
             observations=[])
    layout = resolve_state(settings.state_root, settings.repo_root)
    queue = SproutQueue.load(layout.sprouts, layout.frozen_sprouts)
    assert queue.sprouts and queue.sprouts[0].expected_value == "存在"

    # 拍 2**不**显式给 B猜（默认路径）：引擎应把芽的预期并进去
    result = run_tick(settings=settings, tick=2,
                      observations=[Observation("主体/x.md", "存在性", "存在",
                                                "主体:x.md")])
    kinds = {(d.obj, d.dimension): d.kind.value for d in result.diffs}
    assert kinds[("主体/x.md", "存在性")] == "预测内对"
    assert result.outcomes and result.outcomes[0].redeemed is True
    assert result.predictions.get("topic_expectation") == "存在"


def test_predicted_wrong_does_not_carry_its_stale_expectation(tmp_path, settings):
    """「预测内错」产出的芽**不**带旧预期：现实已经推翻它，派回去＝让执行者改回错的样子。"""
    from infinigrow.engine.sprout_queue import SproutQueue
    run_tick(settings=settings,
             predictions=[Prediction("主体/n.md", "文件数", "1", tick=1, evidence="p1")],
             observations=[Observation("主体/n.md", "文件数", "2", "主体根")])
    layout = resolve_state(settings.state_root, settings.repo_root)
    queue = SproutQueue.load(layout.sprouts, layout.frozen_sprouts)
    assert queue.sprouts and queue.sprouts[0].expected_value is None


def test_act_caused_readings_are_recorded_but_never_spawn(tmp_path, settings):
    """本拍**动作自己造成**的读数变化：入账、进报告，但不派芽（否则是空转）。"""
    subject = tmp_path / "subject"
    subject.mkdir()
    settings = load_settings(env={}, state_root=str(tmp_path / "state"),
                             repo_root=str(REPO_ROOT), subject_root=str(subject))
    settings.cold_start_ticks = 0
    # 先造一根芽（否则本拍无芽可领，执行者根本不会被调用）
    run_tick(settings=settings, tick=1,
             predictions=[Prediction("主体/made.md", "存在性", "存在", tick=1,
                                     evidence="提议新建")],
             observations=[])

    def executor(prompt: str) -> str:
        # 假装执行者动手：往主体里写一个文件（引擎会在动手前后各读一次主体）
        (subject / "made.md").write_text("done\n", encoding="utf-8")
        return "动手：创建 主体/made.md"

    result = run_tick(settings=settings, tick=2, llm=executor, org_session=False)
    assert result.executor is not None, "有芽可领时执行者应当被调用"
    # 动作造成的键（新文件的存在性/字节数、文件数）被标出来
    assert "subject×文件数" in result.act_caused
    assert "主体/made.md×存在性" in result.act_caused
    assert result.new_sprouts == []              # 自己造成的变化不派芽
    layout = resolve_state(settings.state_root, settings.repo_root)
    rows = [json.loads(line) for line in
            layout.diff_ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(r.get("act_caused") for r in rows)   # 但照旧入账（不隐藏）


def test_explicit_predictions_are_not_extended(tmp_path, settings):
    """调用方显式给的 B猜就是全部：引擎不许偷偷往里加芽承诺（可复跑的前提）。"""
    run_tick(settings=settings,
             predictions=[Prediction("主体/x.md", "存在性", "存在", tick=1,
                                     evidence="p1")],
             observations=[Observation("主体/x.md", "存在性", "缺失", "主体:x.md")])
    result = run_tick(settings=settings, tick=2,
                      predictions=[Prediction("别的对象", "大小", "1", tick=2, evidence="p2")],
                      observations=[Observation("别的对象", "大小", "1", "文件:x")])
    assert result.diff_summary["by_kind"] == {"预测内对": 1}
    assert "topic_expectation" not in result.predictions


# ---------------------------------------------------------------- N43 提议闭环
def _journal_subject(tmp_path, name="subject", entries=1):
    """造一个「主体/journal/ 里有 N 格」的现场（测试用，不碰真实主体）。"""
    subject = tmp_path / name
    (subject / "journal").mkdir(parents=True)
    for i in range(entries):
        (subject / "journal" / ("%04d-20260916.md" % (i + 1))).write_text(
            "x\n", encoding="utf-8")
    return subject


def test_relative_expectation_is_anchored_to_pre_action_reality(tmp_path):
    """N43：差额预期（`+1`）在**动手前**的读数上锚成绝对值。

    它承诺的是「再推进一格」，不是提议那一拍的快照——这样芽被领到时目标不会过期。
    """
    subject = _journal_subject(tmp_path)
    settings = load_settings(env={}, state_root=str(tmp_path / "state"),
                             repo_root=str(REPO_ROOT), subject_root=str(subject))
    result = run_tick(settings=settings,
                      predictions=[Prediction("主体/journal/", "文件数", "+1", tick=1,
                                              evidence="计划：本拍在 journal/ 里再长一格")],
                      observations=[Observation("主体/journal/", "文件数", "1",
                                                "主体目录:journal")])
    diff = [d for d in result.diffs if d.key == ("主体/journal/", "文件数")][0]
    assert diff.kind.value == "预测内错"           # 没长出来 → 差异
    assert diff.expected == "2"                    # 锚定成「当前 1 + 1」，不是字面 `+1`


def test_unanchorable_delta_is_left_as_is(tmp_path, settings):
    """锚不上（该量本拍读不到）→ 差额原样保留，不假装成可对账的承诺。"""
    result = run_tick(settings=settings,
                      predictions=[Prediction("主体/nowhere/", "文件数", "+1", tick=1,
                                              evidence="计划：缺依据")],
                      observations=[])
    diff = [d for d in result.diffs if d.key == ("主体/nowhere/", "文件数")][0]
    assert diff.kind.value == "预测未执行" and diff.expected == "+1"


def test_proposal_sprout_is_redeemed_when_the_entry_is_written(tmp_path):
    """N43 端到端：提议「再长一格」→ 芽带差额 → 执行者按**自己的创建拍**命名建下一格 →
    对账判「预测内对」、芽**兑现**（不再有「名字对不上→连领 3 拍耗尽」的白烧）。

    这是 v2.2.5 真机现场的复刻：提议拍 257 写下 `journal/0257-….md`，执行者在拍 291 建出
    `0291-….md` → 芽对象与产物永远对不上。
    """
    subject = _journal_subject(tmp_path)
    settings = load_settings(env={}, state_root=str(tmp_path / "state"),
                             repo_root=str(REPO_ROOT), subject_root=str(subject))
    settings.cold_start_ticks = 0
    # 拍 1：提议（差额）→ 现实没长 → 差异 → 芽（带 `+1`）
    run_tick(settings=settings, tick=1,
             predictions=[Prediction("主体/journal/", "文件数", "+1", tick=1,
                                     evidence="计划：本拍在 journal/ 里再长一格")],
             observations=[Observation("主体/journal/", "文件数", "1", "主体目录:journal")])
    from infinigrow.engine.sprout_queue import SproutQueue
    layout = resolve_state(settings.state_root, settings.repo_root)
    queue = SproutQueue.load(layout.sprouts, layout.frozen_sprouts)
    assert [s.expected_value for s in queue.sprouts] == ["+1"]      # 芽带的是差额
    assert queue.sprouts[0].dimension == "文件数"

    def executor(prompt: str) -> str:
        # 执行者动手：写下一格，文件名按**自己这一拍**的拍号（K7）
        (subject / "journal" / "0002-20260916.md").write_text("下一格\n", encoding="utf-8")
        return "动手：journal/ 再长一格"

    # 拍 2：领到那根芽 → 动手 → W回 → 对账
    result = run_tick(settings=settings, tick=2, llm=executor, org_session=False)
    assert result.topic_sprout == queue.sprouts[0].id
    diff = [d for d in result.diffs if d.key == ("主体/journal/", "文件数")][0]
    assert diff.kind.value == "预测内对" and diff.expected == "2"   # 目标在领做这拍锚定
    assert result.outcomes and result.outcomes[0].redeemed is True
    assert result.outcomes[0].verifiable is True                   # 这个量机械层读得到


def test_tick_number_recovers_from_ledgers_when_heartbeat_is_unreadable(tmp_path, settings):
    """心跳读不出来时**从账本恢复拍号**，不许静默回到 1（否则报告同名覆写）。

    实测现场：心跳在某一瞬读不出 → 旧实现静默当新仓 → 本拍编号回到 1 →
    `reconcile-00001.md` 被覆写、账本拍号跳变（账本跨拍 1-16、心跳却是 2）。
    """
    for tick in (1, 2, 3):
        run_tick(settings=settings, tick=tick)
    layout = resolve_state(settings.state_root, settings.repo_root)
    # 造一个坏心跳（不可解析）
    layout.tick_status.write_text("{ 这不是合法 JSON", encoding="utf-8")
    result = run_tick(settings=settings)                     # 不给拍号 → 走恢复路径
    assert result.tick == 4, "应从账本最大拍号 3 恢复成第 4 拍，而不是回到 1"
    assert any("已从账本恢复" in n for n in result.notes)
    import json as _json
    status = _json.loads(layout.tick_status.read_text(encoding="utf-8"))
    assert status["tick"] == 4 and "已从账本恢复" in status["last_note"]


def test_tick_number_recovers_when_heartbeat_sequence_went_backwards(tmp_path, settings):
    """心跳**可读但拍号落后**（账本最大拍号 > 心跳拍号，序列倒退）也必须从账本恢复。

    v2.2.1 后真机复见：心跳没坏（可读、tick=4），账本却跨拍 1-16——旧恢复逻辑只守
    「不可读」一种触发，新序列 4、5、6… 会逐一覆写旧报告 `reconcile-00004..00016.md`。
    """
    for tick in (1, 2, 3):
        run_tick(settings=settings, tick=tick)
    layout = resolve_state(settings.state_root, settings.repo_root)
    # 造「账本有更大拍号的历史行、心跳却停在 3」的序列倒退现场
    import json as _json
    with layout.diff_ledger.open("a", encoding="utf-8") as fh:
        fh.write(_json.dumps({"tick": 16, "obj": "主体/hist.md", "dimension": "存在性",
                              "expected": "存在", "actual": "存在", "kind": "预测内对",
                              "evidence": "hist", "spawns": False, "source": "mechanical"},
                             ensure_ascii=False) + "\n")
    result = run_tick(settings=settings)                     # 不给拍号 → 走恢复路径
    assert result.tick == 17, "应从账本最大拍号 16 恢复成第 17 拍，而不是继续新序列 4"
    assert any("序列倒退" in n and "已从账本恢复" in n for n in result.notes)
    status = _json.loads(layout.tick_status.read_text(encoding="utf-8"))
    assert status["tick"] == 17 and "序列倒退" in status["last_note"]


# ---------------------------------------------------------------- N48：提醒的出口
def _library_state(layout):
    import json as _json
    return [_json.loads(line) for line in
            layout.library.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_unused_library_sprout_is_not_respawned_when_one_already_exists(tmp_path, settings):
    """M1（N48 真凶）：某对象已在活跃**或冻结**里有一根芽 → 不再立新的。

    现场：库 91 条条目全部已有芽，却每拍再立 ~36 根（去重只扫活跃队列）→ 队列被占满。
    """
    settings.cold_start_ticks = 0
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    for tick in (1, 2):
        run_tick(settings=settings, tick=tick)
    # 造一条「闲置很久」的库条目：它的芽已经躺在冻结区（挂起≠死亡）
    from infinigrow.ledger.store import append_jsonl
    from infinigrow.engine.model import Sprout, SproutOrigin
    from infinigrow.engine.sprout_queue import SproutQueue
    append_jsonl(layout.library, {"name": "主体/old.md", "created_tick": 0,
                                  "last_used_tick": 0, "source": "maturity-cap"},
                 layout.root)
    queue = SproutQueue.load(layout.sprouts, layout.frozen_sprouts, cap=50)
    queue.frozen.append(Sprout(id="lib0002-001-主体_old_md", obj="主体/old.md",
                               dimension="可用性", pointer="p",
                               origin=SproutOrigin.LIBRARY_UNUSED, created_tick=2))
    queue.save(layout.sprouts, layout.frozen_sprouts, layout.root)

    result = run_tick(settings=settings, tick=3, org_session=False)
    assert not any("lib" in s for s in result.new_sprouts), \
        "冻结区已有芽的对象不许再立新芽（N48 的洪泛就是这个缺口）"


def test_library_question_is_closed_after_three_asks(tmp_path, settings):
    """M2：同一库条目被问满 3 次仍无消费 → **结案**（写 `closed_tick`＋结案指针），
    在队芽退场（只移动进冻结区），且此后**不再产芽**。

    这是 G2「提醒没有出口」的机械判据：没有它，「能力库未用」是一条永真、可无限重生的
    提醒——做多少次都不算完成。
    """
    settings.cold_start_ticks = 0
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    run_tick(settings=settings, tick=1)
    from infinigrow.ledger.store import append_jsonl
    from infinigrow.engine.model import Sprout, SproutOrigin
    from infinigrow.engine.sprout_queue import SproutQueue
    append_jsonl(layout.library, {"name": "主体/old.md", "created_tick": 0,
                                  "last_used_tick": 0, "source": "maturity-cap"},
                 layout.root)
    # 一根已经连领满 3 次的库芽（＝被问满上限仍无消费）
    queue = SproutQueue.load(layout.sprouts, layout.frozen_sprouts, cap=50)
    sprout = Sprout(id="lib0002-001-主体_old_md", obj="主体/old.md", dimension="可用性",
                    pointer="能力库:主体/old.md(末次使用拍0)",
                    origin=SproutOrigin.LIBRARY_UNUSED, created_tick=2, leads=3,
                    last_lead_tick=2)
    queue.sprouts.append(sprout)
    queue.save(layout.sprouts, layout.frozen_sprouts, layout.root)

    result = run_tick(settings=settings, tick=3, llm=lambda p: "不动手（夹具）",
                      org_session=False)
    assert "主体/old.md" in result.library.get("closed", [])
    rows = _library_state(layout)
    closed = [r for r in rows if r.get("name") == "主体/old.md" and r.get("closed_tick")]
    assert closed and closed[0]["closed_by"] == "asked-out"
    assert closed[0]["asked"] == 3
    assert closed[0]["closure_pointer"].startswith("留痕:traces/")   # 结案指针指向留痕
    assert sprout.id in result.library.get("retired_by_close", [])   # 在队芽退场（只移动）
    queue2 = SproutQueue.load(layout.sprouts, layout.frozen_sprouts, cap=50)
    assert sprout.id not in {s.id for s in queue2.sprouts}
    assert sprout.id in {s.id for s in queue2.frozen}                # 冻结≠删除

    # 出口是**永久的**：后续各拍不再为这条已结案的条目产芽
    for tick in (4, 5, 6):
        later = run_tick(settings=settings, tick=tick, org_session=False)
        assert not any("主体_old_md" in s for s in later.new_sprouts)


def test_executor_output_marks_library_entry_as_used(tmp_path, settings):
    """M3①：执行者留痕**输出**里出现条目名 → `last_used_tick` 更新（真实更新方），
    且该条目在队的芽退场（问题答完了）；提示词里的题面不算（那是自证）。"""
    settings.cold_start_ticks = 0
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    run_tick(settings=settings, tick=1)
    from infinigrow.ledger.store import append_jsonl
    from infinigrow.engine.model import Sprout, SproutOrigin
    from infinigrow.engine.sprout_queue import SproutQueue
    append_jsonl(layout.library, {"name": "主体/journal/0001-20260915.md",
                                  "created_tick": 0, "last_used_tick": 0,
                                  "source": "maturity-cap"}, layout.root)
    queue = SproutQueue.load(layout.sprouts, layout.frozen_sprouts, cap=50)
    sprout = Sprout(id="lib0002-001-主体_journal_0001", obj="主体/journal/0001-20260915.md",
                    dimension="可用性", pointer="p", origin=SproutOrigin.LIBRARY_UNUSED,
                    created_tick=2)
    queue.sprouts.append(sprout)
    queue.save(layout.sprouts, layout.frozen_sprouts, layout.root)

    result = run_tick(settings=settings, tick=3,
                      llm=lambda p: "本轮动手：读了 journal/0001-20260915.md 并复用它的结论",
                      org_session=False)
    assert "主体/journal/0001-20260915.md" in result.library.get("consumed_this_tick", [])
    rows = _library_state(layout)
    used = [r for r in rows if r.get("name") == "主体/journal/0001-20260915.md"
            and r.get("usage_pointer")]
    assert used and used[0]["last_used_tick"] == 3 and used[0]["source"] == "trace"
    assert sprout.id in result.library.get("retired_by_consumption", [])
