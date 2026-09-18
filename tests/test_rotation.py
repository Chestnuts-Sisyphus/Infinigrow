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
                                        rotate_all, rotate_frozen_sprouts,
                                        rotate_ledger, rotate_journal,
                                        search_archive)
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


def test_rotate_files_moves_excess_traces_and_reconciles(tmp_path):
    """留痕/报告按**份数**轮转（T2/A3）：造超量份数 → 只留最近 N 份，
    其余整体移进 `state/archive/files/<类>/`，归档**可检索**（只移动不删的另一半）。"""
    from infinigrow.ledger.rotation import rotate_files
    settings, layout = _layout(tmp_path, "files")
    for i in range(105):
        (layout.traces_dir / ("tick-%05d.md" % i)).write_text(
            "# trace %d\n针 %d\n" % (i, i), encoding="utf-8")
    for i in range(105):
        (layout.reconcile_dir / ("reconcile-%05d.md" % i)).write_text(
            "# report %d\n" % i, encoding="utf-8")
    reports = rotate_files(layout, keep_files=100, stamp="20260101-000004")
    by_name = {r["name"]: r for r in reports}
    assert by_name["traces"]["moved"] == 5 and by_name["traces"]["kept"] == 100
    assert by_name["reconcile"]["moved"] == 5 and by_name["reconcile"]["kept"] == 100
    assert len(list(layout.traces_dir.glob("*.md"))) == 100     # 只留最近 100 份
    assert len(list(layout.reconcile_dir.glob("*.md"))) == 100
    assert not (layout.traces_dir / "tick-00000.md").exists()   # 最旧那份已进归档
    hits = search_archive(layout, "针 0")                        # 归档里找得回（搜内容）
    assert any(h.startswith("files/traces/") for h in hits)
    assert (layout.archive_dir / "files" / "reconcile" / "reconcile-00000.md").is_file()


def test_rotate_journal_archives_redacts_and_clears(tmp_path):
    """`tools/rotate_journal.py`（启动器在句柄空隙调用）：超阈值 → 归档件**脱敏**、
    主件清空；低于阈值 → noop；归档不覆盖（同秒换后缀）。"""
    import tools.rotate_journal as rj
    settings, layout = _layout(tmp_path, "log")
    layout.logs_dir.mkdir(parents=True, exist_ok=True)
    layout.archive_dir.mkdir(parents=True, exist_ok=True)
    log = layout.logs_dir / "tick.log"
    payload = "line with Z:\\local\\path somewhere\n"           # 盘符形态，两平台都命中脱敏
    payload += "x" * 5000 + "\n"
    log.write_text(payload, encoding="utf-8")
    report = rj.rotate_journal(str(layout.root), max_bytes=1024)
    assert report and report["name"] == "logs/tick.log"
    assert report["moved"] == 1 and report["redacted"] >= 1
    assert log.is_file() and log.stat().st_size <= 1            # 主件另起（空）
    archived = list((layout.archive_dir / "files" / "logs").glob("tick.log.*"))
    assert len(archived) == 1
    text = archived[0].read_text(encoding="utf-8")
    assert "<redacted>" in text and "x" * 5000 in text           # 路径已脱敏、内容在
    assert "line with" in text.split("<redacted>")[0]
    # 低于阈值 → noop
    assert rj.rotate_journal(str(layout.root), max_bytes=1024) is None
    # 同秒重跑不覆盖：再次超阈值 → 换后缀
    log.write_text(payload, encoding="utf-8")
    rj.rotate_journal(str(layout.root), max_bytes=1024)
    assert len(list((layout.archive_dir / "files" / "logs").glob("tick.log.*"))) == 2


def test_rotate_journal_moves_excess_into_subject_archive(tmp_path):
    """K6/A7：主体 journal 超上限 → 只移动进 `<主体根>/archive/journal/`（不删）。"""
    subject = tmp_path / "subject"
    journal = subject / "journal"
    journal.mkdir(parents=True, exist_ok=True)
    for i in range(205):                       # 205 篇 > 默认 200
        (journal / ("%04d-20260915.md" % i)).write_text("x", encoding="utf-8")
    report = rotate_journal(subject, keep_files=200, stamp="20260915-120000")
    assert report and report["moved"] == 5
    assert report["kept"] == 200
    kept = sorted(p.name for p in journal.glob("*.md"))
    assert len(kept) == 200
    assert kept[0] == "0005-20260915.md"                 # 最旧 5 篇被移走
    archived = list((subject / "archive" / "journal").glob("*.md.*"))
    assert len(archived) == 5                            # 5 篇都在归档里（只移动不删）
    all_names = kept + [a.name.split(".")[0] for a in archived]
    assert len(set(all_names)) == 205                    # 一篇没丢


def test_rotate_journal_noop_below_limit(tmp_path):
    """K6/A7：低于上限（或 journal 不存在）＝不动（幂等）。"""
    subject = tmp_path / "subject2"
    journal = subject / "journal"
    journal.mkdir(parents=True, exist_ok=True)
    for i in range(50):
        (journal / ("%04d-20260915.md" % i)).write_text("x", encoding="utf-8")
    assert rotate_journal(subject, keep_files=200) is None
    assert not (subject / "archive").exists()
    assert rotate_journal(tmp_path / "no-such-subject", keep_files=200) is None


# ---------------------------------------------------------------- M5：冻结区容量与整理
def test_rotate_frozen_sprouts_moves_oldest_and_keeps_every_line(tmp_path):
    """M5/N48-4：冻结区超上限 → 最旧的**只移动**进 `state/archive/files/frozen/`。

    判据：①主件缩短到尾部 `keep_tail` 行；②归档件 ∪ 主件 ＝ 原文件（逐字，一行不丢）；
    ③低于上限＝不动（幂等）——冻结区此前**没有任何容量判据**（实测每拍 +36~38 行单调增长）。
    """
    settings, layout = _layout(tmp_path)
    lines = ["{\"id\": \"lib%04d-001-A\", \"obj\": \"A\"}" % i for i in range(10)]
    layout.frozen_sprouts.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert rotate_frozen_sprouts(layout, cap=50, keep_tail=40) is None   # 未超上限 → 不动
    report = rotate_frozen_sprouts(layout, cap=5, keep_tail=4,
                                   stamp="20260916-220000")
    assert report and report["moved"] == 6 and report["kept"] == 4
    kept = [ln for ln in layout.frozen_sprouts.read_text(encoding="utf-8").splitlines()
            if ln.strip()]
    assert kept == lines[-4:]                                  # 保留的是**最新的**尾部
    archive = (layout.archive_dir / "files" / "frozen"
               / "sprouts-frozen.20260916-220000.jsonl")
    assert archive.is_file()
    archived = [ln for ln in archive.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.startswith("#")]
    assert archived == lines[:6]                               # 移走的是最旧的 6 行
    assert archived + kept == lines                            # 一行不丢、顺序不变


def test_gardener_rotates_frozen_sprouts(tmp_path):
    """M5 接线：园丁每次跑顺手整理冻结区（阈值是配置项 `frozen_cap`／`frozen_keep_tail`）。"""
    settings, layout = _layout(tmp_path)
    layout.frozen_sprouts.write_text(
        "\n".join("{\"id\": \"s%d\"}" % i for i in range(12)) + "\n", encoding="utf-8")
    from infinigrow.core.config import load_settings as _ls
    from infinigrow.garden.gardener import run_gardener
    s2 = _ls(env={}, state_root=str(tmp_path / "state"), repo_root=str(REPO_ROOT),
             subject_root=str(settings.subject_path()), frozen_cap=10, frozen_keep_tail=8)
    report = run_gardener(settings=s2, write_alert=False)
    kept = [ln for ln in layout.frozen_sprouts.read_text(encoding="utf-8").splitlines()
            if ln.strip()]
    assert len(kept) == 8
    assert any("冻结区整理" in n for n in report.notes)


def test_gardener_rotates_subject_journal(tmp_path):
    """K6/A7：园丁顺手轮转主体 journal（`journal_keep_files` 可配）。"""
    settings, layout = _layout(tmp_path)
    subject = settings.subject_path()
    journal = subject / "journal"
    journal.mkdir(parents=True, exist_ok=True)
    for i in range(15):                          # 超过可配的 10 篇
        (journal / ("%04d-20260915.md" % i)).write_text("x", encoding="utf-8")
    from infinigrow.core.config import load_settings as _ls
    s2 = _ls(env={}, state_root=str(tmp_path / "state"), repo_root=str(REPO_ROOT),
             subject_root=str(subject), journal_keep_files=10)
    from infinigrow.garden.gardener import run_gardener
    report = run_gardener(settings=s2, write_alert=False)
    kept = list(journal.glob("*.md"))
    assert len(kept) == 10
    assert any("journal 轮转" in n for n in report.notes)
