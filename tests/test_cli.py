# -*- coding: utf-8 -*-
"""CLI 测试（T8/A15）：`status` 一键总览与 `pause`/`resume`。

验收判据（可复跑）：
  1. `python -m infinigrow status` 打印含「拍号 / 主体文件数 / 兑现率判定 / ALERT 首行」；
  2. `pause` 后计划任务 State=Disabled，`resume` 后回 Ready（**不删**）——
     真机动作在会话里实测；本测试锁「非 Windows 拒绝」与「status 结构」两条纯机械面。
"""
from __future__ import annotations

import json

from infinigrow.cli import main


def _write_state(tmp_path, state="state"):
    """造一个最小状态根（status 只读它，不需要真实拍）。

    时间戳用**今天**（`datetime.date.today()`）：`status` 的「今日执行者调用」按当天
    过滤——写死历史日期会让这个测试跨天就红（不是功能回归）。
    """
    import datetime as _dt
    today = _dt.date.today().isoformat()
    root = tmp_path / state
    (root / "reconcile").mkdir(parents=True, exist_ok=True)
    (root / "traces").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / "archive").mkdir(parents=True, exist_ok=True)
    (root / "tick_status.json").write_text(json.dumps({
        "consecutive_failures": 0, "consecutive_executor_failures": 1,
        "last_rc": 0, "last_executor_rc": 1,
        "last_time": "%s 19:00:00" % today,
        "tick": 17, "engine_version": "2.2.1", "engine_commit": "test"},
        ensure_ascii=False), encoding="utf-8")
    (root / "subject.json").write_text(json.dumps({
        "root_name": "subject-test", "exists": True, "file_count": 3,
        "total_bytes": 1024}, ensure_ascii=False), encoding="utf-8")
    (root / "sprouts.jsonl").write_text("", encoding="utf-8")
    (root / "sprouts-frozen.jsonl").write_text("", encoding="utf-8")
    (root / "outcomes.jsonl").write_text(
        json.dumps({"sprout_id": "sp0001-001-x", "predicted_edge": "判读",
                    "actual_edge": "判读", "redeemed": True, "pointer": "p",
                    "tick": 16, "sample": True, "verifiable": True, "obj": "主体/x.md"},
                   ensure_ascii=False) + "\n", encoding="utf-8")
    (root / "executor.jsonl").write_text(
        json.dumps({"command": "x", "kind": "tick", "rc": 0, "duration_ms": 100,
                    "tick": 16, "time": "%s 19:00:00" % today,
                    "usage": {"total_tokens": 1200}}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    (root / "ALERT.md").write_text("# 引擎正常（%s 19:00:00）\n\n- 无致命旗\n" % today,
                                   encoding="utf-8")
    return root


def test_status_prints_required_fields(tmp_path, capsys):
    root = _write_state(tmp_path)
    code = main(["--state-root", str(root), "status"])
    out = capsys.readouterr().out
    assert code == 0
    assert "拍号：17" in out                        # 拍号
    assert "主体：subject-test" in out and "文件 3 个" in out   # 主体文件数
    assert "兑现率：有样本" in out and "1.00" in out            # 兑现率判定
    assert "ALERT 首行：# 引擎正常" in out          # ALERT 首行
    assert "今日执行者调用：1 次" in out and "token 合计 1200" in out  # 用量段
    assert "可领 0 根／共 0 根" in out              # K4/A5：队列口径（空队列）


def test_status_shows_claimable_count(tmp_path, capsys):
    """K4/A5：status 显示「可领 N 根／共 M 根」——可领≠活跃（leads<3 才算）。"""
    root = _write_state(tmp_path)
    from infinigrow.engine.model import Sprout, SproutOrigin
    rows = [
        Sprout(id="sp0001-001-x", obj="主体/a.md", dimension="存在性", pointer="p",
               origin=SproutOrigin.DIFF, created_tick=10, leads=3).as_record(),  # 已耗尽
        Sprout(id="sp0001-002-y", obj="主体/b.md", dimension="存在性", pointer="p",
               origin=SproutOrigin.DIFF, created_tick=11, leads=1).as_record(),  # 可领
    ]
    (root / "sprouts.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8")
    code = main(["--state-root", str(root), "status"])
    out = capsys.readouterr().out
    assert code == 0
    assert "可领 1 根／共 2 根" in out              # 1 根可领（leads=1），共 2 根
    assert "活跃 2" in out                         # 活跃仍是 2（非冻结行数）


def test_status_shows_idle_streak(tmp_path, capsys):
    """K8/A6：status 显示「连续 N 拍无芽可领」（空转成本显形）。"""
    root = _write_state(tmp_path)
    status = json.loads((root / "tick_status.json").read_text(encoding="utf-8"))
    status["no_ticket_streak"] = 9
    (root / "tick_status.json").write_text(json.dumps(status, ensure_ascii=False),
                                           encoding="utf-8")
    code = main(["--state-root", str(root), "status"])
    out = capsys.readouterr().out
    assert code == 0
    assert "空转：连续 9 拍无芽可领" in out


def test_status_lists_failed_unknown_usage(tmp_path, capsys):
    """K9/A10：失败调用 usage=unknown 单列（成本账不假装失败不存在）。"""
    root = _write_state(tmp_path)
    import datetime as _dt
    today = _dt.date.today().isoformat()
    (root / "executor.jsonl").write_text(
        json.dumps({"command": "x", "kind": "tick", "rc": 1, "duration_ms": 100,
                    "tick": 17, "time": "%s 19:05:00" % today,
                    "usage": "unknown"}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    code = main(["--state-root", str(root), "status"])
    out = capsys.readouterr().out
    assert code == 0
    assert "失败未计费/未知" in out and "usage=unknown" in out


def test_status_shows_alert_line_even_when_state_minimal(tmp_path, capsys):
    root = _write_state(tmp_path)
    (root / "outcomes.jsonl").write_text("", encoding="utf-8")
    code = main(["--state-root", str(root), "status"])
    out = capsys.readouterr().out
    assert code == 0
    assert "兑现率：无样本" in out                  # 无样本＝诚实呈现，不是 0


def test_pause_resume_refused_on_non_windows(tmp_path, monkeypatch, capsys):
    """非 Windows：pause/resume 不上手（环境不满足，rc=4），不许假装成功。"""
    monkeypatch.setattr("infinigrow.cli.sys.platform", "linux")
    code = main(["--state-root", str(tmp_path), "pause"])
    out = capsys.readouterr().out
    assert code == 4 and "仅 Windows" in out
    code = main(["--state-root", str(tmp_path), "resume"])
    out = capsys.readouterr().out
    assert code == 4 and "仅 Windows" in out
