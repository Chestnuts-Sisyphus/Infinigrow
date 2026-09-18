# Infinigrow

[![ci](https://github.com/Chestnuts-Sisyphus/Infinigrow/actions/workflows/ci.yml/badge.svg)](https://github.com/Chestnuts-Sisyphus/Infinigrow/actions/workflows/ci.yml)
[![release](https://img.shields.io/github/v/release/Chestnuts-Sisyphus/Infinigrow?color=8B5CF6)](https://github.com/Chestnuts-Sisyphus/Infinigrow/releases)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](pyproject.toml)
[![runtime deps](https://img.shields.io/badge/runtime%20deps-0-brightgreen.svg)](pyproject.toml)

**一个靠「预测 → 对账 → 把差异变成芽」来生长的引擎。**

[English](README.md) · [机制正本](docs/zh/mechanism.md) · [架构](docs/zh/architecture.md) · [运转手册](docs/zh/running.md) · [安全](SECURITY.md)

> 本文是 `README.md` 的中文版。公开文档以英文为主（面向冷读者）；
> **机制正本与设计文档的中文原版在 [`docs/zh/`](docs/zh/)**，英文版在 [`docs/`](docs/)。

---

## 想法

多数「自主 agent」循环靠**累积**生长：更多笔记、更多记忆、更多摘要。那种生长没有梯度——
它可以永远转下去而不变好，最后只是反复耕同一块地。

Infinigrow 靠**被现实反驳**生长。每一拍：

1. **预测**——动手之前，先写下「现实应该变成什么样」（对象、维度、预期态、证据指针）；
2. **动手**——真的做事（由执行者完成，也可以是「什么也不做」）；
3. **对账**——把现实读回来，与预测**机械**比对；
4. **生芽**——每个差异成为下一件要做的事。**没有差异，就没有芽。**

第 1 步存在的意义是**可证伪**：没有写下来的预测，「进步」就是系统自己说了算；
有了它，账本可以现算**兑现率**（预测被现实证实的比例），不用征求任何人的意见。

## 你可以拿它做什么

- **自我改进循环的骨架**：把执行者换成你的模型或脚本（`run_tick(..., llm=...)`，或一条
  读 stdin / 写 stdout 的命令），引擎负责其余全部机械部分——预测清单、对账、生芽、队列纪律、
  账本、心跳、并发锁。
- **预测准确率的实验记录本**：差异账／兑现账／成熟链都是**追加型** JSONL；兑现率现算，
  并按「对象域 × 边类型 × 成熟链步」分桶。想做「它到底有多准」的长期研究，数据格式是现成的。
- **一套可直接搬走的约束**：如果你也在写 agent 循环，这四条是踩过坑之后的形状——
  **执行会话不得自造任务**、**零差异零芽**、**同对象同维度只养一根芽**、
  **成熟链同拍最多 +1**（退役登记见 [`docs/zh/superseded.md`](docs/zh/superseded.md)）。
- **三个可单独使用的工具**：静态规则扫描、隐私/身份清场扫描、提示词↔代码同源校验，
  都能脱离引擎单独跑。

## 机制一张表

只有两个仓库：**B＝认知**、**W＝现实**；一切结构都是两者之间的边：

| 边 | 方向 | 「长了」的判据 |
|---|---|---|
| 判读 | W→B | 该对象的预测在下一次对账中被证实 |
| 行动 | B→W | 动作让现实发生了可查的变化 |
| 原理 | B→B | 推出的认知在从未测过的域成立 |
| 固化 | W→W | 同一类输入不再烧认知（自动了） |

一条经验沿「判读 → 行动 → 原理 → 固化」成熟；第四步是封顶，封顶不是终点而是新问题。
芽源恰好三个：**差异**、**成熟链封顶**（「它还能在哪用」）、**能力库未用**（「为什么没用上，
换个域是否成立」）。其余（队列纪律、提醒的出口、域饱和、账本、静态规则）见
[`docs/zh/mechanism.md`](docs/zh/mechanism.md)（英文版：[`docs/mechanism.md`](docs/mechanism.md)）。

## 五分钟跑通（零 token、零凭据、不出网）

```bash
git clone https://github.com/Chestnuts-Sisyphus/Infinigrow && cd Infinigrow
pip install -e ".[dev]"

infinigrow version              # 引擎版本
infinigrow dry-run              # 解析后的配置、主体根、执行者（不写盘）
infinigrow tick --probe         # 跑一拍
infinigrow tick --json          # 同上，机读
infinigrow gardener             # 机械免疫系统（锁／断流／失败升级／轮转）
infinigrow scan                 # 十条静态规则
infinigrow selftest             # 每条规则的正反用例
infinigrow status               # 拍号、主体、队列组成、容量闸+重问闸、合规率、执行者损耗、用量分账、告警
infinigrow rotate               # 历史行移进 state/archive/（只移动不删）
```

状态默认落在 `./state/`（已被 git 忽略），可指到任意位置：

```bash
infinigrow --state-root /tmp/ig tick
IG_STATE_ROOT=/tmp/ig infinigrow tick
```

### 接上会动手的执行者

默认是**机械拍**：零 token、零凭据、不出网。要让它动手，给它一个**执行者**——
任何「提示词从 **stdin** 进、答案从 **stdout** 出」的命令：

```bash
infinigrow tick --executor "你的命令 参数"      # 或设 IG_EXECUTOR
```

四种失败（非零退出／超时／空输出／起不来）全部记进 `state/executor.jsonl`，且与拍失败
分开计数；每次调用的原文落 `state/traces/`。详见 [`docs/zh/running.md`](docs/zh/running.md)。

```python
from infinigrow import load_settings, run_tick

def my_executor(prompt: str) -> str:
    # 你的模型/脚本/人；接「会执行命令」的东西之前先读 SECURITY.md
    return "..."

result = run_tick(settings=load_settings(), llm=my_executor)
print(result.diff_summary, result.new_sprouts)
```

### 它在长什么（生长主体）

引擎需要一个被生长的目录（**生长主体**），默认取仓库的**同级**目录；里面的对象命名为
`主体/<相对路径>`，机械观测读存在性、文件数、字节数与目录格数。详见
[`docs/zh/growth-subject.md`](docs/zh/growth-subject.md)。

### 挂上计划任务（Windows）

```bat
tools\run_tick.bat                        :: 版本闸 -> 跑一拍 -> 园丁
tools\manage_scheduled_task.bat install   :: 注册任务（默认每 10 分钟）
```

任务动作是隐藏启动器（`wscript //nologo tools\run_tick_hidden.vbs`）——直接挂 `.bat` 或裸
`python` 每跑一次都会闪一个控制台窗口、抢走焦点。规则 R10 与测试守住这条。

## 架构

```
CLI ─▶ scheduler ─┐
                  ├─▶ engine ───────▶ ledger ──────▶ core
     rules ───────┤   tick             store           paths / config / encoding
     garden ──────┘   reconcile        rotation        exit_codes / version_check
                      sprout_* / model  （唯一写盘路径）
                      org_trigger / org_session
                      subject / executor / domain_saturation
```

六层包，依赖单向；全工程只有一处允许直接与磁盘打交道。完整分层与每条边界背后的原因：
[`docs/zh/architecture.md`](docs/zh/architecture.md)。

## 机器守着的保证（不靠记忆）

```bash
infinigrow scan                          # R1 零绝对路径 · R2 提示词↔代码同源
                                         # R3 禁自造芽条款 · R4 状态根被忽略
                                         # R5 无凭据字面量 · R6 无 BOM · R7 rc 单一来源
                                         # R8 单一写盘路径 · R9 同源表不缩表
                                         # R10 计划任务走隐藏启动器
infinigrow selftest                      # 每条规则一条正例、一条反例
python tools/check_prompt_code_sync.py   # 双向同源校验
python tools/privacy_scan.py --root .    # 发布前：路径／凭据／邮箱
```

CI 在 Linux 与 Windows、Python 3.11 与 3.12 上都跑这些，外加一次**冷启动**：空状态根跑三拍、
零 token、零凭据，并断言产物里不出现任何绝对路径。

## 永远用最新版引擎

```bash
python tools/run_latest.py        # 能升就升到最新再跑；升不动就按现有版本照常跑
infinigrow version --check        # 只查：本地版 vs 最新发布（落后时退出码 3）
```

「能升就升；升不动就按现有版本照常跑并说明为什么」——不会因为「不是最新版」把引擎停掉，
也不会在有拍在飞时替换引擎代码。细节见 [`docs/zh/upgrading.md`](docs/zh/upgrading.md)。

## 现状与限制

引擎在真机上运转（每十分钟一拍、接着执行者、账本持续增长）。v2.0.0 之后的每一处改动都来自
一次真机观察；值得知道的都在 Release 说明与[退役登记表](docs/zh/superseded.md)里。

不掩饰的限制：

- **机械拍不做认知**：它只能证明机制在转，不会长出东西。
- **引擎刻意小**（≈4,400 行 Python ＋ ≈2,600 行测试），**运行时依赖 0 个**；
  调度、代理、多通道轮转、沙箱这些部署面属于使用者，起点是 [`SECURITY.md`](SECURITY.md)。
- **执行者接口就是一个普通可调用/命令**：不带任何厂商 SDK。
- **机制语言是中文**（代码、提示词、账本字段）；英文文档里附了双语术语表。
- **主体是使用者的**：仓库不带任何主体、账本与状态。

## 文档

| 文档 | 回答什么 |
|---|---|
| [`docs/zh/mechanism.md`](docs/zh/mechanism.md) | 机制正本（中文；英文版 [`docs/mechanism.md`](docs/mechanism.md) 含术语表） |
| [`docs/zh/architecture.md`](docs/zh/architecture.md) | 分层、写盘路径、状态布局、一拍的时序 |
| [`docs/zh/growth-subject.md`](docs/zh/growth-subject.md) | 在长什么、怎么观测、命名规则 |
| [`docs/zh/running.md`](docs/zh/running.md) | 执行者通道、调度、长窗口观察 |
| [`docs/zh/upgrading.md`](docs/zh/upgrading.md) | 「默认最新版」这条规则 |
| [`docs/zh/privacy.md`](docs/zh/privacy.md) | 三条硬线与发布前清单 |
| [`docs/zh/versioning.md`](docs/zh/versioning.md) | v1 与 v2，以及版本号在这里的含义 |
| [`docs/zh/superseded.md`](docs/zh/superseded.md) | 已退役机制与取代者 |
| [`CHANGELOG.md`](CHANGELOG.md) | 逐版本变化 |

## 许可

MIT，见 [LICENSE](LICENSE)。
