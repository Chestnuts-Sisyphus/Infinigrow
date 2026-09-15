# -*- coding: utf-8 -*-
"""文档↔代码同源：**机制正本说的，代码里真得有**（反之亦然）。

v1 的病根是「同一件事两处写、两边各自演化」。`tools/check_prompt_code_sync.py` 管的是
提示词↔代码；本测试补上**文档↔代码**那一半：`docs/mechanism.md` 是机制正本，
它写下的每条判据都必须在代码里有对应实现，否则文档就成了愿望清单。
"""
from __future__ import annotations

from pathlib import Path

from infinigrow.engine.model import (EDGE_DIRECTION, EDGE_GROWTH_TEST, Edge, MATURITY_CAP,
                                     MATURITY_CHAIN, SPROUTING_KINDS, DiffKind, SproutOrigin)

REPO_ROOT = Path(__file__).resolve().parents[1]
MECHANISM = (REPO_ROOT / "docs" / "mechanism.md").read_text(encoding="utf-8")
PROMPTS = "\n".join((REPO_ROOT / "prompts" / n).read_text(encoding="utf-8")
                    for n in ("tick.md", "org-session.md"))


def test_all_edges_documented_and_implemented():
    """四条边：枚举里有、正本里有、判据短语也在。"""
    for edge in Edge:
        assert edge.value in MECHANISM, "正本缺边：%s" % edge.value
        assert edge in EDGE_DIRECTION and edge in EDGE_GROWTH_TEST
        assert EDGE_GROWTH_TEST[edge]              # 每条边必须有机械判据短语


def test_maturity_chain_length_matches_doc():
    assert len(MATURITY_CHAIN) == MATURITY_CAP == 4
    assert "四步" in MECHANISM or "4 步" in MECHANISM
    assert str(MATURITY_CAP) in MECHANISM


def test_diff_kinds_documented():
    for kind in DiffKind:
        assert kind.value in MECHANISM, "正本缺差异类型：%s" % kind.value
    assert len(SPROUTING_KINDS) == 3               # 四类里恰好三类产芽


def test_three_sprout_sources_documented_and_implemented():
    """芽源恰三个：枚举三值 ⊂ 正本 ⊂ 提示词；且正本明写「零差异零芽」。"""
    values = [o.value for o in SproutOrigin]
    assert len(values) == 3
    for value in values:
        assert value in MECHANISM, "正本缺芽源：%s" % value
        assert value in PROMPTS, "提示词缺芽源：%s" % value
    assert "零差异零芽" in MECHANISM and "零差异零芽" in PROMPTS


def test_no_self_sprout_claim_is_documented():
    """正本必须写明「执行会话不自产芽」——这是机制的核心红线，不许只在代码里。"""
    assert "不自产芽" in MECHANISM or "不自造芽" in MECHANISM
    assert "不要登记新芽" in PROMPTS


def test_superseded_table_covers_the_self_sprout_clause():
    """废弃登记表必须点名那条旧条款（退役件不许悄悄消失）。"""
    text = (REPO_ROOT / "docs" / "superseded.md").read_text(encoding="utf-8")
    assert "完成即分岔" in text and "已清" in text


def test_changelog_known_limitations_exist():
    """已知限制必须真的写着（Release 说明要引用它）。"""
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "已知限制" in text


def test_journal_naming_rule_is_synced_across_three_sources():
    """K7/A8：`journal/` 命名规则 `<创建拍号4位>-<创建日期YYYYMMDD>.md` 三处同源。

    执行者提示词（tick.md）／组织会话提议（org-session.md）／主体声明（subject.md）
    必须写同一句；代码里 `subject.valid_journal_name` 是机械判据。改一处＝三处一起改。
    """
    from infinigrow.engine.subject import valid_journal_name
    # 机械判据本身
    assert valid_journal_name("0085-20260915.md")
    assert valid_journal_name("0041-20260914.md")
    assert not valid_journal_name("0085-20260914")        # 缺 .md
    assert not valid_journal_name("85-20260915.md")       # 拍号不足 4 位
    assert not valid_journal_name("0085-2026-09-15.md")   # 日期带横杠
    # 三处文本都必须含同一句规则说明（防一边改了另一边忘改）
    subject_text = (REPO_ROOT.parent / "Infinigrow-subject" / "subject.md")
    assert subject_text.is_file(), "主体声明缺失：%s" % subject_text
    texts = {
        "tick.md": (REPO_ROOT / "prompts" / "tick.md").read_text(encoding="utf-8"),
        "org-session.md": (REPO_ROOT / "prompts" / "org-session.md").read_text(encoding="utf-8"),
        "subject.md": subject_text.read_text(encoding="utf-8"),
    }
    for name, text in texts.items():
        assert "<创建拍号4位>-<创建日期YYYYMMDD>.md" in text, "%s 缺命名规则" % name
        assert "YYYYMMDD" in text, "%s 缺日期段说明" % name
