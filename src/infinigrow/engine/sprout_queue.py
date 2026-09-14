# -*- coding: utf-8 -*-
"""芽队列纪律：上限、冻结、连领上限、取题排序（冷启动随机化 → 字典序）。

三条纪律都是从 v1 的「原地打转」现场换来的：

- **同对象同维度合并**（新顶旧）：同一个差异反复出现只是一个差异，不是一百个芽；
  v1 的病灶是 221 根待长里 186 根同族、题面逐字相同——合并律就是治它的。
- **上限 50 + 溢出进冻结区**：只动队列不动账本，冻结≠删除（可回看、可重新点亮）。
- **连领上限 3 拍**（长任务芽豁免）：防一根芽霸占取题位。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..ledger.store import read_jsonl, write_jsonl_work_file
from .model import SPROUTING_KINDS, Sprout


@dataclass
class SproutQueue:
    """活跃芽队列（工作文件，可覆写；冻结区与账本全留）。"""

    cap: int = 50
    lead_limit: int = 3
    cold_start_ticks: int = 50
    sprouts: list[Sprout] = field(default_factory=list)
    frozen: list[Sprout] = field(default_factory=list)

    # ---------------------------------------------------------------- 增删
    def add(self, sprout: Sprout) -> tuple[str, Optional[Sprout]]:
        """加入一根芽。返回 (动作, 被挤出的芽)。

        动作取值：`added`｜`replaced`（同对象同维度，新顶旧）｜`duplicate`（同 id 已存在）。
        """
        for i, exist in enumerate(self.sprouts):
            if exist.id == sprout.id:
                return "duplicate", None
            if exist.key == sprout.key:
                self.sprouts[i] = sprout          # 同对象同维度：新顶旧（单槽语义）
                return "replaced", None
        self.sprouts.append(sprout)
        return "added", self._enforce_cap()

    def _enforce_cap(self) -> Optional[Sprout]:
        """超限把**最旧**的挤出到冻结区（按 created_tick 升序，稳定可预期）。"""
        if len(self.sprouts) <= self.cap:
            return None
        self.sprouts.sort(key=lambda s: (s.created_tick, s.id))
        moved = self.sprouts.pop(0)
        self.frozen.append(moved)
        return moved

    def revive(self, sprout: Sprout, tick: int) -> None:
        """冻结区轮转：差异重新出现＝**重新点亮**（挂起≠死亡）。

        重新点亮会把 `created_tick` 刷成当前拍、并清掉连领计数——否则一根很旧的芽
        刚复活就会因为「最旧」被再次挤出队列（冻结-复活的无意义抖动）。
        """
        for i, f in enumerate(self.frozen):
            if f.id == sprout.id:
                self.frozen.pop(i)
                break
        sprout.created_tick = tick
        sprout.leads = 0
        sprout.last_lead_tick = None
        self.add(sprout)

    def review_frozen(self, recent_diffs, tick: int, max_relight: int = 3) -> list[str]:
        """冻结区重看（T4/A5）：每 `frozen_review_every` 拍重看一次冻结区。

        判据（具体状态，反不完全归纳）：冻结芽的 (对象, 维度) 在**本拍差异**里仍以
        **未消解**形态出现（预测未执行／预测外发现／预测内错）→ 重新点亮（挂起≠死亡）；
        否则记为「未点亮＋原因」。每拍最多重亮 `max_relight` 根，防批量复活把队列顶爆
        （刚复活的刚刷新过出生拍，不会被「最旧」立即挤出）。

        此前 `frozen_review_every` 只有配置项没有调用方——冻结区一旦被挤满就永不重看，
        冻结芽只能在下次「同一差异重现」时靠 `revive` 复活。现在引擎每 N 拍自己重看。
        """
        alive = {(d.obj, d.dimension) for d in recent_diffs
                 if d.kind in SPROUTING_KINDS}
        notes: list[str] = []
        relit = 0
        for s in sorted(self.frozen, key=lambda x: (x.created_tick, x.id)):
            if (s.obj, s.dimension) in alive:
                if relit < max_relight:
                    self.revive(s, tick)
                    notes.append("冻结区重看：重新点亮 %s（%s×%s）"
                                 % (s.id, s.obj, s.dimension))
                    relit += 1
                else:
                    notes.append("冻结区重看：未点亮 %s（原因：本拍重亮已达上限）"
                                 % s.id)
            else:
                notes.append("冻结区重看：未点亮 %s（原因：差异已消解或未重现）" % s.id)
        return notes

    # ---------------------------------------------------------------- 取题
    def eligible(self, tick: int) -> list[Sprout]:
        """可领的芽：连领未超限，或标记长任务。"""
        out = []
        for s in self.sprouts:
            if s.long_task or s.leads < self.lead_limit:
                out.append(s)
        return out

    @staticmethod
    def order_key(sprout: Sprout) -> tuple:
        """取题顺序键＝**最久没被碰过的优先**；平局按出生拍、再按字典序（全可复现）。

        ⚠ 这里踩过一个真坑（T12 现场演练抓到的）：原先直接按 `id` 字典序取题，而芽 ID
        带**芽源前缀**（`sp`＝差异、`cap`＝成熟链封顶、`lib`＝能力库未用），
        于是 `cap*` 会**永远插在** `sp*` 前面——连跑 12 拍，取到的全是封顶芽，
        主芽源（差异）被饿死。**那是排序偏置，不是纪律**。

        现在的口径与提示词里写的一致：「同域冷却 ＋ 最久未碰优先（平局决胜按字典序）」
        —— 代码与提示词不再各说各话。
        """
        touched = (sprout.last_lead_tick if sprout.last_lead_tick is not None
                   else sprout.created_tick)
        return (touched, sprout.created_tick, sprout.id)

    def take_topic(self, tick: int, rng_seed: Optional[int] = None) -> Optional[Sprout]:
        """取本拍要做的芽。

        冷启动期（前 `cold_start_ticks` 拍）随机化＝避免「排序偏好」把早期样本压偏；
        之后就按 `order_key`（最久未碰 → 出生拍 → 字典序）——同一输入永远同一选择，
        可复查、可复现。随机用 `random.Random(seed)` 且 seed 默认取拍号（CI 里也能跑）。
        """
        pool = self.eligible(tick)
        if not pool:
            return None
        if tick <= self.cold_start_ticks:
            # 这里要的是**可复现的确定性伪随机**（同拍号同选择，CI 可复跑），
            # 不是密码学随机：冷启动随机化只为打散早期排序偏好，不涉及任何安全用途。
            rng = random.Random(tick if rng_seed is None else rng_seed)  # noqa: S311
            return rng.choice(sorted(pool, key=self.order_key))
        return sorted(pool, key=self.order_key)[0]

    def mark_lead(self, sprout: Sprout, tick: int) -> None:
        sprout.leads += 1
        sprout.last_lead_tick = tick

    # ---------------------------------------------------------------- 持久化
    def to_records(self) -> list[dict]:
        return [s.as_record() for s in self.sprouts]

    def save(self, active_path: Path, frozen_path: Path, root: Path) -> None:
        """整份重写队列（工作文件可覆写；账本不受影响＝冻结/合并只动队列）。"""
        for path, items in ((active_path, self.sprouts), (frozen_path, self.frozen)):
            write_jsonl_work_file(path, [s.as_record() for s in items], root)

    @classmethod
    def load(cls, active_path: Path, frozen_path: Path, **kwargs) -> "SproutQueue":
        q = cls(**kwargs)
        q.sprouts = [Sprout.from_record(r) for r in read_jsonl(active_path)]
        q.frozen = [Sprout.from_record(r) for r in read_jsonl(frozen_path)]
        return q

    def summary(self) -> dict:
        by_origin: dict[str, int] = {}
        for s in self.sprouts:
            by_origin[s.origin.value] = by_origin.get(s.origin.value, 0) + 1
        return {"active": len(self.sprouts), "frozen": len(self.frozen),
                "by_origin": by_origin}
