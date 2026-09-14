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
