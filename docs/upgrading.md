# 升级规则：运行的引擎永远是当前最新版

## 规则本身

**任何在跑的 Infinigrow 都应是当前最新发布版。** 这条不需要靠记忆维持——有两个机械件：

```bash
infinigrow version --check      # 判据：本地版 vs 最新发布。落后 → 退出码 3
python tools/update_local.py    # 动作：一条命令升级 + 当场自检
```

- `--check` 只读 GitHub 公开的 releases 接口，**零凭据**、零写入；
  离线或查不到时明确报 `unknown`（退出码 0），**绝不把「不知道」说成「已是最新」**。
- `update_local.py` 是唯一被推荐的升级入口，它做三件事：
  `git fetch --tags` → 落后则 `git pull --ff-only` → `pip install -e .` → 跑自检与规则扫描。
  它在**落后时才动**，本地有未推送提交时**拒绝合并**，升级后自检不过会以退出码 3 报出来。

## 为什么不做成后台自动升级

**运行中的代码被静默替换**是另一种危险：跑着跑着换了灵魂，出了问题说不清是哪一版在跑。
所以这里的形态是「**判据随时可查 + 动作便宜到顺手就做**」，而不是「悄悄替你换掉」。
升级动作一次三秒，做之前你还能看一眼差了多少个提交。

## 手动升级（等价于脚本做的事）

```bash
cd <你的 Infinigrow 目录>
git fetch --tags
git log --oneline HEAD..origin/main      # 先看看差了什么
git pull --ff-only                       # 非快进会失败——说明本地有改动，先自己处理
python -m pip install -e .               # 只更新元数据与入口点
python -m infinigrow selftest            # 自检：规则正/反用例
python -m infinigrow scan                # 静态规则扫描
python -m infinigrow version --check     # 确认已是最新
```

## 版本号怎么看

- 版本单一事实源是 `src/infinigrow/__init__.py` 的 `__version__` 与 `pyproject.toml` 的 `version`；
  两者不一致会被 `tests/test_version.py` 拦下。
- 语义含义与 v1/v2 的断代关系见 [`versioning.md`](versioning.md)。
- 每个版本改了什么、已知限制是什么，见仓库根 [`CHANGELOG.md`](../CHANGELOG.md)；Release 正文另有清单。

## 如果你把 Infinigrow 跑在定时任务里

推荐形态：**先查版本、再跑拍**。落后就升级，不要带着旧版跑。

```bash
infinigrow version --check || python tools/update_local.py
```

（`||` 的含义：`--check` 落后时返回 3 → 触发升级。若你希望停机而不是就地升级，
把右边换成告警语句即可——判据和动作是分开的，用法由你定。）
