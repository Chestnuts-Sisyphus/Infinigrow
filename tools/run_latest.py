#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_latest —— 运行入口：**默认用最新版引擎；升不动就按现有版本跑**。

定规（2026-09-14 确立）：
> Infinigrow 是**引擎**本身；要保证的是**引擎**用最新版。
> 「它生长的主体」（状态、账本、被生长的对象）是另一回事，不在此列。

语义（三段，缺一不可）：

1. **有条件升级**（落后 ＋ 工作区干净 ＋ 无拍在飞 ＋ 历史不分叉 ＋ 升级后自检通过）
   → **升级，然后用新版起跑**。这是默认行为：对使用者来说，默认就是新版。
2. **没条件升级**（工作区有改动／有拍在飞／历史分叉／离线／pull 失败／自检不过并已回滚）
   → **按现有版本照常起跑**，并说清「为什么这次不是最新版」。
   **绝不因为「不是最新版」就把引擎停掉**——旧版能跑就让它跑，这才是可用的定规。
3. 想要更严的人（CI、发布验证）可以加 `--require-latest`：升不了就不跑。

**升级只动引擎代码**：`state/`（生长主体：账本、队列、报告）是 git 忽略项，
`pull`/`reset` 不会碰它。引擎换代，主体留痕不受影响。

用法：
    python tools/run_latest.py                 # 默认：能升就升到最新，然后跑一拍
    python tools/run_latest.py -- --probe      # 「--」之后透传给 `infinigrow tick`
    python tools/run_latest.py --check         # 只报告版本状态，不起跑
    python tools/run_latest.py --no-update     # 不尝试升级，直接用当前版本跑
    python tools/run_latest.py --require-latest  # 严格模式：升不到最新就不跑
退出码：0=正常起跑（含「按旧版跑」）；3=升级后自检未过（已回滚，但仍按旧版起跑）；
       4=严格模式下未能拿到最新版，或环境不满足。
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
                  offline: bool = False, require_latest: bool = False,
                  can_update: bool = True) -> str:
    """起跑决策（纯函数，可单测）。

    返回：`start`（已最新，直接跑）｜`update_then_start`（有条件升级，升了再跑）
    ｜`start_stale`（升不动，**按现有版本照常跑**）｜`start_unverified`（离线，未验证照跑）
    ｜`refuse_stale`（仅严格模式 `--require-latest` 下：拿不到最新版就不跑）
    """
    if offline:
        return "start_unverified"
    if not behind:
        return "start"
    # 落后：能不能升级？＝工作区干净、没拍在飞、历史不分叉、且允许升级
    blocked_reason = dirty or running or bool(ahead) or not can_update
    if not blocked_reason:
        return "update_then_start"
    return "refuse_stale" if require_latest else "start_stale"


def stale_reason(*, ahead: int, dirty: bool, running: bool,
                 can_update: bool = True) -> str:
    """说清「为什么这次不是最新版」——不解释就等于静默用旧版。"""
    if not can_update:
        return "指定了 --no-update"
    if running:
        return "有拍在飞（不在运行中替换引擎代码）"
    if dirty:
        return "工作区有未提交改动（升级不会盖掉你的改动）"
    if ahead:
        return "历史分叉（本地领先又落后，不硬合）"
    return "未知原因"


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
    ap = argparse.ArgumentParser(description="默认用最新版引擎；升不动就按现有版本跑")
    ap.add_argument("--check", action="store_true", help="只报告版本状态，不起跑")
    ap.add_argument("--no-update", action="store_true", help="不尝试升级，直接用当前版本跑")
    ap.add_argument("--require-latest", action="store_true",
                    help="严格模式：拿不到最新版就不跑（CI/发布验证用）")
    ap.add_argument("--repo", default=str(REPO_ROOT))
    ap.add_argument("payload", nargs="*", help="透传给 `infinigrow tick` 的参数")
    args = ap.parse_args(argv)

    repo = Path(args.repo).resolve()
    if not (repo / ".git").is_dir():
        print("FAIL：%s 不是 git 仓库——本入口需要 git 历史来判定版本" % repo)
        return 4

    print("引擎：%s（%s）" % (engine_label(repo), repo))

    if args.no_update:
        print("按当前版本起跑（--no-update：本次不尝试升级）")
        return _run_payload(repo, args.payload)

    rc, out = git("fetch", "--tags", "--quiet")
    offline = rc != 0
    if offline:
        print("WARN：git fetch 失败（离线？）——无法判定是否最新，按当前版本起跑")

    ahead = behind = 0
    dirty = False
    if not offline:
        try:
            ahead, behind, dirty = status_counts()
        except (RuntimeError, ValueError) as exc:
            print("WARN：%s —— 无法判定是否最新，按当前版本起跑" % exc)
            offline = True

    running = (repo / LOCK_REL).exists()
    verdict = start_verdict(behind=behind, ahead=ahead, dirty=dirty, running=running,
                            offline=offline, require_latest=args.require_latest,
                            can_update=not args.no_update)
    print("版本状态：领先 %d／落后 %d／工作区%s／有拍在飞=%s → %s"
          % (ahead, behind, "脏" if dirty else "干净", running, verdict))

    if args.check:
        return 0 if verdict != "refuse_stale" else 4

    if verdict == "refuse_stale":
        print("严格模式（--require-latest）：引擎落后 %d 个提交且无法升级（%s）→ 不跑。"
              % (behind, stale_reason(ahead=ahead, dirty=dirty, running=running,
                                      can_update=not args.no_update)))
        return 4

    if verdict == "update_then_start":
        rc, before = git("rev-parse", "HEAD")
        before = before.strip()
        rc, out = git("pull", "--ff-only", "--quiet")
        if rc != 0:
            print("WARN：git pull --ff-only 失败（非快进）→ **按现有版本起跑**\n%s"
                  % out.strip()[:300])
            return _run_payload(repo, args.payload)
        sh([sys.executable, "-m", "pip", "install", "-q", "-e", ".", "--no-deps"])
        print("已升到：%s" % git("log", "--oneline", "-1")[1].strip())
        print("引擎：%s" % engine_label(repo))
        print("升级后自检：")
        gate = selftest_ok(repo)
        if gate == "env_error":
            print("WARN：新版跑不起来（包解析不到）——**不回滚**（回滚解决不了环境问题），"
                  "按现有版本起跑")
            return _run_payload(repo, args.payload)
        if gate == "fail":
            print("自检未过 → **回滚**到 %s，按回滚后的版本起跑"
                  "（宁可跑旧版，也不跑自检不过的新版）" % before[:8])
            git("reset", "--hard", before)
            return _run_payload(repo, args.payload)
        print("自检全绿，用最新版起跑。")

    elif verdict == "start_stale":
        print("引擎不是最新版（%s）→ **按现有版本照常起跑**。"
              % stale_reason(ahead=ahead, dirty=dirty, running=running,
                             can_update=not args.no_update))
    elif verdict == "start_unverified":
        print("按当前版本起跑（未经验证：无法确认是否最新）")
    elif dirty:
        print("（提示：本地在最新提交之上有未提交改动——严格说这已不是发布版）")

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
