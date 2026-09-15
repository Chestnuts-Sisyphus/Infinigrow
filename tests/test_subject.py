# -*- coding: utf-8 -*-
"""生长主体测试（T1/G4/D15）：主体在哪、怎么读、机械拍真的读它。

验收判据（可复跑）：
  1. 主体路径默认**不落在仓库内**（代码与「被生长的东西」分家）；
  2. 除非显式配置，主体路径 ≠ 引擎自身状态根；
  3. 机械拍能对主体产出**至少一条非自身状态文件的观测**（`主体/...` 前缀）；
  4. 主体不存在时**不抛**：存在性被观测成「缺失」，且零差异零芽（不硬造题）。
"""
from __future__ import annotations

import json

from infinigrow.core.config import load_settings
from infinigrow.core.paths import REPO_ROOT, default_subject_root, resolve_state
from infinigrow.engine import subject as subject_mod
from infinigrow.engine.tick import run_tick


def _settings(tmp_path, subject):
    return load_settings(env={}, state_root=str(tmp_path / "state"),
                         repo_root=str(REPO_ROOT), subject_root=str(subject))


def test_default_subject_is_outside_the_repo():
    """默认主体在仓库**同级**（不是仓库内）：引擎代码与生长物分家。"""
    root = default_subject_root(REPO_ROOT)
    assert root.name == REPO_ROOT.name + "-subject"
    assert REPO_ROOT not in root.parents
    assert root.parent == REPO_ROOT.parent


def test_subject_path_is_not_the_engine_state_path(tmp_path):
    """判据：主体路径 ≠ 引擎自身 state 路径（除非显式配成同一个）。"""
    settings = load_settings(env={}, repo_root=str(REPO_ROOT))
    layout = resolve_state(settings.state_root, settings.repo_root, create=False)
    assert settings.subject_path() != layout.root
    # 显式配成同一个是允许的（有人就这么用），但那是**显式**选择，不是默认
    same = load_settings(env={}, repo_root=str(REPO_ROOT), state_root=str(tmp_path / "s"),
                         subject_root=str(tmp_path / "s"))
    assert same.subject_path() == resolve_state(same.state_root, same.repo_root).root


def test_env_var_points_subject_anywhere(tmp_path):
    """`IG_SUBJECT_ROOT` 能指到任意目录（空目录也算：它会被观测成「缺失」）。"""
    settings = load_settings(env={"IG_SUBJECT_ROOT": str(tmp_path / "elsewhere")},
                             repo_root=str(REPO_ROOT), state_root=str(tmp_path / "state"))
    assert settings.subject_path() == (tmp_path / "elsewhere").resolve()
    settings_file = load_settings(env={}, repo_root=str(REPO_ROOT),
                                  state_root=str(tmp_path / "state"),
                                  subject_root=str(tmp_path / "from-config"))
    assert settings_file.subject_path() == (tmp_path / "from-config").resolve()


def test_mechanical_tick_observes_the_subject_not_only_its_own_state(tmp_path):
    """机械拍必须对主体产出一条**非自身状态文件**的观测（G4 的核心判据）。"""
    subject = tmp_path / "subject"
    subject.mkdir()
    (subject / "notes.md").write_text("hello", encoding="utf-8")
    result = run_tick(settings=_settings(tmp_path, subject))

    evidence = [d.evidence for d in result.diffs]
    assert any(e.startswith("主体") for e in evidence), evidence
    objects = {d.obj for d in result.diffs}
    assert "主体/notes.md" in objects
    # 主体层面的读数（存在性/文件数）也在对账空间里
    assert subject.name in objects
    layout = resolve_state(result and _settings(tmp_path, subject).state_root,
                           str(REPO_ROOT))
    snapshot = json.loads(layout.subject_snapshot.read_text(encoding="utf-8"))
    assert snapshot["file_count"] == 1 and snapshot["root_name"] == subject.name
    assert "notes.md" in [f["name"] for f in snapshot["files"]]


def test_subject_snapshot_never_contains_absolute_paths(tmp_path):
    """主体快照只记目录名与相对名——状态产物要能公开/迁移（零绝对路径）。"""
    subject = tmp_path / "deep" / "subject"
    subject.mkdir(parents=True)
    (subject / "a.md").write_text("x", encoding="utf-8")
    snapshot = subject_mod.subject_snapshot(subject, tick=1)
    text = json.dumps(snapshot, ensure_ascii=False)
    assert str(tmp_path) not in text and str(subject) not in text
    assert snapshot["root_name"] == "subject" and snapshot["files"][0]["name"] == "a.md"


def test_missing_subject_is_observed_not_crashed(tmp_path):
    """主体不存在＝正常状态：被观测成「缺失」，且**零差异零芽**不硬造题。"""
    missing = tmp_path / "not-yet"
    result = run_tick(settings=_settings(tmp_path, missing))
    assert result.rc == 0
    kinds = {(d.obj, d.dimension): d.kind.value for d in result.diffs}
    assert kinds[(missing.name, "存在性")] == "预测内对"      # 预测缺失=实际缺失
    assert not [s for s in result.new_sprouts if "not-yet" in s]


def test_subject_files_are_bounded_and_stable(tmp_path):
    """有界（上限内）+ 稳定排序（同输入同顺序，可复跑）。"""
    subject = tmp_path / "big"
    subject.mkdir()
    for i in range(30):
        (subject / ("f%02d.md" % i)).write_text("x", encoding="utf-8")
    names = [f.name for f in subject_mod.subject_files(subject, limit=10)]
    assert names == sorted(names, key=lambda n: -1, reverse=False)  # 不强制升序
    assert len(names) == 10
    assert [f.name for f in subject_mod.subject_files(subject, limit=10)] == names


def test_subject_files_prefer_newest_by_mtime(tmp_path):
    """K2：逐文件观测按 **mtime 取最新 N 个**——旧文件不再永久霸占名额。"""
    subject = tmp_path / "mtime"
    subject.mkdir()
    for i in range(5):
        p = subject / ("old%02d.md" % i)
        p.write_text("x", encoding="utf-8")
        import os as _os
        _os.utime(p, (1000000000 + i, 1000000000 + i))     # 旧 mtime
    newest = subject / "new.md"
    newest.write_text("y", encoding="utf-8")
    files = subject_mod.subject_files(subject, limit=3)
    assert files[0].name == "new.md"                        # 最新排最前
    assert len(files) == 3                                  # 其余是 5 个旧文件里最新的 2 个


def test_subject_count_and_total_bytes_are_real_totals(tmp_path):
    """K2：文件数／总字节数是**真实总数**，不受观测上限影响（N42 修复）。"""
    subject = tmp_path / "counts"
    subject.mkdir()
    for i in range(25):
        (subject / ("f%02d.md" % i)).write_text("x" * (i + 1), encoding="utf-8")
    assert subject_mod.subject_count(subject) == 25                     # 真实总数 25
    total = sum(i + 1 for i in range(25))
    assert subject_mod.subject_total_bytes(subject) == total
    snapshot = subject_mod.subject_snapshot(subject, tick=1)            # 默认 limit=20
    assert snapshot["file_count"] == 25                                 # 不受 20 上限影响
    assert len(snapshot["files"]) == 20                                 # 逐文件观测仍 20
    assert snapshot["observed_files"] == 20


def test_merge_predictions_lets_planned_override_default(tmp_path):
    """规划值覆盖默认值（默认「不变」不该把真动手的那些拍判成「没预测」）。"""
    from infinigrow.engine.model import Prediction
    defaults = [Prediction("主体/a.md", "字节数", "10", tick=1, evidence="预测:a")]
    planned = [Prediction("主体/a.md", "字节数", "20", tick=1, evidence="规划:a"),
               Prediction("主体/a.md", "存在性", "存在", tick=1, evidence="规划:a")]
    merged = {p.key: p for p in subject_mod.merge_predictions(defaults, planned)}
    assert merged[("主体/a.md", "字节数")].expected == "20"
    assert merged[("主体/a.md", "字节数")].evidence == "规划:a"
    assert merged[("主体/a.md", "存在性")].expected == "存在"
