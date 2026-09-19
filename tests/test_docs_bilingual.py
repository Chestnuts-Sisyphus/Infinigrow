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
         "privacy.md", "versioning.md", "upgrading.md", "superseded.md", "markers.md")

#: **正文级**判据的阈值：中文某节 ≥ 这么多行才比（短节的译文行数天然波动，比了是噪声）
MIN_ZH_LINES = 8
#: 英文同位节至少要保住中文行数的这个比例（1:1 翻译的表与段不会低于它；**整段没译**才会）
MIN_RATIO = 0.5

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


# ------------------------------------------------------- M6：正文级同源（不只比标题）
def section_bodies(text: str) -> list[int]:
    """每个 `##`/`###`/`####` 节**正文**的非空行数（标题与空行不算）。"""
    out, cur, seen = [], None, False
    for line in text.splitlines():
        if re.match(r"^#{2,4}\s+\S", line):
            if seen:
                out.append(cur)
            cur, seen = 0, True
        elif seen and line.strip():
            cur += 1
    if seen:
        out.append(cur)
    return out


def body_deficits(zh_text: str, en_text: str) -> list[tuple]:
    """中文某节 ≥ `MIN_ZH_LINES` 行、英文同位节却 < `MIN_RATIO` 比例 → 记一条缺口。"""
    zh, en = section_bodies(zh_text), section_bodies(en_text)
    out = []
    for i, n in enumerate(zh):
        got = en[i] if i < len(en) else 0
        if n >= MIN_ZH_LINES and got < n * MIN_RATIO:
            out.append((i + 1, n, got))
    return out


#: 两册都必须**逐字含**的锚点（编号与常量名不翻译，翻了就查不到）
SHARED_ANCHORS = {
    "mechanism.md": ("N48-1", "N48-2", "N48-3", "N48-4", "N48-5",
                     "SUBJECT_DIR_LIMIT", "SUBJECT_FILE_LIMIT", "TRACE_GATE_FILES"),
    "running.md": ("K12", "A17", "IG_EXECUTOR_TIMEOUT_S"),
}

#: 各说各话的锚点：中文原话 ↔ 英文必须含的对应说法
PAIRED_ANCHORS = {
    "mechanism.md": (("19 个字符", "19 characters"),),
    "running.md": (("留 ≥1/3 余量", "leave at least 1/3 of the window"),),
}


def test_english_docs_carry_every_zh_section_body():
    """英文册不许「有标题没正文」：逐节按位置比行数（Q7 的正文级升级）。"""
    problems = []
    for name in PAIRS:
        if name == "markers.md":
            continue                      # 登记表本身是同一张表，不比「翻译量」
        d = body_deficits(_read(ZH / name), _read(DOCS / name))
        if d:
            problems.append("%s：%s" % (name, d))
    assert not problems, ("英文册系统性缺段（节号／中文行数／英文行数）：\n  "
                          + "\n  ".join(problems))


def test_anchors_that_carry_numbers_or_ids_are_bilingual():
    """编号与带数字的判据句必须**两册都在**（只在中文＝英文读者复核不了）。"""
    missing = []
    for name, anchors in SHARED_ANCHORS.items():
        en = _read(DOCS / name)
        for a in anchors:
            if a not in en:
                missing.append("%s：英文册缺锚点 %s" % (name, a))
    for name, pairs in PAIRED_ANCHORS.items():
        en, zh = _read(DOCS / name), _read(ZH / name)
        for zh_needle, en_needle in pairs:
            if zh_needle not in zh:
                missing.append("%s：中文册原话被改写，判据需同步（%s）" % (name, zh_needle))
            if en_needle not in en:
                missing.append("%s：英文册缺对应说法 %s" % (name, en_needle))
    assert not missing, "\n  ".join(missing)


# ------------------------------------------------------- M6：编号登记表
MARKER_RX = re.compile(r"(?<![A-Za-z0-9])([KANTGOSHMQBCRU]\d{1,2}(?:-\d)?)(?![A-Za-z0-9])")


def marker_rows(text: str) -> dict:
    """登记表行：`| 编号 | 命题 | 执法落点 | 状态 |` → {编号: (命题, 落点, 状态)}。"""
    out = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and MARKER_RX.fullmatch(cells[0]):
            out[cells[0]] = tuple(cells[1:])
    return out


def referenced_markers() -> set:
    """docs（中英两册，登记表自身除外）里**被引用**的编号。"""
    out = set()
    for p in list(DOCS.glob("*.md")) + list(ZH.glob("*.md")):
        if p.name == "markers.md":
            continue
        out.update(MARKER_RX.findall(p.read_text(encoding="utf-8")))
    return out


def test_every_marker_referenced_in_docs_is_registered():
    """引用即登记：docs 里出现的每个编号都要在登记表内（两册都要）。"""
    referenced = referenced_markers()
    assert len(referenced) >= 60, "清点本身退化了（只找到 %d 个编号）" % len(referenced)
    for name in ("markers.md", "zh/markers.md"):
        rows = marker_rows(_read(DOCS / name))
        absent = sorted(referenced - set(rows))
        assert not absent, "%s 未登记被引用的编号：%s" % (name, absent)


def test_registry_rows_point_at_something_real():
    """每行必须有**执法落点**；登记表不许留死行（引用的编号在仓内已不存在）。"""
    live = set()
    for base in (DOCS, ZH, REPO / "src", REPO / "tests", REPO / "prompts"):
        for p in list(base.rglob("*.md")) + list(base.rglob("*.py")):
            live.update(MARKER_RX.findall(p.read_text(encoding="utf-8", errors="replace")))
    for name in ("markers.md", "zh/markers.md"):
        rows = marker_rows(_read(DOCS / name))
        assert len(rows) >= 60, "登记表缩水了（%d 行）" % len(rows)
        for mid, (claim, where, status) in rows.items():
            assert claim and where and status, "%s：四个格不许留空（%s）" % (mid, (claim, where, status))
            if mid not in live:
                assert "孤儿" in status, \
                    "%s：仓内已无引用，状态必须如实写「孤儿」（不许伪装成生效）" % mid
            if "生效" in status:
                assert ("." in where) or ("/" in where), \
                    "%s：状态说生效，落点必须是可打开的文件或测试" % mid


def test_the_body_parity_check_itself_bites(tmp_path):
    """**判据自检**：把英文册某节砍成一行，缺口检查必须报出来（否则闸是摆设）。"""
    zh = "# T\n\n## 1. 一\n\n" + "\n".join("行 %d" % i for i in range(12)) + "\n"
    ok = "# T\n\n## 1. One\n\n" + "\n".join("line %d" % i for i in range(8)) + "\n"
    thin = "# T\n\n## 1. One\n\nonly one line\n"
    a, b, c = tmp_path / "a.md", tmp_path / "b.md", tmp_path / "c.md"
    a.write_text(zh, encoding="utf-8")
    b.write_text(ok, encoding="utf-8")
    c.write_text(thin, encoding="utf-8")
    assert body_deficits(_read(a), _read(b)) == []
    assert body_deficits(_read(a), _read(c)) == [(1, 12, 1)]
    # 登记表自检：删掉一行 → 引用检查必须报缺（用真实 docs 的编号名做样本）
    rows = marker_rows(_read(DOCS / "zh" / "markers.md"))
    sample = sorted(rows)[0]
    assert sample in referenced_markers() or "孤儿" in rows[sample][2]
