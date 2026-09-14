# -*- coding: utf-8 -*-
"""账本轮转测试（T6/G7）：**只移动不删**，而且不丢语义。

验收判据（可复跑）：
  1. 造超阈值账本 → 轮转后主账本变小、归档区有档；
  2. **没丢事实**：归档行 ∪ 主账本保留行 ＝ 原账本全部行（逐字比对，含坏行）；
  3. **保语义**：成熟链按「每对象最新一行」保留 → 轮转前后 `maturity_of` 结果一致；
  4. 归档**可检索**（只移动不删的另一半：留得下，还要找得回）；
  5. 低于阈值＝不动（幂等）。
"""
from __future__ import annotations

import json

from infinigrow.core.paths import REPO_ROOT, resolve_state
from infinigrow.core.config import load_settings
from infinigrow.engine.tick import maturity_of, run_tick
from infinigrow.ledger.rotation import (LEDGER_POLICY, TAIL, archived_files,
                                        rotate_all, rotate_ledger, search_archive)
from infinigrow.ledger.store import append_jsonl, read_jsonl


def _layout(tmp_path, state="state"):
    settings = load_settings(env={}, state_root=str(tmp_path / state),
                             repo_root=str(REPO_ROOT),
                             subject_root=str(tmp_path / "subject"))
    return settings, resolve_state(settings.state_root, settings.repo_root, create=True)


def test_rotate_moves_lines_and_keeps_every_fact(tmp_path):
    settings, layout = _layout(tmp_path)
    original = []
    for i in range(500):
        rec = {"kind": "预测内对", "obj": "X%03d" % i, "dimension": "字节数", "tick": i}
        append_jsonl(layout.diff_ledger, rec, layout.root)
        original.append(json.dumps(rec, ensure_ascii=False, sort_keys=True))

    report = rotate_ledger(layout.diff_ledger, layout.archive_dir, layout.root,
                           policy=(TAIL,), keep_tail=100, stamp="20260101-000000")
    assert report and report["moved"] == 400 and report["kept"] == 100
    assert report["bytes_after"] < report["bytes_before"]

    kept = [line for line in layout.diff_ledger.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    archive = layout.archive_dir / report["archive"]
    moved = [line for line in archive.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.startswith("#")]
    assert kept == original[-100:]
    assert moved == original[:-100]
    assert moved + kept == original                     # 一行不少、一行不改（头+尾=原序）


def test_rotation_is_a_noop_below_threshold(tmp_path):
    settings, layout = _layout(tmp_path, "small")
    append_jsonl(layout.diff_ledger, {"kind": "预测内对", "obj": "X", "tick": 1},
                 layout.root)
    reports = rotate_all(layout, max_bytes=10 * 1024 * 1024, keep_tail=100)
    assert reports == [] and archived_files(layout) == []


def test_latest_per_key_policy_preserves_maturity_semantics(tmp_path):
    """成熟链按「每对象最新一行」保留：轮转前第 4 步，轮转后**还是**第 4 步。"""
    settings, layout = _layout(tmp_path, "maturity")
    for tick in range(1, 5):
        append_jsonl(layout.maturity_chain,
                     {"obj": "old.jsonl", "step": tick, "tick": tick}, layout.root)
    for step in (1, 2):
        append_jsonl(layout.maturity_chain,
                     {"obj": "new.jsonl", "step": step, "tick": step}, layout.root)
    before = maturity_of(layout)
    assert before == {"old.jsonl": 4, "new.jsonl": 2}

    report = rotate_ledger(layout.maturity_chain, layout.archive_dir, layout.root,
                           policy=LEDGER_POLICY["maturity.jsonl"], keep_tail=2,
                           stamp="20260101-000001")
    assert report and report["kept"] == 2               # 两个对象各留一行
    assert maturity_of(layout) == before                # 语义没倒退


def test_rotation_end_to_end_via_tick_and_gardener(tmp_path):
    """真机形态：先跑几拍攒账，再让园丁顺手轮转（阈值调小）。"""
    settings, layout = _layout(tmp_path, "e2e")
    settings.rotate_max_bytes = 200                     # 小阈值：几拍就超
    settings.rotate_keep_tail = 5
    for _ in range(6):
        assert run_tick(settings=settings).rc == 0
    from infinigrow.garden.gardener import run_gardener
    report = run_gardener(settings=settings)
    assert report.rotated, report.as_dict()
    assert archived_files(layout)
    # 轮转后账本仍可解析（坏行不会被留下）
    for name in ("diffs.jsonl", "outcomes.jsonl", "maturity.jsonl"):
        path = layout.root / name
        if path.is_file():
            rows = read_jsonl(path)
            assert rows is not None


def test_archive_is_searchable(tmp_path):
    settings, layout = _layout(tmp_path, "search")
    for i in range(50):
        append_jsonl(layout.diff_ledger,
                     {"kind": "预测内对", "obj": "needle-%02d" % i, "tick": i},
                     layout.root)
    rotate_ledger(layout.diff_ledger, layout.archive_dir, layout.root,
                  policy=(TAIL,), keep_tail=5, stamp="20260101-000002")
    hits = search_archive(layout, "needle-07")
    assert hits and hits[0].startswith("diffs.")


def test_bad_lines_survive_rotation(tmp_path):
    """坏行也要跟着走（轮转不是「顺手清洗历史」）。"""
    settings, layout = _layout(tmp_path, "badline")
    path = layout.diff_ledger
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write('{"kind": "预测内对", "obj": "good", "tick": 1}\n')
        fh.write("{ 这不是合法 JSON\n")
        fh.write('{"kind": "预测内对", "obj": "good2", "tick": 2}\n')
    report = rotate_ledger(path, layout.archive_dir, layout.root, policy=(TAIL,),
                           keep_tail=1, stamp="20260101-000003")
    archive_text = (layout.archive_dir / report["archive"]).read_text(encoding="utf-8")
    assert "这不是合法 JSON" in archive_text


def test_archive_name_cannot_escape_the_root(tmp_path):
    """越界的账本路径被**响亮拒绝**；归档名里的 `..` 被洗掉（写盘守卫 + 名字净化）。"""
    settings, layout = _layout(tmp_path, "guard")
    import pytest
    with pytest.raises(PermissionError):                 # 越界＝**响亮拒绝**，不是静默跳过
        rotate_ledger(layout.root / ".." / "outside.jsonl", layout.archive_dir,
                      layout.root, policy=(TAIL,), keep_tail=1, stamp="../../evil")
    assert not (tmp_path / "evil.jsonl").exists()        # 根外没被写出任何东西
    assert archived_files(layout) == []                  # 归档区也没被污染
