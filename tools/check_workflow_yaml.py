# -*- coding: utf-8 -*-
"""GitHub Actions 工作流文件的纯标准库语法哨兵。

为什么不用 PyYAML：`yaml` 不在 `dev` extra 里，测试里 `import yaml` 会在
CI 上 ModuleNotFoundError → 静默 skip，正是本轮 M5 要堵的「恒 skip 空闸」。
这里只守一个**已知会炸整个 workflow 的坑**：块映射里一行未加引号的标量含了
半角 `: `（冒号+空格），YAML 会把它读成嵌套映射，报
「mapping values are not allowed here」→ CI 0 秒挂。当初把
`Privacy scan (通用层：…)`（全角冒号，安全）改写成
`Privacy scan (generic layer: paths / …)`（半角冒号）就踩中它。

规则：
  · 缩进里不许有制表符（YAML 明令禁止）。
  · 一行 `key: value`，若 value 是未加引号的普通标量且内部含 `: ` → 报错。
  · `run: |` 这类块标量之后的缩进正文属于脚本，不套此规则（跳过）。
全角冒号 `：` 不是 YAML 映射标记，所以中文注释/中文 name 一律放行。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

# 块标量起始符：`|`、`>` 及其 chomp/指示符变体（`|-`、`>+`、`|2` …）
_BLOCK_SCALAR = ("|", ">")
# value 以这些起头 → 是引号/流式集合/别名，内部 `: ` 合法
_QUOTED_OR_FLOW = ("'", '"', "[", "{", "&", "*")


def _indent_of(raw: str) -> int:
    return len(raw) - len(raw.lstrip(" "))


def check_workflow_text(text: str) -> list[str]:
    """返回问题描述列表（空列表＝通过）。"""
    problems: list[str] = []
    lines = text.splitlines()
    # >0 表示正处在某个键（缩进 = 该值）开启的块标量里，其更深缩进的行是脚本正文
    scalar_key_indent = -1

    for lineno, raw in enumerate(lines, 1):
        stripped = raw.strip()

        # 制表符检查对每一行都成立（含块标量正文）
        lead = raw[: len(raw) - len(raw.lstrip(" \t"))]
        if "\t" in lead:
            problems.append("第 %d 行：缩进含制表符，YAML 禁止" % lineno)

        if not stripped:
            continue

        indent = _indent_of(raw)
        if scalar_key_indent >= 0:
            if indent > scalar_key_indent:
                continue            # 块标量正文：不参与映射解析
            scalar_key_indent = -1   # 缩进回退，块标量结束

        if stripped.startswith("#"):
            continue

        body = stripped[2:] if stripped.startswith("- ") else stripped
        marker_indent = indent + 2 if stripped.startswith("- ") else indent

        # 只在「key: value」形态处找坑：无冒号或行尾即冒号（key 独开一层）都跳过
        if ": " not in body and not body.endswith(":"):
            continue
        if ": " not in body:
            continue

        key, _, value = body.partition(": ")
        value = value.strip()
        if value.startswith(_BLOCK_SCALAR):
            scalar_key_indent = marker_indent
            continue
        if not value or value.startswith(_QUOTED_OR_FLOW):
            continue
        # 到这里 value 是未加引号的普通标量——内部再出现 `: ` 即被误读成映射
        if ": " in value:
            problems.append(
                "第 %d 行：未加引号标量含半角 ': '（会被读成嵌套映射）：%s"
                % (lineno, key.strip())
            )
    return problems


def main(argv: list[str]) -> int:
    files = sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))
    if not files:
        print("未找到工作流文件：%s" % WORKFLOW_DIR, file=sys.stderr)
        return 1
    failed = False
    for path in files:
        problems = check_workflow_text(path.read_text(encoding="utf-8"))
        rel = path.relative_to(REPO_ROOT).as_posix()
        if problems:
            failed = True
            print("%s：" % rel)
            for p in problems:
                print("  - %s" % p)
        else:
            print("%s：OK" % rel)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
