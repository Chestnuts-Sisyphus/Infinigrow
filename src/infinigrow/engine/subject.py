# -*- coding: utf-8 -*-
"""生长主体：**引擎在长什么**（T1/G4/D15 的实现层）。

引擎代码（Infinigrow 本身）与「它生长的主体」是两件事。没有主体时，机械拍只能观测
自己的状态文件——那是「仪表盘在看仪表盘」，不是生长（v1 的原地打转，根因之一就在这）。
本模块把主体变成一个**可机械读的对象**：

| 问题 | 回答（机械、可查） |
|---|---|
| 主体是什么 | 一个目录（`subject_root`），里面是「要生长的东西」 |
| 主体在哪 | `Settings.subject_path()`：显式配置 → 否则仓库**同级**目录 |
| 怎么读 | 只读目录列表与文件字节数（**不起子进程、不出网**） |
| 怎么判它变了 | `(对象, 维度)` 的机械值变化：存在性 / 文件数 / 每个文件的字节数 |

**命名约定**：主体里的对象一律叫 `主体/<相对路径>`（POSIX 分隔符）。这个前缀不是装饰——
它让「主体对象」与「引擎自身状态对象」（如 `tick_status.json`）在同一个对账空间里
**永不撞名**，也让域饱和判据能把「同一目录下的对象」认成同一域。

**为什么不落绝对路径**：主体的绝对路径只出现在控制台输出与文档里；
落进状态文件时只记**目录名**（`root_name`）。状态产物必须能通过「零绝对路径」扫描
（`tools/check_no_abs_paths.py`），否则开源/分享状态目录时会把本机目录结构带出去。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .model import Observation, Prediction

#: 主体对象名前缀（对账空间里的命名空间，见模块头）
SUBJECT_PREFIX = "主体/"

#: 一次观测最多列多少个主体文件（判据要**有界**：主体可以很大，一拍不能没完没了）
SUBJECT_FILE_LIMIT = 20

#: 存在性维度的取值（机制语言，不写 True/False 那种含糊值）
EXISTS = "存在"
MISSING = "缺失"

#: `journal/` 下文件的**命名规则**（K7/A8 定死并机械化）：`<创建拍号4位>-<创建日期YYYYMMDD>.md`。
#: 拍号段＝创建它的那一拍的拍号；日期段＝创建那天的机械日期。两条线此前各写各的
#: （执行者按拍号段、组织会话按当日日期），跨午夜会出现两种写法 → 对账当成两个对象。
#: 本常量是机械判据；执行者提示词 / 组织会话提议 / 主体声明示例三处**写同一句**，
#: 由 `tests/test_mechanism_docs.py` 锁定同源（改一处＝三处一起改）。
JOURNAL_NAME_RX = re.compile(r"^\d{4}-\d{8}\.md$")


def valid_journal_name(name: str) -> bool:
    """`journal/` 文件名的机械校验：`<创建拍号4位>-<创建日期YYYYMMDD>.md`。"""
    return bool(name) and bool(JOURNAL_NAME_RX.match(name))

#: 「这个目录不是内容」的机械排除表（工具缓存/版本库等，不是被生长的东西）
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "venv",
             "node_modules", ".mypy_cache"}


@dataclass(frozen=True)
class SubjectFile:
    """主体里一个文件的可查事实（路径用相对名，绝不落绝对路径）。"""

    name: str          # 相对名（POSIX 分隔符）
    bytes: int
    mtime: float


def subject_leaf(root: Path) -> str:
    """主体的名字（用于对象命名与快照；只取目录名，不取整条路径）。"""
    return Path(root).name or str(root)


def subject_files(root: Path, limit: int = SUBJECT_FILE_LIMIT) -> list[SubjectFile]:
    """列出主体文件（有界、稳定排序、只读）。

    - 不存在的主体根 → 空列表（**不抛**：主体还没建起来是正常状态，该被观测成「缺失」）；
    - 排序＝**mtime 降序（最新的在前）**，平局按相对名升序——旧的、很久没动的文件
      不该永久霸占观测名额（N42 修复：按 mtime 取最新 N 个，新长出来的文件会被看见）；
    - 上限 `limit`：只限制**逐文件**观测的数量；「文件数」维度用真实总数
      （见 `subject_count`，不受本上限影响）。
    """
    base = Path(root)
    if not base.is_dir():
        return []
    out: list[SubjectFile] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(base).parts
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue                      # 读不到＝本拍不观测它（不猜、不假装）
        out.append(SubjectFile(name="/".join(rel_parts), bytes=stat.st_size,
                               mtime=stat.st_mtime))
    out.sort(key=lambda f: (-f.mtime, f.name))
    return out[:limit]


def subject_count(root: Path) -> int:
    """主体文件的**真实总数**（不受观测上限影响）。

    N42 修复：此前「文件数」维度用的是**截断后**的 `len(files)`——主体文件超过
    `SUBJECT_FILE_LIMIT` 时，自报数字就永远小于磁盘实数（实测：磁盘 31 文件，
    引擎自报 20）。「文件数」是主体层面的生长读数，必须如实报总数。
    """
    return _subject_stats(root)[0]


def subject_total_bytes(root: Path) -> int:
    """主体文件的**真实总字节数**（与 `subject_count` 同一口径，不受观测上限影响）。"""
    return _subject_stats(root)[1]


def _subject_stats(root: Path) -> tuple[int, int]:
    """一次遍历算「文件总数＋总字节数」（只读；跳过 SKIP_DIRS）。"""
    base = Path(root)
    if not base.is_dir():
        return 0, 0
    total, total_bytes = 0, 0
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(base).parts):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        total += 1
        total_bytes += stat.st_size
    return total, total_bytes


def subject_object(rel_name: str) -> str:
    """主体内相对名 → 对账空间里的对象名（`主体/<相对名>`）。"""
    return SUBJECT_PREFIX + rel_name.replace("\\", "/")


def valid_subject_object(obj: str, allowed_objs: set[str],
                         for_proposal: bool = False) -> tuple[bool, str]:
    r"""组织会话产出的对象名**机械闸**（T5/A11）。

    判据（具体状态，反不完全归纳）：
    - 对象已在可对账清单（本拍主体观测集）→ 通过；
    - 否则必须是 `主体/<相对路径>`，且相对路径**合法**（非空、无 `..` 段、
      不以 `/`/`\` 开头＝非绝对、无盘符前缀、不以 `.` 开头＝不藏隐藏文件）——
      这是「**提议创建**」的合法路径（`for_proposal=True` 时放行）；
    - findings 描述的是**已观察到的现实**，必须引用可对账清单里的对象
      （`for_proposal=False`：不许发明机械层读不到的对象名——那是空谈的来源）。

    返回 (是否通过, 理由)。此前对象名纪律只是提示词里的约定，没有机械闸。
    """
    if obj in allowed_objs:
        return True, "已在可对账清单"
    if not obj.startswith(SUBJECT_PREFIX):
        return False, "对象名必须以 %s 开头（主体对象）" % SUBJECT_PREFIX
    rel = obj[len(SUBJECT_PREFIX):]
    segments = rel.split("/")
    bad = (not rel or any(seg in ("", ".", "..") for seg in segments)
           or rel.startswith(("/", "\\")) or rel.startswith(".")
           or bool(re.match(r"^[A-Za-z]:", rel)))
    if bad:
        return False, "非法相对路径：%r（不许越界/绝对/隐藏）" % rel
    if for_proposal:
        return True, "主体内合法新相对路径（可提议创建）"
    return False, "不在可对账清单（findings 必须引用现实可查的对象）"


def observe_subject(root: Path, limit: int = SUBJECT_FILE_LIMIT) -> list[Observation]:
    """机械观测主体 → W回 清单（存在性 / 文件数 / 每个文件的字节数与存在性）。

    「文件数」这一条是主体层面的**生长读数**：它变了就说明主体真的长了/缩了，
    与该文件是谁、内容是什么无关（内容级判断归执行者与组织会话，这里只报可查事实）。

    **N42 修复**：文件数用**真实总数**（`subject_count`，不受 `limit` 影响）——
    主体文件超过观测上限时自报数字也必须如实；逐文件观测仍按 `limit` 有界
    （取 **mtime 最新**的 N 个，旧的不会永久霸占名额）。

    **每个文件同时报「存在性」与「字节数」**：观测到的维度必须和预测的维度对称——
    只观测字节数、不观测存在性，会让「预测某文件存在」变成「预测未执行」的假差异
    （实测：首拍就因此凭空长出一根芽）。
    """
    base = Path(root)
    leaf = subject_leaf(base)
    files = subject_files(base, limit=limit)
    exists = base.is_dir()
    out = [
        Observation(leaf, "存在性", EXISTS if exists else MISSING, "主体根"),
        Observation(leaf, "文件数", str(subject_count(base)), "主体根"),
    ]
    for item in files:
        out.append(Observation(subject_object(item.name), "存在性", EXISTS,
                               "主体:%s" % item.name))
        out.append(Observation(subject_object(item.name), "字节数", str(item.bytes),
                               "主体:%s" % item.name))
    return out


def predict_subject_unchanged(root: Path, tick: int,
                              limit: int = SUBJECT_FILE_LIMIT) -> list[Prediction]:
    """默认 B猜：本拍主体**不变**（与 `predict_unchanged` 同一姿态，只是对象换成主体）。

    这不是「保守」，是可对账的承诺：如果本拍主体变了而没预测到，对账会记成差异——
    差异就是生长信号。执行者/组织会话可以**覆盖**这里的任何一条（写更精确的预期），
    也可以预测**尚不存在的文件**（预期=存在）——那是「该创建它」的合法提议：
    现实侧读不到它 → 「预测未执行」→ 照样产芽。
    """
    base = Path(root)
    leaf = subject_leaf(base)
    files = subject_files(base, limit=limit)
    exists = base.is_dir()
    out = [
        Prediction(leaf, "存在性", EXISTS if exists else MISSING, tick=tick,
                   evidence="预测:主体根"),
        Prediction(leaf, "文件数", str(subject_count(base)), tick=tick,
                   evidence="预测:主体根"),
    ]
    for item in files:
        out.append(Prediction(subject_object(item.name), "存在性", EXISTS, tick=tick,
                              evidence="预测:主体:%s" % item.name))
        out.append(Prediction(subject_object(item.name), "字节数", str(item.bytes),
                              tick=tick, evidence="预测:主体:%s" % item.name))
    return out


def subject_snapshot(root: Path, tick: int, limit: int = SUBJECT_FILE_LIMIT) -> dict:
    """主体快照（落 `state/subject.json`）：这一拍引擎眼中的主体长什么样。

    **只记目录名与相对名**——不记绝对路径（见模块头）。人要看绝对路径，
    用 `infinigrow dry-run`（控制台输出，不落盘）。
    """
    base = Path(root)
    files = subject_files(base, limit=limit)
    count, total_bytes = _subject_stats(base)
    return {
        "tick": tick,
        "root_name": subject_leaf(base),
        "exists": base.is_dir(),
        "file_count": count,
        "total_bytes": total_bytes,
        "files": [{"name": f.name, "bytes": f.bytes} for f in files],
        "object_prefix": SUBJECT_PREFIX,
        "file_limit": limit,
        "observed_files": len(files),
    }


def subject_readings(root: Path, limit: int = SUBJECT_FILE_LIMIT
                     ) -> dict[tuple[str, str], str]:
    """主体读数 → {(对象, 维度): 值}（供「动手前后作差」用：差集＝动作自己造成的变化）。

    为什么需要它：动作会改变文件数/字节数，而这些读数又参与对账——如果不把
    「动作自己造成的变化」认出来，每一手动作都会给引擎派回一堆「处理你自己刚造成的结果」
    的活（实测：执行者只能拒绝，白烧一轮——那是不产出生长的空转，不是运转）。
    """
    return {(obs.obj, obs.dimension): obs.actual for obs in observe_subject(root, limit)}


def merge_predictions(defaults: Iterable[Prediction],
                      planned: Iterable[Prediction]) -> list[Prediction]:
    """默认 B猜 与**规划过的** B猜 合并：同 `(对象, 维度)` 时规划值覆盖默认值。

    为什么要覆盖：默认值是「不变」，而规划值是「做完这件事之后应该变成什么」。
    没有覆盖，任何真动手的一拍都会被对账记成「预测内错」——差异不是行动的证据，
    只是没预测的证据。规划值是**更强**的承诺，兑现账判的就是它。
    """
    out: dict[tuple[str, str], Prediction] = {}
    order: list[tuple[str, str]] = []
    for pred in defaults:
        if pred.key not in out:
            order.append(pred.key)
        out[pred.key] = pred
    for pred in planned:
        if pred.key not in out:
            order.append(pred.key)
        out[pred.key] = pred
    return [out[k] for k in order]
