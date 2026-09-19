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
from typing import Iterable, Optional

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
#: 本常量是机械判据，**执法点是对象名机械闸**（`valid_subject_object` 的提议分支）：
#: 组织会话点名一个尚不存在的 `journal/` 直接子文件时，名字不合规格即被拒收——
#: 执法范围就这一条，因为引擎只能拦自己会读的东西。**写盘侧**（执行者真建的文件）
#: 靠提示词约定（`prompts/tick.md`）＋测试守护：引擎不替执行者改文件名，改了就等于
#: 把现实悄悄抹成符合预期。执行者提示词 / 组织会话提议 / 主体声明示例三处**写同一句**，
#: 由 `tests/test_mechanism_docs.py` 锁定同源（改一处＝三处一起改）。
JOURNAL_NAME_RX = re.compile(r"^\d{4}-\d{8}\.md$")

#: 主体的日志目录名（命名判据只管**这个目录的直接子文件**，见上方边界说明）
JOURNAL_DIR = "journal"

#: **目录对象**的命名（N43）：`主体/<相对路径>/`——结尾的 `/` 是「这是目录」的机械标记，
#: 与文件对象（`主体/<相对路径>`）在同一对账空间里**永不撞名**。
#: 目录观测量＝**文件数**：它让「往某个目录里再长一格」成为一个**名字无关**的可对账量。
#: 为什么需要它：提议「新建某个文件」必须点名文件名，而文件名里的拍号段是**创建拍**的
#: （K7），提议方不知道未来的创建拍 → 提议名与真实产物名永远对不上（实测：提议
#: `journal/0257-….md`，执行者在拍 291 建出 `0291-….md`，芽连领 3 拍耗尽，白烧）。
DIR_OBJECT_SUFFIX = "/"

#: 一次观测最多列多少个子目录（同「有界」纪律：主体可以很宽，一拍不能没完没了）。
#: 目录按**名字**升序取前 N 个（同输入同顺序，可复跑）。
#:
#: **边界写死（M6）**：这是**有界观测面**的机械边界，不是「大概这么多」：
#: 主体目录多于 `SUBJECT_DIR_LIMIT` 时，**名字靠后**的目录不进观测面——后果是
#: 对它的提议/发现会被对象名机械闸（`valid_subject_object`）拒收（不在可对账清单里）。
#: 主体的目录数与目录名**不在这里写**：那是库外的现状，写进注释就会长成假事实
#: （文档里那句陈旧枚举就是这么被订正掉的）。当前值看 `infinigrow status` 的「主体」行。
#: 这里选**最小改法**：
#: 不改排序、不提高上限，只把边界写在代码与文档里（`docs/mechanism.md` §2.1 ＋
#: `docs/growth-subject.md`），并用 `tests/test_subject.py` 把行为**测住**
#: （12 个目录 → 恰好观测前 10 个、第 11 个的名字过不了闸）。
#: 真到了那一天要改（例如「出现过提议/差异的目录优先」），改的是这一条判据，
#: 不是「顺手调个数字」——判据改了要同步文档与测试。
SUBJECT_DIR_LIMIT = 10


def valid_journal_name(name: str) -> bool:
    """`journal/` 文件名的机械校验：`<创建拍号4位>-<创建日期YYYYMMDD>.md`。"""
    return bool(name) and bool(JOURNAL_NAME_RX.match(name))

#: 「这个目录不是内容」的机械排除表（工具缓存/版本库等，不是被生长的东西）
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "venv",
             "node_modules", ".mypy_cache"}

#: 主体根的**轮转归档子树**（K6/G1）：园丁把 `journal/` 超上限的旧篇搬进
#: `<主体根>/archive/journal/`（只移动不删）。这片子树**不属于生长面**：归档件由
#: `store.move_file` 写出来（写新件＋移除源），mtime 是**搬运那一刻**的，比正在长的
#: 内容更新，一旦入观测面就会在「mtime 最新 20」里排到最前，把真内容挤出名额。
#: 实测（主体副本，`IG_JOURNAL_KEEP_FILES=200`）：跨过上限后每次轮转占格 +1，
#: 窗口首格恒为 `archive/journal/…md.<stamp>`，主体文件数还不降——等于没搬走。
#: 所以逐文件窗口、目录对象、文件数/总字节数三处都不算它，对象名闸也不放行
#: （连 `for_proposal` 都不行：不许提议往盲区里长一格）。
#: 只认**主体根下**那一片：`journal/archive/` 是内容侧的同名目录，照旧可观测。
SUBJECT_ARCHIVE_DIR = "archive"


def is_archived(rel_parts: Iterable[str]) -> bool:
    """相对路径（已切成段）是否落在主体根的轮转归档子树里。"""
    parts = tuple(rel_parts)
    return bool(parts) and parts[0] == SUBJECT_ARCHIVE_DIR


def _in_growth_surface(rel_parts: tuple) -> bool:
    """这个相对路径算不算生长面：既不是工具缓存目录，也不是主体的归档子树。"""
    return not is_archived(rel_parts) and not any(p in SKIP_DIRS for p in rel_parts)


@dataclass(frozen=True)
class SubjectFile:
    """主体里一个文件的可查事实（路径用相对名，绝不落绝对路径）。"""

    name: str          # 相对名（POSIX 分隔符）
    bytes: int
    mtime: float


@dataclass(frozen=True)
class SubjectDir:
    """主体里一个子目录的可查事实（N43 目录对象；同样只记相对名）。"""

    name: str          # 相对名（POSIX 分隔符，不带结尾 `/`）
    files: int         # 目录下的文件数（递归，跳过 SKIP_DIRS）


def subject_leaf(root: Path) -> str:
    """主体的名字（用于对象命名与快照；只取目录名，不取整条路径）。"""
    return Path(root).name or str(root)


def subject_path(root: Path, name: str) -> Path:
    """**对象名 → 主体内路径**的唯一解析入口：contain 校验，越界一律拒绝。

    E1（Mimosa high＝路径穿越，CWE-22）的加固点。此前的拼接是裸的 `subject_root / item.name`
    （例如 `engine/org_session.py` 渲染主体摘录时）——名字来自观测/账本，正常形态是主体内
    相对路径（`journal/x.md`），但拼接前不校验就等于「谁往账本里写了奇怪的名字，谁就能把
    读写指到主体根外」。校验与 `core/paths.guard` 同源（`_within`，两边 resolve、
    不跟随越界符号链接），但方向相反：guard 在写盘时按已知 root 兜底，这里是**拼接时**
    就把非法名字挡在门口（读也守——读越界同样是泄漏）。

    为什么加固在**调用侧**（而不是 `encoding.write_text`）：写文本是「编码层」的通用原语，
    它不持有（也不该持有）任何 root 概念；把越界守卫塞进它，等于让编码层替所有调用方
    猜边界，而各调用方的边界（状态根/主体根/仓库根）根本不是同一个。风险的真实形态是
    「**名字 → 路径**」这一个动作，所以校验跟着这个动作走、收在一个函数里。

    拒绝形态：空名、绝对路径（含盘符）、含 `..` 段的相对路径、解析后落在根外的一切路径。
    """
    base = Path(root)
    rel = str(name or "").replace("\\", "/").strip()
    if not rel:
        raise ValueError("空对象名：拒绝解析")
    head = rel.split("/", 1)[0]
    if rel.startswith("/") or ":" in head:
        raise ValueError("对象名必须是主体内相对路径（不得绝对路径）：%r" % name)
    p = base / rel
    from ..core.paths import within_root
    if not within_root(p, base):
        raise PermissionError("拒绝越界访问：%s 不在 %s 之内" % (p, base))
    return p


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
        if not _in_growth_surface(rel_parts):
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


def subject_dirs(root: Path, limit: int = SUBJECT_DIR_LIMIT) -> list[SubjectDir]:
    """列出主体子目录（有界、稳定排序、只读；N43 目录对象）。

    - 不存在的主体根 → 空列表（不抛，同 `subject_files`）；
    - 每个目录报**文件数**（递归计数，跳过 SKIP_DIRS）——这是「这个目录长了几格」的
      机械读数，与文件名无关（提议「再长一格」靠它验收，见模块头 N43）；
    - 排序＝**名字升序**（同输入同顺序，可复跑），上限 `limit`。目录很多时以名字序
      取前 N 个：观测面必须**有界**，没被观测到的目录不会被提议（对象名机械闸只放行
      可对账清单里的对象）。
    """
    base = Path(root)
    if not base.is_dir():
        return []
    out: list[SubjectDir] = []
    for path in sorted(base.rglob("*")):
        if not path.is_dir():
            continue
        rel_parts = path.relative_to(base).parts
        if not _in_growth_surface(rel_parts):
            continue
        out.append(SubjectDir(name="/".join(rel_parts),
                              files=_dir_file_count(path, base)))
    out.sort(key=lambda d: d.name)
    return out[:limit]


def _dir_file_count(path: Path, base: Path) -> int:
    """某个目录下的文件数（递归，只算生长面；与 `_subject_stats` 同一口径）。"""
    count = 0
    for sub in path.rglob("*"):
        if not sub.is_file():
            continue
        if not _in_growth_surface(sub.relative_to(base).parts):
            continue
        count += 1
    return count


def _subject_stats(root: Path) -> tuple[int, int]:
    """一次遍历算「文件总数＋总字节数」（只读；只算生长面，跳过缓存目录与归档子树）。"""
    base = Path(root)
    if not base.is_dir():
        return 0, 0
    total, total_bytes = 0, 0
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        if not _in_growth_surface(path.relative_to(base).parts):
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


def subject_dir_object(rel_name: str) -> str:
    """主体内相对目录名 → 对账空间里的**目录对象**名（`主体/<相对名>/`，N43）。

    结尾的 `/` 是判据的一部分：同一个相对名的文件与目录是两个对象，不许撞名。
    """
    return SUBJECT_PREFIX + rel_name.replace("\\", "/").rstrip("/") + DIR_OBJECT_SUFFIX


def valid_subject_object(obj: str, allowed_objs: set[str],
                         for_proposal: bool = False) -> tuple[bool, str]:
    r"""组织会话产出的对象名**机械闸**（T5/A11）。

    判据（具体状态，反不完全归纳）：
    - **主体根的归档子树直接拒**（G1）：`archive/` 里的东西已被轮转出生长面，
      既不许被 findings 引用，也不许被提议「往里再长一格」——即使有人把它塞进
      `allowed_objs`（拒绝发生在名单比对**之前**）；
    - 对象已在可对账清单（本拍主体观测集）→ 通过；
    - 否则必须是 `主体/<相对路径>`，且相对路径**合法**（非空、无 `..` 段、
      不以 `/`/`\` 开头＝非绝对、无盘符前缀、不以 `.` 开头＝不藏隐藏文件）——
      这是「**提议创建**」的合法路径（`for_proposal=True` 时放行）；
    - findings 描述的是**已观察到的现实**，必须引用可对账清单里的对象
      （`for_proposal=False`：不许发明机械层读不到的对象名——那是空谈的来源）。

    返回 (是否通过, 理由)。此前对象名纪律只是提示词里的约定，没有机械闸。
    """
    rel_head = str(obj or "")
    if rel_head.startswith(SUBJECT_PREFIX):
        head = rel_head[len(SUBJECT_PREFIX):].replace("\\", "/").rstrip("/")
        if is_archived(tuple(head.split("/"))):
            return False, ("%s/ 是轮转归档区，不入生长面（既不可对账也不可提议）"
                           % SUBJECT_ARCHIVE_DIR)
    if obj in allowed_objs:
        return True, "已在可对账清单"
    if not obj.startswith(SUBJECT_PREFIX):
        return False, "对象名必须以 %s 开头（主体对象）" % SUBJECT_PREFIX
    rel = obj[len(SUBJECT_PREFIX):]
    is_dir = rel.endswith(DIR_OBJECT_SUFFIX)            # `主体/<相对路径>/`＝目录对象（N43）
    if is_dir:
        rel = rel[:-len(DIR_OBJECT_SUFFIX)]
    segments = rel.split("/")
    bad = (not rel or any(seg in ("", ".", "..") for seg in segments)
           or rel.startswith(("/", "\\")) or rel.startswith(".")
           or bool(re.match(r"^[A-Za-z]:", rel)))
    if bad:
        return False, "非法相对路径：%r（不许越界/绝对/隐藏）" % rel
    if for_proposal:
        # G3：`journal/` 的直接子文件必须按 K7/A8 的规格命名——不合规格的提议永远对不上
        # 现实（执行者只会按自己的创建拍命名），白烧一拍；这里拒掉，理由点名约定本身。
        if (not is_dir and len(segments) == 2 and segments[0] == JOURNAL_DIR
                and not valid_journal_name(segments[1])):
            return False, ("journal 文件名必须叫 <创建拍号4位>-<创建日期YYYYMMDD>.md，"
                           "收到 %r（K7/A8）" % segments[1])
        return True, ("主体内合法新目录（可提议往它里面长一格）" if is_dir
                      else "主体内合法新相对路径（可提议创建）")
    return False, "不在可对账清单（findings 必须引用现实可查的对象）"


def observe_object(root: Path, obj: str, dimension: str) -> Optional[Observation]:
    """**定键补观测**（M7/N45）：只读「这一个对象 × 这一个维度」，不扩观测面。

    为什么需要：观测（`observe_subject`）与默认预测（`predict_subject_unchanged`）都取
    「mtime 最新 N 个」——主体新增一个文件会把边界上的文件**挤出观测名额**，那一拍它
    既没被观测、又被预测「不变」→ 对账记成「预测未执行」（它其实存在）。
    实测 8 行假差异（拍 267/271/272/274/290/302/306/311），只在中和掉派芽（`act_caused`）
    后留下账本噪声。补观测把这类假差异从根上消掉。

    边界纪律不变：本函数**只按调用方给的键读**，调用方（`engine/tick.augment_observations`）
    只喂**预测里出现过的键**（该集合本来就有界）——不是「把整个主体扫一遍」。

    读不到（对象名不合法/维度不认识/没有这个路径）→ 返回 `None`：不猜、不假装有读数；
    真的缺失仍会被对账如实记成「预测未执行」（拒收≠丢弃）。
    """
    base = Path(root)
    leaf = subject_leaf(base)
    if obj == leaf:                                   # 主体根（存在性／文件数）
        if dimension == "存在性":
            return Observation(leaf, "存在性", EXISTS if base.is_dir() else MISSING, "主体根")
        if dimension == "文件数":
            return Observation(leaf, "文件数", str(subject_count(base)), "主体根")
        return None
    if not obj.startswith(SUBJECT_PREFIX):
        return None
    rel = obj[len(SUBJECT_PREFIX):].replace("\\", "/")
    is_dir = rel.endswith(DIR_OBJECT_SUFFIX)
    if is_dir:
        rel = rel[:-len(DIR_OBJECT_SUFFIX)]
    if not rel or any(seg in ("", ".", "..") for seg in rel.split("/")):
        return None                                   # 非法相对路径：不越界读
    if is_archived(tuple(rel.split("/"))):
        return None                                   # G1：归档不入生长面，不补读数
    path = base / rel
    if is_dir:
        if dimension != "文件数":
            return None
        if not path.is_dir():
            return Observation(subject_dir_object(rel), "文件数", "0", "目录不存在")
        return Observation(subject_dir_object(rel), "文件数",
                           str(_dir_file_count(path, base)), "主体目录:%s" % rel)
    if dimension == "存在性":
        return Observation(subject_object(rel), "存在性",
                           EXISTS if path.is_file() else MISSING, "主体:%s" % rel)
    if dimension == "字节数":
        try:
            return Observation(subject_object(rel), "字节数", str(path.stat().st_size),
                               "主体:%s" % rel)
        except OSError:
            return None
    return None


def observe_subject(root: Path, limit: int = SUBJECT_FILE_LIMIT) -> list[Observation]:
    """机械观测主体 → W回 清单（存在性 / 文件数 / 每个文件 / 每个子目录的格数）。

    「文件数」这一条是主体层面的**生长读数**：它变了就说明主体真的长了/缩了，
    与该文件是谁、内容是什么无关（内容级判断归执行者与组织会话，这里只报可查事实）。

    **N42 修复**：文件数用**真实总数**（`subject_count`，不受 `limit` 影响）——
    主体文件超过观测上限时自报数字也必须如实；逐文件观测仍按 `limit` 有界
    （取 **mtime 最新**的 N 个，旧的不会永久霸占名额）。

    **每个文件同时报「存在性」与「字节数」**：观测到的维度必须和预测的维度对称——
    只观测字节数、不观测存在性，会让「预测某文件存在」变成「预测未执行」的假差异
    （实测：首拍就因此凭空长出一根芽）。

    **每个子目录报「文件数」（N43）**：目录对象 `主体/<相对路径>/` 让「往这个目录里
    再长一格」成为一个**名字无关**的可对账量——提议新建文件时点不出未来的创建拍
    （K7 的拍号段＝创建拍），点名就必然对不上（见 `DIR_OBJECT_SUFFIX` 的注释）。
    """
    base = Path(root)
    leaf = subject_leaf(base)
    files = subject_files(base, limit=limit)
    dirs = subject_dirs(base)
    exists = base.is_dir()
    out = [
        Observation(leaf, "存在性", EXISTS if exists else MISSING, "主体根"),
        Observation(leaf, "文件数", str(subject_count(base)), "主体根"),
    ]
    for item in dirs:
        out.append(Observation(subject_dir_object(item.name), "文件数", str(item.files),
                               "主体目录:%s" % item.name))
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

    **目录对象（N43）与观测对称**：每个子目录一条 `文件数` 预测。组织会话提议
    「往 `主体/journal/` 里再长一格」时，写差额（`+1`）覆盖默认值——
    领做/对账时按当时现实锚定（见 `engine/tick.resolve_relative_predictions`），
    文件名由执行者按其真实创建拍命名（K7），验收不含文件名。
    """
    base = Path(root)
    leaf = subject_leaf(base)
    files = subject_files(base, limit=limit)
    dirs = subject_dirs(base)
    exists = base.is_dir()
    out = [
        Prediction(leaf, "存在性", EXISTS if exists else MISSING, tick=tick,
                   evidence="预测:主体根"),
        Prediction(leaf, "文件数", str(subject_count(base)), tick=tick,
                   evidence="预测:主体根"),
    ]
    for item in dirs:
        out.append(Prediction(subject_dir_object(item.name), "文件数", str(item.files),
                              tick=tick, evidence="预测:主体目录:%s" % item.name))
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

    `dirs`（N43）＝子目录与各自的文件数（目录对象 `主体/<相对路径>/` 的读数）。
    组织会话扫现实（K14）与「再长一格」的提议都读它。
    """
    base = Path(root)
    files = subject_files(base, limit=limit)
    dirs = subject_dirs(base)
    count, total_bytes = _subject_stats(base)
    return {
        "tick": tick,
        "root_name": subject_leaf(base),
        "exists": base.is_dir(),
        "file_count": count,
        "total_bytes": total_bytes,
        "files": [{"name": f.name, "bytes": f.bytes} for f in files],
        "dirs": [{"name": d.name, "files": d.files} for d in dirs],
        "object_prefix": SUBJECT_PREFIX,
        "dir_object_suffix": DIR_OBJECT_SUFFIX,
        "file_limit": limit,
        "observed_files": len(files),
        "observed_dirs": len(dirs),
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
