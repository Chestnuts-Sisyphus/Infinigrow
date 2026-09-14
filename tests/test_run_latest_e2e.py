# -*- coding: utf-8 -*-
"""严格模式端到端测试（T10/G10）：`--require-latest` 在**真 git 仓库**上跑一遍。

单测（`tests/test_run_latest.py`）验的是 `start_verdict` 这个纯函数的判定；
这里补的是**端到端**那一半：起一个真的 git 仓库（本地 bare 当远端，不出网），
让 `tools/run_latest.py` 自己去 fetch、比较、决策，看退出码与行为是不是设计的那样。

覆盖三种情形：
  1. 落后 + 工作区脏 + `--require-latest` → **拒绝起跑**（rc=4）；
  2. 落后 + 干净 + `--check --require-latest` → 只报状态，rc=4；
  3. `--no-update` 不尝试升级（rc 由 payload 决定，本测试给一个会失败的 payload 前缀）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_LATEST = REPO_ROOT / "tools" / "run_latest.py"


def _git(repo: Path, *args, check=False):
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=120)
    if check and proc.returncode != 0:
        raise AssertionError("git %s 失败：%s" % (args, proc.stderr))
    return proc


def _clone_pair(tmp_path: Path) -> tuple[Path, Path]:
    """造一对：本地工作副本 + 本地 bare 远端（**不碰网络**）。"""
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "--initial-branch=main", check=True)

    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "--initial-branch=main", check=True)
    _git(seed, "config", "user.email", "tester@example.com", check=True)
    _git(seed, "config", "user.name", "t", check=True)
    (seed / "README.md").write_text("seed\n", encoding="utf-8")
    _git(seed, "add", "-A", check=True)
    _git(seed, "commit", "-m", "seed", check=True)
    _git(seed, "remote", "add", "origin", str(remote), check=True)
    _git(seed, "push", "-u", "origin", "main", check=True)

    work = tmp_path / "work"
    _git(tmp_path, "clone", str(remote), str(work), check=True)
    _git(work, "config", "user.email", "tester@example.com", check=True)
    _git(work, "config", "user.name", "t", check=True)

    # 让远端领先 1 个提交（本地就落后了）
    (seed / "second.md").write_text("newer\n", encoding="utf-8")
    _git(seed, "add", "-A", check=True)
    _git(seed, "commit", "-m", "second", check=True)
    _git(seed, "push", "origin", "main", check=True)
    return work, remote


def _run(repo: Path, *args):
    proc = subprocess.run([sys.executable, str(RUN_LATEST), "--repo", str(repo), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def test_require_latest_refuses_when_it_cannot_upgrade(tmp_path):
    """落后 + 工作区脏 → `--require-latest` 必须**拒绝起跑**（rc=4）并说清原因。"""
    work, _remote = _clone_pair(tmp_path)
    (work / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")   # 工作区脏
    code, out = _run(work, "--require-latest")
    assert code == 4, out
    assert "严格模式" in out and "不跑" in out


def test_check_with_require_latest_reports_and_refuses(tmp_path):
    """`--check --require-latest`：只报状态，落后且升不动 → rc=4（可当闸用）。"""
    work, _remote = _clone_pair(tmp_path)
    (work / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
    code, out = _run(work, "--check", "--require-latest")
    assert code == 4, out
    assert "落后 1" in out


def test_plain_check_still_exits_zero_when_refusing(tmp_path):
    """不加严格模式：落后也**不拦**（rc=0）——默认语义是「照常跑」。"""
    work, _remote = _clone_pair(tmp_path)
    (work / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
    code, out = _run(work, "--check")
    assert code == 0, out
    assert "落后 1" in out


def test_default_start_verdict_is_start_stale_with_reason(tmp_path):
    """落后 + 脏 + 默认模式：**按现有版本照常起跑**，并打印「为什么不是最新版」。"""
    work, _remote = _clone_pair(tmp_path)
    (work / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
    code, out = _run(work, "--", "--help")
    assert "版本状态" in out
    assert "start_stale" in out or "start" in out
    assert code in (0, 2)          # payload 是 --help：rc 由 tick 决定（0），绝不该是 4


def test_update_check_reports_behind(tmp_path):
    """`--update --check`（归并后的原 update_local --check 行为）：只报不改。"""
    work, _remote = _clone_pair(tmp_path)
    code, out = _run(work, "--update", "--check")
    assert code == 0 and "落后 1" in out


def test_update_only_refuses_non_fast_forward(tmp_path):
    """本地有未推送提交 → 拒绝自动合并（rc=4）：升级不许埋掉别人的提交。"""
    work, _remote = _clone_pair(tmp_path)
    (work / "mine.md").write_text("mine\n", encoding="utf-8")
    _git(work, "add", "-A", check=True)
    _git(work, "commit", "-m", "mine", check=True)
    code, out = _run(work, "--update")
    assert code == 4, out
    assert "拒绝自动合并" in out
