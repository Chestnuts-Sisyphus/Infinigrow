#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""update_local —— **兼容壳**：真正的实现在 `tools/run_latest.py --update`。

T10 的归并结论：同一件事（把本地运行副本升到最新发布并当场自检）只能有一份实现。
两份实现＝两份判据，迟早出现「一个拒绝非快进、另一个不拒绝」「一个回滚、另一个不回滚」。
所以本文件不再包含任何升级逻辑，只做两件事：

    1. 打印一句「已归并」的说明（让老命令的使用者知道去哪看）；
    2. 把参数**按白名单**转给 `run_latest.main`：
         --check   → run_latest --update --check
         --repo X  → run_latest --update --repo X（X 必须是已存在目录）
         默认       → run_latest --update

两处刻意的选择：

- **不用子进程转发**：直接 import 并调用 `run_latest.main`。少一层进程＝少一层
  「外部输入被交给子进程」的注入面，也不会出现「两个解释器/两套环境」的怪事。
- **参数按白名单**：只放行两个明确开关，其余一律拒绝并提示直接调 run_latest.py。

为什么保留这个文件而不是删掉：删除是不可逆动作（本项目硬约束是「只增改不删」），
而且旧命令可能已经写进计划任务或别人的笔记里——保留一个**会自己说清楚**的转发壳，
比一个突然报「文件不存在」的缺口友好得多。

退出码与 `run_latest.py --update` 一致：
    0 已是最新或升级成功｜3 升级后自检未过（已回滚）｜4 git/pip 层面失败。
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS = REPO_ROOT / "tools"

#: 允许转发的开关（白名单：多余的一律拒绝，不猜使用者想干什么）
ALLOWED_FLAGS = ("--check", "--help", "-h")
PATH_FLAG = "--repo"


def _help() -> int:
    print("update_local（兼容壳）——真正的实现：python tools/run_latest.py --update")
    print("用法：python tools/update_local.py [--check] [--repo <目录>]")
    print("      --check   只看差多少，什么都不改")
    print("      --repo X  指定本地副本（X 必须是已存在目录）")
    return 0


def forward_args(argv):
    """把外部参数压成白名单内的 argv 片段；越界返回 None（＝参数不合格）。"""
    out = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token in ("--help", "-h"):
            out.append("__HELP__")           # 本壳自己的帮助：不转发给 run_latest
        elif token in ALLOWED_FLAGS:
            out.append(token)
        elif token == PATH_FLAG:
            value = argv[i + 1] if i + 1 < len(argv) else ""
            candidate = Path(value)
            if not value or not candidate.is_dir():
                print("FAIL：%s 需要一个**已存在的目录**（收到 %r）" % (PATH_FLAG, value))
                return None
            out += [PATH_FLAG, str(candidate.resolve())]
            i += 1
        else:
            print("FAIL：本壳只转发 %s 与 %s（其余请直接调 tools/run_latest.py）：%r"
                  % ("、".join(ALLOWED_FLAGS), PATH_FLAG, token))
            return None
        i += 1
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    import run_latest                     # 延迟导入：只在真要用的时候加载
    run_latest.harden_stdio()             # **先切流**：本壳自己也要打印中文
    if any(tok in ("--help", "-h") for tok in argv):
        return _help()
    print("说明：本命令已归并进 tools/run_latest.py（实现在那一份，避免两套判据）。")
    forwarded = forward_args(argv)
    if forwarded is None:
        return 4
    if not (TOOLS / "run_latest.py").is_file():
        print("FAIL：找不到 tools/run_latest.py —— 本壳无法转发。")
        return 4
    print("      等价命令：python tools/run_latest.py --update %s"
          % " ".join(forwarded).strip())
    return run_latest.main(["--update", *forwarded])


if __name__ == "__main__":
    sys.exit(main())
