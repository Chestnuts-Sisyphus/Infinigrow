# -*- coding: utf-8 -*-
"""从 `CHANGELOG.md` 抽出某个 tag 那一节（Q11：tag → Release 的说明来源）。

用法：`python tools/extract_changelog_section.py v2.2.16 > notes.md`

纪律：**不是**「抽到啥算啥」——抽不到、或正文短于 `MIN_CHARS`，就以非零退出，
让 CI **失败**而不是发一条空壳 Release（公开面宁缺毋滥）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

MIN_CHARS = 80
ROOT = Path(__file__).resolve().parents[1]


def extract(tag: str, changelog: Path) -> str:
    """返回该 tag 对应的小节正文（含标题行）；找不到 → 抛 ValueError。"""
    version = tag.lstrip("vV")
    text = changelog.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = None
    pattern = re.compile(r"^##\s+v?%s\b" % re.escape(version))
    for i, line in enumerate(lines):
        if pattern.match(line.strip()):
            start = i
            break
    if start is None:
        raise ValueError("CHANGELOG.md 里没有 v%s 的小节" % version)
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    body = "\n".join(lines[start:end]).strip()
    # 正文（去掉标题行）太短 → 视为「没写」，不放行
    detail = "\n".join(body.splitlines()[1:]).strip()
    if len(detail) < MIN_CHARS:
        raise ValueError("v%s 的小节太短（%d 字符 < %d）：先写 CHANGELOG 再打 tag"
                         % (version, len(detail), MIN_CHARS))
    return body


def main(argv: list[str]) -> int:
    # 输出即 Release 正文，必须逐字节等于 UTF-8 的 CHANGELOG——不能随平台默认控制台
    # 编码漂移（Windows 裸 python 的 stdout 默认 cp936，会把正文写成 GBK 字节）。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    want_title = "--title" in argv
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print("用法：python tools/extract_changelog_section.py <tag> [--title]", file=sys.stderr)
        return 2
    try:
        body = extract(args[0], ROOT / "CHANGELOG.md")
    except (OSError, ValueError) as exc:
        print("抽出失败：%s" % exc, file=sys.stderr)
        return 1
    if want_title:
        # Release 标题＝CHANGELOG 那一节的标题（与手工建的 16 条 Release 保持同一种写法）
        print(body.splitlines()[0].lstrip("# ").strip())
    else:
        print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
