# Infinigrow v2.1.0 — 运转线（The runtime line）

**判据层未变**：四条边（判读/行动/原理/固化）、成熟链四步、差异四类、芽源三个——
一个都没动。这一版补的是「让它真的运转起来」所需的东西：引擎终于知道
**自己在长什么**、**由谁动手**、**语义判断由谁跑**，以及三条配套纪律。

```bash
pip install -e ".[dev]"
infinigrow dry-run            # 看：状态根、生长主体、执行者
infinigrow tick --probe       # 跑一拍（默认机械拍：零 token、零凭据、不出网）
```

## 新增能力

- **生长主体**：被生长的东西被显式定义成一个目录（默认在仓库**同级**，
  `IG_SUBJECT_ROOT` 可指到任意位置）。机械观测改为**读主体**——存在性、文件数、
  每个文件的字节数（有界且稳定排序），对象命名 `主体/<相对路径>`。
  没有主体时不会报错、也不会硬造题：「缺失」本身就是一种如实的观测。
  → [`docs/growth-subject.md`](https://github.com/Chestnuts-Sisyphus/Infinigrow/blob/main/docs/growth-subject.md)
- **执行者通道**：`infinigrow tick --executor "<命令>"`（或 `IG_EXECUTOR`）。
  提示词经 **stdin** 进、**stdout** 出；输出原文落 `state/traces/`，
  每次调用记 `state/executor.jsonl`（rc / 耗时 / 提示与输出长度 / 可选用量）。
  **不给执行者＝机械拍**，这条默认姿态没有变。四种失败（非零退出／超时／空输出／
  命令起不来）全部可见，且与拍失败**分开计数**。
  → [`docs/running.md`](https://github.com/Chestnuts-Sisyphus/Infinigrow/blob/main/docs/running.md)
- **组织会话运行体**：语义判断从「写在提示词里的判据」变成真代码：输入 B猜＋留痕＋W回，
  输出四类差异与**规划预测**；发现落 `state/org-findings.jsonl`，
  结局由后来的对账现算（`infinigrow org-status`：待验／被证实／被推翻）——
  **判断不由引擎自述**。
- **规划预测覆盖默认**：默认 B猜是「不变」；组织会话写的规划值会覆盖它。
  没有这层覆盖，任何真动手的一拍都会被判成「预测内错」——那说明的不是「干错了」，
  而是「没预测」。
- **域饱和判据**：同一「对象域 × 标准可验证量」只养**一根未完成芽**（含同拍内）。
  重复差异不新生芽，而是登记为已有芽的 `absorbed`；差异**照旧入账**
  （打标 `absorbed_by_domain`）——配额不是隐藏。解冻只由**新产出的量**或被消解触发。
- **账本轮转**：按大小阈值把历史行**移动**到 `state/archive/`（只移动不删）。
  历史型账本保留尾部 N 行；**状态型账本（成熟链／能力库）每个键保留最新一行**
  ——否则很久没碰过的对象会随轮转悄悄倒退。归档可检索。
- **兑现率诚实呈现**：兑现账新增 `sample` 字段，分母只数「执行者真动过手」的拍；
  一行样本都没有时写「**无样本**」（不可计算），不写 0、不写「差」。
- **三种新静态规则**（共 9 条，正/反用例齐备）：**R7** rc 语义单一来源、
  **R8** 写盘窗口一致（引擎里只有 `ledger/store.py` 与 `core/encoding.py` 能直接写盘）、
  **R9** 同源表不缩表。

## 工程

- 一键件 `tools/run_tick.bat`（**版本闸 → 跑一拍 → 园丁**）＋ 计划任务注册器
  （`Infinigrow_tick`，默认每 10 分钟）。
- **CI 双平台**：矩阵加 `windows-latest`（引擎实际跑在 Windows 上）。
- `update_local.py` 归并进 `run_latest.py --update`（旧命令退化为会自我说明的转发壳）。
- 两个真缺陷：`run_latest.py --repo` 原先不生效（版本判定看的是本仓库）；
  取题顺序被芽源前缀支配（`cap*` 永远插在 `sp*` 前面，把主芽源饿死）。
- 双平台 CI 第一次跑就抓到的一族缺陷：非 UTF-8 控制台上中文输出 `UnicodeEncodeError`
  （所有入口现在统一过 `core/encoding.harden_stdio`）、
  `.bat`/`.ps1` 里的中文会被 cmd/PowerShell 的代码页读坏（改为纯 ASCII）、
  产物检查器对 PNG 误报（改为跳过二进制并报数）。

## 已知限制

- 组织会话的语义能力**取决于执行者**：不接执行者时它整段不跑（只留下「该跑了」的提示）。
- 域饱和会把同域同量的后续差异记成 `absorbed`：这是**配额**，不是解决——
  想看全貌请读差异账里带 `absorbed_by_domain` 标记的行。
- 轮转不做压缩：历史行原样留在 `state/archive/`（「只移动不删」是刻意选择）。
- 引擎默认不接执行者，因此开箱跑出来的账本是**机械拍**的：它能证明机制在转，
  但兑现率会一直显示「无样本」，直到你接上一个真正会动手的执行者。

**完整变更**：[`CHANGELOG.md`](https://github.com/Chestnuts-Sisyphus/Infinigrow/blob/main/CHANGELOG.md)
