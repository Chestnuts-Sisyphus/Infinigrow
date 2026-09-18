#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""进程外日志轮转器：`logs/tick.log` 超字节阈值 → 脱敏归档＋清空主件。

为什么轮转职责在这里（v2.2.25，取代园丁内轮转）：
调度器（`tools/run_tick.bat`）以**追加句柄**持有 `logs/tick.log` 贯穿整个 tick 进程；
Windows 下该句柄既不共享删除也不共享写入，引擎在**进程内**永远不可能删除/原地截断它
（v2.2.24 的 busy 容错实测 `PermissionError`，每次都把 `rc=1` 与带本机路径的 traceback
写进日志）。真正的窗口是**两拍之间的句柄空隙**：本脚本由 `run_tick.bat` 在打开任何
句柄**之前**调用，此时上拍进程已退出，归档＋清空走的是干净的 `move_file` 语义。

归档前**脱敏**（判据与 `tools/check_no_abs_paths.py` 同源）：运行日志是引擎排障面，
但归档件是**可迁移产物**，不得携带本机路径（M8 先例：历史日志路径抹除）。
主件保留（清空）供本拍追加；追加内容由引擎「本机路径已省略」纪律保证不携带路径。

用法（由启动器调用，参 1＝状态根，缺省 `<仓库>/state`）：
    python tools/rotate_journal.py [state_root]
"""
from __future__ import annotations

import datetime as _dt
import re
import sys
from pathlib import Path

#: 与 tools/check_no_abs_paths.py 同源的命中形态（盘符路径 / 家目录与挂载点前缀）。
#: 刻意不写出完整形态（写了就成了新的命中源）；只认这几类，判据宁窄而准。
ABS_PATH_RX = re.compile(r"(?<![\w/])(?:[A-Za-z]:[\\/]|/(?:home|Users|mnt|opt)/)[^\s\"'，)；)]*")

LOG_NAME = "tick.log"
DEFAULT_MAX_BYTES = 1048576


def _redact(text: str) -> tuple[str, int]:
    hits = ABS_PATH_RX.findall(text)
    return ABS_PATH_RX.sub("<redacted>", text), len(hits)


def rotate_journal(state_root: str, max_bytes: int = DEFAULT_MAX_BYTES) -> dict:
    """超阈值 → 归档（脱敏）＋清空主件；未超阈值 → `None`（无害 noop，每拍调用）。

    写盘全部走 `ledger.store` 的守卫原语（`require_within`＋`write_work_file`）——
    与引擎同一套「只移动不删／先保险后清空」纪律；主件删除失败（罕见：被其他进程
    持锁）→ 返回警告字典，本拍照常继续，下拍重试（归档件已写好，不丢数据）。
    """
    from infinigrow.ledger.store import require_within, write_work_file

    state = Path(state_root)
    root = state.resolve()
    log = require_within(state / "logs" / LOG_NAME, root)
    if not log.is_file() or log.stat().st_size < max_bytes:
        return None
    dest_dir = require_within(state / "archive" / "files" / "logs", root)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = require_within(dest_dir / ("%s.%s" % (LOG_NAME, stamp)), root)
    suffix = 1
    while dest.exists():
        suffix += 1
        dest = require_within(dest_dir / ("%s.%s-%d" % (LOG_NAME, stamp, suffix)), root)
    text = log.read_text(encoding="utf-8", errors="replace")
    redacted, n = _redact(text)
    write_work_file(dest, redacted, root, require_markers=())
    try:
        log.unlink()
    except OSError as exc:
        return {"name": "logs/" + LOG_NAME, "moved": 1, "kept": 1,
                "archive": dest.name, "redacted": n,
                "note": "主件仍被占用（%s），下拍重试" % exc}
    write_work_file(log, "", root, require_markers=())
    return {"name": "logs/" + LOG_NAME, "moved": 1, "kept": 0,
            "archive": dest.name, "redacted": n}


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    state_root = args[0] if args else str(Path(__file__).resolve().parents[1] / "state")
    max_bytes = DEFAULT_MAX_BYTES
    if len(args) > 1 and args[1].isdigit():
        max_bytes = int(args[1])
    try:
        report = rotate_journal(state_root, max_bytes=max_bytes)
    except Exception as exc:                       # 轮转失败不许炸掉启动链
        print("rotate_journal failed: %s" % exc)
        return 1
    if report:
        print("rotate_journal: %s -> archive/%s (redacted %d, %s)"
              % (report["name"], report["archive"], report["redacted"],
                 report.get("note", "kept 0")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
