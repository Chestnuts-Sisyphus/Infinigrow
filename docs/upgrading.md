# 升级规则：**运转的永远是最新版**

## 规则本身

**任何在跑的 Infinigrow 都必须是当前最新发布版。** 这条不靠人记，而是**运行入口自带版本闸**：

```bash
python tools/run_latest.py          # 运行入口：先确保最新 → 再起跑（默认跑一拍）
python tools/run_latest.py --check  # 只看差多少，不起跑
python tools/run_latest.py -- --probe   # 「--」之后的参数透传给 `infinigrow tick`
```

`run_latest.py` 在起跑前做四件事，**每一件都对应一种「不能升」的情况**：

| 情况 | 行为 | 为什么 |
|---|---|---|
| 工作区有未提交改动 | **拒绝升级**，直接起跑 | 升级不会盖掉人的活儿（要强升用 `--force`） |
| 检测到 `state/locks/tick.lock`（有拍在飞） | **拒绝升级**，本跑用当前版本完成 | **绝不在运行中替换代码** |
| 本地与远端分叉（领先又落后） | **拒绝合并**并报错 | 不硬合、不埋掉本地提交 |
| 升级后自检（`selftest`＋`scan`）不过 | **回滚到升级前的提交**，退出码 3 | 宁可跑旧版，也不跑一个自检不过的新版 |

四处都过了，它才 `git pull --ff-only` → 重装 → 自检 → 起跑。换句话说：
**只要你是通过运行入口起来的，跑着的就是最新版；升不动的每一种情况都会当场说出来，不会静默用旧版。**

## 判据也可以单独查

```bash
infinigrow version --check      # 本地版 vs 最新发布；落后 → 退出码 3
```

只读 GitHub 公开的 releases 接口，**零凭据**、零写入。离线或查不到时明确报 `unknown`（rc 0），
**绝不把「不知道」说成「已是最新」**——不知道就说不知道。

## 为什么不是「后台静默自动升级」

不是不做自动化，而是**把自动化的位置放对**：升级只发生在**起跑之前**这个安全点上，
并且带着自检闸与回滚。理由只有一条——
**运行中替换代码**会让「出问题时说不清是哪一版在跑」；
而起跑前升级，任何时刻跑着的都是一个**自检全绿**的确定版本。

如果你要让它长期无人值守地一直是最新，把运行入口交给调度器即可：

```bash
# 每次起拍都先过版本闸（Windows 计划任务 / cron 都适用）
python tools/run_latest.py
```

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
