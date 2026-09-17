# Contributing

Read [`docs/mechanism.md`](docs/mechanism.md) first — **the mechanism is a set of tests, not a
style**. Changing a test and changing code are two halves of the same change, and a machine
rejects a one-sided edit.

## Local development

```bash
pip install -e ".[dev]"
python -m pytest -q                          # all tests
python -m infinigrow scan                    # static rules (must be all PASS)
python -m infinigrow selftest                # positive and negative rule cases
python tools/check_prompt_code_sync.py       # bidirectional prompt↔code check
python tools/privacy_scan.py --root .        # paths / credentials / emails
python tools/check_no_abs_paths.py state     # state artifacts must not contain local paths
```

Run these before opening a pull request. CI runs the same set on **two platforms** (ubuntu and
windows, Python 3.11 and 3.12) plus a **cold start** (three ticks in an empty state root, asserting
no absolute path in any artifact) and a syntax parse of the Windows launcher files.

## Changing the mechanism (a premise-level change)

The mechanism words (the edges, the maturity chain, the difference kinds, the sprout sources, the
queue and ledger concepts) are **sync terms**: each must appear in `docs/mechanism.md`, in the code
and in the prompts. The table is defined once in `SYNC_TERMS`
(`src/infinigrow/rules/static_scan.py`), `tools/check_prompt_code_sync.py` checks it in both
directions, and rule **R9** guards a coverage floor (someone silently dropping a term brings the
drift surface back).

Four steps for a premise change:

1. `docs/mechanism.md` — say *why*, not only *what* (the English document and the Chinese original
   in `docs/zh/` are both part of the change);
2. the code (`engine/` — the vocabulary and the functions);
3. the prompts (`prompts/`);
4. the commands above, all green.

**A single-sided change is drift**, and CI fails on it. That is deliberate: the previous generation
of this project span in place because one rule was written in two places and the two evolved apart.

## Adding a static rule

1. Write the rule function in `src/infinigrow/rules/static_scan.py` (returns `(detail, passed)`).
2. Add a row to the `RULES` table.
3. Add **both a positive and a negative case** to `SELFTEST_CASES` (a positive case alone fails the
   coverage check).
4. Make it PASS on the real repository. If a new rule fails on first run, clean the repository up —
   do not switch the rule off.

## Style

- Line width 100 (`ruff` enforces it).
- **Comments state constraints, not narration.** Write *why* (the constraint, the trap, the cost),
  never "this line does X".
- Comments and design documents are Chinese; that is this project's normal form, and it is part of
  the mechanism language (the public English docs carry a glossary). Do not translate them as a
  drive-by change.
- Documentation, code and tests change together.

## Commit messages

Short and in English, one line, imperative mood. Put the reasoning in the commit body only when it
is not obvious, and keep it to a couple of lines:

```
<area>: <what changed>

Why: <the constraint or the incident, if not obvious>
Verified: <the command you ran and its result>
```

## Code of conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
