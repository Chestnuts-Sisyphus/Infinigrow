# -*- coding: utf-8 -*-
"""构建信息：**这一版引擎是谁**（版本号 ＋ 提交号），纯文件读取，不起子进程。

为什么要有它：定规是「引擎必须是最新版本才准运转」。既然引擎会自己升级，
就必须能回答一个追溯问题——**这一拍是哪个版本的引擎跑出来的**。
账本里只写 tick 数字不够：升级之后，历史读数属于哪一版引擎就说不清了。

实现上刻意**不调 git 命令**（读 `.git/HEAD` 与 `refs/` 就够了）：
机械拍的一拍里不该出现子进程，这条有测试守着（`tests/test_coldstart.py`）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _git_dir(root: Path = None) -> Optional[Path]:
    """找到 .git 目录（兼容 .git 是文件的工作树/子模块写法）。"""
    git_path = (root or _repo_root()) / ".git"
    if git_path.is_dir():
        return git_path
    if git_path.is_file():
        try:
            for line in git_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("gitdir:"):
                    target = Path(line.split(":", 1)[1].strip())
                    return target if target.is_absolute() else (git_path.parent / target).resolve()
        except OSError:
            return None
    return None


def engine_commit(length: int = 8) -> str:
    """当前检出的提交号（短）。读不到就返回空串——**不猜、不假装**。"""
    git_dir = _git_dir()
    if git_dir is None:
        return ""
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split(":", 1)[1].strip()
            ref_file = git_dir / ref
            if ref_file.is_file():
                return ref_file.read_text(encoding="utf-8").strip()[:length]
            packed = git_dir / "packed-refs"
            if packed.is_file():
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line.endswith(" " + ref):
                        return line.split(" ", 1)[0][:length]
            return ""
        return head[:length]          # detached HEAD：HEAD 里直接是提交号
    except OSError:
        return ""


def engine_identity() -> dict:
    """引擎身份：{version, commit}。供心跳与对账报告记录「这一拍是谁跑的」。"""
    from .. import __version__         # 延迟导入：只在调用期取，避开包初始化期的循环
    return {"version": __version__, "commit": engine_commit()}


def engine_label() -> str:
    """一行字的引擎标签：`Infinigrow 2.0.0 (abc1234)`（提交号取不到时省略括号）。"""
    ident = engine_identity()
    return ("%s %s" % ("Infinigrow", ident["version"])
            + (" (%s)" % ident["commit"] if ident["commit"] else ""))
