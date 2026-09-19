# -*- coding: utf-8 -*-
"""编号登记表清点（M6）：docs 里被引用的编号 与 markers 表里已登记的编号，差在哪。

判据与 `tests/test_docs_bilingual.py` 同源（同一套正则、同一张表），差别只在：
用例是闸（红就退不了），这个脚本是**给人看的清单**——改编号的人先跑它，看见差集再动手。

退出码：0＝两册登记表都覆盖了全部被引用编号；1＝有编号没登记（或有登记行成了死行）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"
ZH = DOCS / "zh"
MARKER_RX = re.compile(r"(?<![A-Za-z0-9])([KANTGOSHMQBCRU]\d{1,2}(?:-\d)?)(?![A-Za-z0-9])")


def referenced() -> set:
    """docs（中英两册）里出现的编号；登记表自身除外（它就是被检查的对象）。"""
    out = set()
    for p in list(DOCS.glob("*.md")) + list(ZH.glob("*.md")):
        if p.name == "markers.md":
            continue
        out.update(MARKER_RX.findall(p.read_text(encoding="utf-8")))
    return out


def registered(path: Path) -> dict:
    """登记表行：`| 编号 | 命题 | 执法落点 | 状态 |`。"""
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and MARKER_RX.fullmatch(cells[0]):
            out[cells[0]] = cells[1:]
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    refs = referenced()
    print("docs 里被引用的编号：%d 个" % len(refs))
    bad = 0
    for path in (DOCS / "markers.md", ZH / "markers.md"):
        rows = registered(path)
        missing = sorted(refs - set(rows))
        dead = sorted(set(rows) - refs)
        print("%s：登记 %d 行｜未登记 %d｜非 docs 引用 %s"
              % (path.relative_to(REPO).as_posix(), len(rows), len(missing), dead))
        if missing:
            bad = 1
            for mid in missing:
                print("  未登记：%s" % mid)
        for mid, cells in rows.items():
            if not all(cells):
                bad = 1
                print("  空格子：%s → %s" % (mid, cells))
    return bad


if __name__ == "__main__":
    sys.exit(main())
