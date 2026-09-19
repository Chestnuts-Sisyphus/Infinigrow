# -*- coding: utf-8 -*-
"""配置：一切「随机器/随使用者而异」的值都从这里来，源码里不留常量。

优先级（后者覆盖前者）：
    内置默认 → 配置文件（toml 或 json）→ 环境变量（`IG_*`）→ 显式传参

为什么不做成「一堆全局常量」：v1 的绝对路径就是那么长出来的——某天为了本机跑通
写死一个路径，之后再也搬不走。这里把「本机相关性」压缩成一张表：

| 配置项 | 环境变量 | 默认 | 说明 |
|---|---|---|---|
| `state_root` | `IG_STATE_ROOT` | `<repo>/state` | 状态根（账本/队列/心跳）|
| `subject_root` | `IG_SUBJECT_ROOT` | `<repo 同级>/<仓库名>-subject` | **生长主体**（引擎在长什么）|
| `prompts_dir` | `IG_PROMPTS_DIR` | `<repo>/prompts` | 提示词目录 |
| `key_dir` | `IG_KEY_DIR` | 空 | 外部凭据目录（空＝不需要凭据）|
| `proxy_url` | `IG_PROXY_URL` | 空 | 出网代理（空＝直连）|
| `executor` | `IG_EXECUTOR` | 空 | **执行者命令**（空＝机械拍，零 token/零凭据/不出网）|
| `executor_timeout_s` | `IG_EXECUTOR_TIMEOUT_S` | 120 | 单次执行者调用超时（秒）|
| `llm_command` | `IG_LLM_COMMAND` | 空 | 旧字段（与 `executor` 同义，保留兼容）|
| `llm_model` | `IG_LLM_MODEL` | 空 | 模型标识（透传给执行者，供其自行取用）|
| `org_gap_ticks` | `IG_ORG_GAP_TICKS` | 5 | 组织段最长空窗（拍）——读的是**尝试账**：只有组织段真的起跑过才算一次，**没接执行者时它根本不跑**（不写行、不占冷却窗）|
| `org_cooldown_min` | `IG_ORG_COOLDOWN_MIN` | 30 | 组织段冷却（分钟，机械时间戳口径）；**实测节奏中位 40.0 分钟**——触发判据④只认「上一拍安静」（数的是差异账**行数**≈0.23 拍），生长拍会把它清零（反相关，N58）；语义与实测见 `docs/mechanism.md` §2.3（Q3/A2/A9）|
| `tick_minutes` | `IG_TICK_MINUTES` | 10 | 调度间隔（分钟；安装计划任务时读它）|
| `queue_cap` | `IG_QUEUE_CAP` | 50 | 活跃芽队列上限 |
| `lead_limit` | `IG_LEAD_LIMIT` | 3 | 同一芽连领上限（拍）|
| `cold_start_ticks` | `IG_COLD_START_TICKS` | 50 | 冷启动随机化拍数（之后走字典序）|
| `frozen_review_every` | `IG_FROZEN_REVIEW_EVERY` | 20 | **冻结区重看节奏（拍）**：每这么多拍扫一次冻结区，给其中的芽「重新点亮」（回到活跃队列）的机会 |
| `frozen_requestion_ticks` | `IG_FROZEN_REQUESTION_TICKS` | 300 | 冻结芽**重问**年限（拍）：冻结满这么多拍仍未被点亮 → 允许重新立芽（挂起≠永久封存）|
| `frozen_cap` | `IG_FROZEN_CAP` | 5000 | 冻结区行数上限（超限＝最旧的**移动**进 `state/archive/`，只移不删）|
| `frozen_keep_tail` | `IG_FROZEN_KEEP_TAIL` | 4000 | 冻结区整理后保留的**尾部行数**（历史行全在归档）|
| `rotate_keep_tail` | `IG_ROTATE_KEEP_TAIL` | 2000 | 轮转后主账本保留的**尾部行数**（历史行全在 `state/archive/`）|
| `rotate_max_bytes` | `IG_ROTATE_MAX_BYTES` | 1048576 | 账本/日志超过这么多字节才轮转 |
| `rotate_keep_files` | `IG_ROTATE_KEEP_FILES` | 200 | 留痕/报告按份数轮转后保留的**最近份数** |
| `journal_keep_files` | `IG_JOURNAL_KEEP_FILES` | 200 | 主体 `journal/` 保留的**最近篇数**（超出的只移动进 `<主体根>/archive/journal/`）|
| `stall_alert_ticks` | `IG_STALL_ALERT_TICKS` | 12 | 连续「无芽可领」（接了执行者但没活干）这么多拍 → ALERT 出「空转」旗（12 拍≈2 小时）|
"""
from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .paths import ENV_CONFIG, ENV_STATE_ROOT, REPO_ROOT

ENV_PREFIX = "IG_"

_FIELDS = {
    "state_root": (str, ""),
    "subject_root": (str, ""),
    "prompts_dir": (str, ""),
    "key_dir": (str, ""),
    "proxy_url": (str, ""),
    "executor": (str, ""),
    "executor_timeout_s": (int, 120),
    "llm_command": (str, ""),
    "llm_model": (str, ""),
    "org_gap_ticks": (int, 5),
    "org_cooldown_min": (int, 30),
    "tick_minutes": (int, 10),
    "queue_cap": (int, 50),
    "lead_limit": (int, 3),
    "cold_start_ticks": (int, 50),
    "frozen_review_every": (int, 20),
    "frozen_requestion_ticks": (int, 300),
    "frozen_cap": (int, 5000),
    "frozen_keep_tail": (int, 4000),
    "rotate_keep_tail": (int, 2000),
    "rotate_max_bytes": (int, 1048576),
    "rotate_keep_files": (int, 200),
    "journal_keep_files": (int, 200),
    "stall_alert_ticks": (int, 12),
    # repo_root 也走同一张表：测试与嵌入使用都会显式指定它（默认＝本次安装位置）
    "repo_root": (str, str(REPO_ROOT)),
}

DEFAULT_CONFIG_NAMES = ("infinigrow.toml", "infinigrow.json")


def _default(name: str):
    """取某字段的**唯一**默认值来源（`_FIELDS`）。

    以前这里把 24 个默认值在 `_FIELDS` 与 `Settings` 里各抄一遍：改一处不改另一处，
    运行时默认与「表上写的默认」就悄悄分家——而表是给人的口径，错表比错默认更难发现。
    """
    return _FIELDS[name][1]


@dataclass
class Settings:
    """解析后的配置（全部字段都有默认值 → 空仓直接可跑）。"""

    state_root: str = _default("state_root")
    subject_root: str = _default("subject_root")
    prompts_dir: str = _default("prompts_dir")
    key_dir: str = _default("key_dir")
    proxy_url: str = _default("proxy_url")
    executor: str = _default("executor")
    executor_timeout_s: int = _default("executor_timeout_s")
    llm_command: str = _default("llm_command")
    llm_model: str = _default("llm_model")
    org_gap_ticks: int = _default("org_gap_ticks")
    org_cooldown_min: int = _default("org_cooldown_min")
    tick_minutes: int = _default("tick_minutes")
    queue_cap: int = _default("queue_cap")
    lead_limit: int = _default("lead_limit")
    cold_start_ticks: int = _default("cold_start_ticks")
    frozen_review_every: int = _default("frozen_review_every")
    frozen_requestion_ticks: int = _default("frozen_requestion_ticks")
    frozen_cap: int = _default("frozen_cap")
    frozen_keep_tail: int = _default("frozen_keep_tail")
    rotate_keep_tail: int = _default("rotate_keep_tail")
    rotate_max_bytes: int = _default("rotate_max_bytes")
    rotate_keep_files: int = _default("rotate_keep_files")
    journal_keep_files: int = _default("journal_keep_files")
    stall_alert_ticks: int = _default("stall_alert_ticks")
    # repo_root 是唯一的例外：表里的默认＝**本机**安装位置，直接当 dataclass 默认会把
    # 绝对路径烙进类定义（搬不走）。留空串，由 __post_init__ 在实例化时回填。
    repo_root: str = ""
    sources: list = field(default_factory=list)   # 记录每个字段来自哪里（可审计）

    def __post_init__(self) -> None:
        if not self.repo_root:
            self.repo_root = str(REPO_ROOT)

    @property
    def repo_path(self) -> Path:
        return Path(self.repo_root).resolve()

    def prompts_path(self) -> Path:
        if self.prompts_dir:
            p = Path(self.prompts_dir).expanduser()
            return (self.repo_path / p).resolve() if not p.is_absolute() else p.resolve()
        return (self.repo_path / "prompts").resolve()

    def subject_path(self) -> Path:
        """生长主体根：显式配置优先，缺省＝仓库同级目录（默认规则见 `core/paths.py`）。"""
        from .paths import default_subject_root
        if self.subject_root:
            p = Path(self.subject_root).expanduser()
            return (self.repo_path / p).resolve() if not p.is_absolute() else p.resolve()
        return default_subject_root(self.repo_path)

    def executor_command(self) -> str:
        """执行者命令：新字段优先，旧字段 `llm_command` 作兼容回退（空＝机械拍）。"""
        return (self.executor or self.llm_command or "").strip()

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in _FIELDS}


def _read_config_file(path: Path) -> dict:
    if not path.is_file():
        return {}
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    # 允许 [infinigrow] 分节，也允许平铺
    return data.get("infinigrow", data)


def load_settings(config_path: "str | os.PathLike | None" = None,
                  env: "dict | None" = None,
                  **overrides: Any) -> Settings:
    """按「默认 → 配置文件 → 环境变量 → 传参」合成配置，并记录来源。"""
    env = dict(os.environ if env is None else env)
    settings = Settings()
    settings.sources.append("defaults")

    cfg_file = config_path or env.get(ENV_CONFIG) or next(
        (REPO_ROOT / n for n in DEFAULT_CONFIG_NAMES if (REPO_ROOT / n).is_file()), None)
    data = _read_config_file(Path(cfg_file)) if cfg_file else {}
    for key, (typ, _default) in _FIELDS.items():
        if key in data:
            setattr(settings, key, typ(data[key]))
            settings.sources.append("file:%s" % Path(cfg_file).name)

    alias = {"state_root": ENV_STATE_ROOT}
    for key, (typ, _default) in _FIELDS.items():
        env_name = alias.get(key, ENV_PREFIX + key.upper())
        if env_name in env and env[env_name] != "":
            setattr(settings, key, typ(env[env_name]))
            settings.sources.append("env:%s" % env_name)

    for key, value in overrides.items():
        if value is None:
            continue
        if key not in _FIELDS:
            raise KeyError("未知配置项：%s" % key)
        setattr(settings, key, _FIELDS[key][0](value))
        settings.sources.append("caller")

    return settings
