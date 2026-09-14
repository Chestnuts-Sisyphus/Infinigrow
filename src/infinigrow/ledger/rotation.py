# -*- coding: utf-8 -*-
"""账本轮转：追加型账本只增不减，长期会把状态目录撑成巨石（T6/G7 的实现层）。

v1 的实测：园丁日志 3.5MB、STATE 629KB，读一次要全量扫——「翻账」越来越贵，
最后没人翻，账本就成了摆设。v2 的账本都是 JSONL（一行一条），所以轮转很干净：

**只移动，不删**：被移走的每一行，逐字进 `state/archive/<名字>.<时间戳>.jsonl`。
主账本只保留**能维持语义**的那部分：

| 账本 | 保留策略 | 为什么 |
|---|---|---|
| 差异账 `diffs.jsonl` | 尾部 N 行 | 消费者（组织会话输入、连续零差异计数）只读最近若干行 |
| 兑现账 `outcomes.jsonl` | 尾部 N 行 | 兑现率**现算**，样本由「当前窗口」决定（历史行在归档件里） |
| 执行者账 `executor.jsonl` | 尾部 N 行 | 同调用明细；汇总看归档件 |
| 组织发现账 `org-findings.jsonl` | 尾部 N 行 | 同发现明细 |
| 组织尝试账 `org-llm.jsonl` | 尾部 N 行 | 触发判据只关心**最近一次**尝试 |
| 成熟链 `maturity.jsonl` | **每个对象最新一行** | 它是「当前状态」型账本（`maturity_of` 按对象取最新步） |
| 能力库 `library.jsonl` | **每个名字最新一行** | 同上（按名字取最近使用拍） |

后面两条是**保语义**的关键：若按尾部行数截，某个很久没被碰过的对象的「已到第几步」
会随轮转一起消失，成熟链就会悄悄倒退——那比账本变大严重得多。

**次序**：先把要移走的行写进归档件，再重写主账本。反过来的话，会出现
「主账本已缩、归档还没写」的窗口，那一刻断电＝真丢账。

**路径**：三处（账本、归档目录、归档文件）全部经 `ledger.store.require_within` 校验，
拿到的是**解析后的根内路径**；归档名由「账本名 + 时间戳」拼成，两段都先洗掉路径语义
（分隔符、`..`），所以归档名不可能指到根外。

阈值（`rotate_max_bytes` / `rotate_keep_tail`）是配置项；园丁每次跑顺手轮转一次
（定期＝跟着看护周期走，不必另设调度）。
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from typing import Iterable, Optional

from ..core.encoding import read_text
from ..core.paths import StateLayout
from ..ledger.store import LedgerError, require_within, write_lines, write_work_file

#: 保留策略：尾部 N 行 / 每 key 最新一行
TAIL = "tail"
LEDGER_POLICY: dict[str, tuple] = {
    "diffs.jsonl": (TAIL,),
    "outcomes.jsonl": (TAIL,),
    "executor.jsonl": (TAIL,),
    "org-findings.jsonl": (TAIL,),
    "org-llm.jsonl": (TAIL,),
    "maturity.jsonl": ("latest", "obj"),
    "library.jsonl": ("latest", "name"),
}

ARCHIVE_HEADER = "# 轮转归档（只移动不删）：%s｜移动 %d 行｜主账本保留 %d 行｜%s\n"

#: 文件名里允许出现的字符（其余一律替换掉：归档名绝不接受分隔符或 `..`）
_SAFE_NAME_RX = re.compile(r"[^0-9A-Za-z._-]")


def _safe_component(text: str, fallback: str = "ledger") -> str:
    """把外部输入的片段洗成**不含路径语义**的文件名片段。"""
    cleaned = _SAFE_NAME_RX.sub("_", str(text or ""))
    cleaned = cleaned.replace("..", "_").strip("._")
    return cleaned or fallback


def _lines(path: Path) -> list[str]:
    """读原始行（**逐字保留**，含解析不了的坏行——轮转不许顺手清洗历史）。"""
    return [line for line in read_text(path).splitlines() if line.strip()]


def _keep_latest_per_key(lines: list[str], key_field: str) -> list[str]:
    """每 key 只留**最后一次出现**（顺序按原文件，稳定可复跑）；坏行一律保留。"""
    parsed: list[Optional[dict]] = []
    last_index: dict[str, int] = {}
    for i, line in enumerate(lines):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            parsed.append(None)
            continue
        parsed.append(rec if isinstance(rec, dict) else None)
        if isinstance(rec, dict) and rec.get(key_field):
            last_index[str(rec[key_field])] = i
    keep = set(last_index.values())
    return [line for i, line in enumerate(lines) if parsed[i] is None or i in keep]


def plan(path: Path, policy: tuple, keep_tail: int) -> Optional[dict]:
    """算出这次该移走什么（纯读，不写盘；便于先看后做与测试断言）。"""
    if not path.is_file():
        return None
    lines = _lines(path)
    if not lines:
        return None
    if policy and policy[0] == "latest":
        kept = _keep_latest_per_key(lines, policy[1])
    else:
        kept = lines[-keep_tail:] if len(lines) > keep_tail else lines
    moved = len(lines) - len(kept)
    if moved <= 0:
        return None
    return {"name": path.name, "total": len(lines), "moved": moved, "kept": len(kept),
            "bytes_before": path.stat().st_size}


def _split_moved(main_lines: list[str], kept_lines: list[str], policy: tuple) -> list[str]:
    """按位置切出「要移走的行」（保留行是主账本的子序列，顺序匹配定位）。"""
    if policy and policy[0] == "latest":
        out, keep_i = [], 0
        for line in main_lines:
            if keep_i < len(kept_lines) and line == kept_lines[keep_i]:
                keep_i += 1
                continue
            out.append(line)
        return out
    return main_lines[:len(main_lines) - len(kept_lines)]


def rotate_ledger(path: Path, archive_dir: Path, root: Path, policy: tuple = (TAIL,),
                  keep_tail: int = 2000, stamp: Optional[str] = None) -> Optional[dict]:
    """轮转单个账本（没得移＝返回 None）。"""
    # ① 账本必须在根内（把「外部传进来的 path」变成可写的根内绝对路径）
    safe_ledger = require_within(Path(path), Path(root))
    plan_result = plan(safe_ledger, policy, keep_tail)
    if plan_result is None:
        return None

    # ② 归档目录必须在根内
    safe_archive_dir = require_within(Path(archive_dir), Path(root))
    safe_stamp = _safe_component(stamp or _dt.datetime.now().strftime("%Y%m%d-%H%M%S"),
                                 fallback="stamp")
    stem = _safe_component(safe_ledger.stem, "ledger")
    # ③ 归档文件本身也必须在根内（文件名两段已洗过路径语义，这里再校验一次落点）
    archive = require_within(safe_archive_dir / ("%s.%s.jsonl" % (stem, safe_stamp)),
                             Path(root))

    main_lines = _lines(safe_ledger)
    if policy and policy[0] == "latest":
        kept_lines = _keep_latest_per_key(main_lines, policy[1])
    else:
        kept_lines = main_lines[-plan_result["kept"]:]
    moved_lines = _split_moved(main_lines, kept_lines, policy)

    safe_archive_dir.mkdir(parents=True, exist_ok=True)
    suffix = 1
    while archive.exists():                 # 同秒重跑：换后缀，不覆盖已有归档
        suffix += 1
        archive = require_within(
            safe_archive_dir / ("%s.%s-%d.jsonl" % (stem, safe_stamp, suffix)), Path(root))

    header = ARCHIVE_HEADER % (safe_ledger.name, len(moved_lines), len(kept_lines),
                               safe_stamp)
    # 先落归档（逐字），再重写主账本——次序是「不丢账」的保证
    write_lines(archive, moved_lines, Path(root), header=header)
    try:
        write_work_file(safe_ledger, "\n".join(kept_lines), Path(root),
                        require_markers=())
    except (LedgerError, OSError) as exc:
        return {"name": safe_ledger.name, "moved": 0, "kept": plan_result["kept"],
                "archive": archive.name,
                "error": "归档已写但主账本重写失败：%s" % exc}
    return {"name": safe_ledger.name, "moved": len(moved_lines), "kept": len(kept_lines),
            "archive": archive.name, "bytes_before": plan_result["bytes_before"],
            "bytes_after": safe_ledger.stat().st_size}


def rotate_all(layout: StateLayout, max_bytes: int = 1048576,
               keep_tail: int = 2000, stamp: Optional[str] = None) -> list[dict]:
    """按阈值轮转全部账本（园丁每次跑顺手调用；也可 `infinigrow rotate` 手工跑）。"""
    reports = []
    for name, policy in LEDGER_POLICY.items():
        path = layout.root / name
        if not path.is_file() or path.stat().st_size < max_bytes:
            continue
        report = rotate_ledger(path, layout.archive_dir, layout.root, policy=policy,
                               keep_tail=keep_tail, stamp=stamp)
        if report:
            reports.append(report)
    return reports


def ledger_sizes(layout: StateLayout) -> dict:
    """账本体检（园丁报告用）：名字 → 字节数。"""
    return {name: (layout.root / name).stat().st_size
            for name in LEDGER_POLICY if (layout.root / name).is_file()}


def archived_files(layout: StateLayout) -> list[str]:
    """归档区里的文件名（可检索的证明：主账本缩了，但历史还在）。"""
    return sorted(p.name for p in Path(layout.archive_dir).glob("*.jsonl"))


def search_archive(layout: StateLayout, needle: str, limit: int = 20) -> list[str]:
    """在归档区里检索（**可检索**是「只移动不删」的另一半：不只要留着，还要找得回来）。"""
    hits = []
    for path in sorted(Path(layout.archive_dir).glob("*.jsonl")):
        for no, line in enumerate(_lines(path), 1):
            if needle in line:
                hits.append("%s:%d" % (path.name, no))
                if len(hits) >= limit:
                    return hits
    return hits


def total_archived_lines(paths: Iterable[Path]) -> int:
    """归档件总行数（测试与体检用）。"""
    return sum(len(_lines(p)) for p in paths)
