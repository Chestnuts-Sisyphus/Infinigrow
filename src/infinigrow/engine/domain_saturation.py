# -*- coding: utf-8 -*-
"""域饱和判据：同一「对象域 × 标准可验证量」**只养一根未完成芽**（T7/G8 的实现层）。

v1 的病灶是「同域可无限复述」：队列里 221 根待长、186 根同族、题面逐字相同。
v2 已有的三道收敛（同对象同维度合并 / 上限 50 / 冻结区）只治**同一个对象**；
同一**域**（一个目录下的一堆对象）仍可以源源不断地各生一根芽。本模块补上这一条。

判据全是**具体状态**（不许用「频率高」这类归纳）：

| 概念 | 机械定义 |
|---|---|
| 对象域 | 对象名里最后一段 `/` 之前的部分；没有 `/` 的对象**自成域**（＝退化成现有合并律） |
| 标准可验证量 | 差异的**维度**（如 `字节数`、`存在性`） |
| 饱和 | 该 (域 × 量) 已有**未完成芽**（在活跃队列或冻结区里都算未完成） |
| 吸收 | 饱和时的新差异**不新生芽**：登记到已有芽的 `absorbed` 计数（差异本身照旧入账，不隐藏） |
| 解冻① | 该 (域 × 量) **产出了新的量**（新差异的 actual ≠ 立芽时的 actual） |
| 解冻② | 该 (域 × 量) 的芽**被消解**（本拍对账为「预测内对」）或**已不在队列**（被顶替/消费） |

一句话：**同一域同一量，同时只允许一个问题没解决**。要再立一根，先拿出新证据（新的量）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

from ..core.paths import StateLayout, guard
from ..ledger.store import LedgerError, write_work_file
from .model import Diff

DOMAIN_SEP = "|"          # 域 与 量 的分隔符（域来自对象名，不会含它）
MARKER = "domains"        # 工作文件标记（防截断洗状态）


def domain_key(obj: str, dimension: str) -> tuple[str, str]:
    """对象 + 维度 → (对象域, 标准可验证量)。规则见模块头（无 `/` 的对象自成域）。"""
    text = str(obj).replace("\\", "/")
    domain = text.rsplit("/", 1)[0] if "/" in text else text
    return (domain or text, str(dimension))


def encode(domain: str, dimension: str) -> str:
    return "%s%s%s" % (domain, DOMAIN_SEP, dimension)


def value_at_freeze(diffs: Iterable[Diff], obj: str, dimension: str) -> str:
    """在给定差异里找 (对象, 维度) 的**实际值**——立芽时把它记下来当「冻结时的量」。

    有了它才谈得上「产出了新的量」：后来的差异 actual 与它不同 → 解冻。
    """
    for diff in diffs:
        if diff.obj == obj and diff.dimension == dimension:
            return str(diff.actual)
    return ""


@dataclass
class Claim:
    """一个 (域 × 量) 上的占用：它归哪根芽、立芽时的量是多少、吸收了多少次。"""

    sprout_id: str
    obj: str
    dimension: str
    value_at_freeze: str
    first_tick: int = 0
    last_tick: int = 0
    absorbed: int = 0
    last_pointer: str = ""

    def as_record(self) -> dict:
        return {"sprout_id": self.sprout_id, "obj": self.obj, "dimension": self.dimension,
                "value_at_freeze": self.value_at_freeze, "first_tick": self.first_tick,
                "last_tick": self.last_tick, "absorbed": self.absorbed,
                "last_pointer": self.last_pointer}

    @classmethod
    def from_record(cls, rec: dict) -> "Claim":
        return cls(sprout_id=str(rec.get("sprout_id") or ""), obj=str(rec.get("obj") or ""),
                   dimension=str(rec.get("dimension") or ""),
                   value_at_freeze=str(rec.get("value_at_freeze") or ""),
                   first_tick=int(rec.get("first_tick") or 0),
                   last_tick=int(rec.get("last_tick") or 0),
                   absorbed=int(rec.get("absorbed") or 0),
                   last_pointer=str(rec.get("last_pointer") or ""))


@dataclass
class GateResult:
    """一次过闸的结果：放行的差异、被吸收的差异、发生的解冻。"""

    kept: list[Diff] = field(default_factory=list)
    absorbed: list[Diff] = field(default_factory=list)
    released: list[str] = field(default_factory=list)
    absorbed_by_key: dict[str, int] = field(default_factory=dict)

    @property
    def summary(self) -> dict:
        return {"kept": len(self.kept), "absorbed": len(self.absorbed),
                "released": len(self.released)}


class DomainState:
    """域饱和状态（工作文件 `state/domains.json`：可覆写，账本才是不动的历史）。"""

    def __init__(self, claims: Optional[dict[str, Claim]] = None) -> None:
        self.claims: dict[str, Claim] = claims or {}

    # ------------------------------------------------------------- 读写
    @classmethod
    def load(cls, path: Path) -> "DomainState":
        if not Path(path).is_file():
            return cls()
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()                       # 坏文件＝空状态（不静默改账，只是重新起算）
        claims = {}
        for key, rec in (data.get("claims") or {}).items():
            if isinstance(rec, dict):
                claims[str(key)] = Claim.from_record(rec)
        return cls(claims)

    def save(self, layout: StateLayout) -> Path:
        path = layout.domains
        guard(path, layout.root)
        payload = {"marker": MARKER, "count": len(self.claims),
                   "claims": {k: v.as_record() for k, v in sorted(self.claims.items())}}
        try:
            write_work_file(path, json.dumps(payload, ensure_ascii=False, indent=2),
                            layout.root, require_markers=(MARKER,))
        except (LedgerError, OSError):
            pass                                # 状态文件写不动不该打断一拍（账本已记事实）
        return path

    # ------------------------------------------------------------- 同步与解冻
    def sync(self, live_sprout_ids: Iterable[str], ok_keys: Iterable[tuple[str, str]],
             tick: int) -> list[str]:
        """按当前事实清理占用：芽不在了 / 芽被消解了 → 释放该 (域 × 量)。

        `live_sprout_ids`＝活跃队列 ∪ 冻结区里的芽 ID（**冻结也是未完成**，不释放）；
        `ok_keys`＝本拍对账为「预测内对」的 (对象, 维度)（＝消解）。
        """
        live = set(live_sprout_ids)
        ok = set(ok_keys)
        released: list[str] = []
        for key, claim in list(self.claims.items()):
            gone = claim.sprout_id not in live
            done = (claim.obj, claim.dimension) in ok
            if gone or done:
                self.claims.pop(key, None)
                released.append("%s（%s）" % (key, "已消解" if done else "芽已不在队列"))
        return released

    # ------------------------------------------------------------- 过闸
    def gate(self, diffs: Sequence[Diff], tick: int) -> GateResult:
        """把差异分成「放行立芽」与「被吸收」两堆（只对**会产芽**的差异起作用）。

        **同拍内也要守配额**：一拍里可能有同域的多个差异同时出现（例如主体里两个文件
        同时不对）。只有第一条放行立芽，其余进吸收计数——否则「一批差异」就能绕过
        「同一域同一量只养一根未完成芽」。顺序是确定的（差异清单本身的顺序，
        而清单来自对账，顺序可复跑）。
        """
        result = GateResult()
        accepted: set[str] = set()
        for d in diffs:
            if not d.spawns:
                result.kept.append(d)          # 不产芽的差异（如缺指针）不受域配额约束
                continue
            domain, dimension = domain_key(d.obj, d.dimension)
            key = encode(domain, dimension)
            claim = self.claims.get(key)

            if claim is None:
                if key in accepted:            # 同拍内第二条：吸收（不立第二根）
                    result.absorbed.append(d)
                    result.absorbed_by_key[key] = result.absorbed_by_key.get(key, 0) + 1
                else:
                    accepted.add(key)
                    result.kept.append(d)
                continue

            if claim.value_at_freeze != str(d.actual):
                # 新产出的量 → 解冻（本拍这条放行，占用在立芽后重新登记）
                result.released.append("%s（产出新量 %s→%s）"
                                       % (key, claim.value_at_freeze, d.actual))
                self.claims.pop(key, None)
                accepted.add(key)
                result.kept.append(d)
                continue

            claim.absorbed += 1
            claim.last_tick = tick
            claim.last_pointer = d.evidence or claim.last_pointer
            result.absorbed.append(d)
            result.absorbed_by_key[key] = result.absorbed_by_key.get(key, 0) + 1
        return result

    def claim(self, obj: str, dimension: str, sprout_id: str, value_at_freeze: str,
              tick: int, pointer: str = "", absorbed: int = 0) -> None:
        """登记占用：这根芽占住了它的 (域 × 量)。

        `absorbed`＝本拍已经因为配额被吸收的次数（同拍内第二次及以后的同域同量差异）——
        占用要带着这个数开始，否则「吸收了多少」会在立芽那一刻被清零。
        """
        domain, dim = domain_key(obj, dimension)
        self.claims[encode(domain, dim)] = Claim(
            sprout_id=sprout_id, obj=obj, dimension=dim, value_at_freeze=str(value_at_freeze),
            first_tick=tick, last_tick=tick, absorbed=int(absorbed),
            last_pointer=pointer)

    def as_dict(self) -> dict:
        return {k: v.as_record() for k, v in sorted(self.claims.items())}

    def summary(self) -> dict:
        return {"占用": len(self.claims),
                "累计吸收": sum(c.absorbed for c in self.claims.values())}
