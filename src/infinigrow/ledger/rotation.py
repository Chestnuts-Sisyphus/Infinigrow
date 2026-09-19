# -*- coding: utf-8 -*-
"""账本与文件型产物轮转：追加型账本只增不减、每拍一份的报告只增不减，
长期会把状态目录撑成巨石（T6/G7 的实现层）。

v1 的实测：园丁日志 3.5MB、STATE 629KB，读一次要全量扫——「翻账」越来越贵，
最后没人翻，账本就成了摆设。v2 的账本都是 JSONL（一行一条），所以轮转很干净：

**只移动，不删**：被移走的每一行/每一份，逐字进 `state/archive/`。
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

**文件型产物**（`rotate_files`，T2/A3）：`traces/`（每拍一份留痕）、`reconcile/`
（每拍一份报告）按**份数**留最近 N 份。同样只移动不删，
归档落在 `state/archive/files/<类>/`，`infinigrow rotate --search` 可检索。
`logs/tick.log`（单文件日志）的轮转在**启动器**（`tools/rotate_journal.py`，两拍之间
的句柄空隙执行、归档前脱敏）——调度器以追加句柄持有它贯穿进程，园丁内轮转必失败。

**次序**：先把要移走的行/文件写进归档件，再缩主件。反过来的话，会出现
「主件已缩、归档还没写」的窗口，那一刻断电＝真丢。

**路径**：所有落点全部经 `ledger.store.require_within` 校验，拿到的是**解析后的根内路径**；
归档名由「名字 + 时间戳」拼成，两段都先洗掉路径语义（分隔符、`..`），
所以归档名不可能指到根外。

阈值（`rotate_max_bytes` / `rotate_keep_tail` / `rotate_keep_files`）是配置项；
园丁每次跑顺手轮转一次（定期＝跟着看护周期走，不必另设调度）。
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path
from typing import Iterable, Optional

from ..core.encoding import read_text
from ..core.paths import StateLayout
from ..ledger.store import LedgerError, move_file, require_within, write_lines, write_work_file

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

#: 文件型产物轮转（账本之外的「每拍一份」类）：目录名 → 归档子目录
FILE_POLICY = (
    ("traces", "files/traces"),        # 执行者留痕（每拍一份 markdown）
    ("reconcile", "files/reconcile"),  # 对账报告（每拍一份 markdown）
)

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


def rotate_files(layout: StateLayout, keep_files: int = 200,
                 stamp: Optional[str] = None) -> list[dict]:
    """轮转**文件型**产物（T2/A3）：traces/、reconcile/ 按**份数**留最近 N 份。
    都**只移动不删**，归档落在 `state/archive/files/<类>/`，与 JSONL 账本归档区分开。

    注意：`logs/tick.log` **不在**这里轮转——调度器（`tools/run_tick.bat`）以追加句柄
    持有它贯穿整个进程（Windows 无删除/写共享，进程内删不清），轮转职责在
    `tools/rotate_journal.py`（两拍之间的句柄空隙，见该模块 docstring）。
    """
    reports = []
    for kind, archive_rel in FILE_POLICY:
        src_dir = getattr(layout, kind + "_dir")
        if not src_dir.is_dir():
            continue
        files = sorted(p for p in src_dir.glob("*.md") if p.is_file())
        if len(files) <= keep_files:
            continue
        moved = files[:len(files) - keep_files]
        dest_dir = layout.archive_dir / archive_rel
        for p in moved:
            move_file(p, require_within(dest_dir / p.name, layout.root), layout.root)
        reports.append({"name": kind, "moved": len(moved), "kept": len(files) - len(moved),
                        "archive": archive_rel})
    return reports


def rotate_frozen_sprouts(layout: StateLayout, cap: int = 5000, keep_tail: int = 4000,
                          stamp: Optional[str] = None) -> Optional[dict]:
    """冻结区容量与整理（M5/N48-4）：超上限时把**最旧的**移动进归档，只移动不删。

    - 冻结区（`state/sprouts-frozen.jsonl`）是「挂起的芽」的落点：**它没有容量判据时
      每拍 +36~38 行单调增长**（实测 3711 行），最后没人翻、也翻不动——与账本轮转
      同一个病，用同一套纪律治：**只移动不删**，先落归档件再缩主件（断电最多多一份归档）。
    - 「最旧的」判据＝**文件里的次序**（冻结区按被挤出的先后追加，前面的＝更早挂起的）；
      保留尾部 `keep_tail` 行。
    - 与 M4（重问判据）的关系：某对象的芽被移出冻结区后，它不再拦「重新立芽」——
      这是**有意的**：容量整理只该丢历史，不该让 4000 行旧挂起把新问题永久压住。
    - 归档落在 `state/archive/files/frozen/`，与其它文件型产物同一片归档区，可检索。
    """
    path = Path(layout.frozen_sprouts)
    if not path.is_file():
        return None
    lines = _lines(path)
    if len(lines) <= max(cap, 0):
        return None
    keep = max(keep_tail, 0)
    moved_lines = lines[:len(lines) - keep]
    kept_lines = lines[len(lines) - keep:]
    safe_stamp = _safe_component(stamp or _dt.datetime.now().strftime("%Y%m%d-%H%M%S"),
                                 fallback="stamp")
    dest_dir = require_within(layout.archive_dir / "files" / "frozen", layout.root)
    dest = require_within(dest_dir / ("sprouts-frozen.%s.jsonl" % safe_stamp), layout.root)
    suffix = 1
    while dest.exists():                # 同秒重跑：换后缀，不覆盖已有归档
        suffix += 1
        dest = require_within(dest_dir / ("sprouts-frozen.%s-%d.jsonl"
                                          % (safe_stamp, suffix)), layout.root)
    dest_dir.mkdir(parents=True, exist_ok=True)
    header = ARCHIVE_HEADER % (path.name, len(moved_lines), len(kept_lines), safe_stamp)
    # 先落归档、再缩主件（与账本同一套次序：不丢是第一位）
    write_lines(dest, moved_lines, layout.root, header=header)
    try:
        write_work_file(path, "\n".join(kept_lines), layout.root, require_markers=())
    except (LedgerError, OSError) as exc:
        return {"name": path.name, "moved": 0, "kept": len(kept_lines),
                "archive": dest.name, "error": "归档已写但冻结区重写失败：%s" % exc}
    return {"name": path.name, "moved": len(moved_lines), "kept": len(kept_lines),
            "archive": "files/frozen/%s" % dest.name}


def rotate_journal(subject_root: Path, keep_files: int = 200,
                   stamp: Optional[str] = None) -> Optional[dict]:
    """轮转主体 `journal/`（K6/A7）：超上限（默认 200 篇，可配）时**只移动**进归档。

    - 主体是「被长的现实」，它的 `journal/` 归它自己管；归档放**主体根自己的**
      `archive/journal/`（不混进引擎状态根——那是另一套账）。
    - 只移动不删；按**文件名字典序**（`<创建拍号4位>-<日期>.md`，拍号小的＝更旧）
      移走最旧的，保留最近 N 篇。
    - 与 K2 的关系（G1 更正，旧措辞已被实测推翻）：观测面按 mtime 取最新 N 个，而
      `move_file` 是「写新件＋移除源」——归档件拿到的是**搬运那一刻**的 mtime，比正在长的
      内容更「新」。副本实测（`IG_JOURNAL_KEEP_FILES=200` 逐篇新增并跑园丁）：跨过上限后
      每次轮转使 20 格窗口里归档件 +1、窗口首格恒为 `archive/journal/…md.<stamp>`，
      主体文件数也不降（363→377）——轮转等于没搬走。
      所以**主体根的 `archive/` 不入生长面**：逐文件窗口、目录对象、文件数/总字节数三处
      都排除它，对象名闸连 `for_proposal` 也不放行（见 `engine/subject.py` 的
      `SUBJECT_ARCHIVE_DIR`）。原先那句「不影响新内容的可见性」是错的，别再写回去。
    - 归档名带时间戳（同秒重跑换后缀，不覆盖）。
    """
    journal = subject_root / "journal"
    if not journal.is_dir():
        return None
    files = sorted(p for p in journal.glob("*.md") if p.is_file())
    if len(files) <= keep_files:
        return None
    moved = files[:len(files) - keep_files]
    dest_dir = subject_root / "archive" / "journal"
    safe_stamp = _safe_component(stamp or _dt.datetime.now().strftime("%Y%m%d-%H%M%S"),
                                 fallback="stamp")
    dest_dir.mkdir(parents=True, exist_ok=True)
    for p in moved:
        dest = dest_dir / ("%s.%s" % (p.name, safe_stamp))
        suffix = 1
        while dest.exists():
            suffix += 1
            dest = dest_dir / ("%s.%s-%d" % (p.name, safe_stamp, suffix))
        move_file(p, dest, subject_root)
    return {"name": "journal", "moved": len(moved), "kept": len(files) - len(moved),
            "archive": str(dest_dir.relative_to(subject_root).as_posix())}


def ledger_sizes(layout: StateLayout) -> dict:
    """账本体检（园丁报告用）：名字 → 字节数。"""
    return {name: (layout.root / name).stat().st_size
            for name in LEDGER_POLICY if (layout.root / name).is_file()}


def archived_files(layout: StateLayout) -> list[str]:
    """归档区里的文件（可检索的证明：主账本缩了，但历史还在）。"""
    return sorted(str(p.relative_to(layout.archive_dir).as_posix())
                  for p in Path(layout.archive_dir).rglob("*")
                  if p.is_file())


def search_archive(layout: StateLayout, needle: str, limit: int = 20) -> list[str]:
    """在归档区里检索（**可检索**是「只移动不删」的另一半：不只要留着，还要找得回来）。

    覆盖 JSONL 账本归档与 `files/` 下的文件型产物（traces/reconcile/logs）。
    """
    hits = []
    for path in sorted(Path(layout.archive_dir).rglob("*")):
        if not path.is_file():
            continue
        for no, line in enumerate(_lines(path), 1):
            if needle in line:
                hits.append("%s:%d" % (path.relative_to(layout.archive_dir).as_posix(), no))
                if len(hits) >= limit:
                    return hits
    return hits


def total_archived_lines(paths: Iterable[Path]) -> int:
    """归档件总行数（测试与体检用）。"""
    return sum(len(_lines(p)) for p in paths)
