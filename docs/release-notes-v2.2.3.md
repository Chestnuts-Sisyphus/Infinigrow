# Infinigrow v2.2.3 — A20 根因硬化（执行者子进程强制 UTF-8 stdio）

真机定位并根治 A20（计划任务上下文执行者持续 400）：

- **根因**：执行者适配器的 `harden_stdio()` 只重配了 stdout/stderr，漏了 stdin。
  引擎经 subprocess 用 UTF-8 把提示词写进 stdin；计划任务启动的进程 stdin 默认编码
  非 UTF-8，把提示词读坏 → 字符串混入孤立代理字符 → JSON 转义成 `\udXXX` →
  上游报「lone leading surrogate in hex escape」→ 400。
  交互 shell 的 stdin 默认就是 UTF-8，所以手动跑同一请求一直成功。
- **引擎侧硬化**：`executor_env()` 注入 `PYTHONIOENCODING=utf-8`，任何适配器都不再
  依赖自己的默认编码（测试锁定）。
- **适配器侧修复**（私有文件）：`harden_stdio()` 补 `sys.stdin.reconfigure(encoding="utf-8")`。
- **验证**：同一计划任务上下文，修复前 rc=1/请求含孤立代理；修复后 rc=0/无孤立代理；
  交互自检连续通过。

定位方法（可复跑）：放宽错误截断抓完整错误体 → 请求指纹打点（sha256/长度/孤立代理标记）
→ 隐藏启动器诊断任务在计划任务上下文复现 → 修复前后同上下文对照。
