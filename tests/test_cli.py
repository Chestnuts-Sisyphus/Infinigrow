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
