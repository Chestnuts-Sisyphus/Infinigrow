<!-- PR 模板：不问过程，问证据。 -->
## 做了什么

（一句话）

## 为什么

（约束或事故；若是机制变更，指向 `docs/mechanism.md` 的节号）

## 证据

- [ ] `python -m pytest -q` 通过
- [ ] `python -m infinigrow scan` 全 PASS
- [ ] `python -m infinigrow selftest` 全绿
- [ ] `python tools/check_prompt_code_sync.py` 同源
- [ ] `python tools/privacy_scan.py --root .` 零命中
- [ ] 若改了机制：`docs/mechanism.md` + 代码 + `prompts/` **三处同改**
- [ ] 若退役了机制：`docs/superseded.md` 加了一行

## 已知限制 / 未覆盖

（如实写；没有写「无」）
