# -*- coding: utf-8 -*-
"""BW 公设的数据模型（全引擎的词汇表，改这里＝改公设）。

只有两个仓库：**B=认知**、**W=现实**；一切结构都是两者之间的**边**：

    判读 READ      W→B   看懂现实（现实输入长出一条认知）
    行动 ACT       B→W   会做（认知变成现实变化）
    原理 PRINCIPLE B→B   想通（从已有认知推出新认知）
    固化 SOLIDIFY  W→W   自动（同输入不再烧认知）

**成熟链**＝一条经验从生到熟的四步：判读 → 行动 → 原理 → 固化。
知识＝边；引擎的进步＝边长了（不是「写了多少字」）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Edge(str, Enum):
    """四箭头。值用中文，是因为它就是机制语言（对外 API 名一律英文）。"""

    READ = "判读"
    ACT = "行动"
    PRINCIPLE = "原理"
    SOLIDIFY = "固化"


EDGE_DIRECTION = {
    Edge.READ: "W→B",
    Edge.ACT: "B→W",
    Edge.PRINCIPLE: "B→B",
    Edge.SOLIDIFY: "W→W",
}

#: 成熟链：一条经验从生到熟的固定四步（第四步即「固化」＝封顶）
MATURITY_CHAIN: tuple[Edge, ...] = (Edge.READ, Edge.ACT, Edge.PRINCIPLE, Edge.SOLIDIFY)
MATURITY_CAP = len(MATURITY_CHAIN)          # 4：封顶＝已固化

#: 每步的机械「长没长」判据（写进文档与静态规则，改这里＝改判据）
EDGE_GROWTH_TEST = {
    Edge.READ: "该对象的预测在下一次 W回 中被证实",
    Edge.ACT: "该动作执行后 W 侧对象发生可查变化",
    Edge.PRINCIPLE: "推出的认知在从未测过的域被验证",
    Edge.SOLIDIFY: "同一类输入不再烧认知（自动通过）",
}


class DiffKind(str, Enum):
    """对账产出的差异四类（只此四类，不许发明第五类）。"""

    WRONG = "预测内错"        # 预期态变 ≠ 实际态变 → 产芽
    OK = "预测内对"           # 预期 = 实际 → **不产芽**（计入被验证）
    UNPREDICTED = "预测外发现"  # 实际有、预测没提 → 产芽
    NOT_EXECUTED = "预测未执行"  # 预测写了没做 → 产芽


#: 产芽的差异类型（N 差异 N 芽；「预测内对」不产芽——这就是「零差异零芽」）
SPROUTING_KINDS = (DiffKind.WRONG, DiffKind.UNPREDICTED, DiffKind.NOT_EXECUTED)


class SproutOrigin(str, Enum):
    """芽的来源（三类，全部由对账/账本机械判定；**执行会话不自产芽**）。"""

    DIFF = "差异对账"          # 主源：对账产出的差异点
    MATURITY_CAP = "成熟链封顶"  # ①对象爬到第 4 步（已固化）→ 开应用面
    LIBRARY_UNUSED = "能力库未用"  # ②能力库条目长期未被消费 → 为何未用／别域是否成立


@dataclass(frozen=True)
class Prediction:
    """B猜：动手前在认知侧写下的、可对账的承诺。"""

    obj: str
    dimension: str
    expected: str
    tick: Optional[int] = None
    evidence: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return (self.obj, self.dimension)


@dataclass(frozen=True)
class Observation:
    """W回：动手后现实侧给出的、可查的回答。"""

    obj: str
    dimension: str
    actual: str
    evidence: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return (self.obj, self.dimension)


@dataclass(frozen=True)
class Diff:
    """差异点：对账的最小产出，也是芽的唯一主源。

    `evidence`（证据指针）强制：无指针的差异进「待补指针」区，不直接成芽。
    """

    kind: DiffKind
    obj: str
    dimension: str
    expected: str
    actual: str
    evidence: str
    tick: int

    @property
    def spawns(self) -> bool:
        return self.kind in SPROUTING_KINDS and bool(self.evidence)

    @property
    def key(self) -> tuple[str, str]:
        return (self.obj, self.dimension)

    def as_record(self) -> dict:
        return {
            "kind": self.kind.value, "obj": self.obj, "dimension": self.dimension,
            "expected": self.expected, "actual": self.actual,
            "evidence": self.evidence, "tick": self.tick,
            "spawns": self.spawns,
        }


@dataclass
class Sprout:
    """芽：一个**可被下一步动作独立消解的差异**（不是「想做的事」）。

    字段里的 `predicted_edge`/`maturity_step` 是**增益预测**（事前选的边与步）——
    做事之后由兑现账判「兑现/打脸」，这是组织会话的业绩来源。

    `expected_value`＝**这株芽带着的预期**（来自产出它的那个差异的 `expected`）：
    引擎当初预测「该对象该维度应当是什么样」。领做它的那一拍，把它**并进本拍 B猜**
    （见 `engine/tick.py`）——否则会出现一种最憋屈的记账：执行者真把差异消解了，
    却因为动手那一拍的预测清单里没有这一条而记成「打脸」。
    """

    id: str
    obj: str
    dimension: str
    pointer: str                     # 差异指针（来源行/账本行），强制
    origin: SproutOrigin
    created_tick: int
    predicted_edge: Optional[Edge] = None
    maturity_step: Optional[int] = None
    expected_value: Optional[str] = None   # 产出它的差异的预期值（可空）
    leads: int = 0                   # 已被领取次数（防霸占）
    last_lead_tick: Optional[int] = None
    long_task: bool = False          # 长任务芽豁免连领限制

    @property
    def key(self) -> tuple[str, str]:
        return (self.obj, self.dimension)

    def as_record(self) -> dict:
        return {
            "id": self.id, "obj": self.obj, "dimension": self.dimension,
            "pointer": self.pointer, "origin": self.origin.value,
            "created_tick": self.created_tick,
            "predicted_edge": self.predicted_edge.value if self.predicted_edge else None,
            "maturity_step": self.maturity_step, "leads": self.leads,
            "last_lead_tick": self.last_lead_tick, "long_task": self.long_task,
            "expected_value": self.expected_value,
        }

    @classmethod
    def from_record(cls, rec: dict) -> "Sprout":
        edge = rec.get("predicted_edge")
        return cls(
            id=rec["id"], obj=rec["obj"], dimension=rec["dimension"],
            pointer=rec.get("pointer", ""), origin=SproutOrigin(rec["origin"]),
            created_tick=rec.get("created_tick", 0),
            predicted_edge=Edge(edge) if edge else None,
            maturity_step=rec.get("maturity_step"), leads=rec.get("leads", 0),
            last_lead_tick=rec.get("last_lead_tick"),
            long_task=rec.get("long_task", False),
            expected_value=rec.get("expected_value"),
        )


@dataclass(frozen=True)
class OutcomeRecord:
    """兑现账一行：预测边 vs 实际边（兑现/打脸）+ 指针 + 拍号 ＋ **是不是样本**。

    兑现率**现算**，不存缓存：按「对象域 × 预测边 × 实际边」这个机械锚分桶，
    防「换类名操纵统计」。对象域与域饱和判据用同一条规则（对象名里最后一段 `/`
    之前的部分；无 `/` 者自成域）——机械锚只认这一处定义。

    `sampled`（G6 的处方）：**没有执行者动手的一拍不是样本**。机械拍不做语义判断、
    也不产出真实生长，它的「打脸」只能说明没动手，不能当成兑现率的分母——
    否则「兑现率 0」会被读成「引擎很差」，而真相是「还没接执行者」。
    """

    sprout_id: str
    predicted_edge: Optional[Edge]
    actual_edge: Optional[Edge]
    redeemed: bool
    pointer: str
    tick: int
    sampled: bool = True
    verifiable: bool = True     # 该芽的维度机械层读得到吗？读不到＝不可对账（不计入兑现率）
    obj: str = ""               # 对象名（分桶用：对象域＝最后一段 `/` 之前；旧行无此字段＝「（无对象）」）

    def bucket(self) -> tuple:
        domain = self.obj.rsplit("/", 1)[0] if "/" in self.obj else self.obj
        return (domain or "（无对象）",
                self.predicted_edge.value if self.predicted_edge else "无",
                self.actual_edge.value if self.actual_edge else "无")

    def as_record(self) -> dict:
        return {
            "sprout_id": self.sprout_id,
            "predicted_edge": self.predicted_edge.value if self.predicted_edge else None,
            "actual_edge": self.actual_edge.value if self.actual_edge else None,
            "redeemed": self.redeemed, "pointer": self.pointer, "tick": self.tick,
            "sample": self.sampled, "verifiable": self.verifiable, "obj": self.obj,
        }
