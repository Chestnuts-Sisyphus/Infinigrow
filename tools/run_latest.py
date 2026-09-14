#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_latest —— 运行入口：**引擎必须是最新版，才准运转**。

定规（2026-09-14 确立，反复强调后加强）：
> Infinigrow 是**引擎**本身；要保证的是**引擎**是最新版。
> 「它生长的主体」（状态、账本、被生长的对象）是另一回事，不在此列。

所以这个入口只对**引擎代码**负责，并且是**硬保证**而不是提示：

| 情形 | 行为 | 说明 |
|---|---|---|
| 已是最新 | 直接起跑 | 正常路径 |
| 落后、且升级条件齐备 | `pull --ff-only` → 重装 → **自检闸** → 用新版起跑 | 升级只发生在起跑前这个安全点 |
| 落后、但工作区有未提交改动 / 历史分叉 | **拒绝起跑**（rc=4） | 我们**知道**它不是最新版 —— 那就别跑。要强跑用 `--allow-stale` |
| 检测到 `state/locks/tick.lock`（有拍在飞） | **拒绝起跑**（rc=4） | 不并发、也不在运行中替换代码 |
| 升级后自检不过 | **回滚**到升级前提交，拒绝起跑（rc=3） | 宁可跑旧版，也不跑自检不过的新版 |
| 离线 / 无法判定 | **起跑**，但大声说明「本次未经验证」（rc=0） | 不知道 ≠ 落后；不能因为断网就让引擎停摆 |

**两件事分清楚**：升级只动 git 跟踪的引擎代码；`state/`（生长主体：账本、队列、报告）
是 git 忽略的，`pull`/`reset` **不会碰它**。引擎换代，主体留痕不受影响。

用法：
    python tools/run_latest.py                 # 确保最新 → 跑一拍
    python tools/run_latest.py -- --probe      # 「--」之后透传给 `infinigrow tick`
    python tools/run_latest.py --check         # 只报告版本状态，不起跑
    python tools/run_latest.py --no-update     # 跳过版本闸（不推荐）
    python tools/run_latest.py --allow-stale   # 已知是旧版仍要跑（显式例外）
退出码：0=正常；3=升级后自检未过（已回滚）；4=引擎不是最新版/环境不满足，**拒绝起跑**。
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

LOCK_REL = Path("state") / "locks" / "tick.lock"


def start_verdict(*, behind: int, ahead: int, dirty: bool, running: bool,
                  offline: bool = False, allow_stale: bool = False) -> str:
    """是否准予起跑（纯函数，可单测）。

    返回：`start`｜`start_unverified`｜`update_then_start`｜`refuse_stale`
    """
    if offline:
        return "start_unverified"        # 不知道 → 跑，但标明未经验证
    if running:
        return "refuse_stale"            # 有拍在飞：不并发，也不动代码
    if not behind:
        return "start"                   # 已是最新：即便有本地改动，它也不是「旧」
    if dirty or ahead:
        return "start" if allow_stale else "refuse_stale"
    return "update_then_start"


def child_env(repo: Path):
    """子进程环境：把 `<repo>/src` 加进 PYTHONPATH。

    为什么必须有：本仓库是 `src/` 布局，`python -m infinigrow` 只有在该包**被安装**
    或 `PYTHONPATH` 指到 `src/` 时才能解析。运行入口不能假设「使用者一定装过」——
    真机首跑就是在未安装状态下直接 `No module named infinigrow`。
    """
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
    return ahead, behind, bool(out.strip())


def selftest_ok(repo: Path):
    """升级后的验收闸：自检 ＋ 规则扫描。返回 `ok`｜`fail`｜`env_error`。

    **必须区分「自检不过」与「根本跑不起来」**：前者回滚（新版有问题），
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


def engine_label(repo: Path) -> str:
    """当前引擎身份（版本＋提交），走版本模块而不是自己拼。"""
    env = child_env(repo)
    rc, out = sh([sys.executable, "-c",
                  "from infinigrow.core.build_info import engine_label;"
                  "print(engine_label())"], cwd=repo, env=env, timeout=120)
    return out.strip() if rc == 0 else "（未知）"


def main(argv=None):
    ap = argparse.ArgumentParser(description="引擎必须是最新版才准运转")
    ap.add_argument("--check", action="store_true", help="只报告版本状态，不起跑")
    ap.add_argument("--no-update", action="store_true", help="跳过版本闸（不推荐）")
    ap.add_argument("--allow-stale", action="store_true",
                    help="已知是旧版仍要起跑（显式例外，会在输出里标明）")
    ap.add_argument("--repo", default=str(REPO_ROOT))
    ap.add_argument("payload", nargs="*", help="透传给 `infinigrow tick` 的参数")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    if not (repo / ".git").is_dir():
        print("FAIL：%s 不是 git 仓库——本入口需要 git 历史来判定版本" % repo)
        return 4

    print("引擎：%s（%s）" % (engine_label(repo), repo))

    if args.no_update:
        print("WARN：--no-update ——本次**未**验证引擎是否为最新版")
        return _run_payload(repo, args.payload)

    rc, out = git("fetch", "--tags", "--quiet")
    offline = rc != 0
    if offline:
        print("WARN：git fetch 失败（离线？）——无法判定是否最新，本次起跑**未经验证**")

    ahead = behind = 0
    dirty = False
    if not offline:
        try:
            ahead, behind, dirty = status_counts()
        except (RuntimeError, ValueError) as exc:
            print("FAIL：%s" % exc)
            return 4

    running = (repo / LOCK_REL).exists()
    verdict = start_verdict(behind=behind, ahead=ahead, dirty=dirty, running=running,
                            offline=offline, allow_stale=args.allow_stale)
    print("版本闸：领先 %d／落后 %d／工作区%s／有拍在飞=%s → %s"
          % (ahead, behind, "脏" if dirty else "干净", running, verdict))

    if args.check:
        return 0 if verdict in ("start", "start_unverified", "update_then_start") else 4

    if verdict == "refuse_stale":
        if running:
            print("拒绝起跑：检测到 %s（有拍在飞）。不并发、也不在运行中替换代码。" % LOCK_REL)
        else:
            print("拒绝起跑：**引擎已知不是最新版**（落后 %d 个提交%s）。"
                  % (behind, "，且工作区有未提交改动" if dirty else "，且历史分叉" if ahead else ""))
            print("处置：处理好本地改动（提交/暂存）后重跑；确要用旧版跑一拍，加 --allow-stale。")
        return 4

    if verdict == "update_then_start":
        rc, before = git("rev-parse", "HEAD")
        before = before.strip()
        rc, out = git("pull", "--ff-only", "--quiet")
        if rc != 0:
            print("FAIL：git pull --ff-only 失败（非快进）→ 引擎仍不是最新版，拒绝起跑\n%s"
                  % out.strip()[:300])
            return 4
        sh([sys.executable, "-m", "pip", "install", "-q", "-e", ".", "--no-deps"])
        print("已升到：%s" % git("log", "--oneline", "-1")[1].strip())
        print("引擎：%s" % engine_label(repo))
        print("升级后自检：")
        gate = selftest_ok(repo)
        if gate == "env_error":
            print("环境错误：新版跑不起来（包解析不到）——**不回滚**（回滚解决不了环境问题），"
                  "退出码 4。")
            return 4
        if gate == "fail":
            print("自检未过 → **回滚**到 %s，拒绝起跑（宁可跑旧版，也不跑自检不过的新版）"
                  % before[:8])
            git("reset", "--hard", before)
            return 3
        print("自检全绿，用新版起跑。")

    elif verdict == "start_unverified":
        print("起跑（未经验证：无法确认是否最新版）")
    elif dirty:
        print("WARN：本地在最新提交之上有未提交改动——严格说这已不是发布版")

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
