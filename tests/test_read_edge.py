# -*- coding: utf-8 -*-
"""判读边可对账化（R1/A1、A2）：让差异源 `判读`（READ）与能力库「可用性」边
**机械可对账**，把「读得到但判不出」变成「读了留痕就能判」。

问题（[已证明] 现场）：判读芽的对象是「预测外新出现」的老 journal 文件，领做拍
已滚出「mtime 最新 N」的观测名额（`SUBJECT_FILE_LIMIT`）→ `observable_keys` 里没有
它的键 → 近 30 拍 8/9 不可对账、`verifiable=false` **永不翻**（分子分母都不计，
但占取题位）。lib 芽（edge=原理，维度「可用性」）同步同病：历史 179 行全不可对账。

修法（方案 A＝零新文件）：兑现判据改读**本拍执行者输出**里对「源对象」的字面点名
（全名或主体内相对写法），与引擎既有 M3「留痕命中＝已用」同一段输出、同一套
命中判据（`sprout_sources.entry_mentioned`）。命不中是**可机械判的**：
`verifiable` 恒 True、未命中＝如实记打脸（读得到却留不下，是「没做」，不是「读不到」
——与固化边证据件判据同构）。

验收（逐条对账）：
  1. 判读芽＋输出点名（全名）→ `verifiable=true` 且 `redeemed=true`；
  2. 判读芽＋输出点名（主体内相对写法）→ 同上（与 M3 同一套命中写法）；
  3. 判读芽＋输出没点名 → `verifiable=true` 但 `redeemed=false`（打脸，不是不可对账）；
  4. 判读芽＋调用方没给留痕（旧路径）→ 行为与从前一致（observable_keys 判）；
  5. lib 芽（可用性边）用同一判据：点名＝兑现，没点名＝打脸；
  6. 非判读/非 lib 芽给了留痕也不受影响（老判据）。
"""
from __future__ import annotations

import json

from infinigrow.core.config import load_settings
from infinigrow.core.paths import REPO_ROOT, resolve_state
from infinigrow.engine.model import Edge, Sprout, SproutOrigin
from infinigrow.engine.tick import evaluate_outcome, run_tick


def _settings(tmp_path, subject=None):
    return load_settings(env={}, state_root=str(tmp_path / "state"),
                         repo_root=str(REPO_ROOT),
                         subject_root=str(subject or (tmp_path / "subject")))


def _read_sprout(obj="主体/journal/0038-20260916.md", tick=38):
    """差异源 `判读` 芽：现实给了新东西而没预测到 → 先看懂（READ 边）。"""
    return Sprout(id="sp0038-001-主体_journal_0038-20260916", obj=obj,
                  dimension="存在性",
                  pointer="本拍现实变化：新出现 %s" % obj,
                  origin=SproutOrigin.DIFF, created_tick=tick,
                  predicted_edge=Edge.READ)


def _lib_sprout(name="主体/journal/0038-20260916.md", tick=38):
    """能力库「可用性」芽：历史 179 行全 `verifiable=false` 的同族。"""
    return Sprout(id="lib0038-001-主体_journal_0038-20260916", obj=name,
                  dimension="可用性",
                  pointer="能力库:%s(末次使用拍7)" % name,
                  origin=SproutOrigin.LIBRARY_UNUSED, created_tick=tick,
                  predicted_edge=Edge.PRINCIPLE)


def _act_sprout(obj="主体/journal/", tick=38):
    """非判读、非 lib 的差异芽（行动边）——对照组：不受留痕判据影响。"""
    return Sprout(id="sp0038-002-主体_journal_", obj=obj, dimension="文件数",
                  pointer="差异账:拍31预测未执行|%s" % obj,
                  origin=SproutOrigin.DIFF, created_tick=tick,
                  predicted_edge=Edge.ACT, expected_value="+1")


def test_read_edge_redeems_on_full_name_mention():
    """验收 1：判读芽＋输出点名（全名）→ 可对账且兑现。"""
    sprout = _read_sprout()
    out = evaluate_outcome(sprout, [], 38, sampled=True,
                           observable_keys=[], reader_text="看到 %s 存在，内容已读。"
                           % sprout.obj)
    assert out.verifiable is True and out.redeemed is True
    assert out.actual_edge == "判读"


def test_read_edge_redeems_on_relative_name_mention():
    """验收 2：主体内相对写法（M3 同一套命中写法）同样算点名。"""
    sprout = _read_sprout()
    out = evaluate_outcome(sprout, [], 38, sampled=True,
                           observable_keys=[], reader_text="读过了 journal/0038-20260916.md，"
                           "记录了认知。")
    assert out.verifiable is True and out.redeemed is True


def test_read_edge_is_redemption_failure_not_unverifiable_when_not_named():
    """验收 3：输出没点名 → 打脸但**可对账**（读得到 ≠ 读不到）。"""
    sprout = _read_sprout()
    out = evaluate_outcome(sprout, [], 38, sampled=True,
                           observable_keys=[], reader_text="没有可读的新东西。")
    assert out.verifiable is True and out.redeemed is False
    assert out.actual_edge is None


def test_read_edge_falls_back_to_old_judgement_without_reader_text():
    """验收 4：调用方没给留痕（旧路径/老调用方）→ 行为与从前一致。"""
    sprout = _read_sprout()
    # 老现场：该对象不在本拍 observable_keys 里 → 如实标不可对账（不假装打脸）
    out = evaluate_outcome(sprout, [], 38, sampled=True, observable_keys=[])
    assert out.verifiable is False and out.redeemed is False
    # 在观测里 → 老判据照旧判
    out2 = evaluate_outcome(sprout, [], 38, sampled=True,
                            observable_keys=[sprout.key, ("主体/别的文件.md", "存在性")])
    assert out2.verifiable is True


def test_library_edge_uses_the_same_reader_verdict():
    """验收 5：lib 芽（可用性边）同一判据——点名＝兑现，没点名＝打脸。"""
    sprout = _lib_sprout()
    hit = evaluate_outcome(sprout, [], 38, sampled=True,
                           observable_keys=[], reader_text="答案：%s 没被用于别的域，"
                           "因为它只对 journal 成立。" % sprout.obj)
    assert hit.verifiable is True and hit.redeemed is True
    miss = evaluate_outcome(sprout, [], 38, sampled=True,
                            observable_keys=[], reader_text="没查到可用线索。")
    assert miss.verifiable is True and miss.redeemed is False


def test_non_reader_edges_are_unaffected_by_reader_text():
    """验收 6：行动边/原理边给了留痕文本也不走留痕判据（老判据不动）。"""
    sprout = _act_sprout()
    out = evaluate_outcome(sprout, [], 38, sampled=True,
                           observable_keys=[], reader_text="主体/journal/ 的文件数变了。")
    # 本拍 observable_keys 里没有 (目录, 文件数) → 如实不可对账（判据没被留痕牵着走）
    assert out.verifiable is False
    out2 = evaluate_outcome(sprout, [], 38, sampled=True,
                            observable_keys=[sprout.key], reader_text="随便写什么")
    assert out2.verifiable is True and out2.redeemed is False


def test_dir_object_read_edge_needs_the_full_name():
    """目录对象（名字以 / 结尾）只认全名——`entry_mentioned` 的窄判据（M3 既有规则）。"""
    sprout = _read_sprout(obj="主体/journal/")
    out = evaluate_outcome(sprout, [], 38, sampled=True, observable_keys=[],
                           reader_text="今天我往 journal/ 里写了一篇。")
    assert out.verifiable is True and out.redeemed is False      # 相对写法不算目录点名
    out2 = evaluate_outcome(sprout, [], 38, sampled=True, observable_keys=[],
                            reader_text="读了主体/journal/ 下的全部。")
    assert out2.redeemed is True


def test_tick_prompt_tells_the_executor_about_the_reader_verdict(tmp_path):
    """题面写明判据（与 cap 芽条款对称）：执行者不该靠猜判据留痕。"""
    from infinigrow.engine.tick import build_tick_prompt
    subject = tmp_path / "subject"
    (subject / "journal").mkdir(parents=True)
    (subject / "journal" / "0038-20260916.md").write_text("x", encoding="utf-8")
    settings = _settings(tmp_path, subject)
    layout = resolve_state(settings.state_root, settings.repo_root)
    prompt = build_tick_prompt(settings, layout, 42, _read_sprout(), [], subject)
    assert "留痕点名" in prompt
    assert "主体/journal/0038-20260916.md" in prompt
    assert "journal/0038-20260916.md" in prompt


def _write_queue(layout, sprout):
    layout.root.mkdir(parents=True, exist_ok=True)
    layout.sprouts.write_text(json.dumps(sprout.as_record(), ensure_ascii=False) + "\n",
                              encoding="utf-8")
    layout.frozen_sprouts.write_text("", encoding="utf-8")


def test_end_to_end_read_sprout_is_redeemed_when_liuhen_names_the_object(tmp_path):
    """真机形态：判读芽被领、执行者输出点名 → 兑现账 `verifiable=true, redeemed=true`。"""
    subject = tmp_path / "subject"
    (subject / "journal").mkdir(parents=True)
    (subject / "journal" / "0038-20260916.md").write_text("x", encoding="utf-8")
    settings = _settings(tmp_path, subject)
    settings.cold_start_ticks = 0
    layout = resolve_state(settings.state_root, settings.repo_root)
    _write_queue(layout, _read_sprout())
    run_tick(settings=settings, tick=1, llm=lambda prompt: "读完了 journal/0038-20260916.md，"
             "这是一篇组织会话留痕。", org_session=False)
    rows = [json.loads(line) for line in
            layout.outcome_ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[-1]["sprout_id"].startswith("sp")
    assert rows[-1]["predicted_edge"] == "判读"
    assert rows[-1]["verifiable"] is True and rows[-1]["redeemed"] is True
    assert rows[-1]["actual_edge"] == "判读"


def test_end_to_end_read_sprout_is_a_verifiable_miss_without_naming(tmp_path):
    """真机形态：执行者没点名 → 打脸但可对账（不再是不可对账的悬案）。"""
    subject = tmp_path / "subject"
    (subject / "journal").mkdir(parents=True)
    (subject / "journal" / "0038-20260916.md").write_text("x", encoding="utf-8")
    settings = _settings(tmp_path, subject)
    settings.cold_start_ticks = 0
    layout = resolve_state(settings.state_root, settings.repo_root)
    _write_queue(layout, _read_sprout())
    run_tick(settings=settings, tick=1, llm=lambda prompt: "本拍无变化。", org_session=False)
    rows = [json.loads(line) for line in
            layout.outcome_ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[-1]["predicted_edge"] == "判读"
    assert rows[-1]["verifiable"] is True and rows[-1]["redeemed"] is False
