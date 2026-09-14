#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_latest —— **运行入口**：确保本地是最新发布，然后才起跑（定规：运转的永远是最新版）。

为什么要有它：上一版给的是「一条升级命令」，那还是要人记得跑。定规要成为**结构**，
就得让「运行」这个动作本身先经过「确保最新」这一步——想跑就跑，跑起来的一定是最新版。

它保证的四件事：

1. **安全点升级**：只在**起跑前**动代码。若检测到锁（`state/locks/tick.lock`）＝有拍在飞，
   **拒绝升级**（绝不替换正在运行的代码），让这一跑用当前版本完成，下一次再升。
2. **工作区不干净就不动**：本地有未提交改动时拒绝自动升级（不是你的活被埋掉，
   而是升级不会悄悄盖掉你的东西）；确实要强升用 `--force`。
3. **升级后必须自检**：`selftest` ＋ `scan` 任一不过 → **回滚到升级前的提交**并报错退出
   （宁可跑旧版，也不跑一个自检不过的新版）。
4. **分叉拒绝合并**：本地领先又落后（分叉）时不硬合，报出来让人处理。

用法：
    python tools/run_latest.py                 # 确保最新 → 跑一拍
    python tools/run_latest.py -- --probe      # 「--」之后的参数透传给 infinigrow tick
    python tools/run_latest.py --check         # 只看差多少，不起跑
    python tools/run_latest.py --no-update     # 只起跑，不做升级检查
    python tools/run_latest.py --force         # 允许在工作区不干净/有锁时升级（慎用）
退出码：0=正常；3=升级后自检未过（已回滚）；4=环境/前置条件不满足。
"""
import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

LOCK_REL = Path("state") / "locks" / "tick.lock"


def decide(*, behind: int, ahead: int, dirty: bool, running: bool,
           allow_force: bool = False) -> str:
    """升级决策（纯函数，可单测）。

    返回：`run_only`（已最新，直接跑）｜`update_then_run`（落后，升级再跑）
    ｜`refuse_dirty`｜`refuse_diverged`｜`refuse_running`
    """
    if dirty and not allow_force:
        return "refuse_dirty"
    if running and not allow_force:
        return "refuse_running"
    if behind and ahead and not allow_force:
        return "refuse_diverged"
    if behind:
        return "update_then_run"
    return "run_only"


def child_env(repo: Path):
    """子进程环境：把 `<repo>/src` 加进 PYTHONPATH。

    为什么必须有这一步：本仓库是 `src/` 布局，`python -m infinigrow` 只有在该包**被安装**
    或 `PYTHONPATH` 指到 `src/` 时才能解析。运行入口不能假设「使用者一定装过」——
    真机首跑就是在未安装状态下直接 `No module named infinigrow`（这个 bug 是跑出来的，
    不是想出来的）。
    """
    import os
    env = dict(os.environ)
    src = str(repo / "src")
    old = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src if not old else (src + os.pathsep + old)
    return env


def sh(cmd, cwd=REPO_ROOT, timeout=900, env=None):
    """跑一条命令，返回 (rc, 输出)。不抛异常——失败由调用方判定并说明。"""
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, env=env)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "执行失败：%r" % exc


def git(*args):
    return sh(["git", *args])


def status_counts():
    """返回 (ahead, behind, dirty)。读不出来时抛 RuntimeError（不猜）。"""
    rc, out = git("rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        raise RuntimeError("读不出当前分支：%s" % out.strip())
    branch = out.strip()
    rc, out = git("rev-list", "--left-right", "--count",
                  "%s...origin/%s" % (branch, branch))
    if rc != 0:
        raise RuntimeError("无法与远端比较（origin/%s 存在吗）：%s" % (branch, out.strip()))
    ahead, behind = (int(x) for x in out.split())
    rc, out = git("status", "--porcelain")
    dirty = bool(out.strip())
    return ahead, behind, dirty


def selftest_ok(repo: Path):
    """升级后的验收闸：自检 ＋ 规则扫描。返回 `ok`｜`fail`｜`env_error`。

    **必须区分「自检不过」与「根本跑不起来」**：前者要回滚（新版有问题），
    后者是环境问题（比如包没装上）——把它当失败会**误回滚一个本来正常的升级**。
    """
    env = child_env(repo)
    verdict = "ok"
    for label, args in (("selftest", ["infinigrow", "selftest"]),
                        ("scan", ["infinigrow", "scan"])):
        rc, out = sh([sys.executable, "-m", *args], cwd=repo, env=env)
        tail = "\n".join(out.strip().splitlines()[-2:])
        print("  %s：rc=%d %s" % (label, rc, tail))
        if rc == 0:
            continue
        if "No module named" in out or "ModuleNotFoundError" in out:
            return "env_error"
        verdict = "fail"
    return verdict


def main(argv=None):
    ap = argparse.ArgumentParser(description="确保最新版再起跑")
    ap.add_argument("--check", action="store_true", help="只报告差多少，不起跑")
    ap.add_argument("--no-update", action="store_true", help="跳过升级检查，直接起跑")
    ap.add_argument("--force", action="store_true", help="允许在不干净/有锁时升级（慎用）")
    ap.add_argument("--repo", default=str(REPO_ROOT))
    ap.add_argument("payload", nargs="*", help="透传给 `infinigrow tick` 的参数")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    if not (repo / ".git").is_dir():
        print("FAIL：%s 不是 git 仓库——本入口需要 git 历史来判定版本" % repo)
        return 4

    if args.no_update:
        return _run_payload(repo, args.payload)

    rc, out = git("fetch", "--tags", "--quiet")
    if rc != 0:
        print("WARN：git fetch 失败（离线？）——**不升级**，用当前版本起跑\n%s" % out.strip()[:200])
        return _run_payload(repo, args.payload)

    try:
        ahead, behind, dirty = status_counts()
    except (RuntimeError, ValueError) as exc:
        print("FAIL：%s" % exc)
        return 4

    running = (repo / LOCK_REL).exists()
    action = decide(behind=behind, ahead=ahead, dirty=dirty, running=running,
                    allow_force=args.force)
    print("版本检查：领先 %d／落后 %d／工作区%s／有拍在飞=%s → 决策=%s"
          % (ahead, behind, "脏" if dirty else "干净", running, action))

    if args.check:
        return 0 if action in ("run_only", "update_then_run") else 4

    if action == "refuse_dirty":
        print("拒绝升级：工作区有未提交改动（升级不会盖掉你的活儿）。"
              "先提交/暂存，或用 --force 明确要强升。")
        return 4
    if action == "refuse_running":
        print("拒绝升级：检测到 %s（有拍在飞）。**绝不在运行中替换代码**；"
              "这一跑用当前版本完成，下次起跑再升。" % LOCK_REL)
        return _run_payload(repo, args.payload)
    if action == "refuse_diverged":
        print("拒绝升级：本地与远端分叉（领先 %d 落后 %d），不硬合——请先处理本地提交。" % (ahead, behind))
        return 4

    if action == "update_then_run":
        rc, before = git("rev-parse", "HEAD")
        before = before.strip()
        rc, out = git("pull", "--ff-only", "--quiet")
        if rc != 0:
            print("FAIL：git pull --ff-only 失败（非快进）\n%s" % out.strip()[:300])
            return 4
        sh([sys.executable, "-m", "pip", "install", "-q", "-e", ".", "--no-deps"])
        print("已升到：%s" % git("log", "--oneline", "-1")[1].strip())
        print("升级后自检：")
        verdict = selftest_ok(repo)
        if verdict == "env_error":
            print("环境错误：新版跑不起来（包解析不到）——**不回滚**（回滚也解决不了环境问题），"
                  "请修好环境后重跑；退出码 4。")
            return 4
        if verdict == "fail":
            print("自检未过 → **回滚**到 %s（宁可跑旧版，也不跑自检不过的新版）" % before[:8])
            git("reset", "--hard", before)
            return 3
        print("自检全绿，用新版起跑。")

    return _run_payload(repo, args.payload)


def _run_payload(repo: Path, payload):
    """起跑：默认跑一拍；`--` 之后给的参数原样透传。"""
    cmd = [sys.executable, "-m", "infinigrow", "tick", *payload]
    print("起跑：%s" % " ".join(cmd[1:]))
    rc, out = sh(cmd, cwd=repo, timeout=3600, env=child_env(repo))
    print(out.rstrip())
    return rc


if __name__ == "__main__":
    sys.exit(main())
