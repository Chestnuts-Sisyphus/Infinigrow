# 引擎版本规则：**默认用最新版，升不动就按现有版本跑**

## 一句话

Infinigrow 是**引擎**；这条规则管的是**引擎**的版本（不是它生长的主体）。
默认行为：**能升就升到最新再跑；升不动就按现有版本照常跑，并说明为什么。**

## 运行入口

```bash
python tools/run_latest.py              # 默认：有条件升级就升到最新，然后跑一拍
python tools/run_latest.py -- --probe   # 「--」之后透传给 `infinigrow tick`
python tools/run_latest.py --check      # 只看版本状态，不起跑
python tools/run_latest.py --no-update  # 不尝试升级，直接用当前版本跑
python tools/run_latest.py --require-latest   # 严格模式：拿不到最新版就不跑
```

## 三段语义（缺一不可）

| 情形 | 行为 | 为什么 |
|---|---|---|
| **有条件升级**（落后 ＋ 工作区干净 ＋ 无拍在飞 ＋ 历史不分叉 ＋ 升级后自检通过） | **升级，然后用新版跑** | 这是默认：对使用者来说默认就是新版 |
| **没条件升级**（工作区有改动／有拍在飞／历史分叉／离线／pull 失败／自检不过已回滚） | **按现有版本照常跑**，并打印「为什么这次不是最新版」 | **绝不因为「不是最新版」把引擎停掉**——旧版能跑就让它跑，规则才可用 |
| **严格模式**（`--require-latest`） | 升不到最新就**不跑**（rc=4） | 给 CI／发布验证这类场合用的**可选严格**，不是默认 |

细节：

- **工作区有未提交改动时不升级**：升级是 `git pull --ff-only`，不会盖掉你的改动；
  这也是为什么它不会「顺手把你的活儿埋掉」。
- **有拍在飞时不升级**：`state/locks/tick.lock` 存在就不动代码——
  绝不在运行中替换引擎。并发本身由引擎自己的锁处理（拿不到锁的那一拍会幂等跳过）。
- **升级后自检不过 → 回滚**（`selftest` ＋ `scan` 任一不过），然后按回滚后的版本跑：
  宁可跑旧版，也不跑一个自检不过的新版。
- **升级只动引擎代码**：`state/`（生长主体：账本、队列、报告）是 git 忽略项，
  `pull`/`reset` 不会碰它。引擎换代，主体留痕不受影响。

## 每一拍都记着「是哪个引擎跑的」

心跳（`state/tick_status.json`）与每份对账报告都带**引擎身份**：

```
- 引擎：Infinigrow 2.0.0 (5b8a069)
```

引擎会自己升级，所以必须能回答一个追溯问题——**这一拍是哪个版本跑出来的**。
只有 tick 数字是不够的：升级之后，历史读数属于哪一版就说不清了。

## 只想知道「我是不是最新」

```bash
infinigrow version --check      # 本地版 vs 最新发布；落后 → 退出码 3
```

只读 GitHub 公开的 releases 接口，**零凭据**、零写入。离线或查不到时明确报 `unknown`（rc 0），
**绝不把「不知道」说成「已是最新」**。

## 手动升级（等价于入口做的事）

```bash
cd <你的 Infinigrow 目录>
git fetch --tags
git log --oneline HEAD..origin/main      # 先看差了什么
git pull --ff-only                       # 非快进会失败——先处理本地改动
python -m pip install -e .
python -m infinigrow selftest && python -m infinigrow scan
python -m infinigrow version --check     # 确认已是最新
```

## 版本号怎么看

- 版本单一事实源是 `src/infinigrow/__init__.py` 的 `__version__` 与 `pyproject.toml` 的 `version`；
  两者不一致会被 `tests/test_version.py` 拦下。
- 语义与 v1/v2 的断代关系见 [`versioning.md`](versioning.md)。
- 每个版本改了什么、已知限制是什么，见 [`CHANGELOG.md`](../CHANGELOG.md)；Release 正文另有清单。
