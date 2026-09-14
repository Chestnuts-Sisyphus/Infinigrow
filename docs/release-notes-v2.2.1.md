# Infinigrow v2.2.1 — 运转可靠性补丁

三个都在真机现场换来的（细节见 CHANGELOG 的 v2.2.1 节）：

- **计划任务不再弹窗**：新增 `tools/run_tick_hidden.vbs`（WSH 窗口样式 0），注册动作改为
  `wscript //nologo <vbs>`。直接挂 `.bat` 会每跑一次闪一个控制台窗口——抢焦点、遮住人正在看的东西。
  注意 `New-ScheduledTaskSettingsSet -Hidden` 只隐藏任务列表**条目**，**不隐藏窗口**。
- **心跳不可读时从账本恢复拍号**：旧实现在心跳读不出时静默按「新仓」起算（拍号回到 1）→
  对账报告被同名覆写、账本拍号跳变。现在从 diffs/outcomes/maturity/executor 账本反推
  最大拍号 +1，并写进本拍说明与心跳——异常要显眼，不许静默。
- **执行者通道抗抖动**：上游会成串返回 400「Invalid request／Upstream request failed」，
  同一题面稍后重放即成功（本地探针：短/整题面各两次全 OK）→ 退避重试 3 → **5 次共约 52 秒**
  （首试带推理档，其后不带）。持续故障才记为执行者失败。

测试 225 条全绿；规则 9/9；自检全绿；隐私双扫零命中。
