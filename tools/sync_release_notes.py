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
  New versions (v2.2.14 onward) already get their titles from `CHANGELOG.md` via the
  tag→release workflow, so they are listed here for completeness of the check, not because
  they need rewriting.

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

#: Recorded one-line titles per version (decision record; see module docstring).
#: v2.2.14+ follow `CHANGELOG.md` verbatim (the release workflow derives them from there).
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


def plan(root: Path = ROOT):
    """Yield `(version, title, body)` for every entry with a non-empty body."""
    for ver, title in TITLES.items():
        body = body_for(ver, root)
        if body:
            yield ver, title, body


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    apply_ = "--apply" in args
    for ver, title in TITLES.items():
        body = body_for(ver)
        if not body:
            print("!! empty body for v%s (skipped — never publish an empty shell)" % ver)
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
