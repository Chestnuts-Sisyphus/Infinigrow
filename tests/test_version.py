# -*- coding: utf-8 -*-
"""版本一致性：版本号有两处（包内 `__version__` 与打包元数据），不许漂移。"""
import re
from pathlib import Path

import infinigrow

REPO_ROOT = Path(__file__).resolve().parents[1]


def _ver_key(text: str) -> tuple:
    return tuple(int(x) for x in text.split(".")[:3])


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
    """当前版本必须是真正的 `## v<version>` 小节标题，且顶部小节是最新的。

    旧写法 `assert "v<ver>" in text` 只要版本号字符串出现在任何地方（哪怕只是
    别节里的一句引用）就算过——那是假覆盖。这里要求它作为**小节标题**存在；
    再钉住发布顺序：顶部那节版本 >= 已发布版本（发版前一个未发布新节正当其位）。
    """
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    version = infinigrow.__version__
    heads = [ln.strip() for ln in text.splitlines() if ln.startswith("## ")]
    assert any(re.match(r"^##\s+v?%s\b" % re.escape(version), h) for h in heads), \
        "CHANGELOG 里没有 v%s 的小节标题（只在正文里被提到不算）" % version
    first = re.search(r"^##\s+v?(\d+\.\d+\.\d+)", heads[0])
    assert first, "CHANGELOG 首个小节标题不带版本号：%r" % heads[0]
    assert _ver_key(first.group(1)) >= _ver_key(version), \
        "顶部小节 v%s 比已发布 v%s 还旧（顺序倒了）" % (first.group(1), version)


def test_public_api_is_exported():
    for name in infinigrow.__all__:
        assert hasattr(infinigrow, name), "公开 API 缺实现：%s" % name
