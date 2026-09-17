# Infinigrow v2.0.0 — the rewrite

**An engine that grows by predicting, reconciling, and turning differences into sprouts.**

Most "autonomous agent" loops grow by accumulating: more notes, more summaries. That kind of
growth has no gradient — it can run forever without getting better. Infinigrow grows by **being
contradicted**: each tick writes down what it expects reality to become, acts, then lets reality
answer, and reconciles mechanically. **Every difference becomes a sprout. No difference, no sprout.**

This is a clean-break rewrite, not a patch on the previous generation: only the mechanism is
carried over; everything else was built from scratch.

## What is in it

- **Six packages, one-way dependencies**: `core → ledger → engine → rules/garden/scheduler → cli`.
- **Parameterised state root**: defaults to `<repo>/state`, redirectable with `--state-root` /
  `IG_STATE_ROOT`. **Zero absolute paths** in source or prompts (rule R1).
- **Sprouts come only from ledgers** — differences, maturity cap ("what else can this be used
  for?"), unused capability-library entries ("why is this not used?"). There is **no** code path
  for the acting session to register a sprout; that is structural, not a comment.
- **No difference, no sprout**; one sprout per object × dimension; queue cap 50 with a frozen zone
  beyond it (the queue is mutable, the ledgers are not).
- **Maturity chain advances at most +1 per tick**; reaching the cap spawns a "put it to other use"
  sprout.
- **Concurrency**: reports are named by tick (`reconcile-00007.md`), `locks/` serialises sessions,
  stale locks are cleaned, and a session that cannot take the lock skips the tick idempotently.
- **Failures are visible**: an unwritable heartbeat raises and exits non-zero — the gardener's
  liveness check must never stall silently.
- **Six static rules**, zero tokens, run on every push: no absolute paths, prompt↔code sync, no
  self-sprout clause, state root gitignored, no credential literals, no BOM; each with a positive
  and a negative case.
- **CI runs a cold start**: three ticks in an empty state root, zero tokens, zero credentials, and
  asserts no absolute path appears in the artifacts.

## Verify it yourself (zero tokens, zero credentials, no network)

```bash
git clone https://github.com/Chestnuts-Sisyphus/Infinigrow && cd Infinigrow
pip install -e ".[dev]"
python -m pytest -q
python -m infinigrow tick --probe        # one tick on an empty state root: differences → sprouts
python -m infinigrow scan                # static rules
python -m infinigrow selftest            # rule cases
python tools/privacy_scan.py --root .    # paths / credentials / emails
```

## Known limitations (read this part)

1. **A mechanical tick does no cognition.** Without an executor a tick only observes and
   reconciles; a "contradicted" outcome in that mode is correct behaviour, not a defect.
2. **The executor interface is a plain function.** No vendor SDK, no key management, no retries or
   provider rotation. Read `SECURITY.md` before wiring anything that runs commands.
3. **The maturity chain records which step an object reached**, not the full evidence of each edge;
   lookups go through ledger pointers.
4. **Domain quotas are not implemented yet.** Convergence comes from "merge per object × dimension
   + cap 50 + frozen zone"; a domain-level threshold waits for measured data rather than a guess.
5. **The previous generation's deployment surface is not ported**: Windows scheduling, proxy
   self-healing, multi-provider rotation — those are host environment, not mechanism.
6. **This is the first version of the rewrite line**, not an equivalent replacement: the previous
   generation's 28 rules, embedded fixtures and per-sprout change history were deliberately left
   out — stacking new rules on old ones is what made it spin.
7. **Packaging had not been exercised on GitHub Actions at release time**; every CI step had been
   run locally in the same order, including the cold start.

## License

MIT.
