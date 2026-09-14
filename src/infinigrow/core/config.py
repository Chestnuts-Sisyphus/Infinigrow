# -*- coding: utf-8 -*-
"""配置：一切「随机器/随使用者而异」的值都从这里来，源码里不留常量。

优先级（后者覆盖前者）：
    内置默认 → 配置文件（toml 或 json）→ 环境变量（`IG_*`）→ 显式传参

为什么不做成「一堆全局常量」：v1 的绝对路径就是那么长出来的——某天为了本机跑通
写死一个路径，之后再也搬不走。这里把「本机相关性」压缩成一张表：

| 配置项 | 环境变量 | 默认 | 说明 |
|---|---|---|---|
| `state_root` | `IG_STATE_ROOT` | `<repo>/state` | 状态根（账本/队列/心跳）|
| `prompts_dir` | `IG_PROMPTS_DIR` | `<repo>/prompts` | 提示词目录 |
| `key_dir` | `IG_KEY_DIR` | 空 | 外部凭据目录（空＝不需要凭据）|
| `proxy_url` | `IG_PROXY_URL` | 空 | 出网代理（空＝直连）|
| `llm_command` | `IG_LLM_COMMAND` | 空 | 起一拍用的外部命令（空＝机械模式，零 token）|
| `llm_model` | `IG_LLM_MODEL` | 空 | 模型标识（透传给上面那条命令）|
| `org_gap_ticks` | `IG_ORG_GAP_TICKS` | 5 | 组织会话 LLM 段最长空窗（拍）|
| `queue_cap` | `IG_QUEUE_CAP` | 50 | 活跃芽队列上限 |
| `lead_limit` | `IG_LEAD_LIMIT` | 3 | 同一芽连领上限（拍）|
| `cold_start_ticks` | `IG_COLD_START_TICKS` | 50 | 冷启动随机化拍数（之后走字典序）|
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
    "prompts_dir": (str, ""),
    "key_dir": (str, ""),
    "proxy_url": (str, ""),
    "llm_command": (str, ""),
    "llm_model": (str, ""),
    "org_gap_ticks": (int, 5),
    "queue_cap": (int, 50),
    "lead_limit": (int, 3),
    "cold_start_ticks": (int, 50),
    "frozen_review_every": (int, 20),
    # repo_root 也走同一张表：测试与嵌入使用都会显式指定它（默认＝本次安装位置）
    "repo_root": (str, str(REPO_ROOT)),
}

DEFAULT_CONFIG_NAMES = ("infinigrow.toml", "infinigrow.json")


@dataclass
class Settings:
    """解析后的配置（全部字段都有默认值 → 空仓直接可跑）。"""

    state_root: str = ""
    prompts_dir: str = ""
    key_dir: str = ""
    proxy_url: str = ""
    llm_command: str = ""
    llm_model: str = ""
    org_gap_ticks: int = 5
    queue_cap: int = 50
    lead_limit: int = 3
    cold_start_ticks: int = 50
    frozen_review_every: int = 20
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
