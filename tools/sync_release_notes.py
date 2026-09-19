#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch-edit historical GitHub Release titles/notes so they match the repository sources.

Why this exists (R7/D2): the public surface (README, docs, commit messages, CHANGELOG) is
English and concise, but the Releases page kept Chinese long-form notes for older versions —
two languages on one page, the shorter one unreadable. This tool rewrites a release's title to
the recorded one-liner and its body to the repository source, so a community member can rerun
the same pass against their own fork.

Where the content comes from (all in-repo, all reviewable):

- body: `docs/release-notes-vX.md` when present (the rewritten English notes), otherwise the
  version's section in `CHANGELOG.md`;
- title: the per-version one-liners recorded below — a **decision record**, not a guess.
  The record only reaches **v2.2.15**. From v2.2.16 on, the published title *is* the
  `CHANGELOG.md` section heading verbatim (including its trailing `(YYYY-MM-DD)`), because that
  is what the tag→release workflow feeds `gh release create --title`. So for those versions the
  title comes from the CHANGELOG, not from the table: `title_for()` derives it. Measured against
  the live Releases page on 2026-09-18 (28 releases), the two groups behave exactly like this —
  v2.0.0…v2.2.15 published == table, v2.2.16…v2.2.25 published == heading with the date.
  Copying the dated ones into the table (as was done up to v2.2.25) is a second source, and
  applying that copy would **strip the date off ten published titles**. Hence the boundary below.

Usage:

    python tools/sync_release_notes.py            # dry run: print what would be set
    python tools/sync_release_notes.py --apply    # call `gh release edit` for each entry

Discipline: a version whose body comes up empty is **skipped with a warning** (never push an
empty shell onto the public page); the dry run is the default so a mistyped run cannot edit
anything.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 手写标题只覆盖到这一版（含）。之后的版本，线上标题＝CHANGELOG 小节标题原文（带日期），
#: 由 `title_for()` 推导——不要把新版本再抄进下面的表：抄进来的副本一律不带日期，
#: `--apply` 会把线上标题的日期抹掉。表里 v2.2.16 之后的条目是**历史遗留的第二份拷贝**，
#: 保留只为让「覆盖到当前版本」这条检查继续成立，它们不再参与写标题。
TITLES_UNTIL = "2.2.15"

#: Recorded one-line titles per version (decision record; see module docstring).
#: v2.2.16 起线上标题由发布工作流从 `CHANGELOG.md` 推导（见上方边界），表内条目只是拷贝。
TITLES = {
    "2.0.0": "v2.0.0 — the rewrite",
    "2.1.0": "v2.1.0 — the runtime line",
    "2.2.0": "v2.2.0 — calibration from a live run",
    "2.2.1": "v2.2.1 — runtime reliability patch",
    "2.2.2": "v2.2.2 — long-run reliability, broken mechanism chains",
    "2.2.3": "v2.2.3 — executor UTF-8 stdin (HTTP 400 root cause)",
    "2.2.4": "v2.2.4 — growth resumed: domain-saturation deadlock, observation truncation",
    "2.2.5": "v2.2.5 — observability and cost",
    "2.2.6": "v2.2.6 — proposals stop naming files; the org session watches reality",
    "2.2.7": "v2.2.7 — a reminder gets an exit; dedup includes the frozen zone",
    "2.2.8": "v2.2.8 — the reality-change window was structurally empty",
    "2.2.9": "v2.2.9 — two readings that named the wrong unit",
    "2.2.10": "v2.2.10 — \"changed\" is reported too",
    "2.2.11": "v2.2.11 — the reality window spans since the last org session",
    "2.2.12": "v2.2.12 — the input block's heading no longer names a window",
    "2.2.13": "v2.2.13 — English-first public surface",
    "2.2.14": "v2.2.14 — a re-proposal no longer makes an old question look new",
    "2.2.15": "v2.2.15 — the solidify edge becomes accountable",
    "2.2.16": "v2.2.16 — the two languages can no longer drift apart",
    "2.2.17": "v2.2.17 — the reading that shows the solidify edge got connected",
    "2.2.18": "v2.2.18 — the re-proposal rule is written down where the mechanism is",
    "2.2.19": "v2.2.19 — a failed redemption is attributed to whoever actually failed",
    "2.2.20": "v2.2.20 — the read and availability edges are now accountable",
    "2.2.21": "v2.2.21 — name-to-path joins are guarded, and the release-note tool is public",
    "2.2.22": "v2.2.22 — executor-side loss and token spend are both visible",
    "2.2.23": "v2.2.23 — the ledger split no longer drops ticks, and the report carries the gate readings",
    "2.2.24": "v2.2.24 — the log rotation fails gracefully on a busy journal, and the README names every status reading",
    "2.2.25": "v2.2.25 — log rotation moves to the launcher's handle gap, where it can actually work",
    "2.2.26": "v2.2.26 — the documents say what the code, the tree and the Release page actually do",
    # 分界线以后这一列只是**兜底镜像**（`plan()` 靠它枚举版本）：真正应用的标题
    # 由 `changelog_title()` 从 CHANGELOG 小节标题原文推导，**带着日期**。
    "2.2.27": "v2.2.27 — the five open judgements are closed, and one correction from last round was wrong",
    "2.2.28": "v2.2.28 — attribution reads the executor's exit code, and two published verdicts are corrected",
}


def body_for(ver: str, root: Path = ROOT) -> str:
    """The release body for a version: docs notes first, else the CHANGELOG section."""
    notes = root / "docs" / ("release-notes-v%s.md" % ver)
    if notes.is_file():
        text = notes.read_text(encoding="utf-8")
        return text.split("\n", 1)[1].lstrip("\n").strip()
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    pattern = r"^## v%s .*?\n(.*?)(?=\n## |\Z)" % re.escape(ver)
    m = re.search(pattern, changelog, re.S | re.M)
    return m.group(1).strip() if m else ""


def changelog_title(ver: str, root: Path = ROOT) -> str:
    """CHANGELOG 里这一版的小节标题**原文**（含尾部 `(YYYY-MM-DD)`）——线上用的就是它。"""
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"^## (v%s .*)$" % re.escape(ver), changelog, re.M)
    return m.group(1).strip() if m else ""


def title_for(ver: str, root: Path = ROOT) -> str:
    """The title `--apply` would set — and the only title the dry run may print.

    边界之前（含 `TITLES_UNTIL`）用手写记录：那份就是线上现在的样子，实测于 2026-09-18。
    边界之后从 CHANGELOG 推导（带日期）：那里的手写副本是**少了日期**的第二份拷贝，
    拿它去 edit 会把线上标题改窄。
    """

    def _key(v: str):
        return tuple(int(x) for x in v.split("."))

    if _key(ver) <= _key(TITLES_UNTIL):
        return TITLES.get(ver, "")
    return changelog_title(ver, root) or TITLES.get(ver, "")


def plan(root: Path = ROOT):
    """Yield `(version, title, body)` for every entry with a non-empty body."""
    for ver in TITLES:
        title = title_for(ver, root)
        body = body_for(ver, root)
        if body and title:
            yield ver, title, body


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    apply_ = "--apply" in args
    for ver in TITLES:
        body = body_for(ver)
        if not body:
            print("!! empty body for v%s (skipped — never publish an empty shell)" % ver)
            continue
        title = title_for(ver)
        if not title:
            print("!! empty title for v%s (skipped — CHANGELOG 里没有这一节)" % ver)
            continue
        print("== v%s ==\ntitle: %s\nbody %d chars, first line: %s"
              % (ver, title, len(body), body.splitlines()[0][:70]))
        if apply_:
            proc = subprocess.run(["gh", "release", "edit", "v" + ver,
                                   "--title", title, "--notes", body],
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", cwd=str(ROOT))
            print("   gh rc=%d %s" % (proc.returncode, (proc.stderr or "").strip()[:120]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
