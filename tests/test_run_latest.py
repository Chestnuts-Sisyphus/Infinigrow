# -*- coding: utf-8 -*-
"""「运转的永远是最新版」的机制测试。

定规要成立，靠的不是「记得升级」，而是**运行入口本身就带版本闸**：
`tools/run_latest.py` 在起跑前确保最新，并在四种情况下拒绝或回滚。
这里把它的决策逻辑（纯函数 `decide`）逐分支锁住——决策错了，定规就是空的。
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("run_latest", REPO_ROOT / "tools" / "run_latest.py")
run_latest = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(run_latest)


# ---------------------------------------------------------------- 决策分支
def test_up_to_date_runs_without_touching_anything():
    assert run_latest.decide(behind=0, ahead=0, dirty=False, running=False) == "run_only"


def test_behind_updates_then_runs():
    assert run_latest.decide(behind=3, ahead=0, dirty=False, running=False) == "update_then_run"


def test_dirty_workspace_refuses_update():
    """工作区有未提交改动 → 拒绝自动升级（升级不会盖掉人的活儿）。"""
    assert run_latest.decide(behind=2, ahead=0, dirty=True, running=False) == "refuse_dirty"


def test_never_replaces_code_while_a_tick_is_in_flight():
    """有拍在飞（锁在）→ 拒绝升级：**绝不在运行中替换代码**。"""
    assert run_latest.decide(behind=2, ahead=0, dirty=False, running=True) == "refuse_running"


def test_diverged_history_refuses_to_merge():
    assert run_latest.decide(behind=2, ahead=1, dirty=False, running=False) == "refuse_diverged"


def test_force_overrides_blocks():
    assert run_latest.decide(behind=1, ahead=0, dirty=True, running=True,
                             allow_force=True) == "update_then_run"


# ---------------------------------------------------------------- 入口与形态
def test_entry_help_works():
    p = subprocess.run([sys.executable, str(REPO_ROOT / "tools" / "run_latest.py"), "--help"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=120)
    assert p.returncode == 0
    for flag in ("--check", "--no-update", "--force"):
        assert flag in p.stdout


def test_selftest_gate_and_rollback_are_present_in_source():
    """自检闸与回滚必须在源码里真的存在（不是文档里说说）。"""
    src = (REPO_ROOT / "tools" / "run_latest.py").read_text(encoding="utf-8")
    assert "selftest_ok" in src and "reset\", \"--hard\"" in src.replace("'", '"')
    assert "回滚" in src


def test_env_error_is_not_treated_as_selftest_failure():
    """「跑不起来」≠「自检不过」：前者不回滚（回滚解决不了环境问题）。

    这条是真机跑出来的 bug：未安装状态下 `python -m infinigrow` 直接 No module named，
    当时的闸会把它当失败并回滚一个本来正常的升级。
    """
    src = (REPO_ROOT / "tools" / "run_latest.py").read_text(encoding="utf-8")
    assert "env_error" in src
    assert "No module named" in src


def test_child_env_makes_the_package_importable_without_install():
    """运行入口不能假设「使用者装过包」：子进程环境必须带上 <repo>/src。"""
    env = run_latest.child_env(REPO_ROOT)
    first = env["PYTHONPATH"].split(__import__("os").pathsep)[0]
    assert Path(first) == REPO_ROOT / "src"


def test_payload_runs_end_to_end_help():
    """端到端：通过运行入口起跑一个无害 payload（tick --help），必须真的跑得起来。"""
    p = subprocess.run([sys.executable, str(REPO_ROOT / "tools" / "run_latest.py"),
                        "--no-update", "--", "--help"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=300, cwd=str(REPO_ROOT))
    assert "No module named" not in p.stdout
    assert p.returncode == 0


def test_upgrade_docs_state_the_rule():
    text = (REPO_ROOT / "docs" / "upgrading.md").read_text(encoding="utf-8")
    assert "run_latest" in text          # 文档必须指向运行入口，别让人另找命令
    assert "最新" in text
