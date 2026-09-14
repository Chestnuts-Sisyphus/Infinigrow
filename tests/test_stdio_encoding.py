# -*- coding: utf-8 -*-
"""非 UTF-8 控制台下的输出纪律（T9 双平台 CI 抓到的一整族真缺陷）。

CI 在 **windows-latest** 上第一次跑，就把这个族暴露了出来：runner 的控制台编码是
**cp1252**（本机是 GBK，恰好能编码中文，所以本地全绿）。凡是**直接打印中文**又没把
stdout 切到 UTF-8 的入口，一律 `UnicodeEncodeError` → 进程 rc=1：

- `tools/run_latest.py` / `update_local.py`（版本闸与升级入口）
- `tools/privacy_scan.py` / `check_prompt_code_sync.py` / `check_no_abs_paths.py` /
  `split_monolith.py`（CI 里逐条要跑的闸）
- `tests/fake_executor.py`、`tools/demo_executor.py`（执行者通道里的两个脚本）

本测试用 `PYTHONIOENCODING=cp1252` **复现那个环境**，逐个入口跑一遍：
判据是具体状态——`rc == 0` 且输出里不出现 `UnicodeEncodeError`。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS = REPO_ROOT / "tools"


def _run(args, **env_extra):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp1252"          # 复现 CI windows runner 的控制台编码
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env.update(env_extra)
    proc = subprocess.run([sys.executable, *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300,
                          cwd=str(REPO_ROOT), env=env)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


# (标签, 参数, 期望 rc) —— 期望 rc 显式写出来：fake_executor 的 fail 模式**本来就该** rc=2
ENTRIES = (
    ("cli version", ["-m", "infinigrow", "version"], 0),
    ("cli dry-run", ["-m", "infinigrow", "dry-run"], 0),
    ("cli scan", ["-m", "infinigrow", "scan"], 0),
    ("run_latest --check", [str(TOOLS / "run_latest.py"), "--check"], 0),
    ("update_local --check", [str(TOOLS / "update_local.py"), "--check"], 0),
    ("update_local --help", [str(TOOLS / "update_local.py"), "--help"], 0),
    ("privacy_scan", [str(TOOLS / "privacy_scan.py"), "--root", "src"], 0),
    ("check_prompt_code_sync", [str(TOOLS / "check_prompt_code_sync.py")], 0),
    ("check_no_abs_paths", [str(TOOLS / "check_no_abs_paths.py"), "docs"], 0),
    ("split_monolith --help", [str(TOOLS / "split_monolith.py"), "--help"], 0),
    ("fake_executor ok", [str(REPO_ROOT / "tests" / "fake_executor.py"), "--mode", "ok"], 0),
    ("fake_executor fail", [str(REPO_ROOT / "tests" / "fake_executor.py"), "--mode", "fail"], 2),
)


@pytest.mark.parametrize("label,args,want_rc", ENTRIES, ids=[e[0] for e in ENTRIES])
def test_entry_survives_a_non_utf8_console(label, args, want_rc):
    code, out = _run(args)
    assert "UnicodeEncodeError" not in out, "%s 在 cp1252 控制台下炸了：\n%s" % (label, out[-800:])
    assert code == want_rc, "%s 的 rc=%d（应为 %d）：\n%s" % (label, code, want_rc, out[-800:])


def test_demo_executor_survives_a_non_utf8_console(tmp_path):
    """演示执行者也要能跑（它由引擎经通道拉起，控制台编码继承自调度器）。"""
    subject = tmp_path / "subject"
    subject.mkdir()
    code, out = _run([str(TOOLS / "demo_executor.py")], IG_PASS_KIND="tick",
                     IG_SUBJECT_ROOT=str(subject))
    assert code == 0 and "UnicodeEncodeError" not in out
    code, out = _run([str(TOOLS / "demo_executor.py")], IG_PASS_KIND="org-session",
                     IG_SUBJECT_ROOT=str(subject))
    assert code == 0 and "UnicodeEncodeError" not in out


def test_cli_tick_reports_chinese_in_a_non_utf8_console(tmp_path):
    """一拍要能在 cp1252 控制台下跑完并把中文报告写进日志（不是崩掉半路）。"""
    state = tmp_path / "state"
    code, out = _run(["-m", "infinigrow", "tick", "--json"], IG_STATE_ROOT=str(state),
                     IG_SUBJECT_ROOT=str(tmp_path / "subject"))
    assert code == 0 and "UnicodeEncodeError" not in out
    assert '"tick": 1' in out
