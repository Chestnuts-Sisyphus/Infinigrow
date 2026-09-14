#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""产物零绝对路径检查器：给**状态目录产出的东西**做一次机械扫描。

为什么要单独一个工具（而不是写在 CI 的 shell 片段里）：CI 现在要在 Windows 上跑，
而「heredoc + grep」那套只有 bash 有；同一个检查本地也要能跑（演练、验收、排查）。
一个跨平台的小工具＝三处（CI、本地、文档）共用同一条判据。

判据：目录下**任何文本文件**里都不许出现
  - 盘符路径（形如「字母 ＋ 冒号 ＋ 斜杠」）；
  - POSIX 的家目录与系统挂载点前缀（家目录、系统目录、挂载点那几类）。
命中即 rc=1（可作闸用）。二进制文件按文本读（errors=replace），坏不了。

用法：
    python tools/check_no_abs_paths.py <目录> [更多目录...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

#: 绝对路径形态（与静态规则 R1／隐私扫描同源；字符类刻意不写出完整形态，
#: 免得本文件自己命中自己——自匹配是这类检查器最常见的假阳性）
ABS_PATH_RX = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:home|Users|mnt|opt)/)")

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "venv",
             "node_modules", ".mypy_cache"}


def scan(root: Path) -> tuple[list[str], list[Path]]:
    """返回 (命中列表, 检查过的文件列表)。传目录＝递归；传单个文件＝只看那一个。"""
    hits: list[str] = []
    files: list[Path] = []
    base = Path(root)
    candidates = [base] if base.is_file() else sorted(base.rglob("*"))
    for path in candidates:
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        for no, line in enumerate(text.splitlines(), 1):
            m = ABS_PATH_RX.search(line)
            if m:
                hits.append("%s:%d %s" % (path, no, m.group(0)))
    return hits, files


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("用法：python tools/check_no_abs_paths.py <目录或文件> [更多...]")
        return 1
    total_files, all_hits = 0, []
    for raw in args:
        target = Path(raw)
        if not target.exists():
            print("跳过（不存在）：%s" % target)
            continue
        hits, files = scan(target)
        total_files += len(files)
        all_hits += hits
        print("检查：%s（%d 个文件）" % (target, len(files)))
    print("检查文件总数：%d" % total_files)
    if all_hits:
        print("绝对路径命中 %d 处：" % len(all_hits))
        for hit in all_hits[:20]:
            print("  - %s" % hit)
        print("FAIL：产物不得含绝对路径（状态目录会被分享/迁移/公开）。")
        return 1
    print("绝对路径命中：无 —— PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
