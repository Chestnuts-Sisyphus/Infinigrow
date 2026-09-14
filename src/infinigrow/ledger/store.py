# -*- coding: utf-8 -*-
"""账本与工作文件的唯一写入口（本模块是全工程仅有的「允许写盘」的地方之一）。

设计：所有写盘都要给一个 **根**，写前用 `paths.guard` 校验「落在根之内」；
调用方不需要（也不允许）自己拼绝对路径。
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Iterable, Iterator

from ..core.encoding import read_text
from ..core.paths import guard


class LedgerError(RuntimeError):
    """账本写失败（写不进去必须响亮，不许静默）。"""


def append_jsonl(path: Path, record: dict, root: Path) -> None:
    """追加一条 JSON 记录（UTF-8 无 BOM；单行一条，便于 grep 与轮转）。"""
    guard(path, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)
    try:
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")
    except OSError as exc:
        raise LedgerError("账本追加失败：%s（%s）" % (path, exc)) from exc


def read_jsonl(path: Path) -> list[dict]:
    """读回全部记录；坏行**跳过并计数**（不抛——账本里历史坏行不该阻断读取）。"""
    if not path.is_file():
        return []
    out = []
    for raw in read_text(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def iter_jsonl_bad_lines(path: Path) -> Iterator[tuple[int, str]]:
    """产出坏行（行号, 原文），供审计工具点名——坏行不隐藏。"""
    if not path.is_file():
        return
    for no, raw in enumerate(read_text(path).splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError:
            yield no, raw


def write_work_file(path: Path, text: str, root: Path,
                    require_markers: Iterable[str] = ()) -> None:
    """原子覆写工作文件：先写同目录临时文件，再 `os.replace` 顶替。

    标记闸：新文本必须含 `require_markers` 里的每个标记，否则拒绝写入
    （防「一次截断把状态洗掉」；要缩容请显式传更小的 marker 集合并说明理由）。
    """
    guard(path, root)
    missing = [m for m in require_markers if m not in text]
    if missing:
        raise LedgerError("拒绝覆写（缺标记 %s）：%s" % ("、".join(missing), path))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text if text.endswith("\n") else text + "\n")
        os.replace(tmp_name, path)
    except OSError as exc:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise LedgerError("工作文件写入失败：%s（%s）" % (path, exc)) from exc


def ledger_stats(path: Path) -> dict:
    """账本体检：行数、坏行数、字节数（供园丁与测试复用）。"""
    records = read_jsonl(path)
    bad = list(iter_jsonl_bad_lines(path))
    size = path.stat().st_size if path.is_file() else 0
    return {"records": len(records), "bad_lines": len(bad), "bytes": size}


def write_jsonl_work_file(path: Path, records: Iterable[dict], root: Path) -> None:
    """整份重写一个 JSONL **工作文件**（队列类）：原子替换，不留中间态。

    与账本的区别在语义而不在格式：工作文件是「当前状态」，账本是「历史事实」。
    允许覆写工作文件（否则队列无法合并/冻结），但用原子替换而非逐行删除——
    断电也不会读到半个文件。
    """
    text = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records)
    write_work_file(path, text, root, require_markers=())
