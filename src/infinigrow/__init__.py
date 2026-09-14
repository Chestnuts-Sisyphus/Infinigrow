# -*- coding: utf-8 -*-
"""Infinigrow —— 让「生长」本身可以无限继续的开源引擎。

一句话：**引擎只做一件事——预测、对账、把差异变成下一根芽。**

公设（BW 底层，机制语言一律说边）：

| 箭头 | 方向 | 含义 |
|---|---|---|
| 判读 | W→B | 看懂现实：现实输入长出一条认知 |
| 行动 | B→W | 会做：认知变成现实变化 |
| 原理 | B→B | 想通：从已有认知推出新认知 |
| 固化 | W→W | 自动：同输入不再烧认知 |

B=认知（belief），W=现实（world）。**现实是唯一裁判**：手前写下预期（B猜），
手后由现实回答（W回），二者不符处＝差异；**差异是芽的唯一来源**。

设计红线（v2 起写死，可被静态规则守护）：

1. **零差异零芽**：执行会话不自造芽；芽只由对账产出的差异点生（N 差异 N 芽）。
2. **状态与代码分家**：状态根可参数化，默认在仓库内 `state/`，且不进版本库；
   **生长主体**（被长的那份现实）默认在仓库**之外**，与代码分家。
3. **零绝对路径**：源码与提示词里不出现任何本机路径；一律走配置项；
   连状态产物也不许含本机路径（`tools/check_no_abs_paths.py` 守）。
4. **追加型账本**：账本只增不改，改只动队列不动账本；历史由**轮转**搬进归档（只移动不删）。
5. **失败必须可见**：任何被吞掉的异常都是缺陷；心跳写不进去要响亮退出；
   执行者失败与拍失败**分开计数**（故障位置不同）。
6. **写盘只有一条路**：`ledger/store.py`（越界守卫 ＋ 原子替换），规则 R8 守。
7. **退出码单一来源**：`core/exit_codes.py`，规则 R7 守。
8. **断流判据用机械时间戳**：不用模型自述的时间。

公开 API：`run_tick`（跑一拍）、`run_gardener`（机械园丁）、`reconcile`（对账）、
`scan`（静态规则扫描）。三块运行体在各自模块里可直接 import：
`engine.subject`（生长主体）、`engine.executor`（执行者通道）、`engine.org_session`（组织会话）。
"""
from .core.config import Settings, load_settings
from .core.paths import StateLayout, resolve_state
from .engine.model import Diff, DiffKind, Edge, Observation, Prediction, Sprout, SproutOrigin
from .engine.reconcile import rate_table, reconcile, redemption_rate
from .engine.sprout_sources import (from_diffs, from_maturity_cap,
                                    from_unused_library)
from .engine.tick import TickResult, run_tick
from .garden.gardener import GardenerReport, run_gardener
from .rules.static_scan import scan
from .scheduler.triggers import should_run_org_session

__version__ = "2.2.1"
__codename__ = "Infinigrow"

__all__ = [
    "Settings", "load_settings", "StateLayout", "resolve_state",
    "Edge", "Prediction", "Observation", "Diff", "DiffKind", "Sprout", "SproutOrigin",
    "reconcile", "redemption_rate", "rate_table",
    "from_diffs", "from_maturity_cap", "from_unused_library",
    "run_tick", "TickResult", "run_gardener", "GardenerReport",
    "scan", "should_run_org_session",
    "__version__", "__codename__",
]
