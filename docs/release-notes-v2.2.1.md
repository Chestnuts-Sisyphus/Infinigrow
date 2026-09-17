# Infinigrow v2.2.1 — runtime reliability patch

Three fixes, all bought from live incidents:

- **The scheduled task no longer opens a console window.** A new launcher
  (`tools/run_tick_hidden.vbs`) runs the tick script with window style 0, and the task action was
  changed to `wscript //nologo <vbs>`. Registering a `.bat` directly flashes a console window on
  every run, which steals focus from whatever the machine's owner is doing.
- **The tick number is recovered when the heartbeat is unreadable.** Previously a heartbeat that
  could not be read fell back to `tick = 0`, so the next tick was numbered 1 — overwriting
  `reconcile-00001.md` and putting a discontinuity into the ledgers. The number is now reconstructed
  from the maximum tick in the ledgers, with a visible note in the report.
- **The executor channel retries through transport-layer truncation.** `IncompleteRead`,
  connection resets, remote disconnects and read timeouts are retried (2 attempts, short backoff);
  every attempt is recorded with its attempt number, and a failure is never hidden as "tried once".

**Full changes**: [`CHANGELOG.md`](../CHANGELOG.md).
