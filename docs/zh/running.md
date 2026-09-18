# 让它运转起来（Running Infinigrow）

> 两份东西：**执行者通道**（引擎怎么真的动手）＋ **调度与看护**（怎么让它自己按时跑）。
> 两者都不写死任何厂商、任何路径、任何凭据。

> **语言说明（Q13/A10）**：引擎的**运行时文案是中文**——`--help`、`status` 输出、对账报告、
> `ALERT.md`、账本字段值都是中文，因为那是机制的语言（术语表见
> `docs/zh/mechanism.md` 与 `docs/mechanism.md`）。英文文档是它的**说明书**。
> 英文运行时（`--lang`／`IG_LANG`）**尚未实现**：要做也**只覆盖 CLI 层文案**，
> 不动机制词与账本字段——那属于**语言边界决策**（英文公开面 ↔ 中文内核），需另行拍板。

---

## 一、执行者通道（让引擎能动手）

### 1. 契约

```
    python -m infinigrow tick --executor "你的命令 参数..."
                    │
                    ├─ stdin  ← 提示词（机制提示词原文 ＋ 本拍题面 ＋ 本拍 B猜）
                    └─ stdout → 你的输出（原样落 state/traces/，可选用量一行）
```

- **不给执行者＝机械拍**：零 token、零凭据、不出网（默认姿态；也是 CI 与空仓验收用的姿态）；
- 一次调用＝一次动手机会。同一通道两种用途（用环境变量 `IG_PASS_KIND` 区分）：
  - `tick`：本拍要消解的差异（题面）；
  - `org-session`：语义判断（找差异、写规划预测、登记芽）。
- **起子进程不用 shell**：命令按引号拆成 argv 后直接执行（`shell=True` 会把
  「拼接字符串」的自由交给调用方，Windows 上还会顺带展开 `%VAR%`）。
  带盘符的路径请用正斜杠或整段加引号。

### 2. 接法

| 方式 | 命令 |
|---|---|
| 一次性（CLI） | `python -m infinigrow tick --executor "你的命令"` |
| 配置项 | `executor = "你的命令"`（`infinigrow.toml`）|
| 环境变量 | `IG_EXECUTOR="你的命令"`（计划任务/守护脚本里最方便）|
| 强制机械拍 | `--no-executor`（即使配置里设了也不接）|
| 超时 | `--executor-timeout 300` 或 `IG_EXECUTOR_TIMEOUT_S`（默认 120 秒）|

**超时 × 调度时限（K12/A17，别把窗口烧满）**：单次执行者调用超时
（`IG_EXECUTOR_TIMEOUT_S`，本机 600 秒）与计划任务的总时限（30 分钟）**不是一回事**。
一拍里可能有一次 tick 调用 ＋ 一次组织会话调用，各自都有独立超时；若两者都烧满
（600+600=1200 秒≈20 分钟），仍在 30 分钟调度时限内，但**余量只剩 10 分钟**——
同一拍里还有对账、记账、园丁，且 30 分钟一到 Windows 任务计划会**终止进程**。
所以：执行者超时 × 每拍调用次数**必须明显小于**调度时限（经验法则：留 ≥1/3 余量）。
卡死时占用窗口、任务被计划器杀、账本停在半拍——这些都比「单次调用失败」贵得多，
宁可让单次调用早点超时（调小 `IG_EXECUTOR_TIMEOUT_S`），也不要把整拍拖到被杀。
（不改使用者的环境变量，这里只写关系与建议。）

### 3. 引擎给执行者的环境变量

| 变量 | 含义 |
|---|---|
| `IG_TICK` | 本拍拍号 |
| `IG_PASS_KIND` | `tick` 或 `org-session`（同一通道、两种提示词）|
| `IG_SUBJECT_ROOT` | 生长主体根（**动手的地方**）|
| `IG_STATE_ROOT` | 状态根（账本与留痕；执行者一般只读）|
| `IG_MODEL` | 配置里的模型标识（透传，供执行者自己取用）|

**工作目录＝仓库根**（不是主体根）：命令照你在仓库里的写法解析，
`python tools/xxx.py` 这类相对路径可以直接用；「该动手的地方」由 `IG_SUBJECT_ROOT` 告诉执行者。
两者分工明确，不靠猜。

凭据**不搬运**：引擎不读、不传、不落盘任何密钥；要什么凭据由使用者自己的环境
或执行者脚本准备（这也是 `SECURITY.md` 里的沙箱建议）。

### 4. 失败必须可见（四况全记账）

| 情形 | 记账 | 心跳计数 |
|---|---|---|
| 正常 | `state/executor.jsonl`：rc=0、耗时、输出长度、用量（若有） | 归零 |
| 非零退出 | 同上，rc=退出码，`note` 说明 | 「执行者连续失败」+1 |
| 超时 | rc=124、`timed_out=true`，子进程被杀 | 同上 |
| 空输出 | rc=0 但 `output_bytes=0`，`note` 点名 | 归零（它没失败，只是什么都没说） |

另外两种也记：**命令起不来**（rc=127）与**进程内可调用抛异常**（rc=1）。
园丁在「执行者连续失败 ≥ 3」时置致命旗并写 `state/ALERT.md`
——机械拍失败与执行者失败**分开计**，因为故障位置不同。

### 5. 留痕

每次调用的提示词与输出**原文**落 `state/traces/<用途>-<拍号>.md`（原子替换；同拍重跑＝同一个文件）。
留痕里的本机绝对路径会被替换成占位符（状态目录要能分享/迁移）。
用量是**可选项**：输出里出现一行 `IG_USAGE {"input_tokens": 0, "cost_usd": 0}`
才会进账；不写就是 `null`——引擎不拿输出长度冒充 token 数。

### 6. 先试跑（不烧任何认知）

```bash
# 1) 看配置与主体（零写盘）
python -m infinigrow dry-run

# 2) 一个本地确定性"执行者"：验证通道、记账、留痕、对账闭环
python -m infinigrow tick --executor "python tools/demo_executor.py" --json

# 3) 只跑组织会话（看它能不能从 B猜/留痕/W回 里找出差异）
python -m infinigrow org-session --tick 1 --executor "python tools/demo_executor.py"

# 4) 看组织会话的判断后来被证实还是被推翻（这是"可被打脸"的落地形态）
python -m infinigrow org-status
```

`tools/demo_executor.py` 是**确定性脚本**，不是模型：它只用来证明机制通。

---

## 二、调度与看护（让运转成为常态）

### 1. 一键件

| 文件 | 干什么 |
|---|---|
| `tools/run_tick.bat` | 一次完整的运转：**版本闸 → 跑一拍 → 园丁（死锁/断流/失败升级/轮转）** |
| `tools/manage_scheduled_task.bat` | `install` / `status` / `uninstall` 计划任务 |
| `tools/scheduled_task.ps1` | 真正的注册逻辑（按当前登录用户，不请求提权） |
| `tools/run_tick_hidden.vbs` | **隐藏启动器**：计划任务挂它，不是挂 `.bat` |

双击 `tools/run_tick.bat` 就能跑一拍；计划任务挂的就是它。

### 2. 挂上计划任务（每 10 分钟一拍）

```bat
tools\manage_scheduled_task.bat install
tools\manage_scheduled_task.bat status
```

- 间隔取 `IG_TICK_MINUTES`（默认 **10 分钟**，与配置项 `tick_minutes` 同义）；
- 任务名默认 `Infinigrow_tick`（可用 `IG_TASK_NAME` 改）；
- **每次起跑都过版本闸**：默认升级到最新版再跑；升不动（工作区脏/有拍在飞/分叉/离线/
  自检不过已回滚）就**按现有版本照常跑**，并打印「为什么这次不是最新版」——
  **绝不因为「不是最新版」把引擎停掉**；
- 卸载：`tools\manage_scheduled_task.bat uninstall`（**只删任务，不删状态与账本**）。

### 2.5 为什么不直接挂 `.bat`（**别去掉这一层**）

让计划任务直接跑 `.bat`（或 `cmd`、裸 `python`），**每跑一次就会在屏幕上闪一个控制台窗口**
——抢焦点、遮住人正在看的东西。`run_tick_hidden.vbs` 用 WSH 的窗口样式 0 把它藏起来，
任务动作因此是 `wscript.exe //nologo …run_tick_hidden.vbs`。
注意 `New-ScheduledTaskSettingsSet -Hidden` 只隐藏任务列表里的**条目**，**不隐藏窗口**，别混。

（同类经验：`.bat`/`.vbs` 一律**纯 ASCII**——cmd 与 wscript 按系统代码页读脚本，
中文注释会破坏解析；需要无窗口跑 Python 时用 `pythonw.exe`。）

### 3. 看护（园丁每次跑顺手做）

| 检查 | 判据 | 后果 |
|---|---|---|
| 死锁 | 锁文件 mtime 年龄 > 15 分钟 | 清掉陈旧锁 |
| 断流 | 最后一拍的**机械时间戳**距今 > 12 小时 | 致命旗（`state/ALERT.md`）|
| 拍失败 | 连续失败 ≥ 3 拍 | 致命旗 |
| 执行者失败 | 连续失败 ≥ 3 次 | 致命旗（含最后 rc）|
| 账本坏行 | 解析不了的行数 > 0 | 致命旗 |
| 账本轮转 | 账本字节数 ≥ `rotate_max_bytes` | 轮转（只移动不删）|

人只需要看一个文件：**`state/ALERT.md`**——有致命旗就写「需要人看一眼」＋逐条原因，
没有就写「引擎正常」＋最后一拍时间。

### 4. 日志

`run_tick.bat` 把每一步追加到 `state/logs/tick.log`（状态根内，随状态一起搬走）。

### 5. 排障顺序（从外面往里）

```bash
python -m infinigrow dry-run        # 配置/主体/执行者是不是你以为的那样
python -m infinigrow tick --json    # 单独跑一拍：看 rc、差异、报告名
python -m infinigrow gardener       # 看护一遍（会写 ALERT.md）并打印体检 JSON
cat state/ALERT.md                  # 人读面
cat state/tick_status.json          # 心跳：拍号/时间戳/连续失败/执行者失败/引擎身份
tail state/executor.jsonl           # 执行者调用账（rc/耗时/输出长度/用量）
python -m infinigrow org-status     # 组织会话发现的结局（待验/被证实/被推翻）
```

**`org-check`：结论在 JSON 里，退出码只管「命令跑没跑成」**：`should_run=true → 0`，
`should_run=false → 5`。这个 5 是 `exit_codes.NOT_THIS_TICK`——「跑成功了，答案是这一拍不该跑」，
2026-09-19 起替掉它原先借用的 **1**（1 重新只属于「参数/用法错误」，写错参数不再躲在一个正当的
「不」后面）。CI 冷启动那一步现在把它挪到跑拍**之前**——空状态根上答案是「该跑」，rc=0，于是
原先那句把真正用法错误一起吞掉的 `|| true` 整个去掉了。
**分支请读 `should_run`，别读 rc。**

---

## 三、成本与用量（接上执行者之后才有意义）

| 事实 | 在哪看 |
|---|---|
| 引擎自身 | **零 token**：机械拍、园丁、规则扫描、对账、记账都不烧认知 |
| 执行者 | 用量由执行者自报（`IG_USAGE` 一行）；引擎只记不猜 |
| 兑现率 | `state/reconcile/reconcile-*.md` 的「兑现率」段：**没有执行者动手就写「无样本」**，不写 0、不写「差」|

兑现率的分母只数**有执行者动手的拍**（`sample=true`）：
机械拍的「打脸」不代表能力差，它只是没有手在动。

## 四、一键总览与暂停/恢复（T8/A15）

```bash
python -m infinigrow status      # 拍号/主体文件数/队列/容量闸+重问闸/合规率/执行者损耗/用量分账/ALERT 首行/今日 token
python -m infinigrow pause       # 停计划任务（**不删**；任务仍在，可 resume）
python -m infinigrow resume      # 恢复计划任务
```

`pause`/`resume` 只切换计划任务的 Enabled 状态（`Disable-ScheduledTask`/`Enable-ScheduledTask`），
**不删除任务、不动账本**。非 Windows 上它们报「环境不满足」（rc=4），不假装成功。
`status` 里的 token 数只统计执行者**自报**的用量（`IG_USAGE`）——执行者不自报就写
「不可估算」，引擎不拿输出长度冒充 token。

## 五、本机部署参考（私有部分，按你的环境照做；**别把密钥写进仓库**）

引擎本身零配置可跑；让它真的动手、真的按时跑，本机需要四件事：

1. **执行者适配器**（私有脚本，放仓库之外）：读你**自己的**密钥来源（只读、经环境变量、
   不落盘不回显），把引擎的提示词（stdin）送给你的模型，把 stdout 原样返回；
   成功时另打一行 `IG_USAGE {…}` 自报用量。契约见本文档「一、执行者通道」。
   引擎**不写死任何厂商**：接什么模型由 `IG_EXECUTOR` 决定。
2. **用户级环境变量**：`IG_EXECUTOR`（适配器命令）、`IG_EXECUTOR_TIMEOUT_S`（超时）、
   以及适配器自己需要的模型档位变量（例如 `IG_MUSE_EFFORT=low`）。
3. **计划任务**：`tools\manage_scheduled_task.bat install` 或
   `tools\scheduled_task.ps1 -Action install`（每 10 分钟一拍，动作是**隐藏启动器**，
   见 §2.5——别把 `.bat` 直接挂上去）。改频率：`IG_TICK_MINUTES`。
4. **生长主体**：默认在仓库同级（`<仓库名>-subject`）；换主体＝改 `IG_SUBJECT_ROOT` 并
   **连同换 `IG_STATE_ROOT`**（旧账本说的是旧主体的事，见 `docs/zh/growth-subject.md`）。

自检：`python <你的适配器> --selftest`（如果有）→ 应打印「在线」类回答；
`python -m infinigrow status` → 看到拍号随时间自增、ALERT 首行「引擎正常」。
排障顺序见 §2.5 之后的「二.5 排障顺序」。

