# -*- coding: utf-8 -*-
"""版本一致性：版本号有两处（包内 `__version__` 与打包元数据），不许漂移。"""
from pathlib import Path

import infinigrow

REPO_ROOT = Path(__file__).resolve().parents[1]


def _pyproject_field(field_name: str) -> str:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith(field_name + " ="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise AssertionError("pyproject.toml 里没有 %s" % field_name)


def _pyproject_version() -> str:
    return _pyproject_field("version")


def test_versions_match():
    assert infinigrow.__version__ == _pyproject_version()


def test_distribution_name_is_just_the_project_name():
    """名称就是 Infinigrow——没有「-engine」之类的后缀（2026-09-14 定名）。"""
    assert _pyproject_field("name") == "infinigrow"


def test_repo_urls_point_at_the_project():
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "Chestnuts-Sisyphus/Infinigrow" in text
    assert "infinigrow-engine" not in text


def test_version_is_v2_line():
    """断代重写：当前线是 v2（v1 已封存，不再发布 1.x）。"""
    major = int(infinigrow.__version__.split(".")[0])
    assert major == 2


def test_codename():
    assert infinigrow.__codename__ == "Infinigrow"


def test_changelog_covers_current_version():
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "v%s" % infinigrow.__version__ in text


def test_public_api_is_exported():
    for name in infinigrow.__all__:
        assert hasattr(infinigrow, name), "公开 API 缺实现：%s" % name
