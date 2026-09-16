# -*- coding: utf-8 -*-
"""路径解析：**状态根参数化**（v2 起，取代 v1 的硬编码绝对路径）。

v1 的病灶：状态根写死在另一个项目的目录下（`<某项目>/loop/树身/`），导致
「引擎代码」与「引擎状态」跨项目耦合——搬走代码带不走状态，开源还泄漏本机目录结构。

v2 规则：
  1. 状态根默认 = `<仓库>/state`（仓库内、且 `.gitignore` 忽略）；
  2. 可用配置或环境变量 `IG_STATE_ROOT` 指到任意位置（含临时目录），**空仓可跑**；
  3. 源码里**不出现任何绝对路径字面量**——本模块是唯一允许与文件系统打交道的路径入口，
     且每次写盘前都做「是否落在状态根之内」的显式校验。

安全姿态：本模块所有对外函数都接受「根」参数并在内部做包含性校验
（`_within`），拒绝 `..` 上跳与越界写——调用方不需要自己拼路径。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# 仓库根：本文件位于 <repo>/src/infinigrow/core/paths.py → 上溯 4 层
_MODULE_PATH = Path(__file__).resolve()
REPO_ROOT = _MODULE_PATH.parents[3]

ENV_STATE_ROOT = "IG_STATE_ROOT"
ENV_CONFIG = "IG_CONFIG"
ENV_SUBJECT_ROOT = "IG_SUBJECT_ROOT"

#: 生长主体的默认目录名后缀（**默认落在仓库之外**：代码与「被生长的东西」分家）
SUBJECT_SUFFIX = "-subject"


def default_subject_root(repo_root: "str | os.PathLike | None" = None) -> Path:
    """主体的默认位置＝仓库的**同级目录** `<仓库名>-subject`。

    为什么不落在仓库内：仓库是**引擎代码**（要维护、要最小改动、要能开源），
    主体是**被生长的东西**（持续变化、属于使用者、可能含私密内容）。两者放一起，
    迟早出现「升级引擎时动了生长痕迹」「开源时把主体一起带出去」这类事故。

    要指到别处：配置项 `subject_root` 或环境变量 `IG_SUBJECT_ROOT`（任意目录）。
    本函数是**默认规则的单一来源**（`config.Settings.subject_path()` 与文档都引用它）。
    """
    repo = Path(repo_root).resolve() if repo_root else REPO_ROOT
    return repo.parent / (repo.name + SUBJECT_SUFFIX)


def _within(path: Path, root: Path) -> bool:
    """判断 path 是否落在 root 之内（两边都先 resolve；不跟随越界符号链接）。"""
    try:
        p = path.resolve()
        r = root.resolve()
    except OSError:
        return False
    return p == r or r in p.parents


def guard(path: Path, root: Path) -> Path:
    """写盘前的统一守卫：越出 root 一律拒绝（宁停不静默写错地方）。"""
    if not _within(path, root):
        raise PermissionError("拒绝越界写：%s 不在 %s 之内" % (path, root))
    return path


@dataclass(frozen=True)
class StateLayout:
    """一次解析出的全部状态路径（引擎运行期只认这一个对象，不再各自拼路径）。"""

    root: Path
    tick_status: Path
    sprouts: Path            # 芽队列（工作文件，可覆写）
    frozen_sprouts: Path     # 冻结区（工作文件）
    diff_ledger: Path        # 差异账（追加型）
    outcome_ledger: Path     # 兑现账（追加型）
    maturity_chain: Path     # 成熟链（追加型）
    library: Path            # 能力库（追加型）
    reconcile_dir: Path      # 对账报告目录
    locks_dir: Path
    log: Path
    # 以下为运转期新增（v2.1）：都落在状态根内，且默认值保证旧调用不需要改
    archive_dir: Path = None            # type: ignore[assignment]  账本归档区（轮转：只移动不删）
    traces_dir: Path = None             # type: ignore[assignment]  执行者留痕（每拍一份）
    logs_dir: Path = None               # type: ignore[assignment]  调度器/看护日志
    subject_snapshot: Path = None       # type: ignore[assignment]  主体快照（工作文件）
    subject_before_snapshot: Path = None  # type: ignore[assignment]  主体**动手前**快照（N55/K14）
    subject_org_anchor: Path = None     # type: ignore[assignment]  上次组织会话看到的清单（N58/K14）
    executor_ledger: Path = None        # type: ignore[assignment]  执行者调用账（追加型）
    org_findings: Path = None           # type: ignore[assignment]  组织会话发现账（追加型）
    settings_file: Path = None          # type: ignore[assignment]  生效配置快照（工作文件）
    domains: Path = None                # type: ignore[assignment]  域饱和状态（工作文件）

    def all_dirs(self) -> Iterable[Path]:
        return (self.root, self.reconcile_dir, self.locks_dir)


def _fill(layout: StateLayout) -> StateLayout:
    """补齐派生路径（构造时只给根与老字段，派生字段在这里统一算）。"""
    from dataclasses import replace
    root = layout.root
    derived = {
        "archive_dir": root / "archive",
        "traces_dir": root / "traces",
        "logs_dir": root / "logs",
        "subject_snapshot": root / "subject.json",
        "subject_before_snapshot": root / "subject-before.json",
        "subject_org_anchor": root / "subject-org-anchor.json",
        "executor_ledger": root / "executor.jsonl",
        "org_findings": root / "org-findings.jsonl",
        "settings_file": root / "settings.json",
        "domains": root / "domains.json",
    }
    patch = {k: v for k, v in derived.items() if getattr(layout, k) is None}
    return replace(layout, **patch) if patch else layout


def resolve_state(state_root: "str | os.PathLike | None" = None,
                  repo_root: "str | os.PathLike | None" = None,
                  create: bool = False) -> StateLayout:
    """解析状态根 → 全部状态路径。

    state_root=None → `<repo>/state`（默认；空仓跑得起来）。
    create=True → 建出目录骨架（只建目录，不写内容）。
    """
    repo = Path(repo_root).resolve() if repo_root else REPO_ROOT
    if state_root:
        root = Path(state_root).expanduser()
        root = (repo / root).resolve() if not root.is_absolute() else root.resolve()
    else:
        root = (repo / "state").resolve()

    layout = StateLayout(
        root=root,
        tick_status=root / "tick_status.json",
        sprouts=root / "sprouts.jsonl",
        frozen_sprouts=root / "sprouts-frozen.jsonl",
        diff_ledger=root / "diffs.jsonl",
        outcome_ledger=root / "outcomes.jsonl",
        maturity_chain=root / "maturity.jsonl",
        library=root / "library.jsonl",
        reconcile_dir=root / "reconcile",
        locks_dir=root / "locks",
        log=root / "engine.log",
    )
    layout = _fill(layout)
    if create:
        for d in (layout.root, layout.reconcile_dir, layout.locks_dir,
                  layout.archive_dir, layout.traces_dir, layout.logs_dir):
            guard(d, root)
            d.mkdir(parents=True, exist_ok=True)
    return layout
