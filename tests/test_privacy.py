# -*- coding: utf-8 -*-
"""发布前隐私闸测试：仓库自身必须是干净的（开源红线的机械化判据）。

两层：
  - **通用层**（随仓库走，CI 也跑）：绝对路径、凭据字面量、邮箱；
  - **项目层**（本地有 `privacy-deny.txt` 时才跑）：本机路径根、身份词、他项目名。
    该文件已在 `.gitignore` 里——**禁列清单本身不进公共仓库**。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER = REPO_ROOT / "tools" / "privacy_scan.py"


def _load_scanner():
    spec = importlib.util.spec_from_file_location("privacy_scan", SCANNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_scanner_exists():
    assert SCANNER.is_file()


def test_repo_is_free_of_generic_privacy_hits():
    scan = _load_scanner()
    rules = list(scan.GENERIC_RULES)
    hits = []
    for full, rel in scan.walk(REPO_ROOT):
        hits.extend(scan.scan_file(full, rules, REPO_ROOT, rel))
    assert hits == [], "通用隐私命中：%s" % hits[:10]


def test_repo_is_free_of_project_deny_hits():
    scan = _load_scanner()
    deny = REPO_ROOT / "privacy-deny.txt"
    if not deny.is_file():
        pytest.skip("本地无项目层禁列（CI 环境正常）")
    rules = scan.load_deny(deny)
    hits = []
    for full, rel in scan.walk(REPO_ROOT):
        hits.extend(scan.scan_file(full, rules, REPO_ROOT, rel))
    assert hits == [], "项目层禁列命中：%s" % hits[:10]


#: 触发通用层规则的本机路径样本。**运行时拼装**：源码里不许出现字面绝对路径，
#: 否则这条测试样本本身会被 R1 与隐私闸扫出来（同 `tests/test_rotation.py` 的脱敏样本口径）。
_ABS_PATH_LINE = "config lives at " + "D" + ":/" + "local" + "/" + "notes.txt" + "\n"


def _make_tree(tmp_path, ignore_lines):
    """造一棵小树：一个被 .gitignore 列出的目录、一个被列出的顶层文件、一个正常目录。"""
    (tmp_path / ".gitignore").write_text("".join(ignore_lines), encoding="utf-8")
    (tmp_path / "localonly").mkdir()
    (tmp_path / "localonly" / "note.md").write_text(_ABS_PATH_LINE, encoding="utf-8")
    (tmp_path / "localfile.md").write_text(_ABS_PATH_LINE, encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "code.md").write_text(_ABS_PATH_LINE, encoding="utf-8")
    return tmp_path


def test_gitignored_top_level_names_are_out_of_scope(tmp_path):
    """**正例**：`.gitignore` 的顶层名＝发布边界，不进公共仓库的东西不参与扫描。

    为什么锁这条：本地专有材料（交接文档、本机配置）里的路径不可能泄漏给任何人，
    但旧口径只认硬编码 `SKIP_DIRS`——每新增一个这类目录就得回来补一行，
    漏补就让本地 `privacy_scan` 与 CI 闸互相矛盾。
    """
    scan = _load_scanner()
    root = _make_tree(tmp_path, ["localonly/\n", "localfile.md\n"])
    rels = {rel for _, rel in scan.walk(root)}
    assert not any(r.startswith("localonly/") for r in rels), rels
    assert "localfile.md" not in rels, rels
    assert "src/code.md" in rels, rels


def test_unignored_paths_are_still_reported(tmp_path):
    """**反例**：没被 `.gitignore` 列出的内容照报——忽略名单不是免检通道。"""
    scan = _load_scanner()
    root = _make_tree(tmp_path, ["localonly/\n"])       # 只忽略目录，顶层文件与 src 不忽略
    hits = []
    for full, rel in scan.walk(root):
        hits.extend(scan.scan_file(full, list(scan.GENERIC_RULES), root, rel))
    reported = {h["file"] for h in hits}
    assert "localfile.md" in reported, hits
    assert "src/code.md" in reported, hits
    assert not any(r.startswith("localonly/") for r in reported), hits


def test_scanner_rejects_parent_traversal(tmp_path):
    """扫描器自身的路径安全：含 .. 上跳的输入必须被拒。"""
    scan = _load_scanner()
    with pytest.raises(SystemExit):
        scan.normalize("../outside")


def test_state_and_archive_are_gitignored():
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    lines = {line.strip().rstrip("/") for line in text.splitlines()}
    for name in ("state", "archive", "privacy-deny.txt"):
        assert name in lines, "%s 必须在 .gitignore 里" % name
