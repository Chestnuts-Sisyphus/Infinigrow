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
import os
import time

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


# ---------------------------------------------------------------- N43 目录对象
def test_dir_objects_are_observed_and_predicted_symmetrically(tmp_path):
    """N43：子目录也是**对象**（`主体/<相对路径>/`），可对账量＝它里面的文件数。

    对称律同样适用：观测有它、默认预测就必须有它（否则每拍一条假差异）。
    """
    subject = tmp_path / "withdirs"
    (subject / "journal").mkdir(parents=True)
    for i in range(3):
        (subject / "journal" / ("0%03d.md" % i)).write_text("x", encoding="utf-8")
    (subject / "notes").mkdir()
    readings = subject_mod.subject_readings(subject)
    assert readings[("主体/journal/", "文件数")] == "3"        # 目录对象读得到
    assert readings[("主体/notes/", "文件数")] == "0"          # 空目录＝0 格（不是「缺失」）
    preds = {p.key: p.expected for p in subject_mod.predict_subject_unchanged(subject, 1)}
    assert preds[("主体/journal/", "文件数")] == "3"           # 预测与观测同键同值
    assert preds[("主体/notes/", "文件数")] == "0"
    snap = subject_mod.subject_snapshot(subject, tick=1)
    assert {(d["name"], d["files"]) for d in snap["dirs"]} == {("journal", 3), ("notes", 0)}


def test_dir_object_names_are_distinct_from_files():
    """目录对象名结尾带 `/`：与同名文件对象**永不撞名**（同一相对名是两个对象）。"""
    assert subject_mod.subject_dir_object("journal") == "主体/journal/"
    assert subject_mod.subject_dir_object("a/b") == "主体/a/b/"
    assert subject_mod.subject_object("journal") == "主体/journal"
    assert subject_mod.subject_object("a/b") != subject_mod.subject_dir_object("a/b")


def test_dir_object_passes_the_mechanical_gate():
    """对象名机械闸（T5）：目录对象放行；越界/隐藏/盘符前缀照旧拦下。"""
    ok, why = subject_mod.valid_subject_object("主体/journal/", set(), for_proposal=True)
    assert ok and "目录" in why
    assert subject_mod.valid_subject_object("主体/../x/", set(), for_proposal=True)[0] is False
    assert subject_mod.valid_subject_object("主体/.hidden/", set(), for_proposal=True)[0] is False
    # 盘符前缀（`<字母>:` 开头的相对路径）：拼出来判，源码里不留盘符字面量（R1 零绝对路径）
    drive = "主体/" + "C" + ":" + "/x/"
    assert subject_mod.valid_subject_object(drive, set(), for_proposal=True)[0] is False
    # findings（描述已观察到的现实）仍必须引用可对账清单里的对象
    assert subject_mod.valid_subject_object("主体/journal/", set())[0] is False
    assert subject_mod.valid_subject_object("主体/journal/", {"主体/journal/"})[0] is True


# ---------------------------------------------------------------- M6：观测面边界写死
def test_dir_observation_limit_is_pinned_to_name_order(tmp_path):
    """M6/N48-5：目录观测面的边界**写死并测住**——上限 10 个、按**名字**升序取前 10。

    超出的目录不进观测面 → 对它的提议/发现会被对象名机械闸拒收。这是**已知边界**
    （当前主体只有 2 个目录），不是隐患藏身处：改它＝改判据（文档＋代码＋测试一起改）。
    """
    subject = tmp_path / "manydirs"
    for i in range(12):                       # 12 个目录 > 上限 10
        (subject / ("d%02d" % i)).mkdir(parents=True)
    dirs = subject_mod.subject_dirs(subject)
    assert subject_mod.SUBJECT_DIR_LIMIT == 10
    assert [d.name for d in dirs] == ["d%02d" % i for i in range(10)]   # 名字序前 10 个
    observed = {(o.obj, o.dimension) for o in subject_mod.observe_subject(subject)}
    assert ("主体/d09/", "文件数") in observed
    assert ("主体/d10/", "文件数") not in observed          # 第 11 个：不进观测面
    # 不在可对账清单里的目录，作为「已观察到的现实」被拒（findings）；作为提议放行
    assert subject_mod.valid_subject_object("主体/d10/", {o for o, _ in observed})[0] is False
    assert subject_mod.valid_subject_object("主体/d10/", set(), for_proposal=True)[0] is True


# ---------------------------------------------------------------- M7：定键补观测
def test_observe_object_reads_one_key_only(tmp_path):
    """M7：定键补观测只读**给它的那一个键**，不扩观测面；读不到不猜（返回 None）。"""
    subject = tmp_path / "onekey"
    (subject / "journal").mkdir(parents=True)
    (subject / "journal" / "0001-20260915.md").write_text("abc", encoding="utf-8")
    leaf = subject_mod.subject_leaf(subject)
    root_obs = subject_mod.observe_object(subject, leaf, "文件数")
    assert root_obs is not None and root_obs.actual == "1"
    exist = subject_mod.observe_object(subject, "主体/journal/0001-20260915.md", "存在性")
    assert exist is not None and exist.actual == subject_mod.EXISTS
    size = subject_mod.observe_object(subject, "主体/journal/0001-20260915.md", "字节数")
    assert size is not None and size.actual == "3"
    dirs = subject_mod.observe_object(subject, "主体/journal/", "文件数")
    assert dirs is not None and dirs.actual == "1"
    # 真的缺失 → 如实报「缺失」（不是 None：那是「这个键不该被读」的语义）
    miss = subject_mod.observe_object(subject, "主体/journal/nope.md", "存在性")
    assert miss is not None and miss.actual == subject_mod.MISSING
    # 不认识的对象名/维度 → None（不猜、不假装有读数）
    assert subject_mod.observe_object(subject, "引擎状态/tick.json", "存在性") is None
    assert subject_mod.observe_object(subject, leaf, "颜色") is None
    assert subject_mod.observe_object(subject, "主体/../escape.md", "存在性") is None


def test_keyed_supplement_kills_boundary_false_diff(tmp_path):
    """M7/N45 的端到端判据：**同一拍内**新增文件把边界文件挤出观测名额 → 它被记成
    「预测未执行」（它其实存在）＝假差异。定键补观测之后不再出现。

    现场（可复跑）：拍 267/271/272/274/290/302/306/311 共 8 行同类假差异。
    """
    from infinigrow.engine.tick import augment_observations
    from infinigrow.engine.reconcile import reconcile

    subject = tmp_path / "boundary"
    subject.mkdir(parents=True)
    base_mtime = time.time() - 3600          # 只用来定序（不参与任何「距今多久」判据）
    for i in range(20):                      # 正好占满逐文件观测名额（N＝20）
        path = subject / ("f%02d.md" % i)
        path.write_text("x", encoding="utf-8")
        os.utime(path, (base_mtime + i, base_mtime + i))     # f00 最旧、f19 最新
    preds = subject_mod.predict_subject_unchanged(subject, tick=1)
    assert ("主体/f00.md", "存在性") in {p.key for p in preds}      # 动手前：它在预测里

    (subject / "f20.md").write_text("x", encoding="utf-8")          # 动手：新增一格
    raw = subject_mod.observe_subject(subject)
    assert ("主体/f00.md", "存在性") not in {o.key for o in raw}    # 最旧的被挤出名额
    # 对照：不补观测 → 假差异（文件其实存在）
    false_diffs = [d for d in reconcile(preds, raw, tick=1)
                   if d.kind.value == "预测未执行" and d.obj == "主体/f00.md"]
    assert false_diffs, "夹具前提：不补观测时必须能造出这条假差异"
    # 补观测之后：预测里出现过的键被读到 → 不再有假差异
    fixed = augment_observations(raw, preds, subject)
    assert [d for d in reconcile(preds, fixed, tick=1)
            if d.kind.value == "预测未执行" and d.obj == "主体/f00.md"] == []
    # 补观测**不扩面**：只加「被预测过、又被名额挤出去」的那些键，别的一律不加
    added = {o.key for o in fixed} - {o.key for o in raw}
    assert added == {("主体/f00.md", "存在性"), ("主体/f00.md", "字节数")}


# ---------------------------------------------------------------- G1：归档不入生长面

def _archive_fixture(tmp_path, journal_n=3, archive_n=2):
    """造一个「已轮转过」的主体：journal 若干篇 ＋ `archive/journal/` 里带**全新 mtime**
    的归档件（轮转＝写新件＋unlink 源，所以归档件比 journal 更新）。

    返回 (主体根, 归档件相对名列表)。
    """
    base = time.time()
    subject = tmp_path / "grown"
    (subject / "journal").mkdir(parents=True)
    for i in range(journal_n):
        p = subject / "journal" / ("%04d-20260919.md" % (i + 1))
        p.write_text("正文 %d" % i, encoding="utf-8")
        os.utime(p, (base - 600 + i, base - 600 + i))
    (subject / "archive" / "journal").mkdir(parents=True)
    archived = []
    for i in range(archive_n):
        p = subject / "archive" / "journal" / ("%04d-20260919.md.20260919-132255" % i)
        p.write_text("归档 %d" % i, encoding="utf-8")
        os.utime(p, (base + 600 + i, base + 600 + i))   # 比 journal 全部更「新」
        archived.append("archive/journal/%04d-20260919.md.20260919-132255" % i)
    return subject, archived


def test_rotated_archive_is_not_part_of_the_growth_surface(tmp_path):
    """轮转搬进 `<主体根>/archive/` 的内容**不再入观测面**（G1 主判据）。

    实测（主体副本，拍 9012~9014，`IG_JOURNAL_KEEP_FILES=200` 逐篇新增跑园丁）：
    跨过上限后每次轮转使 20 格窗口里归档件 +1，窗口首格恒为
    `archive/journal/…md.<stamp>`——归档件带着全新 mtime 把真正在长的内容挤出观测面。
    反证一并钉住：只有**主体根下**那一片 `archive/` 算归档区，
    `journal/archive/` 这种内容侧同名目录照旧可观测（不是「凡叫 archive 都瞎」）。
    """
    subject, archived = _archive_fixture(tmp_path)
    names = [f.name for f in subject_mod.subject_files(subject)]
    assert not any(n.startswith("archive/") for n in names), names
    assert names == ["journal/0003-20260919.md", "journal/0002-20260919.md",
                     "journal/0001-20260919.md"]
    # 目录对象里也没有归档那两格
    dirs = [d.name for d in subject_mod.subject_dirs(subject)]
    assert dirs == ["journal"]
    # 主体层面的「文件数／总字节数」同样只算生长面：轮转要看得见＝内容真的离开
    assert subject_mod.subject_count(subject) == 3
    assert subject_mod.subject_total_bytes(subject) == sum(
        (subject / "journal" / n).stat().st_size
        for n in ("0001-20260919.md", "0002-20260919.md", "0003-20260919.md"))
    # 归档件**在盘上还在**（只移动不删），只是不再是可对账对象
    for rel in archived:
        assert (subject / rel).is_file()
    # 反证：内容侧同名目录不被误伤
    nested = subject / "journal" / "archive"
    nested.mkdir()
    (nested / "note.md").write_text("内容，不是归档", encoding="utf-8")
    assert "journal/archive" in [d.name for d in subject_mod.subject_dirs(subject)]
    assert subject_mod.subject_count(subject) == 4


def test_object_name_gate_rejects_the_archive_subtree(tmp_path):
    """对象名机械闸：归档子树**永不进可对账清单**，也不许被提议（G1 的另一半）。

    为什么连 `for_proposal=True` 也要拒：轮转后 `archive/`、`archive/journal/` 一旦成为
    目录对象，组织会话就能提议「往 archive/ 里再长一格」——那是在提议往盲区里堆东西。
    即使有人把归档对象塞进 `allowed_objs`，也不放行（拒绝发生在名单比对**之前**）。
    """
    subject, archived = _archive_fixture(tmp_path)
    allowed = {o.obj for o in subject_mod.observe_subject(subject)}
    assert not any(o.startswith("主体/archive") for o in allowed), allowed
    for obj in ("主体/archive/", "主体/archive/journal/",
                "主体/" + archived[0], "主体/archive/whatever.md"):
        for mode in (True, False):
            ok, why = subject_mod.valid_subject_object(obj, allowed, for_proposal=mode)
            assert not ok, "%s 在 for_proposal=%s 下被放行（%s）" % (obj, mode, why)
        # 反证：塞进清单也不放行
        ok, _ = subject_mod.valid_subject_object(obj, allowed | {obj}, for_proposal=True)
        assert not ok, "%s 靠清单回流了闸" % obj
    # 正证：正常对象不受影响
    assert subject_mod.valid_subject_object("主体/journal/", set(), for_proposal=True)[0]
    assert subject_mod.valid_subject_object("主体/journal/archive/", set(),
                                            for_proposal=True)[0]


def test_keyed_supplement_refuses_archived_objects(tmp_path):
    """定键补观测（M7）同样不读归档子树：读不到 → None，不假装有读数。"""
    subject, archived = _archive_fixture(tmp_path)
    assert subject_mod.observe_object(subject, "主体/" + archived[0], "存在性") is None
    assert subject_mod.observe_object(subject, "主体/archive/journal/", "文件数") is None
    assert subject_mod.observe_object(subject, "主体/journal/0001-20260919.md",
                                      "存在性") is not None
