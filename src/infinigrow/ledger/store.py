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


def write_lines(path: Path, lines: Iterable[str], root: Path, header: str = "") -> None:
    """把若干**原始行**整份写进一个文件（先过 `guard`，再原子替换）。

    给轮转用的：归档件是「账本行的搬运目的地」。搬运不许在调用方那边自己拼写盘动作——
    那样「路径校验」就只存在于调用方的记忆里。这里把「校验 ＋ 原子写」收在同一条路上，
    与本模块其它写盘能力同权同检（首次写入前还会解析一遍符号链接，防软链跳出根）。
    """
    safe = require_within(path, root)
    write_work_file(safe, header + "".join(line.rstrip("\n") + "\n" for line in lines),
                    root, require_markers=())


def require_within(path: Path, root: Path) -> Path:
    """校验并返回**可写的根内路径**：解析后必须仍在根内，否则拒绝（含软链跳出）。

    返回的是解析后的绝对路径——调用方拿它去写，路径校验就不会被后续拼接绕过去。
    """
    guard(path, root)
    try:
        resolved = Path(path).resolve()
        base = Path(root).resolve()
    except OSError as exc:
        raise PermissionError("路径无法解析，拒绝写：%s（%s）" % (path, exc)) from exc
    if not (resolved == base or base in resolved.parents):
        raise PermissionError("拒绝越界写（解析后不在根内）：%s" % resolved)
    return resolved


def create_exclusive(path: Path, text: str, root: Path) -> bool:
    """**原子独占创建**一个文件：成功 True，已存在 False。

    锁文件不是「内容写盘」而是**互斥原语**：它必须用 `O_CREAT|O_EXCL` 一步创建
    （「先看有没有、再创建」之间会有竞态窗口，两个会话都能拿到锁）。
    这种能力放在本模块而不是让调用方自己拼系统调用——否则越界守卫就漏了一处，
    而「写盘只有一条路」这条纪律也就名存实亡了。
    """
    safe = require_within(path, root)
    safe.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(safe), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    except OSError as exc:
        raise LedgerError("独占创建失败：%s（%s）" % (safe, exc)) from exc
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return True


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


def truncate_file(path: Path, root: Path) -> None:
    """**原地**清空工作文件（不换 inode、不删文件）。

    与 `write_work_file` 的差别只在落盘方式：`os.replace` 需要目标可替换，而 Windows 下
    被追加句柄占用（无 `FILE_SHARE_DELETE`）的文件连 `unlink` 都会撞 `WinError 32`——
    日志轮转正撞在这上面（归档件已写好，主件却清不掉，每拍报错一次）。只有原地截断
    能做这件事；句柄的追加方（`O_APPEND`）不受影响，下一次写仍落在文件尾。调用方必须
    **先**把内容写进归档件——数据先保险，再清主件。
    """
    guarded = require_within(path, root)
    try:
        guarded.write_text("", encoding="utf-8", newline="\n")
    except OSError as exc:
        raise LedgerError("工作文件清空失败：%s（%s）" % (guarded, exc)) from exc


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


def move_file(src: Path, dst: Path, root: Path) -> None:
    """把文件**整体搬进**根内的另一处（文件型产物轮转用：只移动不删）。

    次序：先写归档件（原子替换），**成功之后**才移除源文件——中间断电最多出现
    「源还在、归档多一份」，绝不会出现「源没了、归档也没成」（那才是真丢）。
    两处都过 `require_within`：调用方不许自己拼路径语义。
    """
    safe_src = require_within(Path(src), root)
    safe_dst = require_within(Path(dst), root)
    if safe_src == safe_dst:
        return
    try:
        text = read_text(safe_src)
    except OSError as exc:
        raise LedgerError("归档源读取失败：%s（%s）" % (safe_src, exc)) from exc
    write_work_file(safe_dst, text, root, require_markers=())
    try:
        safe_src.unlink()
    except OSError as exc:
        raise LedgerError("归档后源文件移除失败（数据已在归档件里，待人工清理）：%s（%s）"
                          % (safe_src, exc)) from exc
