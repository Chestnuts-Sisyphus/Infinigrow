# 参与贡献（CONTRIBUTING）

先读 [`docs/mechanism.md`](docs/mechanism.md)——**机制是判据，不是风格**。
改判据与改代码是同一件事的两半，缺一半会被机器拦下。

## 本地开发

```bash
pip install -e ".[dev]"
python -m pytest -q              # 全部测试
python -m infinigrow scan        # 静态规则（必须全 PASS）
python -m infinigrow selftest    # 规则的正/反用例
python tools/check_prompt_code_sync.py
python tools/privacy_scan.py --root .
python tools/check_no_abs_paths.py state   # 状态产物不得含本机路径（有产物时）
```

推 PR 前请把上面这些跑一遍；CI 也会跑一遍（现在**双平台**：ubuntu 与 windows，
含**冷启动空仓跑三拍**、产物零绝对路径、一键件语法解析）。

## 改机制（P0 变更）

机械词（判读/行动/原理/固化/成熟链/差异/兑现账/成熟链封顶/能力库未用/零差异零芽/
生长主体/执行者/组织会话/域饱和/轮转）
是**同源词**：它们在 `docs/mechanism.md`、代码、提示词三处必须同时存在。
同源表定义在 `src/infinigrow/rules/static_scan.py` 的 `SYNC_TERMS`（单一事实源），
`tools/check_prompt_code_sync.py` 做双向检查；规则 **R9** 再守住这张表的**覆盖下限**
（有人静默删词＝漂移面回来了）。

改判据的四步：

1. 改 `docs/mechanism.md`（写清「为什么」，不只是「改成什么」）；
2. 改代码（`engine/` 下的词汇表与函数）；
3. 改提示词（`prompts/`）；
4. 跑上面那组命令，全绿。

**只改一处＝漂移**，CI 会失败——这是刻意的：本项目的上一代就是因为「同一条规则两处写、
各自演化」而原地打转。

## 加一条静态规则

1. 在 `src/infinigrow/rules/static_scan.py` 写规则函数（返回 `(明细, 是否通过)`）；
2. 在 `RULES` 表加一行；
3. 在 `SELFTEST_CASES` 加**正例与反例**（只加正例会被覆盖检查判 FAIL）；
4. 让它在真实仓库上 PASS（若规则第一次跑就 FAIL，先把仓库改干净，别关掉规则）。

## 代码风格

- 行宽 100（`ruff` 管）；中文注释与文档是这个项目的正常形态，不要翻译成英文。
- 注释只写**为什么**（约束、坑、代价），不写「这行在干什么」。
- 三处改动永远一起做：文档 / 代码 / 测试。

## 提交信息

```
<范围>: <做了什么>（一句话，中文或英文都行）

为什么这么做：<约束或事故，若不是显然>
验证：<跑了哪条命令，结果如何>
```

## 行为准则

见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。
