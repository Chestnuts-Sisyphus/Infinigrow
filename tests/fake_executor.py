# -*- coding: utf-8 -*-
"""假执行者（测试用）：四种返回形态，一次覆盖 T2 的验收四况。

    python tests/fake_executor.py --mode ok        # rc=0，有输出（含一行用量）
    python tests/fake_executor.py --mode fail      # rc=2，有输出（stderr 也走同路）
    python tests/fake_executor.py --mode empty     # rc=0，**空输出**
    python tests/fake_executor.py --mode timeout   # 睡够久，让调用方超时杀掉

它总是先把 stdin（提示词）读干——不读的话父进程写管道会在长提示词上被卡住，
那会造出「测试看起来在测超时、其实在测管道」的假象。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def _harden_stdio() -> None:
    """stdout/stderr 切 UTF-8：Windows 控制台默认不是 UTF-8（CI runner 是 cp1252，
    有的机器是 GBK），直接打印中文会 UnicodeEncodeError，让整段调用 rc!=0。
    逻辑只有一份：引擎的 `core/encoding.harden_stdio`（这里延迟导入）。
    """
    src = str(Path(__file__).resolve().parents[1] / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        from infinigrow.core.encoding import harden_stdio as _h
    except ImportError:                      # 没装包也没关系：自己切一下流
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass
        return
    _h()


def main(argv=None) -> int:
    _harden_stdio()
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="ok",
                    choices=("ok", "fail", "empty", "timeout", "echo", "flaky"))
    ap.add_argument("--sleep", type=float, default=30.0)
    ap.add_argument("--count-file", default="")
    args = ap.parse_args(argv)

    prompt = sys.stdin.read()          # 必须读干：否则父进程可能卡在管道上

    if args.mode == "ok":
        print("假执行者：收到 %d 字节提示词" % len(prompt))
        print('IG_USAGE {"input_tokens": 11, "output_tokens": 22, "cost_usd": 0.001}')
        return 0
    if args.mode == "echo":
        print(prompt)
        return 0
    if args.mode == "fail":
        print("假执行者：失败路径（stderr）", file=sys.stderr)
        return 2
    if args.mode == "flaky":
        # K5/A9：首次调用模拟「传输层截断」（IncompleteRead 签名），第二次成功。
        # 用计数文件跨进程记次数（子进程之间不共享内存）。
        count = 0
        if args.count_file:
            cf = Path(args.count_file)
            try:
                count = int(cf.read_text(encoding="utf-8").strip() or "0")
            except (OSError, ValueError):
                count = 0
            cf.write_text(str(count + 1), encoding="utf-8")
        if count == 0:
            print("EXECUTOR-ERROR: IncompleteRead(3132 bytes read, 3803 more expected)",
                  file=sys.stderr)
            return 1
        print("假执行者：第 %d 次调用成功（截断后重试）" % (count + 1))
        print('IG_USAGE {"input_tokens": 11, "output_tokens": 22, "cost_usd": 0.001}')
        return 0
    if args.mode == "empty":
        return 0
    time.sleep(args.sleep)             # timeout：等调用方来杀
    print("假执行者：超时模式本不该跑到这里")
    return 0


if __name__ == "__main__":
    sys.exit(main())
