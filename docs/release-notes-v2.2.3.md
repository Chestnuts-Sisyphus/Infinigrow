# Infinigrow v2.2.3 — root cause of the executor-400 family (UTF-8 stdin)

A live incident was traced to its root and fixed: an executor called from a scheduled task failed
with HTTP 400 repeatedly, while the same call succeeded from an interactive shell.

- **Root cause**: the executor adapter's `harden_stdio()` reconfigured stdout and stderr but not
  **stdin**. The engine writes the prompt into the child's stdin as UTF-8; a process started by the
  scheduler reads stdin with the system code page, so the prompt was corrupted, stray surrogate
  characters appeared, and the upstream rejected the request ("lone leading surrogate in hex
  escape"). An interactive shell happens to default to UTF-8, which is why manual runs always
  worked.
- **Fixes**: the adapter also reconfigures stdin, and the engine injects
  `PYTHONIOENCODING=utf-8` into the executor's environment, so no adapter has to depend on its own
  default code page.
- **Verification**: same-context comparison before and after (rc=1 → rc=0, stray surrogate
  present → absent), then end-to-end on the real scheduled task: two consecutive ticks with rc=0,
  executor failure count 9 → 0, alert cleared.

**Full changes**: [`CHANGELOG.md`](../CHANGELOG.md).
