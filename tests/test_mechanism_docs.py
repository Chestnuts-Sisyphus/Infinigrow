# -*- coding: utf-8 -*-
"""文档↔代码同源：**机制正本说的，代码里真得有**（反之亦然）。

v1 的病根是「同一件事两处写、两边各自演化」。`tools/check_prompt_code_sync.py` 管的是
提示词↔代码；本测试补上**文档↔代码**那一半。

**语言分层（2026-09-17）**：机制正本是**中文**（`docs/zh/mechanism.md`）——机制词是
引擎的标识符（代码/提示词/账本都用它）；公开文档是英文（`docs/mechanism.md`），
必须带**双语术语表**。所以：中文正本管「判据短语」的同源断言，
英文公开文档管「术语覆盖」的断言（两边都不许缺）。
"""
from __future__ import annotations

from pathlib import Path

from infinigrow.engine.model import (EDGE_DIRECTION, EDGE_GROWTH_TEST, Edge, MATURITY_CAP,
                                     MATURITY_CHAIN, SPROUTING_KINDS, DiffKind, SproutOrigin)

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"
#: 机制正本（中文；判据短语在这里）
MECHANISM = (DOCS / "zh" / "mechanism.md").read_text(encoding="utf-8")
#: 公开设计文档（英文；术语与译文在这里）
MECHANISM_EN = (DOCS / "mechanism.md").read_text(encoding="utf-8")
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
    text = (DOCS / "zh" / "superseded.md").read_text(encoding="utf-8")
    assert "完成即分岔" in text and "已清" in text
    english = (DOCS / "superseded.md").read_text(encoding="utf-8")
    assert "Branch on completion" in english and "cleared" in english     # 英文公开版同样登记


def test_release_notes_state_known_limitations():
    """已知限制必须真的写着（Release 说明要引用它）——公开面是英文的。"""
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "release-notes-v2.0.0.md" in changelog          # 变更日志指到发布说明
    for name in ("release-notes-v2.0.0.md", "release-notes-v2.1.0.md"):
        text = (DOCS / name).read_text(encoding="utf-8")
        assert "Known limitations" in text, "%s 缺已知限制" % name


def test_english_public_docs_carry_the_mechanism_glossary():
    """公开文档必须是英文，且带**双语术语表**（机制词是标识符，不能只在中文正本里）。

    语言分层：判据短语在中文正本（`docs/zh/`），公开英文文档负责「读得懂 + 术语可查」。
    """
    for edge in Edge:
        assert edge.value in MECHANISM_EN, "英文文档缺术语：%s" % edge.value
    for kind in DiffKind:
        assert kind.value in MECHANISM_EN, "英文文档缺差异类型：%s" % kind.value
    for origin in SproutOrigin:
        assert origin.value in MECHANISM_EN, "英文文档缺芽源：%s" % origin.value
    assert "Glossary" in MECHANISM_EN and "no difference, no sprout" in MECHANISM_EN


def test_journal_naming_rule_is_synced_across_three_sources():
    """K7/A8：`journal/` 命名规则 `<创建拍号4位>-<创建日期YYYYMMDD>.md` 三处同源。

    执行者提示词（tick.md）／组织会话提议（org-session.md）／主体文档（`docs/zh/growth-subject.md`）
    必须写同一句；代码里 `subject.valid_journal_name` 是机械判据。改一处＝各处一起改。
    （本机主体声明 `<仓库同级>/<主体名>/subject.md` 也同步该句，但它不在仓库里、不在 CI 上
    ——仓库内断言以中文正本为准；英文公开文档用英文写出同一条规则。）
    """
    from infinigrow.engine.subject import valid_journal_name
    # 机械判据本身
    assert valid_journal_name("0085-20260915.md")
    assert valid_journal_name("0041-20260914.md")
    assert not valid_journal_name("0085-20260914")        # 缺 .md
    assert not valid_journal_name("85-20260915.md")       # 拍号不足 4 位
    assert not valid_journal_name("0085-2026-09-15.md")   # 日期带横杠
    # 三处文本都必须含同一句规则说明（防一边改了另一边忘改）
    texts = {
        "tick.md": (REPO_ROOT / "prompts" / "tick.md").read_text(encoding="utf-8"),
        "org-session.md": (REPO_ROOT / "prompts" / "org-session.md").read_text(encoding="utf-8"),
        "zh/growth-subject.md": (DOCS / "zh" / "growth-subject.md").read_text(encoding="utf-8"),
    }
    for name, text in texts.items():
        assert "<创建拍号4位>-<创建日期YYYYMMDD>.md" in text, "%s 缺命名规则" % name
        assert "YYYYMMDD" in text, "%s 缺日期段说明" % name
    english = (DOCS / "growth-subject.md").read_text(encoding="utf-8")
    assert "YYYYMMDD" in english, "英文公开文档缺命名规则"


def test_reminder_exit_and_requestion_are_documented():
    """N48 修复（v2.2.7）：**提醒的出口**与**冻结芽的重问**必须三处同源。

    为什么锁这两条：它们治的是同一个病的两半——
    ① 去重缺口（只扫活跃队列 → 每拍重立 ~36 根重复芽，把队列占满）；
    ② 提醒没有出口（「可用性」机械层读不到兑现 → 一条永真、可无限重生的提醒）。
    只修 ① 不修 ② ＝ 把这条渠道断电（队列 ~150 拍后见底 → 空转）。
    所以正本、提示词、代码三处都必须写着「结案」与「重问」，缺一处就是漂移。
    """
    words = {"结案": "engine/sprout_sources.py", "重问": "engine/sprout_queue.py"}
    for term, owner in words.items():
        assert term in MECHANISM, "机制正本缺：%s" % term
        assert term in PROMPTS, "提示词缺：%s" % term
        assert term in (REPO_ROOT / "src" / "infinigrow" / owner).read_text(encoding="utf-8")


def test_observation_surface_boundary_is_documented():
    """M6/M7 的文档面：观测面**有界**（目录 10／文件 20）与**定键补观测**必须写在正本里，
    并且和代码里的常量同源——「边界」这种东西不写下来就等于不存在。"""
    from infinigrow.engine.subject import SUBJECT_DIR_LIMIT, SUBJECT_FILE_LIMIT
    assert str(SUBJECT_DIR_LIMIT) in MECHANISM and str(SUBJECT_FILE_LIMIT) in MECHANISM
    assert "定键补观测" in MECHANISM
    # 英文公开文档必须同样写着（公开面与正本两边都不许缺）
    assert "keyed supplemental reading" in MECHANISM_EN
    architecture = (DOCS / "architecture.md").read_text(encoding="utf-8")
    assert "directory object" in architecture.lower(), "架构文档的观测面摘要必须含目录对象（M9）"
    assert str(SUBJECT_DIR_LIMIT) in MECHANISM_EN
    zh_arch = (DOCS / "zh" / "architecture.md").read_text(encoding="utf-8")
    assert "目录对象" in zh_arch


def test_frozen_zone_has_a_capacity_rule_documented():
    """M5：冻结区容量判据（超上限只移动最旧的进归档）必须写在正本与配置表里。"""
    from infinigrow.core.config import Settings
    assert "frozen_cap" in MECHANISM and "frozen_requestion_ticks" in MECHANISM
    assert hasattr(Settings, "frozen_cap") and hasattr(Settings, "frozen_requestion_ticks")
    assert hasattr(Settings, "frozen_keep_tail")


def test_replacement_keeps_the_age_is_documented_everywhere():
    """Q1/A1：同键「新顶旧」时**继承旧芽出生拍**——五处同改，缺一处就是漂移面。

    这条规则曾经只落在代码 docstring、测试与 CHANGELOG 里，两份机制正本与提示词都没写
    （收尾自检抓到的静默漂移面）。所以这里把它**钉住**：中英正本＋组织会话提示词
    都必须写着「重提不改年龄」（含推论：连领预算不继承）。判据短语在中英两侧各取一个
    不可歧义的说法，机械可判。
    """
    from infinigrow.engine.sprout_queue import SproutQueue
    from infinigrow.engine.model import Sprout, SproutOrigin
    # 机械行为本身（正本说的，代码真做）
    q = SproutQueue(cap=10)
    q.add(Sprout(id="s1", obj="A", dimension="大小", pointer="p",
                 origin=SproutOrigin.DIFF, created_tick=10))
    q.add(Sprout(id="s2", obj="A", dimension="大小", pointer="p",
                 origin=SproutOrigin.DIFF, created_tick=90))
    assert q.sprouts[0].created_tick == 10
    # 五处文本（中英正本各一处 ＋ 提示词一处）
    assert "重提不改问题的年龄" in MECHANISM, "中文正本缺 Q1 规则"
    assert "连领计数不继承" in MECHANISM, "中文正本缺「连领预算不继承」"
    assert "does not change the question's age" in MECHANISM_EN, "英文正本缺 Q1 规则"
    assert "lead budget is not inherited" in MECHANISM_EN, "英文正本缺「连领预算不继承」"
    assert "重提不改问题的年龄" in PROMPTS, "提示词缺 Q1 规则"


def test_quiet_streak_semantics_are_settled_not_open_anymore():
    """N58-① 收口：判据④「行数口径」是**已定案**，三处必须同写，旧「未决项」措辞不许回来。

    为什么锁这条：这个未决项挂了很久，唯一的实际风险不是数字选错，而是**有人把标签
    当成拍数去「顺手修」**——那会让组织段近乎永不触发（实测拍 556–628：最长连续安静 1 拍）。
    定案＝行为不变，所以同时钉住 `DEFAULT_ZERO_GAP == 10`。
    """
    from infinigrow.engine.org_trigger import DEFAULT_ZERO_GAP
    assert DEFAULT_ZERO_GAP == 10, "定案是语义口径，不是调数字"
    assert "语义定案：保持行数口径" in MECHANISM, "中文正本缺 N58-① 的裁定"
    assert "未决项（N58-①）" not in MECHANISM, "旧措辞回来了：这条已收口"
    assert "semantics are now settled" in MECHANISM_EN, "英文公开文档缺 N58-① 的裁定"
    assert "open decision" not in MECHANISM_EN, "旧措辞回来了：这条已收口"
    trigger_path = REPO_ROOT / "src" / "infinigrow" / "engine" / "org_trigger.py"
    trigger = trigger_path.read_text(encoding="utf-8")
    assert "语义定案：保持行数口径" in trigger, "代码 docstring 与正本漂移"
