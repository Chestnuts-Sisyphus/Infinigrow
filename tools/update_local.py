#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""update_local —— 把**本地运行副本**升到最新发布，并当场自检（定规：运行的引擎永远最新版）。

它只做三件事，全部是「对已有仓库/已装包」的操作，**不写任何源码内容**：

    1. `git fetch --tags` ＋ 比对本地 HEAD 与 `origin/<默认分支>`；
    2. 落后就 `git pull --ff-only`（**快进合并**：本地有自己提交时直接失败而不是乱合）；
       然后用 pip 重装本包（`-e .`，只更新元数据与入口点）；
    3. 跑自检（`selftest` ＋ 静态规则扫描），**绿了才算升好**。

为什么要一条命令而不是让人记三步：定规要能落地，就得便宜到「顺手就做了」。
为什么默认不自动升级：**运行中的代码被静默替换**是另一种危险（跑着跑着换了灵魂，
出了问题不知道是哪版）。所以这里给的是「一句话升级＋当场验证」，而不是后台自动更新。

用法：
    python tools/update_local.py            # 检查并升级（落后才动）
    python tools/update_local.py --check    # 只看差多少，什么都不改
    python tools/update_local.py --repo <路径>
退出码：0=已是最新或升级成功；3=升级后自检未过（需人看）；4=git/pip 操作失败。
"""
import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))


def run(cmd, cwd=None, timeout=600):
    """执行一条命令，返回 (rc, 合并输出)。不抛异常——失败由调用方判定并报出来。"""
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "执行失败：%r" % exc


def git(repo: Path, *args):
    return run(["git", *args], cwd=repo)


def main(argv=None):
    ap = argparse.ArgumentParser(description="把本地运行副本升到最新版并自检")
    ap.add_argument("--repo", default=str(REPO_ROOT))
    ap.add_argument("--check", action="store_true", help="只报告差异，不改任何东西")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    if not (repo / ".git").is_dir():
        print("FAIL：%s 不是 git 仓库（升级需要 git 历史）" % repo)
        return 4

    rc, branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        print("FAIL：读不出当前分支\n%s" % branch)
        return 4
    branch = branch.strip()

    rc, _ = git(repo, "fetch", "--tags", "--quiet")
    if rc != 0:
        print("FAIL：git fetch 失败（网络或权限）")
        return 4

    rc, counts = git(repo, "rev-list", "--left-right", "--count",
                     "%s...origin/%s" % (branch, branch))
    if rc != 0:
        print("FAIL：无法与远端比较（origin/%s 不存在？）" % branch)
        return 4
    ahead, behind = (int(x) for x in counts.split())
    print("本地 %s：领先 %d 提交 / 落后 %d 提交" % (branch, ahead, behind))

    if behind == 0:
        print("已是最新（无需升级）。")
        return 0
    if args.check:
        print("落后 %d 个提交——去掉 --check 即执行升级。" % behind)
        return 0
    if ahead:
        print("本地有 %d 个未推送提交：**拒绝自动合并**（请先处理自己的提交，别让升级把它埋掉）" % ahead)
        return 4

    rc, out = git(repo, "pull", "--ff-only", "--quiet")
    if rc != 0:
        print("FAIL：git pull --ff-only 失败（非快进，需人处理）\n%s" % out)
        return 4
    print("已快进到最新提交：%s" % git(repo, "log", "--oneline", "-1")[1].strip())

    rc, out = run([sys.executable, "-m", "pip", "install", "-q", "-e", ".", "--no-deps"],
                  cwd=repo)
    if rc != 0:
        print("WARN：pip 重装失败（继续自检；若入口点异常需人手修）\n%s" % out[-400:])

    print("\n=== 升级后自检 ===")
    ok = True
    for label, cmd in (("自检（规则正反用例）", [sys.executable, "-m", "infinigrow", "selftest"]),
                       ("静态规则扫描", [sys.executable, "-m", "infinigrow", "scan"])):
        rc, out = run(cmd, cwd=repo, timeout=300)
        tail = "\n".join(out.strip().splitlines()[-3:])
        print("%s：rc=%d\n%s" % (label, rc, tail))
        ok = ok and rc == 0
    if not ok:
        print("\nFAIL：升级后自检未过——需人看（不要带着红的状态跑引擎）")
        return 3
    print("\nOK：本地已是最新版，且自检全绿。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
