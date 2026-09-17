# -*- coding: utf-8 -*-
"""两个时间闸「到点化」（R5/A3、A4）与证据件合规率（R8/A9）的读数测试。

R5：`status` 必须能看到「还有多远」——容量闸剩余行数（`frozen_cap − 现有行数`）
与重问闸最早可重问拍（引擎口径：只数**候选池里的条目**、只数已冻结满年限的；
与观测层 drill ④ 同源，避免「还差 0 拍」式假警报）。

R8：`status`/对账报告必须能看到「窗口内 cap 领做中，证据件存在比例」——
此前只能人肉数 `app/` 目录，而且对不上账本行；现在与账本行在同一路径函数
（`app_evidence_path`）上对账。
"""
from __future__ import annotations

import json

from infinigrow.cli import main
from infinigrow.core.config import load_settings
from infinigrow.core.paths import REPO_ROOT, resolve_state
from infinigrow.engine.sprout_sources import (app_evidence_compliance,
                                              app_evidence_path,
                                              frozen_requestion_eta,
                                              library_entries)


def _settings(tmp_path, subject=None):
    return load_settings(env={}, state_root=str(tmp_path / "state"),
                         repo_root=str(REPO_ROOT),
                         subject_root=str(subject or (tmp_path / "subject")))


def _write(state, name: str, rows) -> None:
    if isinstance(rows, dict):                        # 单条记录（如心跳）也按行写
        rows = [rows]
    p = state / name
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                 encoding="utf-8")


def test_app_evidence_path_is_shared_by_verdict_and_compliance():
    """合规率读数的路径必须与引擎当初给执行者的**同一个**（否则对不上账）。"""
    obj = "主体/journal/0376-20260916.md"
    assert app_evidence_path(obj, 438) == "app/0438-journal_0376-20260916.md"
    assert app_evidence_path("主体/journal/", 7) == "app/0007-journal.md"
    assert app_evidence_path("", 1) == "app/0001-主体.md"


def test_app_evidence_compliance_counts_real_files(tmp_path):
    """R8 核心：合规率与主体 `app/` 实际文件数一致（机械对账的另一半）。"""
    subject = tmp_path / "subject"
    (subject / "app").mkdir(parents=True)
    rows = [
        {"sprout_id": "cap0443-001-a", "tick": 443, "redeemed": True, "sample": True,
         "verifiable": True, "obj": "主体/journal/0386-20260917.md", "predicted_edge": "固化"},
        {"sprout_id": "cap0449-002-b", "tick": 449, "redeemed": False, "sample": True,
         "verifiable": True, "obj": "主体/journal/0392-20260917.md", "predicted_edge": "固化"},
        {"sprout_id": "cap0200-003-c", "tick": 200, "redeemed": False, "sample": True,
         "verifiable": False, "obj": "主体/old.md", "predicted_edge": "固化"},
    ]
    # 只有 443 那行有证据件（449 那行＝执行者侧未落地，没有）
    (subject / "app" / "0443-journal_0386-20260917.md").write_text("x", encoding="utf-8")
    comp = app_evidence_compliance(rows, subject, tick_from=430)
    assert comp["cap 领做"] == 2                      # 窗口只数近 30 拍
    assert comp["证据件存在"] == 1
    assert comp["合规率"] == 0.5
    assert comp["缺失样例"] == ["app/0449-journal_0392-20260917.md"]
    # 目录里真实文件数与读数一致（验收：「与主体 app/ 实际文件数一致」）
    assert len(list((subject / "app").glob("*.md"))) == comp["证据件存在"]


def test_frozen_requestion_eta_matches_the_drill_engine_caliber():
    """R5 重问 ETA：与观测层 drill ④ 同源口径——
    只数候选池（未结案未消费）里「不活跃且已冻结满年限」的条目。"""
    entries = library_entries([
        {"name": "主体/journal/0247-20260916.md", "created_tick": 200, "last_used_tick": 200,
         "source": "maturity-cap"},
        {"name": "主体/journal/9999.md", "created_tick": 100, "last_used_tick": 150,
         "source": "maturity-cap"},                        # 已消费 → 不在候选池
        {"name": "主体/journal/8888.md", "created_tick": 300, "last_used_tick": 300,
         "source": "maturity-cap", "closed_tick": 310, "closed_by": "asked-out"},
    ])                                                    # 已结案 → 不在候选池
    frozen = [
        {"obj": "主体/journal/0247-20260916.md", "frozen_tick": 325},
        {"obj": "主体/journal/0247-20260916.md", "frozen_tick": 400},   # 最新冻结拍为准
    ]
    eta = frozen_requestion_eta(entries, frozen, active_objs=(), tick=479,
                                requestion_ticks=300)
    assert eta["最早可重问拍"] == 700                     # 400 + 300
    assert eta["最早可重问对象"] == "主体/journal/0247-20260916.md"
    assert eta["还差拍数"] == 221
    # 对象在活跃队列 → 闸不适用（挂起≠死亡）
    eta2 = frozen_requestion_eta(entries, frozen, active_objs=["主体/journal/0247-20260916.md"],
                                 tick=479, requestion_ticks=300)
    assert eta2["最早可重问拍"] is None and eta2["冻结待重问"] == 0
    # 没冻满年限 → 还没到
    eta3 = frozen_requestion_eta(entries, [{"obj": "主体/journal/0247-20260916.md",
                                            "frozen_tick": 450}],
                                 active_objs=(), tick=479, requestion_ticks=300)
    assert eta3["最早可重问拍"] == 750 and eta3["还差拍数"] == 271


def test_status_shows_capacity_left_and_requestion_eta(tmp_path, capsys):
    """R5 验收：`status` 出现两行——容量闸剩多少行、重问最早可重问拍。"""
    state = tmp_path / "state"
    state.mkdir()
    _write(state, "outcomes.jsonl", [])
    _write(state, "sprouts-frozen.jsonl", [
        {"id": "f1", "obj": "主体/journal/0247-20260916.md", "dimension": "存在性",
         "pointer": "差异账:x", "frozen_tick": 325, "origin": "差异对账",
         "created_tick": 300, "leads": 0},               # 冻结 1 行
    ])
    _write(state, "sprouts.jsonl", [])
    _write(state, "library.jsonl", [
        {"name": "主体/journal/0247-20260916.md", "created_tick": 200,
         "last_used_tick": 200, "source": "maturity-cap"},
    ])
    _write(state, "tick_status.json", {"tick": 479})
    rc_ = main(["--state-root", str(state), "status"])
    out = capsys.readouterr().out
    assert rc_ == 0
    assert "冻结区容量闸：1 行／上限 5000（剩 4999 行）" in out
    assert "重问闸：最早可重问拍 625（主体/journal/0247-20260916.md" in out
    assert "还差 146 拍" in out


def test_status_shows_evidence_compliance_line(tmp_path, capsys):
    """R8 验收：`status` 出现「证据件合规率」一行，且与主体实际文件数一致。"""
    state = tmp_path / "state"
    state.mkdir()
    subject = tmp_path / "subject"
    (subject / "app").mkdir(parents=True)
    (subject / "app" / "0455-journal_0400-20260917.md").write_text("x", encoding="utf-8")
    _write(state, "outcomes.jsonl", [
        {"sprout_id": "cap0455-001-a", "tick": 455, "redeemed": True, "sample": True,
         "verifiable": True, "obj": "主体/journal/0400-20260917.md", "predicted_edge": "固化"},
        {"sprout_id": "cap0460-002-b", "tick": 460, "redeemed": False, "sample": True,
         "verifiable": True, "obj": "主体/journal/0405-20260917.md", "predicted_edge": "固化"},
    ])
    _write(state, "sprouts-frozen.jsonl", [])
    _write(state, "sprouts.jsonl", [])
    _write(state, "library.jsonl", [])
    _write(state, "tick_status.json", {"tick": 479})
    rc_ = main(["--state-root", str(state), "--subject-root", str(subject), "status"])
    out = capsys.readouterr().out
    assert rc_ == 0
    assert "证据件合规率（近 30 拍 cap 领做）：1/2 = 0.50" in out
    assert "缺失：app/0460-journal_0405-20260917.md" in out


def test_reconcile_report_includes_the_compliance_line(tmp_path):
    """R8 验收（报告侧）：对账报告的兑现率段也带合规率（status 的完整版同源）。"""
    from infinigrow.engine.tick import run_tick
    subject = tmp_path / "subject"
    (subject / "journal").mkdir(parents=True)
    (subject / "journal" / "0001-20260917.md").write_text("x", encoding="utf-8")
    settings = _settings(tmp_path, subject)
    settings.cold_start_ticks = 0
    layout = resolve_state(settings.state_root, settings.repo_root)
    layout.root.mkdir(parents=True, exist_ok=True)
    layout.sprouts.write_text(json.dumps({
        "id": "cap0001-001-主体_journal_0001-20260917", "obj": "主体/journal/0001-20260917.md",
        "dimension": "应用面", "pointer": "成熟链:x@拍1", "origin": "成熟链封顶",
        "created_tick": 1, "predicted_edge": "固化", "maturity_step": 4,
        "leads": 0, "last_lead_tick": None, "long_task": False,
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    layout.frozen_sprouts.write_text("", encoding="utf-8")
    run_tick(settings=settings, tick=1, llm=lambda prompt: "不动手（夹具）", org_session=False)
    report = layout.reconcile_dir / "reconcile-00001.md"
    text = report.read_text(encoding="utf-8")
    assert "证据件合规率（近 30 拍 cap 领做）" in text
    assert "0/1 = 0.00" in text


# --------------------------------------------------------------- R2/N69：执行者侧损耗
def test_executor_side_loss_counts_unparsed_traces(tmp_path):
    """R2 读数：与打脸归因**同源**（同一字面标记）；缺留痕不计入分母（零样本≠通过）。"""
    from infinigrow.engine.reconcile import executor_side_loss
    traces = tmp_path / "traces"
    traces.mkdir()
    (traces / "tick-00010.md").write_text("## 输出（原样）\n\n正常输出\n", encoding="utf-8")
    (traces / "tick-00011.md").write_text(
        "留痕说明：第 1 轮输出不是 JSON，按最终留痕处理\n", encoding="utf-8")
    (traces / "tick-00012.md").write_text("正常\n", encoding="utf-8")
    loss = executor_side_loss(traces, tick_now=12, window=10)
    assert loss["留痕"] == 3 and loss["回退"] == 1
    assert abs(loss["比例"] - 1 / 3) < 1e-9
    empty = executor_side_loss(tmp_path / "none", tick_now=12, window=10)
    assert empty["留痕"] == 0 and empty["比例"] is None      # 零样本 → 不可计算，不写 0 假数
    windowed = executor_side_loss(traces, tick_now=12, window=2)   # 窗口只覆盖 11/12 两拍
    assert windowed["留痕"] == 2 and windowed["回退"] == 1


def test_status_shows_executor_side_loss_line(tmp_path, capsys):
    """R2 验收：`status` 出现「执行者侧损耗」一行（修复未授权时损耗也长期可见）。"""
    state = tmp_path / "state"
    state.mkdir()
    traces = state / "traces"
    traces.mkdir()
    (traces / "tick-00479.md").write_text(
        "留痕说明：第 1 轮输出不是 JSON，按最终留痕处理\n", encoding="utf-8")
    _write(state, "outcomes.jsonl", [])
    _write(state, "sprouts-frozen.jsonl", [])
    _write(state, "sprouts.jsonl", [])
    _write(state, "library.jsonl", [])
    _write(state, "tick_status.json", {"tick": 479})
    rc_ = main(["--state-root", str(state), "status"])
    out = capsys.readouterr().out
    assert rc_ == 0
    assert "执行者侧损耗（近 10 拍）：回退 1/1 份留痕＝1.00" in out


# --------------------------------------------------------------- R9/E5：用量按芽源分账
def test_usage_split_buckets_tokens_by_sprout_source(tmp_path, capsys):
    """R9：join 键＝拍号——同一拍的调用归到那拍领做的芽源；无题与未报单列不摊派。

    S1/A4（v2.2.23）：组织会话（kind=org-session，不领芽）独立一桶入分账——
    各桶次之和＝「今日执行者调用」总数，分账不许丢调用。
    """
    import datetime as dt
    state = tmp_path / "state"
    state.mkdir()
    today = dt.date.today().isoformat()
    _write(state, "executor.jsonl", [
        {"tick": 10, "kind": "tick", "rc": 0, "usage": {"total_tokens": 1000},
         "time": today + " 10:00:00"},
        {"tick": 11, "kind": "tick", "rc": 0, "usage": {"total_tokens": 500},
         "time": today + " 10:10:00"},
        {"tick": 12, "kind": "tick", "rc": 1, "usage": "unknown",
         "time": today + " 10:20:00"},                       # 无题拍：没领到芽
        {"tick": 11, "kind": "org-session", "rc": 0, "usage": {"total_tokens": 777},
         "time": today + " 10:11:00"},                        # 组织会话＝独立桶
    ])
    _write(state, "outcomes.jsonl", [
        {"sprout_id": "cap0010-001-x", "tick": 10, "redeemed": True, "sample": True,
         "verifiable": True, "obj": "主体/x.md", "predicted_edge": "固化"},
        {"sprout_id": "sp0011-001-y", "tick": 11, "redeemed": True, "sample": True,
         "verifiable": True, "obj": "主体/y.md", "predicted_edge": "判读"},
    ])
    _write(state, "sprouts-frozen.jsonl", [])
    _write(state, "sprouts.jsonl", [])
    _write(state, "library.jsonl", [])
    _write(state, "tick_status.json", {"tick": 12})
    rc_ = main(["--state-root", str(state), "status"])
    out = capsys.readouterr().out
    assert rc_ == 0
    assert "用量分账（今日，按芽源）" in out
    assert "cap 1 次／1000 token" in out
    assert "sp 1 次／500 token" in out
    assert "（无题） 1 次／0 token（未报 1）" in out
    assert "组织会话 1 次／777 token" in out
    # S1/A4 验收：各桶次之和＝今日执行者调用总数（4 次＝3 tick＋1 org-session）
    assert "今日执行者调用：4 次" in out
    import re
    bucket_times = sum(int(m.group(1)) for m in
                       re.finditer(r"(?:cap|sp|lib|组织会话|（无题）) (\d+) 次", out))
    assert bucket_times == 4
