# -*- coding: utf-8 -*-
"""发布工具链（Q11）：tag → Release 的说明**只有一个来源**——`CHANGELOG.md`。

为什么锁这条：Release 正文此前靠人手工敲，敲漏一节就是公开面降级；
自动化的第一原则是「**抽不到就别发**」——宁可 CI 失败让人补，也不发空壳。
"""
from __future__ import annotations

from pathlib import Path

from tools.extract_changelog_section import MIN_CHARS, extract

REPO = Path(__file__).resolve().parents[1]
CHANGELOG = REPO / "CHANGELOG.md"


def test_extracts_the_section_for_a_real_tag():
    body = extract("v2.2.15", CHANGELOG)
    assert body.startswith("## v2.2.15")
    assert "solidify edge" in body
    assert len(body) > MIN_CHARS


def test_accepts_a_bare_version_too():
    assert extract("2.2.14", CHANGELOG).startswith("## v2.2.14")


def test_missing_tag_fails_loudly(tmp_path):
    """抽不到 → 抛错（工作流据此失败），**不静默发空**。"""
    fake = tmp_path / "CHANGELOG.md"
    fake.write_text("# Changelog\n\n## v1.0.0 — x\n\n- one line\n", encoding="utf-8")
    try:
        extract("v9.9.9", fake)
    except ValueError as exc:
        assert "没有 v9.9.9" in str(exc)
    else:                                             # pragma: no cover - 断言失败路径
        raise AssertionError("缺失 tag 必须抛 ValueError")


def test_too_short_section_is_rejected(tmp_path):
    """标题在、正文太短 → 同样拒绝（防「占位小节」被发成 Release）。"""
    fake = tmp_path / "CHANGELOG.md"
    fake.write_text("## v1.2.3 — stub\n\n- ok\n", encoding="utf-8")
    try:
        extract("v1.2.3", fake)
    except ValueError as exc:
        assert "太短" in str(exc)
    else:                                             # pragma: no cover
        raise AssertionError("过短小节必须抛 ValueError")


def test_release_workflow_uses_the_changelog_as_its_only_source():
    """工作流必须走这个工具、必须幂等（已存在的 Release 不覆盖）、必须有 contents: write。"""
    text = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "extract_changelog_section.py" in text
    assert "gh release view" in text and "found=no" in text      # 幂等：先查再发
    assert "permissions:" in text and "contents: write" in text
