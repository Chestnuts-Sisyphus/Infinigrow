# -*- coding: utf-8 -*-
"""双语文档一致性（Q7/C1/N63）：两套文档不许各长各的——**机械校验**。

背景（[已证明]）：机制改动要五处同改（英／中／提示词／代码／测试），但此前**没有任何闸**
保证两套文档的结构对齐：包装轮把英文公开文档重写成「冷读者版」时，`running.md` 成了
英文 5 节 / 中文 17 节、`growth-subject.md` 的 5~7 节换了题、`mechanism.md` 的末节
一边是术语表、一边是同源说明——两边各自演化，正是 v1 那个病根的翻版。

判据（全部机械可判，且是**位置对位置**的）：

| 对象 | 断言 |
|---|---|
| `docs/*.md` ↔ `docs/zh/*.md` | 各级标题的**层号序列**逐位相同（标题文字是译文，不可比文本） |
| 目录覆盖 | `docs/` 里除**声明式例外**（`release-notes-*`＝公开面只有英文）外，每篇都有中文镜像；反向亦然 |
| `README.md` ↔ `README.zh-CN.md` | 标题骨架相同 ＋ 围栏代码块数相同 ＋ 代码块里的**命令行**（去掉行尾注释后）逐条相同 |

为什么要比「命令行」而不是「文本」：README 的注释是两边各自的语言，但**跑的命令必须是同一条**
——文档教人跑的命令两边不一致，等于两份说明书。
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"
ZH = DOCS / "zh"

#: 逐对校验的文档（英文公开面 ↔ 中文正本）
PAIRS = ("mechanism.md", "architecture.md", "growth-subject.md", "running.md",
         "privacy.md", "versioning.md", "upgrading.md", "superseded.md")

#: **声明式例外**：Release 说明只有英文（公开面按语言边界只做英文，见 H8/Q13）。
#: 例外必须写在这里——新增文档忘了写镜像会直接失败，不许悄悄绕过。
ENGLISH_ONLY = ("release-notes-v2.0.0.md", "release-notes-v2.1.0.md",
                "release-notes-v2.2.0.md", "release-notes-v2.2.1.md",
                "release-notes-v2.2.2.md", "release-notes-v2.2.3.md")


def heading_levels(text: str) -> list[int]:
    """标题的**层号序列**（`##` → 2；不含一级标题）。只比结构，不比译文。"""
    out = []
    for line in text.splitlines():
        m = re.match(r"^(#{2,4})\s+\S", line)
        if m:
            out.append(len(m.group(1)))
    return out


def fenced_blocks(text: str) -> int:
    """围栏代码块数（``` 成对出现）。"""
    return sum(1 for line in text.splitlines() if line.startswith("```"))


#: 命令行开头（只有这些行才算「两条文档教人跑的命令」；示意图与表格不算）
COMMAND_RX = re.compile(r"^(infinigrow|python|pip|git|tools[\\/])")
#: 行尾注释（`#` 与 `.bat` 的 `::`）与行尾括注（`(...)`／`（...）`）
_COMMENT = re.compile(r"\s+(#|::).*$")
_ANNOTATION = re.compile(r"\s*[\(（][^)）]*[\)）]\s*$")
_QUOTED = re.compile(r'"[^"]*"')


def commands_in_blocks(text: str) -> list[str]:
    """代码块里的**命令行**：只留命令本身。

    注释是各自语言、占位参数是各自语言的示例（`"your-command"` ↔ `"你的命令"`）、
    行尾括注是各自的说明——这些**都不算漂移**；命令与参数必须一致。
    """
    out: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("```"):
            inside = not inside
            continue
        if not inside:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "::")):
            continue
        if not COMMAND_RX.match(stripped):
            continue
        cmd = _ANNOTATION.sub("", _COMMENT.sub("", stripped)).strip()
        cmd = _QUOTED.sub('"<arg>"', cmd)
        if cmd:
            out.append(cmd)
    return out


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_every_doc_pair_has_the_same_heading_skeleton():
    """`docs/<doc>` 与 `docs/zh/<doc>` 的标题骨架**逐位相同**（Q7 的主判据）。"""
    problems = []
    for name in PAIRS:
        en, zh = DOCS / name, ZH / name
        assert en.is_file(), "缺英文文档：%s" % name
        assert zh.is_file(), "缺中文镜像：%s" % name
        a, b = heading_levels(_read(en)), heading_levels(_read(zh))
        if a != b:
            problems.append("%s：英文 %d 节 %s／中文 %d 节 %s" % (name, len(a), a, len(b), b))
    assert not problems, "双语文档结构漂移：\n  " + "\n  ".join(problems)


def test_mirror_coverage_is_complete_except_the_declared_exceptions():
    """覆盖完整性：英文每篇都有中文镜像（例外＝Release 说明）；中文每篇都有英文镜像。"""
    english = {p.name for p in DOCS.glob("*.md")} - set(ENGLISH_ONLY)
    mirrored = {p.name for p in ZH.glob("*.md")}
    assert english == mirrored, ("没有镜像的英文文档：%s；没有英文原文的中文文档：%s"
                                 % (sorted(english - mirrored), sorted(mirrored - english)))
    # 例外必须**真的只**是 Release 说明（有人把新文档写进例外＝放宽判据，这里拦下）
    assert all(n.startswith("release-notes-") for n in ENGLISH_ONLY)


def test_readme_pair_matches_in_sections_blocks_and_commands():
    """README 两版：章节骨架、代码块数、**跑的命令**逐条相同（注释可以是各自语言）。"""
    en, zh = _read(REPO / "README.md"), _read(REPO / "README.zh-CN.md")
    en_headings = [n for n in re.findall(r"^(#{1,4})\s+\S", en, re.M)]
    zh_headings = [n for n in re.findall(r"^(#{1,4})\s+\S", zh, re.M)]
    assert len(en_headings) == len(zh_headings), (
        "README 章节数不一致：%d vs %d" % (len(en_headings), len(zh_headings)))
    assert en_headings == zh_headings, "README 章节层号序列不一致"
    assert fenced_blocks(en) == fenced_blocks(zh), "README 代码块数不一致"
    en_cmds, zh_cmds = commands_in_blocks(en), commands_in_blocks(zh)
    assert en_cmds == zh_cmds, ("README 命令不一致：\n  只有英文：%s\n  只有中文：%s"
                                % ([c for c in en_cmds if c not in zh_cmds],
                                   [c for c in zh_cmds if c not in en_cmds]))


def test_the_checker_itself_catches_drift(tmp_path):
    """**判据自检**（防「闸是摆设」）：改一处结构，检查函数必须报出来。"""
    a = tmp_path / "en.md"
    b = tmp_path / "zh.md"
    a.write_text("# T\n\n## 1. One\n\n## 2. Two\n\n### 2.1 Sub\n", encoding="utf-8")
    b.write_text("# T\n\n## 1. 一\n\n## 2. 二\n\n### 2.1 子\n", encoding="utf-8")
    assert heading_levels(_read(a)) == heading_levels(_read(b))
    b.write_text("# T\n\n## 1. 一\n\n## 2. 二\n", encoding="utf-8")     # 中文少一节
    assert heading_levels(_read(a)) != heading_levels(_read(b))
    # 命令比较：注释不同不算漂移，命令不同才算
    c = "# T\n\n```bash\ninfinigrow status   # engine state\n```\n"
    d = "# T\n\n```bash\ninfinigrow status   # 引擎状态\n```\n"
    e = "# T\n\n```bash\ninfinigrow scan     # 引擎状态\n```\n"
    assert commands_in_blocks(c) == commands_in_blocks(d)
    assert commands_in_blocks(c) != commands_in_blocks(e)
