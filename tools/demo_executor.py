#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""演示执行者：**确定性脚本**，用来验证「执行者通道 → 现实变化 → 对账 → 兑现」这条链路。

写在前面（诚实声明）：

- 它**不是模型**，不烧 token、不出网、不需要凭据。它做的事是脚本能做的确定动作。
- 它存在的理由：引擎的**通道、记账、对账、兑现判定**必须能被端到端验证一遍。
  用真实模型做这件事，验证的是模型能力；用确定性脚本做，验证的才是机制本身。
- 它**只在主体根内单层文件名**上动手（点号开头、含分隔符、指向根外的一律拒绝）——
  演示脚本也没有资格碰引擎自身状态。

它按 `IG_PASS_KIND` 分两种行为：

| 用途 | 行为 |
|---|---|
| `org-session` | 看主体文件清单，提出**下一步该长的那一个文件**（发现 ＋ 规划预测），输出 JSON 契约 |
| `tick` | 题面对象是主体里尚未存在的 `growth-*.md` → 创建它（一次一个，已存在则不动） |

两种行为都打印一行 `IG_USAGE`（全零），用来验证「用量可选字段」这条路是通的。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

GROWTH_RX = re.compile(r"growth-(\d+)\.md")
SUBJECT_PREFIX = "主体/"


def _subject_root() -> Path:
    raw = os.environ.get("IG_SUBJECT_ROOT", "").strip()
    return Path(raw).resolve() if raw else Path(".").resolve()


def _growth_names(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    out = []
    for path in sorted(root.glob("growth-*.md")):
        if path.is_file():
            out.append(path.name)
    return out


def _next_growth(root: Path) -> str:
    numbers = [int(m.group(1)) for m in (GROWTH_RX.fullmatch(n) for n in _growth_names(root)) if m]
    return "growth-%d.md" % (max(numbers) + 1 if numbers else 1)


def _safe_target(root: Path, name: str):
    """只允许主体根内、**单层文件名**的目标（演示脚本的可写面就这么大）。"""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    target = (root / name).resolve()
    if target.parent != root.resolve():
        return None
    return target


def _content(name: str) -> str:
    return ("# %s（演示主体）\n"
            "\n"
            "本文件由 tools/demo_executor.py 创建——确定性脚本，不是模型。\n"
            "它的存在证明这条链路是通的：\n"
            "题面（差异）→ 执行者动手 → 现实出现可查变化 → 对账 → 兑现账。\n" % name)


def org_session() -> int:
    """组织会话用途：从主体现状提出下一步（发现 ＋ 规划预测）。"""
    root = _subject_root()
    existing = _growth_names(root)
    target = _next_growth(root)
    payload = {
        "findings": [{
            "kind": "预测外发现",
            "obj": SUBJECT_PREFIX + target,
            "dimension": "存在性",
            "expected": "（预测未提）",
            "actual": "缺失",
            "pointer": "主体文件清单:%s 下现有 %d 个 growth-*.md，无 %s"
                       % (root.name, len(existing), target),
        }],
        "predictions": [{
            "obj": SUBJECT_PREFIX + target,
            "dimension": "存在性",
            "expected": "存在",
            "pointer": "计划：本拍由执行者创建 %s（演示执行者按此承诺动手）" % target,
        }],
        "notes": ("确定性演示执行者：主体现有 %s；建议下一步长出 %s"
                  % (existing or "（空）", target)),
    }
    print("组织会话（演示执行者）：主体现有 %d 个文件，提出 %s"
          % (len(existing), target))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print('IG_USAGE {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0,'
          ' "provider": "demo-deterministic"}')
    return 0


def tick_pass(prompt: str) -> int:
    """执行会话用途：题面对象若在主体内且尚不存在 → 创建它；否则不动手。"""
    root = _subject_root()
    obj = ""
    for line in prompt.splitlines():
        if line.startswith("- 对象："):
            obj = line.split("：", 1)[1].split("｜")[0].strip()
            break
    print("演示执行者（确定性，非模型）：收到题面，对象=%r" % (obj or "（无）"))
    if not obj.startswith(SUBJECT_PREFIX):
        print("本拍对象不在主体内 → **不动手**（演示脚本没有资格碰引擎自身状态）。")
        print('IG_USAGE {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0,'
              ' "provider": "demo-deterministic"}')
        return 0

    rel = obj[len(SUBJECT_PREFIX):]
    target = _safe_target(root, rel)
    if target is None:
        print("题面对象名不合规（含分隔符/点号开头/越出主体根）→ 拒绝动手。")
        return 0
    if target.is_file():
        print("对象已存在（%s）：本拍不重复动手——让现实保持原样，等对账判对错。" % rel)
        print('IG_USAGE {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0,'
              ' "provider": "demo-deterministic"}')
        return 0

    lines = _content(rel).rstrip("\n").splitlines()
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        from infinigrow.ledger.store import write_lines   # 与引擎同一条受守卫的写盘路径
    except ImportError:
        print("FAIL：找不到 infinigrow 包（需要 PYTHONPATH 指向仓库的 src/）。")
        return 3
    write_lines(target, lines, root)
    size = target.stat().st_size
    print("已创建：%s（%d 字节）" % (rel, size))
    print("留痕：动手前 B猜=对象 %s 维度 存在性 预期 存在（由组织会话规划）；"
          "动手后现实=%d 字节。" % (obj, size))
    print('IG_USAGE {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0,'
          ' "provider": "demo-deterministic"}')
    return 0


def main() -> int:
    prompt = sys.stdin.read()
    kind = os.environ.get("IG_PASS_KIND", "tick")
    if kind == "org-session":
        return org_session()
    return tick_pass(prompt)


if __name__ == "__main__":
    sys.exit(main())
