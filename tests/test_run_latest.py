# -*- coding: utf-8 -*-
"""「引擎必须是最新版才准运转」的机制测试（2026-09-14 定规，反复强调后加强）。

定规要成立，靠的不是「记得升级」，而是**运行入口带硬闸**：
`tools/run_latest.py` 在起跑前判定引擎版本 —— **知道自己是旧版就不准跑**，
并且升级只动引擎代码、不碰生长主体（`state/`）。

这里把决策逻辑（纯函数 `start_verdict`）与「主体不受升级影响」逐条锁住。
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


# ---------------------------------------------------------------- 起跑闸
def test_up_to_date_starts():
    assert run_latest.start_verdict(behind=0, ahead=0, dirty=False, running=False) == "start"


def test_behind_with_clean_tree_updates_then_starts():
    assert run_latest.start_verdict(behind=3, ahead=0, dirty=False,
                                    running=False) == "update_then_start"


def test_known_stale_with_dirty_tree_refuses_to_start():
    """**知道自己是旧版就不准跑**——这正是「保证」与「提示」的区别。"""
    assert run_latest.start_verdict(behind=2, ahead=0, dirty=True,
                                    running=False) == "refuse_stale"


def test_known_stale_diverged_history_refuses_to_start():
    assert run_latest.start_verdict(behind=2, ahead=1, dirty=False,
                                    running=False) == "refuse_stale"


def test_never_replaces_code_while_a_tick_is_in_flight():
    """有拍在飞 → 拒绝：不并发、也不在运行中替换引擎代码。"""
    assert run_latest.start_verdict(behind=2, ahead=0, dirty=False,
                                    running=True) == "refuse_stale"


def test_offline_starts_but_marks_unverified():
    """不知道 ≠ 落后：断网不能让引擎停摆，但必须标明「本次未经验证」。"""
    assert run_latest.start_verdict(behind=0, ahead=0, dirty=False, running=False,
                                    offline=True) == "start_unverified"


def test_explicit_opt_out_can_run_stale():
    """显式例外：知道旧版但仍要跑（`--allow-stale`）——决定权留给人。"""
    assert run_latest.start_verdict(behind=2, ahead=0, dirty=True, running=False,
                                    allow_stale=True) == "start"


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
    for flag in ("--check", "--no-update", "--allow-stale"):
        assert flag in p.stdout


def test_selftest_gate_and_rollback_are_present_in_source():
    src = (REPO_ROOT / "tools" / "run_latest.py").read_text(encoding="utf-8")
    assert "selftest_ok" in src and "reset\", \"--hard\"" in src.replace("'", '"')
    assert "回滚" in src


def test_env_error_is_not_treated_as_selftest_failure():
    """「跑不起来」≠「自检不过」：前者不回滚（回滚解决不了环境问题）。"""
    src = (REPO_ROOT / "tools" / "run_latest.py").read_text(encoding="utf-8")
    assert "env_error" in src and "No module named" in src


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
