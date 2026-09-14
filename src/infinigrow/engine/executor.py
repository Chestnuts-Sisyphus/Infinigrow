# -*- coding: utf-8 -*-
"""执行者通道：把「引擎说要做什么」变成「真有东西动手了」（T2/G2/G14 的实现层）。

**通道契约（一句话）**：提示词经 **stdin** 进、输出经 **stdout** 出，一次调用＝一次动手机会。

```
    python -m infinigrow tick --executor "你的命令 参数..."
                    │
                    ├─ stdin  ← 本拍题面 + 本拍 B猜 + 纪律（提示词文件原文）
                    └─ stdout → 你的输出（原样落留痕；可选带一行用量）
```

四条设计约束：

1. **不给执行者＝机械拍**：`executor` 为空时本模块根本不会被调用，零 token、零凭据、不出网。
   接法由配置/CLI 给（`--executor` / `IG_EXECUTOR`），**不写死任何厂商**。
2. **失败必须可见**：rc、超时、找不到命令、空输出——四种都记账（`state/executor.jsonl`）
   并进心跳的「执行者连续失败」计数；园丁据此告警。静默失败是上一代最贵的教训。
3. **留痕**：输出**原文**落 `state/traces/<拍号>-<用途>.md`（账本只记长度与元数据），
   否则「上一拍到底说了什么」只能靠猜，组织会话就没有可对账的输入。
4. **产物不落绝对路径**：账本里只记命令的**首段基名**与主体目录名；
   命令或输出里出现本机路径时一律替换为占位符（状态目录要能公开/迁移）。

用量（可选）：输出里出现以 `IG_USAGE ` 开头的行，其后的 JSON 会被解析进账本
（例：`IG_USAGE {"input_tokens": 1234, "cost_usd": 0.012}`）。**不猜**用量——
执行者不说，账本里就是 `null`，不拿输出长度冒充 token 数。
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..core.paths import StateLayout, guard
from ..ledger.store import append_jsonl, write_work_file

#: 超时的退出码（沿用 shell 惯例 124；与「命令自己返回 124」可能撞车，故另有 timed_out 标记）
TIMEOUT_RC = 124
#: 找不到执行者（沿用 shell 惯例 127）
NOT_FOUND_RC = 127

#: 用量行的前缀（执行者可选用；不写＝账本里 usage 为 null）
USAGE_PREFIX = "IG_USAGE "

#: 用途标签（同一通道、两种提示词；账本据此区分）
KIND_TICK = "tick"
KIND_ORG = "org-session"

ABS_PATH_RX = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:home|Users|mnt|opt)/)[^\s\"'|;]*")
PATH_PLACEHOLDER = "（本机路径已省略）"


@dataclass
class ExecutorRun:
    """一次执行者调用的全部可查事实（账本行就是它的 `as_record()`）。"""

    tick: int
    kind: str
    command_label: str
    rc: int
    duration_s: float
    prompt_bytes: int
    output_bytes: int
    output: str = ""
    timed_out: bool = False
    usage: Optional[dict] = None
    note: str = ""
    cwd_name: str = ""
    time: str = field(default_factory=lambda: _dt.datetime.now()
                      .strftime("%Y-%m-%d %H:%M:%S"))

    @property
    def ok(self) -> bool:
        return self.rc == 0 and not self.timed_out

    def as_record(self) -> dict:
        return {
            "tick": self.tick, "kind": self.kind, "command": self.command_label,
            "rc": self.rc, "timed_out": self.timed_out,
            "duration_ms": int(self.duration_s * 1000),
            "prompt_bytes": self.prompt_bytes, "output_bytes": self.output_bytes,
            "usage": self.usage, "note": self.note, "cwd_name": self.cwd_name,
            "time": self.time,
        }

    def label(self) -> str:
        """一行字的调用摘要（进对账报告；**不含本机路径**）。"""
        state = "超时" if self.timed_out else ("成功" if self.rc == 0 else "失败")
        return ("%s（%s）rc=%d 用时=%.2fs 提示=%dB 输出=%dB%s"
                % (self.command_label or "（无命令）", state, self.rc, self.duration_s,
                   self.prompt_bytes, self.output_bytes,
                   " 用量=%s" % json.dumps(self.usage, ensure_ascii=False)
                   if self.usage else ""))


def redact_paths(text: str) -> str:
    """把文本里的本机绝对路径替换成占位符（状态产物不得含本机路径）。"""
    return ABS_PATH_RX.sub(PATH_PLACEHOLDER, text or "")


def split_command(command: str) -> list[str]:
    """把一行命令拆成 argv（支持引号包裹；**不用 shell**）。

    刻意不走 `shell=True`：那等于把「拼接字符串」的自由交给调用方，
    Windows 上还会顺带把 `%VAR%` 展开——执行者通道不该有这层隐含解释器。
    带盘符的本机路径请**用正斜杠或整段加引号**（两种平台都不歧义）；
    反斜杠在 Windows 命令行里是转义字符，shlex 与 cmd 的解释并不一致。
    """
    text = (command or "").strip()
    if not text:
        return []
    try:
        argv = shlex.split(text, posix=True)
    except ValueError:
        argv = text.split()
    return [tok for tok in (t.strip('"').strip("'") for t in argv) if tok]


def command_label(command: str) -> str:
    """命令的**首段基名**（账本里只记这个，避免把本机目录结构写进状态）。"""
    argv = split_command(command)
    if not argv:
        return ""
    return Path(argv[0]).name


def executor_env(subject_root: Path, state_root: Path, tick: int, kind: str,
                 model: str = "") -> dict:
    """子进程环境：原样继承 ＋ 注入本拍上下文（执行者不必解析提示词猜路径）。

    注入的是**本拍上下文**（拍号/用途/主体根/状态根/模型名），不是凭据：
    凭据一律由使用者在自己的环境或执行者脚本里准备，引擎不搬运、不落盘、不回显。
    """
    env = dict(os.environ)
    env["IG_TICK"] = str(tick)
    env["IG_PASS_KIND"] = kind
    env["IG_SUBJECT_ROOT"] = str(subject_root)
    env["IG_STATE_ROOT"] = str(state_root)
    if model:
        env["IG_MODEL"] = model
    return env


def parse_usage(output: str) -> Optional[dict]:
    """从输出里找 `IG_USAGE {json}` 行。找到就返回 dict，找不到返回 None（不猜）。"""
    for line in (output or "").splitlines():
        text = line.strip()
        if not text.startswith(USAGE_PREFIX):
            continue
        try:
            data = json.loads(text[len(USAGE_PREFIX):])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def run_command(command: str, prompt: str, *, tick: int, kind: str, cwd: Path,
                state_root: Path, subject_root: Path, timeout_s: int = 120,
                model: str = "") -> ExecutorRun:
    """起一次执行者子进程。**不抛异常**——失败也返回 ExecutorRun（rc/timed_out 标明）。"""
    argv = split_command(command)
    label = command_label(command)
    cwd_name = Path(cwd).name if cwd else ""
    started = time.time()
    if not argv:
        return ExecutorRun(tick=tick, kind=kind, command_label=label, rc=NOT_FOUND_RC,
                           duration_s=0.0, prompt_bytes=len(prompt or ""), output_bytes=0,
                           note="执行者命令为空（不是错误路径：空＝机械拍，不该走到这里）",
                           cwd_name=cwd_name)
    try:
        proc = subprocess.run(
            argv, input=prompt or "", capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout_s,
            cwd=str(cwd) if cwd else None,
            env=executor_env(subject_root, state_root, tick, kind, model))
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        return ExecutorRun(tick=tick, kind=kind, command_label=label, rc=TIMEOUT_RC,
                           duration_s=time.time() - started,
                           prompt_bytes=len(prompt or ""), output_bytes=len(partial),
                           output=partial, timed_out=True,
                           note="超时 %ds 后被杀" % timeout_s, cwd_name=cwd_name)
    except (OSError, subprocess.SubprocessError) as exc:
        return ExecutorRun(tick=tick, kind=kind, command_label=label, rc=NOT_FOUND_RC,
                           duration_s=time.time() - started,
                           prompt_bytes=len(prompt or ""), output_bytes=0,
                           note="起不来：%s" % redact_paths(repr(exc))[:200],
                           cwd_name=cwd_name)

    output = (proc.stdout or "") + (proc.stderr or "")
    note = "" if proc.returncode == 0 else "非零退出（stderr 见留痕）"
    if not output.strip() and proc.returncode == 0:
        note = "空输出（rc=0 但没有返回任何内容）"
    return ExecutorRun(tick=tick, kind=kind, command_label=label, rc=proc.returncode,
                       duration_s=time.time() - started,
                       prompt_bytes=len(prompt or ""), output_bytes=len(output),
                       output=output, usage=parse_usage(output), note=note,
                       cwd_name=cwd_name)


def run_callable(fn: Callable[[str], str], prompt: str, *, tick: int, kind: str,
                 label: str = "（进程内可调用）") -> ExecutorRun:
    """进程内执行者（`run_tick(llm=...)` 与测试用）：同样记账，同样可见。"""
    started = time.time()
    try:
        output = fn(prompt) or ""
        rc = 0
        note = "" if output.strip() else "空输出（rc=0 但没有返回任何内容）"
    except Exception as exc:                              # noqa: BLE001 — 失败要记账，不是崩掉
        output, rc, note = "", 1, "调用抛异常：%s" % redact_paths(repr(exc))[:200]
    return ExecutorRun(tick=tick, kind=kind, command_label=label, rc=rc,
                       duration_s=time.time() - started, prompt_bytes=len(prompt or ""),
                       output_bytes=len(output), output=output,
                       usage=parse_usage(output), note=note, cwd_name="")


def write_trace(layout: StateLayout, run: ExecutorRun, prompt: str,
                subject_root: Path) -> Path:
    """落留痕：`state/traces/<用途>-<拍号>.md`（提示词全文 ＋ 输出全文）。

    留痕是**工作文件**（同拍重跑＝同一文件，原子替换），账本是追加型的调用账。
    路径一律先 redact：留痕要能被分享/迁移，不能夹带本机绝对路径。
    """
    name = "%s-%05d.md" % (run.kind, run.tick)
    path = layout.traces_dir / name
    guard(path, layout.root)
    body = [
        "# 留痕 · %s · 拍 %d" % (run.kind, run.tick),
        "",
        "- 执行者：%s" % (run.command_label or "（无命令）"),
        "- 返回码：%d%s" % (run.rc, "（超时）" if run.timed_out else ""),
        "- 用时：%.2fs｜提示 %dB｜输出 %dB" % (run.duration_s, run.prompt_bytes,
                                                run.output_bytes),
        "- 主体根名：%s" % Path(subject_root).name,
        "",
        "## 提示词（原样）",
        "",
        "```text",
        redact_paths(prompt),
        "```",
        "",
        "## 输出（原样）",
        "",
        "```text",
        redact_paths(run.output),
        "```",
    ]
    write_work_file(path, "\n".join(body), layout.root, require_markers=("# 留痕",))
    return path


def record_executor_run(layout: StateLayout, run: ExecutorRun) -> None:
    """把一次调用记进账（失败也记——「没做成」是事实，不该消失）。"""
    record = run.as_record()
    record["note"] = redact_paths(record.get("note") or "")
    append_jsonl(layout.executor_ledger, record, layout.root)


def make_runner(*, command: str, callable_fn: Optional[Callable[[str], str]],
                tick: int, kind: str, cwd: Path, state_root: Path,
                subject_root: Path, timeout_s: int = 120, model: str = "",
                ) -> Optional[Callable[[str], ExecutorRun]]:
    """按「命令行 or 进程内可调用」造一个执行者 runner（同一条通道，同一份记账）。

    两者都给时**命令行优先**（显式 CLI/配置的意图更强）；两者都空＝返回 None
    （＝机械拍：本模块不会被调用，零 token）。
    """
    if command:
        def _run(prompt: str) -> ExecutorRun:
            return run_command(command, prompt, tick=tick, kind=kind, cwd=cwd,
                               state_root=state_root, subject_root=subject_root,
                               timeout_s=timeout_s, model=model)
        return _run
    if callable_fn is not None:
        def _run_callable(prompt: str) -> ExecutorRun:
            return run_callable(callable_fn, prompt, tick=tick, kind=kind)
        return _run_callable
    return None
