# -*- coding: utf-8 -*-
"""调度与一键件测试（T4/G1、T9/G11/G12）：挂东西之前先把「挂的东西」本身验了。

断言的是**结构事实**（文件存在、语法可解析、引用了正确的入口），不假装验证了
「计划任务真的会按时跑」——那件事只能在真机上挂好之后看（本轮的 T12 演练做这件事）。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS = REPO_ROOT / "tools"
RUN_TICK = TOOLS / "run_tick.bat"
MANAGE = TOOLS / "manage_scheduled_task.bat"
PS1 = TOOLS / "scheduled_task.ps1"
CHECK_PATHS = TOOLS / "check_no_abs_paths.py"


def test_one_click_files_exist():
    for path in (RUN_TICK, MANAGE, PS1, CHECK_PATHS):
        assert path.is_file(), "缺一键件：%s" % path.name


def test_run_tick_bat_goes_through_the_version_gate():
    """一键件必须走版本闸（「运行的引擎永远最新版」的落地处）——不是直接跑 tick。"""
    text = RUN_TICK.read_text(encoding="utf-8")
    assert "run_latest.py" in text
    assert "infinigrow\" gardener" in text or "-m infinigrow gardener" in text
    assert "@echo off" in text.lower()
    assert "%~dp0" in text                       # 用脚本自己所在目录定位，不写死路径
    assert "IG_STATE_ROOT" in text


def test_bat_files_are_syntactically_balanced():
    """括号/引号配平（粗粒度语法检查：能把「明显写坏」的批处理挑出来）。"""
    for path in (RUN_TICK, MANAGE):
        text = path.read_text(encoding="utf-8")
        body = "\n".join(line for line in text.splitlines()
                         if not line.strip().lower().startswith("rem"))
        assert body.count("(") == body.count(")"), "%s 括号不配平" % path.name
        assert body.count('"') % 2 == 0, "%s 引号不配平" % path.name


def test_powershell_script_parses():
    """用 PowerShell 自己的解析器验 PS1 语法（本机没有 powershell 时跳过）。"""
    exe = shutil.which("powershell") or shutil.which("pwsh")
    if exe is None:
        pytest.skip("本机没有 PowerShell：跳过语法解析（CI 的 windows 矩阵会跑到）")
    cmd = [exe, "-NoProfile", "-Command",
           "[void][System.Management.Automation.Language.Parser]::ParseFile('%s', "
           "[ref]$null, [ref]$null); 'PARSE_OK'" % PS1]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120)
    assert "PARSE_OK" in (proc.stdout or ""), (proc.stdout or "") + (proc.stderr or "")


def test_scheduled_task_script_has_install_uninstall_status():
    text = PS1.read_text(encoding="utf-8")
    for token in ("Register-ScheduledTask", "Unregister-ScheduledTask",
                  "Get-ScheduledTask", "RepetitionInterval", "Infinigrow_tick",
                  "IG_TICK_MINUTES"):
        assert token in text, "计划任务脚本缺：%s" % token


def test_check_no_abs_paths_tool_reports_clean_tree(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_no_abs_paths", CHECK_PATHS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "state.json").write_text('{"tick": 3}', encoding="utf-8")
    hits, files = mod.scan(clean)
    assert hits == [] and len(files) == 1

    dirty = tmp_path / "dirty"
    dirty.mkdir()
    # 造病灶：用拼装方式构造路径字面量（免得测试文件自己命中规则）
    absolute = "C" + ":" + "/" + "Users/" + "someone/state"
    (dirty / "state.json").write_text('{"root": "%s"}' % absolute, encoding="utf-8")
    hits, _files = mod.scan(dirty)
    assert hits and "state.json" in hits[0]
    assert mod.main([str(dirty)]) == 1 and mod.main([str(clean)]) == 0


def test_ci_runs_on_windows_too():
    """T9/G11 的结构判据：CI 矩阵含 windows-latest（真实运行环境是 Windows）。"""
    text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "windows-latest" in text and "ubuntu-latest" in text
    assert "check_no_abs_paths.py" in text
