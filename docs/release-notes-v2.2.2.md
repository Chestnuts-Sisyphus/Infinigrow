# Infinigrow v2.2.2 — closing the loop on long-run reliability

Ten items, each one corresponding to a leftover from the previous round's list: long-run
reliability problems and broken mechanism chains found on a live run.

- **Heartbeat sequence regression is also recovered.** v2.2.1 only handled "heartbeat unreadable";
  a live run then showed "heartbeat readable but behind the ledgers' maximum tick" (ledgers spanned
  1–16 while the heartbeat said 4), so the new sequence 4, 5, 6… overwrote old reports one by one.
  The recovery now also triggers on a backwards sequence.
- **Rotation for traces, reconciliation reports and the tick log** — by file count for the first
  two, by byte size for the log. Move-only, into `state/archive/files/`, searchable with
  `infinigrow rotate --search`.
- **The third sprout source is connected**: capping an object writes a capability-library entry
  (before that, nothing wrote to `library.jsonl`, so "unused capability" was a dead path).
- **Frozen sprouts get reviewed** every N ticks (a diff that reappears re-lights its sprout), and
  the pending-pointer timeout produces a sprout instead of only being recorded.
- **The object-name gate** for the org session became mechanical (names must come from the
  accountable list, or be a legal new path).
- **Cooldown and gap triggers for the org session** are visible state (`state/org-due.json`), and
  the org session's findings are reconciled later rather than trusted.
- **`status` / `pause` / `resume`** one-liners.
- **Fixed a family of path-dependent defects**: `run_latest.py --repo` had no effect on the version
  check; the artifact checker mis-reported; the executor's working directory is the repository root
  (relative commands resolve), while the subject location comes from `IG_SUBJECT_ROOT`.

**Full changes**: [`CHANGELOG.md`](../CHANGELOG.md).
