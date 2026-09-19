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

    # 上面两组只查子串：`10`／`20` 在正本里因别的判据（空转 12 拍、冷却 30 分钟、
    # 队列 50）本来就出现，改常量也不会让它变红——所以判据要钉在**写明上限的那句话**上。
    zh_subject = (DOCS / "zh" / "growth-subject.md").read_text(encoding="utf-8")
    en_subject = (DOCS / "growth-subject.md").read_text(encoding="utf-8")
    for pattern, doc, label in (
            ("每个子目录（最多 %d 个）" % SUBJECT_DIR_LIMIT, zh_subject, "中文正本·目录上限"),
            ("每个文件（最多 %d 个）" % SUBJECT_FILE_LIMIT, zh_subject, "中文正本·文件上限"),
            ("目录上限 %d 个" % SUBJECT_DIR_LIMIT, zh_subject, "中文正本·目录上限句"),
            ("Directory limit %d, file limit %d" % (SUBJECT_DIR_LIMIT, SUBJECT_FILE_LIMIT),
             en_subject, "英文公开文档·上限句")):
        assert pattern in doc, "%s 与代码常量不符（找的是：%s）" % (label, pattern)
        # 反证：句式必须真的带数字，改成 99 就该找不到
        assert pattern.replace(str(SUBJECT_DIR_LIMIT), "99").replace(
            str(SUBJECT_FILE_LIMIT), "99") not in doc, "%s 的句式不带数字，判据失效" % label


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


def test_bucket_axes_claimed_in_readme_and_prompt_match_the_code():
    """兑现率桶的轴：代码是唯一事实源，公开文档与提示词不许宣称第三轴是成熟步。

    为什么锁这条：README（中英）与 `prompts/org-session.md` 一度都写着
    「对象域 × 边类型 × 成熟链步」，而 `reconcile._bucket` 算的是
    （对象域, 预测边, 实际边）——提示词照错轴要求会话「引哪一桶」，
    等于让它去引一个机械上算不出来的桶。判据是机械的：旧措辞出现即红。
    """
    from infinigrow.engine.reconcile import _bucket
    assert _bucket({"obj": "主体/journal/x.md", "predicted_edge": "固化",
                    "actual_edge": "固化"}) == ("主体/journal", "固化", "固化")
    wrong = ("edge type × maturity step", "边类型 × 成熟链步", "边类型 × 成熟步")
    for rel, must_have in (("README.md", "predicted edge × actual edge"),
                           ("README.zh-CN.md", "对象域 × 预测边 × 实际边"),
                           ("prompts/org-session.md", "对象域 × 预测边 × 实际边")):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert must_have in text, "%s 缺正确的桶轴" % rel
        for phrase in wrong:
            assert phrase not in text, "%s 又宣称成熟步是桶的轴：%s" % (rel, phrase)


def test_subject_state_claims_in_the_design_of_record_are_dated_snapshots():
    """讲主体的文档只能写**带日期的快照**，不能写成无日期的现状——主体在库外会长。

    为什么锁这条：`docs/zh/growth-subject.md` 一度写「当前主体只有 2 个目录
    （journal／archive）」，而实测（拍 633）两个顶层目录是 `journal`／`app`，
    `archive/` 要到首次轮转才建。判据（目录上限 10）一直是对的，错的是**当成现状的观测**。
    反向断言＝旧枚举回来即红；正向断言＝快照必须带日期。
    """
    text = (DOCS / "zh" / "growth-subject.md").read_text(encoding="utf-8")
    assert "journal／archive" not in text, "主体目录枚举又写回旧的那一份"
    assert "带日期的快照" in text, "库外现状必须标注为快照（附实测日期），否则会长成假事实"
    assert "目录上限 10 个" in text, "判据本身不许被顺手改掉（改判据＝改文档＋代码＋测试）"


def _count_py_lines(folder):
    """行数语义与 `wc -l` 一致：数换行符，不数 splitlines 的尾巴。"""
    total = 0
    for path in (REPO_ROOT / folder).rglob("*.py"):
        total += path.read_bytes().count(b"\n")
    return total


def test_readme_size_figures_match_the_tree():
    """README（双语）写的规模数字必须与树对上，且两版互相对上。

    为什么锁这条：这一版 README 的规模数字刚错过一次（宣称 ~4,400／~2,600，
    实测 7,083／5,617，低估约 60%）。**改掉数字不等于改掉漏洞**——之所以能烂，
    是因为没有任何机械判据盯着它。容差取 100 行＝该句「四舍五入到百位」的写法本身。
    """
    import re
    src = _count_py_lines("src")
    tests = _count_py_lines("tests")
    patterns = {"README.md": r"[~≈]?([\d,]+) lines of Python plus [~≈]?([\d,]+) lines of tests",
                "README.zh-CN.md": r"[~≈]?([\d,]+) 行 Python ＋ [~≈]?([\d,]+) 行测试"}
    claimed = {}
    for rel, pattern in patterns.items():
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        match = re.search(pattern, text)
        assert match, "%s 找不到规模数字那句（措辞变了要同步改这条判据）" % rel
        pair = tuple(int(g.replace(",", "")) for g in match.groups())
        claimed[rel] = pair
        assert abs(pair[0] - src) <= 100, "%s 的 Python 行数 %s 与实测 %s 对不上" % (rel, pair[0], src)
        assert abs(pair[1] - tests) <= 100, "%s 的测试行数 %s 与实测 %s 对不上" % (rel, pair[1], tests)
    assert claimed["README.md"] == claimed["README.zh-CN.md"], "双语规模数字各说一遍"


def test_every_numeric_knob_is_listed_in_the_config_table():
    """`core/config.py` 的配置表必须收录每个整型旋钮，默认值与环境变量名都要对得上。

    为什么锁这条：`frozen_review_every` 每拍都在 `tick.py` 里用（`tick % cfg.frozen_review_every`），
    却在**任何文档里都不存在**——表就是这张表的读者唯一的旋钮清单，漏一行不会报错，
    只会安静地变成「没人知道的开关」。反向也查：表里不许有字段表没有的行。
    """
    import re

    from infinigrow.core.config import ENV_PREFIX, _FIELDS
    src = (REPO_ROOT / "src" / "infinigrow" / "core" / "config.py").read_text(encoding="utf-8")
    rows = {m[0]: (m[1], m[2]) for m in re.findall(
        r"^\| `([a-z_]+)` \| `(IG_[A-Z_]+)` \| (\d+) \|", src, re.M)}
    ints = {name: default for name, (kind, default) in _FIELDS.items() if kind is int}
    assert ints, "配置表判据失去对象：整型字段一个都没有了"
    for name, default in sorted(ints.items()):
        assert name in rows, "旋钮 `%s` 没进配置表（使用者无从发现它）" % name
        env, stated = rows[name]
        assert env == ENV_PREFIX + name.upper(), "%s 的环境变量名与表不一致" % name
        assert stated == str(default), "%s：表里写 %s，真实默认 %s" % (name, stated, default)
    for name in sorted(rows):
        assert name in _FIELDS, "表里有 `%s` 但字段表没有（凭空造的旋钮）" % name


def test_org_trigger_measures_attempts_not_llm_calls():
    """组织段判据的单位＝**一次起跑过的组织段尝试**，四处文案同一口径（且不许写反）。

    为什么锁这条（第二轮订正）：那份账的文件名是 `org-llm.jsonl`，最早的文案写「距上次
    LLM 段」——但一行也可以在执行者失败、甚至提示词缺失时写下，「试过」不等于「调成过」。
    而上一轮订正时又走向另一个反面：写着「只跑机械拍的根拍 1 也会留一行」，实测（`IG_EXECUTOR=""`
    连跑 3 拍：无 `org-llm.jsonl`、`org-check` 仍报①）证明**没接执行者时组织段根本不跑**。
    两头都是同一件事：文案说的单位必须与写入条件一致。旧措辞（两种）出现即红。
    """
    trigger = (REPO_ROOT / "src" / "infinigrow" / "engine" / "org_trigger.py").read_text(
        encoding="utf-8")
    assert "一次组织段尝试" in trigger, "冷却闸文案又回到不准确的单位"
    assert "距上次组织段尝试不足" in trigger, "冷却闸的 reason 不再说「尝试」"
    assert "没接执行者时组织段根本不跑" in trigger, "自述还留着上一版写反的那半句"
    assert "LLM 段" not in trigger, "面向使用者的文案把「尝试」说成了「LLM 调用」"
    assert "①从未跑过组织段" in trigger
    for doc in (MECHANISM, MECHANISM_EN):
        assert ("组织段尝试账" in doc) or ("org-attempt ledger" in doc), "正本没写单位"
        assert ("三条路径" in doc) or ("three paths" in doc), "正本没说清写入条件是三条"
        assert ("定案" in doc) or ("Settled" in doc), "正本没记下 2026-09-19 的判定"
        assert "机械拍（没接执行者）跑组织段时同样写一行" not in doc, "写反的那句回来了"
    cfg = (REPO_ROOT / "src" / "infinigrow" / "core" / "config.py").read_text(encoding="utf-8")
    assert "没接执行者时它根本不跑" in cfg, "配置表那行没跟上正本口径"
    assert "机械段也算一次尝试" not in cfg, "配置表把没发生过的事写成了判据"


def test_security_doc_states_the_two_scan_scopes_separately():
    """SECURITY.md 的扫描面必须与实测一致：默认那一遍不进被忽略目录，显式指定才扫。

    为什么锁这条：旧文案写「扫描器还在 `archive/…/_venvtest` 下报 ~48 条」，把两种情形
    混成一句。隐私扫描对齐 `.gitignore` 之后，默认那一遍连 `archive/` 都不进；而那串
    数字也不对——显式 `--root archive` 实测是数千条。文案若不分开写，读的人会以为
    「默认扫描里有一堆已知豁免」，而实际默认扫描是零命中。旧措辞出现即红。
    """
    security = (REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "privacy_scan.py --root ." in security and "privacy_scan.py --root archive" in security
    assert "not scanned at all" in security
    assert "~48 findings" not in security, "旧措辞回来了：它把默认扫描与显式扫描混为一谈"


def test_org_check_exit_code_documented_in_both_languages():
    """`org-check` 的「不该跑」码：文档写的数字必须**等于**常量，且双语同口径。

    为什么锁这条（并且不许写死数字）：这一位曾经是借用位——文档、代码、CI 三处各自
    描述同一个 1，谁改了另外两处不知道，就是 v1 的老病。判据如果写成 `assert "5" in doc`
    那是装饰性的：常量哪天改回 1、或者文档单独漂成 6，断言都不会红。所以数字从
    `exit_codes.NOT_THIS_TICK` 取，句式换数字必须找不到（自带反证）。
    """
    from infinigrow.core import exit_codes as rc

    phrase = "should_run=false → %d" % rc.NOT_THIS_TICK
    for name in ("running.md", "zh/running.md"):
        doc = (DOCS / name).read_text(encoding="utf-8")
        assert phrase in doc, "%s 没写「不该跑」的专属码" % name
        assert "should_run=false → 1" not in doc, "%s 又回到借用位" % name
    assert rc.NOT_THIS_TICK != rc.USAGE
    cli = (REPO_ROOT / "src" / "infinigrow" / "cli.py").read_text(encoding="utf-8")
    assert "rc.NOT_THIS_TICK" in cli, "文档改了，cli.py 还在返回借用的 USAGE"
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "org-check --tick 9 || true" not in ci, \
        "`|| true` 回来了：它把真正的用法错误（1）和「本拍不该跑」一起吞掉"
    org_line = next(i for i, line in enumerate(ci.splitlines()) if "infinigrow org-check" in line)
    tick_line = next(i for i, line in enumerate(ci.splitlines()) if "infinigrow tick" in line)
    assert org_line < tick_line, "CI 里的 org-check 不在空状态根那一步，rc 就不再是 0"


def test_subject_capacity_split_is_documented_and_no_stale_enumeration():
    """`journal/` 轮转、`app/` 刻意不轮转——这条判定必须写在双语主体文档里，且旧枚举不许回流。

    为什么锁这条：主体根两个子树只有 `journal/` 有容量判据（`journal_keep_files`），`app/`
    的证据件是固化边的对账对象，搬走＝引擎自己造出「缺失」差异。这不是「先不管」，是**决定
    不加**，所以它得有文档位置、有配置名、有反证；否则下一轮读的人只能重新推一遍。
    同一处还钉第五轮的教训：那句把观测当现状的目录枚举当时只改了文档，`subject.py` 里
    同一句话留到了现在——所以这次把禁令同时扫 `src/` 与 `prompts/`。
    """
    from infinigrow.engine.subject import SUBJECT_DIR_LIMIT, SUBJECT_FILE_LIMIT

    for name in ("growth-subject.md", "zh/growth-subject.md"):
        doc = (DOCS / name).read_text(encoding="utf-8")
        assert "journal_keep_files" in doc, "%s 没给出轮转判据的配置名" % name
        assert ("刻意不轮转" in doc) or ("deliberately not rotated" in doc), \
            "%s 没写清 app/ 不轮转是决定，不是疏漏" % name
        assert ("对账对象" in doc) or ("reconciled against" in doc), "%s 没写为什么不轮转" % name
        assert "带日期的快照" in doc or "dated snapshot" in doc, "%s 的规模数字没标成快照" % name
        # 「保持 10／20」这条定案由常量拼出：改上限而不改定案句式即红
        verdict = ("保持 %d／%d" % (SUBJECT_DIR_LIMIT, SUBJECT_FILE_LIMIT) if name.startswith("zh")
                   else "both stay at %d / %d" % (SUBJECT_DIR_LIMIT, SUBJECT_FILE_LIMIT))
        assert verdict in doc, "%s 没写下限的定案（或定案句式被改写）" % name
        assert verdict.replace(str(SUBJECT_DIR_LIMIT), "99") not in doc, \
            "%s 的定案句式对任何数字都成立＝装饰性判据" % name
    stale = "journal／archive"
    for folder in ("src", "prompts"):
        for p in (REPO_ROOT / folder).rglob("*.py" if folder == "src" else "*.md"):
            assert stale not in p.read_text(encoding="utf-8"), \
                "库外现状又写成了代码里的事实：%s" % p.relative_to(REPO_ROOT).as_posix()


def test_rotated_archive_out_of_surface_is_documented_in_all_five_places():
    """G1 定案「主体根的 `archive/` 不入生长面」五处同改，且旧措辞不许回流。

    为什么锁这条：轮转把 journal 旧篇搬进 `<主体根>/archive/journal/`，而搬运＝写新件，
    归档件因此拿到全新 mtime——在「mtime 最新 20」的窗口里排到最前。旧文档与
    `rotate_journal` 的 docstring 都写着「不影响新内容的可见性」，实测被推翻。
    定案句式由常量拼出（换归档目录名就找不到），并拒绝那句旧措辞以任何形式回来。
    """
    from infinigrow.engine.subject import SUBJECT_ARCHIVE_DIR

    prompt_line = "主体根的 `%s/` 是**轮转归档区，不入生长面**" % SUBJECT_ARCHIVE_DIR
    zh_verdict = "所以 `%s/` **三处都不算**" % SUBJECT_ARCHIVE_DIR
    en_verdict = "So `%s/` is excluded in" % SUBJECT_ARCHIVE_DIR
    docs = (DOCS / "zh/growth-subject.md").read_text(encoding="utf-8")
    assert zh_verdict in docs, "zh 正本的定案句式变了（或常量名换了没同步）"
    assert "要到 `journal` 首次轮转才建" not in docs, \
        "zh 正本还用「archive/ 要到首次轮转才建」当目录名额的理由"
    en = (DOCS / "growth-subject.md").read_text(encoding="utf-8")
    assert en_verdict in en, "英文正本的定案句式变了（或常量名换了没同步）"
    assert "Rotated content really leaves the growth surface" in en
    for name in ("tick.md", "org-session.md"):
        pr = (REPO_ROOT / "prompts" / name).read_text(encoding="utf-8")
        assert prompt_line in pr, "prompts/%s 没写这条归档边界（或常量名换了）" % name
    rot = (REPO_ROOT / "src" / "infinigrow" / "ledger" / "rotation.py"
           ).read_text(encoding="utf-8")
    assert "是错的" in rot, "rotate_journal 没标注那句被实测推翻的旧说法"
    assert "轮转把最旧的移走不会影响" not in rot, "旧的陈述句式回来了：轮转会影响可见性"
    assert "SUBJECT_ARCHIVE_DIR" in rot, "轮转侧没指向观测面的执法常量"


def test_evidence_miss_buckets_are_documented_and_refuted_claim_stays_refuted():
    """缺失归因三类桶名（G2）双语同源；那句被证伪的「命名错配」说法不许回流。

    为什么锁这条：桶名是 `status`／对账报告／双语正本共用的**读数名**，改一侧不改另一侧
    就是漂移。同一节还写下了一次**证伪**（近 30 次 cap 领做里命名漂移 0），所以正本必须
    把它标成被推翻的猜测，不能被后人在没有证据的情况下改回「命名错配导致假打脸」。
    """
    from infinigrow.engine.sprout_sources import EVIDENCE_MISS_BUCKETS

    assert len(EVIDENCE_MISS_BUCKETS) == 3
    zh = (DOCS / "zh/mechanism.md").read_text(encoding="utf-8")
    en = (DOCS / "mechanism.md").read_text(encoding="utf-8")
    for name in EVIDENCE_MISS_BUCKETS:
        assert name in zh, "zh 正本缺桶名「%s」" % name
        assert name in en, "英文正本缺桶名「%s」（读数名两边同字）" % name
    for doc, who in ((zh, "zh"), (en, "en")):
        assert "trace_write_paths" in doc, "%s 正本没指向只读输出段的判据函数" % who
        assert ("证伪" in doc) or ("推翻" in doc) or ("refuted" in doc), \
            "%s 正本没写明那次猜测被证伪" % who
    src = (REPO_ROOT / "src" / "infinigrow" / "engine" / "reconcile.py").read_text(
        encoding="utf-8")
    assert "TRACE_OUTPUT_HEADING" in src and "trace_write_paths" in src, \
        "判据函数或它读的那一段标题没了（正本还在引用它）"
