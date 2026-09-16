# -*- coding: utf-8 -*-
"""「默认用最新版引擎；升不动就按现有版本跑」的机制测试（2026-09-14 定规）。

定规的三段语义必须都被锁住：

1. 有条件升级 → **升级再用新版跑**（默认行为）；
2. 没条件升级 → **按现有版本照常跑**，并说清为什么（**不因为旧版就停掉引擎**）；
3. 严格模式 `--require-latest` → 升不到最新就不跑（CI／发布验证用）。

另外锁住「引擎」与「生长主体」的分家：升级只动引擎代码，`state/` 不受影响。
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


# ---------------------------------------------------------------- 三段语义
def test_up_to_date_starts():
    assert run_latest.start_verdict(behind=0, ahead=0, dirty=False, running=False) == "start"


def test_behind_with_clean_tree_updates_then_starts():
    """有条件升级 → 升级再用新版跑。这是默认行为。"""
    assert run_latest.start_verdict(behind=3, ahead=0, dirty=False,
                                    running=False) == "update_then_start"


def test_behind_with_dirty_tree_still_runs_on_current_version():
    """**升不动就按旧版跑**——绝不因为「不是最新版」把引擎停掉。"""
    assert run_latest.start_verdict(behind=2, ahead=0, dirty=True,
                                    running=False) == "start_stale"


def test_behind_with_tick_in_flight_still_runs():
    """有拍在飞：不替换代码，但照常跑（引擎自身的锁会处理并发）。"""
    assert run_latest.start_verdict(behind=2, ahead=0, dirty=False,
                                    running=True) == "start_stale"


def test_behind_with_diverged_history_still_runs():
    assert run_latest.start_verdict(behind=2, ahead=1, dirty=False,
                                    running=False) == "start_stale"


def test_behind_with_updates_disabled_still_runs():
    assert run_latest.start_verdict(behind=2, ahead=0, dirty=False, running=False,
                                    can_update=False) == "start_stale"


def test_offline_starts_and_is_marked_unverified():
    """不知道 ≠ 落后：断网不能让引擎停摆，但要标明「未验证」。"""
    assert run_latest.start_verdict(behind=0, ahead=0, dirty=False, running=False,
                                    offline=True) == "start_unverified"


def test_strict_mode_refuses_when_it_cannot_reach_latest():
    """严格模式（CI／发布验证）：拿不到最新版就不跑——这是**可选的严**，不是默认。"""
    assert run_latest.start_verdict(behind=2, ahead=0, dirty=True, running=False,
                                    require_latest=True) == "refuse_stale"
    assert run_latest.start_verdict(behind=2, ahead=0, dirty=False, running=False,
                                    require_latest=True) == "update_then_start"


def test_stale_reasons_are_explicit():
    """「为什么这次不是最新版」必须说出来——不解释就等于静默用旧版。"""
    assert "工作区" in run_latest.stale_reason(ahead=0, dirty=True, running=False)
    assert "拍在飞" in run_latest.stale_reason(ahead=0, dirty=False, running=True)
    assert "分叉" in run_latest.stale_reason(ahead=1, dirty=False, running=False)
    assert "no-update" in run_latest.stale_reason(ahead=0, dirty=False, running=False,
                                                 can_update=False)


# ---------------------------------------------------------------- 引擎与主体分家
def test_upgrade_never_touches_the_growth_subject():
    """升级动的是引擎代码；生长主体（`state/`）是 git 忽略的，pull/reset 不碰它。

    这是「引擎」与「引擎所生长的主体」分家的机械化判据。
    """
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "state/" in {line.strip() for line in gitignore}
    # git 视角里 state/ 下的东西是不可见的（忽略），所以 pull/reset 无从改它
    p = subprocess.run(["git", "check-ignore", "-q", "state/ledger-probe.jsonl"],
                       cwd=str(REPO_ROOT), capture_output=True)
    if p.returncode != 0:      # 不在 git 仓库环境时退化为「规则在位」检查
        assert "state/" in "\n".join(gitignore)


def test_tick_records_which_engine_version_ran():
    """既然引擎会自己升级，每一拍就必须能回答「这是哪个版本的引擎跑的」。"""
    src = (REPO_ROOT / "src" / "infinigrow" / "engine" / "tick.py").read_text(encoding="utf-8")
    assert "engine_version" in src and "engine_commit" in src
    from infinigrow.core.build_info import engine_identity, engine_label
    ident = engine_identity()
    assert ident["version"] and ident["version"][0].isdigit()
    assert engine_label().startswith("Infinigrow ")


def test_engine_identity_reads_git_without_subprocess():
    """引擎身份不许起子进程（机械拍里不该有子进程，另有测试守这一条）。"""
    src = (REPO_ROOT / "src" / "infinigrow" / "core" / "build_info.py").read_text(
        encoding="utf-8")
    assert "subprocess" not in src


# ---------------------------------------------------------------- 入口形态
def test_entry_help_works():
    p = subprocess.run([sys.executable, str(REPO_ROOT / "tools" / "run_latest.py"), "--help"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=120)
    assert p.returncode == 0
    for flag in ("--check", "--no-update", "--require-latest"):
        assert flag in p.stdout


def test_selftest_gate_and_rollback_are_present_in_source():
    src = (REPO_ROOT / "tools" / "run_latest.py").read_text(encoding="utf-8")
    assert "selftest_ok" in src and "reset\", \"--hard\"" in src.replace("'", '"')
    assert "回滚" in src


def test_env_error_is_not_treated_as_selftest_failure():
    """「跑不起来」≠「自检不过」：前者不回滚（回滚解决不了环境问题）。"""
    src = (REPO_ROOT / "tools" / "run_latest.py").read_text(encoding="utf-8")
    assert "env_error" in src and "No module named" in src


def test_launcher_output_never_carries_the_absolute_repo_path(tmp_path):
    """M8/N47：启动器的输出**不许带仓库绝对路径**。

    为什么这条是硬判据：计划任务把本入口的 stdout/stderr 整份重定向进
    `state/logs/tick.log`——一打印就等于把本机目录结构长久写进**可被分享/迁移**的
    状态产物（实测 `state/logs/tick.log` 里 306 行带盘符路径）。
    """
    import os
    import shutil
    repo_copy = tmp_path / "repo-copy"
    shutil.copytree(REPO_ROOT, repo_copy,
                    ignore=shutil.ignore_patterns(".git", "state", "archive",
                                                  "__pycache__", ".pytest_cache",
                                                  ".ruff_cache"))
    assert (repo_copy / ".git").is_dir() is False
    env = dict(os.environ)
    p = subprocess.run([sys.executable, str(repo_copy / "tools" / "run_latest.py"),
                        "--check", "--repo", str(repo_copy)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180, env=env)
    out = (p.stdout or "") + (p.stderr or "")
    assert str(repo_copy) not in out, "启动器把仓库绝对路径打印出来了"
    assert repo_copy.name in out                     # 用目录名说明「是哪个仓库」就够


def test_child_env_makes_the_package_importable_without_install():
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
    assert "run_latest" in text and "最新" in text
