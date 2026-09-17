# -*- coding: utf-8 -*-
"""固化边可对账化（Q2/A3/N60）：让「应用面」变成一条**机械可对账**的边。

问题（[已证明] 现场）：`cap*`（成熟链封顶 → 开应用面）的维度「应用面」机械层读不到 →
兑现永远判不出：累计 160 次领做、`verifiable=true` **0 条**，而它占着取题位的一大块
（最近 30 拍 24/31）。修法：执行者在主体里留一份**应用证据件**（约定路径由引擎给），
引擎按**它的存在性**对账——「应用发生了」于是有了机械形态。

验收（逐条对账）：
  1. 证据路径由引擎规定，机械可重算（同芽同拍 → 同一路径）；
  2. 证据件存在 → 该 cap 芽的兑现账行 **`verifiable=true` 且 `redeemed=true`**；
  3. 证据件缺失 → 同样 `verifiable=true`，但 `redeemed=false`（读得到，所以是「没做」）；
  4. 证据键不进成熟链、不产芽（它是**记录**，不是域对象）；
  5. `status` 的「固化边」计数随之下降（可对账的行不再落进那个桶）。
"""
from __future__ import annotations

import json

from infinigrow.core.config import load_settings
from infinigrow.core.paths import REPO_ROOT, resolve_state
from infinigrow.engine.sprout_sources import (APP_EVIDENCE_DIR, app_evidence_object,
                                             app_evidence_relpath, is_app_edge)
from infinigrow.engine.model import Edge, Sprout, SproutOrigin
from infinigrow.engine.reconcile import redemption_report
from infinigrow.engine.tick import run_tick


def _settings(tmp_path, subject=None):
    return load_settings(env={}, state_root=str(tmp_path / "state"),
                         repo_root=str(REPO_ROOT),
                         subject_root=str(subject or (tmp_path / "subject")))


def _cap_sprout(obj="主体/journal/0001-20260917.md", tick=1):
    return Sprout(id="cap0001-001-主体_journal_0001-20260917", obj=obj,
                  dimension="应用面", pointer="成熟链:%s@拍%d" % (obj, tick),
                  origin=SproutOrigin.MATURITY_CAP, created_tick=tick,
                  predicted_edge=Edge.SOLIDIFY, maturity_step=4)


def _write_queue(layout, sprout):
    layout.root.mkdir(parents=True, exist_ok=True)
    layout.sprouts.write_text(json.dumps(sprout.as_record(), ensure_ascii=False) + "\n",
                              encoding="utf-8")
    layout.frozen_sprouts.write_text("", encoding="utf-8")


def test_evidence_path_is_a_mechanical_function_of_sprout_and_tick():
    """路径由引擎规定（不让执行者猜）：同芽同拍永远同一路径，且落在 `app/` 下。"""
    sprout = _cap_sprout()
    assert app_evidence_relpath(sprout, 438) == "app/0438-journal_0001-20260917.md"
    assert app_evidence_object(sprout, 438) == "主体/app/0438-journal_0001-20260917.md"
    assert app_evidence_relpath(sprout, 438).startswith(APP_EVIDENCE_DIR + "/")
    # 目录对象（名字以 / 结尾）也有一份：`主体/journal/` → `journal.md`
    assert app_evidence_relpath(_cap_sprout(obj="主体/journal/"), 7) == "app/0007-journal.md"
    assert is_app_edge(sprout) is True
    assert is_app_edge(Sprout(id="x", obj="主体/a.md", dimension="存在性", pointer="p",
                              origin=SproutOrigin.DIFF, created_tick=1)) is False


def test_cap_edge_is_redeemed_only_when_the_evidence_file_exists(tmp_path):
    """真机形态（验收 2/3）：证据件存在＝兑现且**可对账**；缺失＝打脸但同样可对账。"""
    subject = tmp_path / "subject"
    (subject / "journal").mkdir(parents=True)
    (subject / "journal" / "0001-20260917.md").write_text("x", encoding="utf-8")
    settings = _settings(tmp_path, subject)
    settings.cold_start_ticks = 0
    layout = resolve_state(settings.state_root, settings.repo_root)

    # ① 执行者不写证据件 → 打脸，但这一行是**可对账**的（读得到 ≠ 读不到）
    _write_queue(layout, _cap_sprout())
    run_tick(settings=settings, tick=1, llm=lambda prompt: "不动手（夹具）", org_session=False)
    rows = [json.loads(line) for line in
            layout.outcome_ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[-1]["sprout_id"].startswith("cap")
    assert rows[-1]["verifiable"] is True and rows[-1]["redeemed"] is False

    # ② 执行者按题面给的路径写了证据件 → 兑现且可对账
    (subject / "app").mkdir()
    (subject / "app" / "0002-journal_0001-20260917.md").write_text("应用记录", encoding="utf-8")
    _write_queue(layout, _cap_sprout())
    run_tick(settings=settings, tick=2, llm=lambda prompt: "不动手（夹具）", org_session=False)
    rows = [json.loads(line) for line in
            layout.outcome_ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[-1]["verifiable"] is True and rows[-1]["redeemed"] is True
    assert rows[-1]["actual_edge"] == "固化"


def test_evidence_key_neither_spawns_nor_advances_maturity(tmp_path):
    """验收 4：证据键是**记录**不是域对象——不产芽（否则每拍失败都堆一根不可完成的芽）、
    不推成熟链（否则每份证据件都会被当成新域对象进能力库）。"""
    subject = tmp_path / "subject"
    (subject / "journal").mkdir(parents=True)
    (subject / "journal" / "0001-20260917.md").write_text("x", encoding="utf-8")
    settings = _settings(tmp_path, subject)
    settings.cold_start_ticks = 0
    layout = resolve_state(settings.state_root, settings.repo_root)
    _write_queue(layout, _cap_sprout())
    run_tick(settings=settings, tick=1, llm=lambda prompt: "不动手（夹具）", org_session=False)

    evidence_obj = app_evidence_object(_cap_sprout(), 1)
    diffs = [json.loads(line) for line in
             layout.diff_ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    evidence_diffs = [d for d in diffs if d["obj"] == evidence_obj]
    assert evidence_diffs, "证据件必须在差异账里留一行（应用发生没发生，机械可查）"
    # 差异照记（事实不隐藏），另有「不派芽」的标记（与 act_caused 同一套写法）
    assert all(d.get("app_evidence") is True for d in evidence_diffs)
    sprout_ids = [json.loads(line)["id"] for line in
                  layout.sprouts.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert not [s for s in sprout_ids if "app_" in s], "证据件不产芽"
    maturity = layout.maturity_chain.read_text(encoding="utf-8")
    assert evidence_obj not in maturity, "证据件不进成熟链"


def test_redemption_report_moves_cap_rows_into_the_denominator(tmp_path):
    """验收 5：可对账的 cap 行不再落进「固化边」桶——计数开始下降。"""
    rows = [
        {"sprout_id": "cap0001-001-a", "tick": 1, "redeemed": True, "sample": True,
         "verifiable": True, "obj": "主体/x.md", "predicted_edge": "固化"},
        {"sprout_id": "cap0001-002-b", "tick": 1, "redeemed": False, "sample": True,
         "verifiable": False, "obj": "主体/y.md", "predicted_edge": "固化"},
    ]
    report = redemption_report(rows)
    assert report["样本数"] == 1 and report["兑现率"] == 1.0
    assert report["固化边"]["n"] == 1          # 只剩读不到的那一行
    assert "cap0001-001-a" not in report["固化边"]["单独列出"]


def test_tick_prompt_hands_the_executor_the_exact_evidence_path(tmp_path):
    """题面必须**逐字给出**路径：判据要公平——执行者不该靠猜命名。"""
    from infinigrow.engine.tick import build_tick_prompt
    subject = tmp_path / "subject"
    (subject / "journal").mkdir(parents=True)
    (subject / "journal" / "0001-20260917.md").write_text("x", encoding="utf-8")
    settings = _settings(tmp_path, subject)
    layout = resolve_state(settings.state_root, settings.repo_root)
    prompt = build_tick_prompt(settings, layout, 42, _cap_sprout(), [], subject)
    assert "固化边" in prompt
    assert app_evidence_relpath(_cap_sprout(), 42) in prompt


def test_status_shows_the_windowed_cap_edge_reading(tmp_path, capsys):
    """验收口径（Q2）：`status` 必须能看出「这条边接上了没有」。

    累计桶（固化边）建在**追加型账本**上，只增不减（旧行不会消失），所以它的绝对值说明不了
    改造效果——机械读数＝**最近 30 拍新领做的 cap 行里有多少是可对账的**：接上证据边之后
    这个比例从 0 变成 1（滚动窗口里改造前的旧行随时间退出）。
    """
    from infinigrow.cli import main
    state = tmp_path / "state"
    state.mkdir()
    rows = [
        {"sprout_id": "cap0418-001-a", "tick": 418, "redeemed": False, "sample": True,
         "verifiable": False, "obj": "主体/x.md", "predicted_edge": "固化"},
        {"sprout_id": "cap0443-002-b", "tick": 443, "redeemed": True, "sample": True,
         "verifiable": True, "obj": "主体/y.md", "predicted_edge": "固化"},
        {"sprout_id": "cap0100-003-c", "tick": 100, "redeemed": False, "sample": True,
         "verifiable": False, "obj": "主体/z.md", "predicted_edge": "固化"},
    ]
    (state / "outcomes.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    (state / "tick_status.json").write_text(json.dumps({"tick": 445}), encoding="utf-8")
    rc_ = main(["--state-root", str(state), "status"])
    out = capsys.readouterr().out
    assert rc_ == 0
    assert "固化边（应用面，未接证据边的行）：2 条累计" in out     # 两条不可对账的旧行
    assert "最近 30 拍 cap 领做 2 次，可对账 1（不可对账 1）" in out
