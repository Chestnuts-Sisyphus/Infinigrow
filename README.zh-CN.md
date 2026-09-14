# Infinigrow（中文说明）

**靠「预测 → 对账 → 把差异变成芽」来生长的引擎。**

[English README](README.md) · [机制正本](docs/mechanism.md) · [架构](docs/architecture.md) · [安全说明](SECURITY.md)

---

## 它是什么

多数「自主 agent」循环靠**累积**生长：更多笔记、更多记忆、更多摘要。
这种生长没有梯度——它可以永远转下去而不会变好，最后只是在同一道沟里反复犁。

Infinigrow 靠**被现实反驳**生长。每一拍：

1. **预测（B猜）**：动手前写下「我预期现实会变成什么样」；
2. **动手**：做事；
3. **对账**：现实给出回答（W回），引擎机械地比对「预期 vs 实际」；
4. **生芽**：每个差异成为一根芽——下一件要消解的事。**没有差异就没有芽。**

引擎本体约 2,000 行 Python（另有约 600 行测试），默认不联网、不需要任何凭据。
**空状态目录、零 token 跑一拍**就是 CI 每次 push 都会做的事。

## 为什么是「预测 + 对账」

预测是让生长**可被证伪**的唯一办法。没有它，「进步」就是系统自己说了算；
有了它，账本能自己算出兑现率（预测被现实证实的比率），不需要任何人评价。

由此而来的设计决定：

| 决定 | 理由 |
|---|---|
| 芽**只**来自账本（差异／成熟链封顶／能力库未用） | 执行会话不得自己造活干。上一代引擎可以的时候，队列里 221 根待长塞进 186 根同族、题面逐字相同，直接原地打转 |
| **N 差异 N 芽；零差异零芽** | 否则芽数量会变成好看的数字游戏 |
| 账本**只增不改**，只有队列可变 | 能改的统计不是统计 |
| 成熟链**同拍最多 +1** | 曾有并发会话把它一次加了两级 |
| 对账报告名带拍号，会话取独占锁 | 同秒覆盖曾静默吃掉报告 |
| 心跳写失败**抛异常** | 园丁的断流判据读的就是它；静默停摆会让两条守卫线一起报「正常」 |

## 快速开始

```bash
pip install -e ".[dev]"

infinigrow version              # Infinigrow 2.1.0
infinigrow dry-run              # 只解析配置与路径（零写盘）
infinigrow tick --probe         # 跑一拍（零 token）
infinigrow gardener             # 机械园丁（免疫系统）
infinigrow scan                 # 静态规则（路径／同源／凭据／BOM…）
infinigrow selftest             # 规则正反用例
```

状态默认落在 `./state/`，**已被 .gitignore 忽略**。可以指到任何地方：

```bash
infinigrow --state-root /tmp/ig tick
IG_STATE_ROOT=/tmp/ig infinigrow tick
```

## 机制一表

| 边 | 方向 | 「长了」的判据 |
|---|---|---|
| 判读 | W→B | 对该对象的预测在下一次对账被证实 |
| 行动 | B→W | 动作执行后现实侧对象发生可查变化 |
| 原理 | B→B | 推出的认知在从未测过的域被验证 |
| 固化 | W→W | 同类输入不再烧认知（自动通过） |

成熟链：判读 → 行动 → 原理 → 固化（四步，第四步即封顶）。
芽的三个来源：差异对账、成熟链封顶（「它还能在哪用」）、能力库未用
（「为什么没被用上／换个域是否成立」）。其余见[机制正本](docs/mechanism.md)。

## 接执行者

一拍可以接一个执行者；不接就是纯机械拍。

```python
from infinigrow import load_settings, run_tick

def my_executor(prompt: str) -> str:
    # 你的模型／脚本／人；接任何会执行命令的东西之前先读 SECURITY.md
    return "..."

result = run_tick(settings=load_settings(), llm=my_executor)
print(result.diff_summary, result.new_sprouts)
```

## 由机器守、不靠记忆守的约定

```bash
infinigrow scan      # R1 零绝对路径 · R2 提示词↔代码同源 · R3 禁自造芽条款
                     # R4 状态根被忽略 · R5 无凭据字面量 · R6 无 BOM
infinigrow selftest  # 每条规则都有正例与反例
python tools/check_prompt_code_sync.py   # 提示词与代码双向同源校验
python tools/privacy_scan.py --root .    # 发布前的路径/凭据/邮箱扫描
```

## 状态与限制

v2.0.0 是重写线的第一个版本。已知限制见
[CHANGELOG.md](CHANGELOG.md#known-limitations-v200)：机械拍自身不烧认知、
执行者接口就是一个普通函数、部署集成（调度器/代理/多通道轮转）刻意不做进本版。

## 许可

MIT —— 见 [LICENSE](LICENSE)。
