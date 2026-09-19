# -*- coding: utf-8 -*-
"""触盘层直接用例：`ledger/store.py` 是**全工程唯一允许写盘**的地方之一，
它的每一道闸都必须有**一条用例直接钉住**——不能只靠上层引擎「顺路跑到」。

为什么单独建这一册：此前这些写盘能力只被间接覆盖（引擎跑一拍时路过），
于是「标记闸失效」「独占创建有竞态」「越界写被放行」这类病灶可以长期无人察觉。
这里对 8 个写盘闸逐个给出**正例**与（在有拒绝语义处的）**反例**。
"""
from __future__ import annotations

import pytest

from infinigrow.ledger.store import (LedgerError, append_jsonl, create_exclusive,
                                      iter_jsonl_bad_lines, ledger_stats, move_file,
                                      read_jsonl, require_within, write_jsonl_work_file,
                                      write_lines, write_work_file)


# ---------------------------------------------------------------- ① append_jsonl
def test_append_jsonl_accumulates_and_guard_rejects_escape(tmp_path):
    """追加型账本：逐条落盘、读回有序；越出根直接拒写。"""
    root = tmp_path / "state"
    root.mkdir()
    ledger = root / "outcomes.jsonl"
    append_jsonl(ledger, {"tick": 1, "kind": "redeem"}, root)
    append_jsonl(ledger, {"tick": 2, "kind": "contradict"}, root)
    assert [r["tick"] for r in read_jsonl(ledger)] == [1, 2]
    # 反例：想写到根外面 → guard 拒（不静默写到别处）
    with pytest.raises(PermissionError):
        append_jsonl(tmp_path / "outside.jsonl", {"x": 1}, root)


# ---------------------------------------------------------------- ② 坏行容错
def test_read_jsonl_skips_bad_lines_but_surfaces_them(tmp_path):
    """坏行**跳过不阻断读取**，但 `iter_jsonl_bad_lines` / `ledger_stats` 必须点名它们。"""
    root = tmp_path / "state"
    root.mkdir()
    ledger = root / "diffs.jsonl"
    ledger.write_text('{"ok": 1}\n不是JSON\n# 注释行\n{"ok": 2}\n', encoding="utf-8")
    assert [r["ok"] for r in read_jsonl(ledger)] == [1, 2]           # 坏行不阻断
    bad = list(iter_jsonl_bad_lines(ledger))
    assert len(bad) == 1 and bad[0][0] == 2, "坏行行号必须被点名（不隐藏）"
    stats = ledger_stats(ledger)
    assert stats == {"records": 2, "bad_lines": 1, "bytes": ledger.stat().st_size}


# ---------------------------------------------------------------- ③ require_within
def test_require_within_returns_resolved_or_rejects(tmp_path):
    """解析后仍在根内 → 返回解析路径；`.`/软链跳出 → PermissionError。"""
    root = tmp_path / "state"
    (root / "nested").mkdir(parents=True)
    inside = root / "nested" / "f.json"
    resolved = require_within(inside, root)
    assert resolved == inside.resolve() and resolved.is_relative_to(root.resolve())
    with pytest.raises(PermissionError):
        require_within(root / ".." / "sneak.json", root)


# ---------------------------------------------------------------- ④ create_exclusive（竞态）
def test_create_exclusive_loses_race_without_clobbering(tmp_path):
    """独占创建：首次 True；已存在时 False 且**绝不覆盖**已有内容（锁的语义）。"""
    root = tmp_path / "state"
    root.mkdir()
    lock = root / "locks" / "tick.lock"                          # 父目录不存在也要能建
    assert create_exclusive(lock, "holder=A\n", root) is True
    assert lock.read_text(encoding="utf-8") == "holder=A\n"
    assert create_exclusive(lock, "holder=B\n", root) is False   # 第二个会话抢锁失败
    assert lock.read_text(encoding="utf-8") == "holder=A\n", "输家不得改写赢家内容"


# ---------------------------------------------------------------- ⑤ write_work_file（标记闸）
def test_write_work_file_marker_gate_blocks_shrink(tmp_path):
    """标记闸：缺标记 → LedgerError 且原文件分毫未动；带标记 → 原子覆写、无临时残留。"""
    root = tmp_path / "state"
    root.mkdir()
    work = root / "sprouts.jsonl"
    write_work_file(work, "HEADER-MARK\nrow1\n", root, require_markers=("HEADER-MARK",))
    with pytest.raises(LedgerError):
        write_work_file(work, "row-only\n", root, require_markers=("HEADER-MARK",))
    assert work.read_text(encoding="utf-8").startswith("HEADER-MARK")  # 洗状态被挡住
    # 覆写成功路径：不留 .part/.tmp 中间态
    write_work_file(work, "HEADER-MARK\nrow1\nrow2\n", root, require_markers=("HEADER-MARK",))
    assert sorted(p.name for p in root.iterdir()) == ["sprouts.jsonl"]


# ---------------------------------------------------------------- ⑥ write_jsonl_work_file
def test_write_jsonl_work_file_replaces_wholesale(tmp_path):
    """工作文件整份重写（当前态语义）：重写后只剩新内容，非追加。"""
    root = tmp_path / "state"
    root.mkdir()
    q = root / "queue.jsonl"
    write_jsonl_work_file(q, [{"id": 1}, {"id": 2}], root)
    write_jsonl_work_file(q, [{"id": 3}], root)
    assert [r["id"] for r in read_jsonl(q)] == [3]


# ---------------------------------------------------------------- ⑦ write_lines
def test_write_lines_prefixed_with_header_within_root(tmp_path):
    """原始行整份写（轮转搬运用）：header 在最前，每行补换行；越界拒。"""
    root = tmp_path / "state"
    (root / "archive").mkdir(parents=True)
    dest = root / "archive" / "old.jsonl"
    write_lines(dest, ["a", "b\n", "c"], root, header="# moved\n")
    assert dest.read_text(encoding="utf-8").splitlines() == ["# moved", "a", "b", "c"]
    with pytest.raises(PermissionError):
        write_lines(tmp_path / "escape.jsonl", ["x"], root)


# ---------------------------------------------------------------- ⑧ move_file（先归档后移除）
def test_move_file_writes_archive_then_removes_source(tmp_path):
    """搬运次序：归档件成功后才移除源；两处都必须在根内（越界任一侧都拒）。"""
    root = tmp_path / "state"
    (root / "archive").mkdir(parents=True)
    src = root / "traces" / "one.md"
    src.parent.mkdir()
    src.write_text("content\n", encoding="utf-8")
    dst = root / "archive" / "one.md"
    move_file(src, dst, root)
    assert dst.read_text(encoding="utf-8") == "content\n"
    assert not src.exists(), "归档成功后源必须被移走（只移动不删＝搬，不是复制）"
    # 越界目标：源在根内、目的地在根外 → 拒
    with pytest.raises(PermissionError):
        move_file(src if src.exists() else dst, tmp_path / "out.md", root)
