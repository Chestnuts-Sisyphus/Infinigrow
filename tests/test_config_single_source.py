# -*- coding: utf-8 -*-
"""配置默认值单一真源（M7）＋ 三个隐藏数值闸入正本 ＋ 四个旋钮的行为用例。

为什么这么测（缺口是现跑查出来的，不是猜的）：

1. `Settings` 的 24 个字面默认从前在 `_FIELDS`（表）与类定义里**各抄一遍**——改一处
   不改另一处，运行时默认与「表上写的默认」就悄悄分家，而表是给人的口径。
   这里不写「逐个断言相等」（派生之后那是恒真式），而是断言**真源只有一个**：
   类定义里不许再有字面量默认，且表一动运行时默认必须跟着动。
2. 三个数值闸从前只活在源码里：`DEFAULT_ZERO_GAP`（判据④的行数阈值）、
   `TRACE_GATE_FILES`（「本拍用过」读最近几份留痕）、`review_frozen(max_relight=…)`
   （每拍最多重亮几根）。使用者在正本里读到的是「最近若干份」这种**不含数字**的措辞，
   等于判据不可复核。这里要求：**双语正本与 prompts 里的数字必须等于常量本身**。
3. 四个旋钮（`org_cooldown_min`／`tick_minutes`／`executor_timeout_s`／
   `rotate_keep_files`）各有行为用例：证明「改这个旋钮，行为真的变」，
   而不是只证明「配置能读进来」。
"""
from __future__ import annotations

import datetime as _dt
import inspect
import os
import re
import sys
from pathlib import Path

from infinigrow.core.config import _FIELDS, Settings, _default, load_settings
from infinigrow.core.paths import REPO_ROOT, resolve_state
from infinigrow.engine.executor import TIMEOUT_RC, run_command
from infinigrow.engine.model import Diff, DiffKind, Sprout, SproutOrigin
from infinigrow.engine.org_trigger import (DEFAULT_COOLDOWN_MIN, DEFAULT_ZERO_GAP,
                                           cadence_seconds, org_ledger_path,
                                           should_run_org_session)
from infinigrow.engine.sprout_queue import SproutQueue
from infinigrow.engine.tick import TRACE_GATE_FILES, recent_trace_output
from infinigrow.ledger.rotation import rotate_files
from infinigrow.ledger.store import append_jsonl

REPO = Path(__file__).resolve().parents[1]
FAKE = Path(__file__).resolve().parent / "fake_executor.py"

#: `review_frozen` 的重亮上限默认值——**从签名里取**，不在测试里另抄一个数
MAX_RELIGHT = inspect.signature(SproutQueue.review_frozen).parameters["max_relight"].default


def _settings(tmp_path, name="state", **env):
    return load_settings(env=dict(env), state_root=str(tmp_path / name),
                         repo_root=str(REPO_ROOT), subject_root=str(tmp_path / "subject"))


def _text(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def _flat(rel):
    """正本按 ~95 字符硬换行，判等必须**先把空白压平**（否则换行位置一变就假红）。"""
    return re.sub(r"\s+", " ", _text(rel))


# ------------------------------------------------- 1. 默认值的真源只有一处
def test_every_field_default_equals_the_table():
    """表（`_FIELDS`）与运行时默认逐字段相等，且类型也一致。"""
    settings = Settings()
    for name, (typ, table_default) in _FIELDS.items():
        assert typ in (int, str), "%s：表里出现了未登记的类型" % name
        if name == "repo_root":
            continue                     # 见下一条：这个字段刻意不从表取默认
        assert getattr(settings, name) == table_default, "%s：运行时默认与表不符" % name
        assert isinstance(getattr(settings, name), typ), "%s：类型漂移" % name


def test_settings_class_body_holds_no_literal_defaults():
    """类定义里不许再出现字面量默认（`repo_root` 是唯一例外，且不烙本机路径）。

    实测反证：把任一字段改回字面量，本条立刻红——那正是「两处抄写」重新分家的形态。
    """
    body = _text("src/infinigrow/core/config.py").split("class Settings:", 1)[1]
    body = body.split("def __post_init__", 1)[0]
    literal = re.findall(r"^    (\w+): (?:str|int) = (?!_default\()", body, re.M)
    assert literal == ["repo_root"], "类定义里出现了字面量默认：%s" % literal
    assert re.search(r'^    repo_root: str = ""$', body, re.M), \
        "repo_root 必须以空串留在类里（默认＝本次安装位置，不烙进源码）"
    for name in _FIELDS:
        if name != "repo_root":
            assert '_default("%s")' % name in body, "%s 没有从表取默认" % name
    assert Settings().repo_root == str(REPO_ROOT)


def test_the_documented_default_column_matches_the_table():
    """模块 docstring 那张表的「默认」列必须等于 `_FIELDS`（文档与真源不许分家）。"""
    doc = _text("src/infinigrow/core/config.py")
    rows = re.findall(r"^\| `(\w+)` \| `[A-Z_]+` \| ([^|]+?) \|", doc, re.M)
    seen = {name for name, _ in rows}
    for name, cell in rows:
        cell = cell.strip()
        if cell.isdigit():
            assert int(cell) == _default(name), \
                "%s：表文档写 %s，真源是 %s" % (name, cell, _default(name))
    uncovered = [n for n, (typ, dflt) in _FIELDS.items()
                 if typ is int and dflt and n != "repo_root" and n not in seen]
    assert not uncovered, "整型旋钮没进文档表：%s" % uncovered


# ------------------------------------------------- 2. 三个数值闸：数字要在正本里读得到
#: 闸名 → （中文正本必需串, 英文正本必需串）；数字全部由常量插值，改常量不改文档必红
GATE_NEEDLES = {
    "判据④行数阈值": ("`zero_gap`（%d）" % DEFAULT_ZERO_GAP,
                     "`zero_gap` (%d)" % DEFAULT_ZERO_GAP),
    "留痕闸份数": ("最近 %d 份**执行者**留痕" % TRACE_GATE_FILES,
                 "the last %d executor traces" % TRACE_GATE_FILES),
    "每拍重亮上限": ("每拍最多重新点亮 %d 根" % MAX_RELIGHT,
                  "at most %d sprouts are re-lit per sweep" % MAX_RELIGHT),
}


def test_every_numeric_gate_is_documented_with_its_own_number():
    """双语正本各自必须含**等于常量**的数字；只写在一侧也算红（单侧＝漂移）。"""
    zh, en = _flat("docs/zh/mechanism.md"), _flat("docs/mechanism.md")
    for gate, (needle_zh, needle_en) in GATE_NEEDLES.items():
        assert needle_zh in zh, "%s：中文正本没有可读数字（应为 %s）" % (gate, needle_zh)
        assert needle_en in en, "%s：英文正本没有可读数字（应为 %s）" % (gate, needle_en)


def test_the_relight_cap_is_reachable_from_the_prompts_too():
    """「每拍最多重亮 N 根」还必须出现在 prompts 里——占取题位的是会话，不是读者。"""
    texts = " ".join(_flat("prompts/" + p.name) for p in sorted((REPO / "prompts").glob("*.md")))
    needle = GATE_NEEDLES["每拍重亮上限"][0]
    assert needle in texts, "prompts 里读不到重亮上限：%s" % needle


def test_a_number_only_in_code_would_fail_the_gate_check():
    """反证：把文档里的数字换成含糊措辞，闸必须报缺（否则这条检查恒真）。"""
    zh_needle, en_needle = GATE_NEEDLES["留痕闸份数"]
    zh, en = _flat("docs/zh/mechanism.md"), _flat("docs/mechanism.md")
    assert zh_needle in zh
    assert zh_needle not in zh.replace(zh_needle, "最近若干份**执行者**留痕")
    assert en_needle in en
    assert en_needle not in en.replace(en_needle, "the last few traces")


def test_the_trace_gate_reads_exactly_that_many_traces(tmp_path):
    """留痕闸的行为与文档数字同源：**只**认最近 `TRACE_GATE_FILES` 份执行者留痕。"""
    layout = resolve_state(_settings(tmp_path, "gate").state_root, str(REPO_ROOT), create=True)
    total = TRACE_GATE_FILES + 2
    base = _dt.datetime(2026, 9, 19, 12, 0, 0)
    for i in range(total):
        path = layout.traces_dir / ("tick-%05d.md" % i)
        path.write_text("## 输出（原样）\n\n条目%d\n" % i, encoding="utf-8")
        stamp = (base + _dt.timedelta(minutes=i)).timestamp()
        os.utime(path, (stamp, stamp))
    text = recent_trace_output(layout)
    for i in range(total - TRACE_GATE_FILES, total):
        assert "条目%d" % i in text, "最近这份留痕没被读到（tick-%05d）" % i
    for i in range(total - TRACE_GATE_FILES):
        assert "条目%d" % i not in text, "超出 %d 份的旧留痕被读进来了" % TRACE_GATE_FILES


def test_the_relight_cap_releases_only_that_many_sprouts():
    """重亮上限的行为与文档数字同源：N+1 根都够条件，本拍也只放行 N 根。"""
    queue = SproutQueue(cap=1, lead_limit=3)
    for i in range(MAX_RELIGHT + 2):
        queue.add(_sprout(i), tick=1)          # cap=1 → 除最后一根外全部进冻结区
    assert len(queue.frozen) == MAX_RELIGHT + 1
    diffs = [Diff(DiffKind.NOT_EXECUTED, "对象%d" % i, "维度", "预期", "实际", "指针", 9)
             for i in range(MAX_RELIGHT + 1)]
    notes = queue.review_frozen(diffs, tick=9)
    relit = [n for n in notes if "重新点亮" in n]
    capped = [n for n in notes if "本拍重亮已达上限" in n]
    assert len(relit) == MAX_RELIGHT, "重亮数与文档数字不一致：%s" % notes
    assert len(capped) == 1, "达上限的行数不对（上限应为 %d）：%s" % (MAX_RELIGHT, notes)


def _sprout(i):
    return Sprout(id="sp0001-%03d-对象%d" % (i, i), obj="对象%d" % i, dimension="维度",
                  pointer="指针", origin=SproutOrigin.DIFF, created_tick=1)


# ------------------------------------------------- 3. 四个旋钮的行为用例
def test_org_cooldown_minutes_moves_the_very_same_ledger(tmp_path):
    """同一条尝试账、同一个时点：旋钮 30→5 分钟，判定从「冷却闸拦住」变成「放行」。"""
    settings = _settings(tmp_path, "cd")
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    stamp = _dt.datetime.now() - _dt.timedelta(minutes=10)
    append_jsonl(org_ledger_path(layout),
                 {"tick": 5, "time": stamp.strftime("%Y-%m-%d %H:%M:%S"),
                  "note": "上一次组织段"}, layout.root)
    now = stamp + _dt.timedelta(minutes=10)
    assert settings.org_cooldown_min == DEFAULT_COOLDOWN_MIN == _default("org_cooldown_min")
    blocked = should_run_org_session(layout, tick=6, now=now, gap=99,
                                     cooldown_min=settings.org_cooldown_min)
    assert blocked.should_run is False and "冷却闸" in blocked.reason

    short = load_settings(env={"IG_ORG_COOLDOWN_MIN": "5"}, repo_root=str(REPO_ROOT))
    assert short.org_cooldown_min == 5
    released = should_run_org_session(layout, tick=6, now=now, gap=99,
                                      cooldown_min=short.org_cooldown_min)
    assert "冷却闸" not in released.reason
    fired = should_run_org_session(layout, tick=6, now=now, gap=1,
                                   cooldown_min=short.org_cooldown_min)
    assert fired.should_run is True and "空窗补跑" in fired.reason


def test_tick_minutes_is_the_scheduler_interval_in_seconds():
    """`tick_minutes` 的下游：换算成调度器读的秒数；非正数必须响亮报错，不许悄悄 0 秒。"""
    assert _default("tick_minutes") == 10
    assert cadence_seconds(load_settings(env={}, repo_root=str(REPO_ROOT)).tick_minutes) == 600
    minutes = load_settings(env={"IG_TICK_MINUTES": "7"}, repo_root=str(REPO_ROOT)).tick_minutes
    assert minutes == 7 and cadence_seconds(minutes) == 420
    for bad in (0, -1):
        try:
            cadence_seconds(bad)
            raise AssertionError("非正间隔必须报错，实际静默返回")
        except ValueError:
            pass


def test_executor_timeout_seconds_actually_kills_the_call(tmp_path):
    """`executor_timeout_s` 是真的**杀掉**子进程，不是记在账上的装饰数字。"""
    settings = _settings(tmp_path, "to")
    settings.executor_timeout_s = 1
    assert settings.executor_timeout_s != _default("executor_timeout_s")
    assert _default("executor_timeout_s") == 120
    command = '"%s" "%s" --mode timeout --sleep 20' % (sys.executable, FAKE)
    started = _dt.datetime.now()
    run = run_command(command, "提示词", tick=1, kind="tick", cwd=tmp_path,
                      state_root=Path(settings.state_root),
                      subject_root=settings.subject_path(),
                      timeout_s=settings.executor_timeout_s)
    elapsed = (_dt.datetime.now() - started).total_seconds()
    assert run.timed_out is True and run.rc == TIMEOUT_RC
    assert elapsed < 15, "超时闸没生效：等它自己睡完了（%ss）" % elapsed
    assert "超时" in run.note


def test_rotate_keep_files_decides_how_many_traces_survive(tmp_path):
    """`rotate_keep_files`＝留最近 N 份，且**只移动不删**：主目录 N 份 + 归档若干份。"""
    layout = resolve_state(_settings(tmp_path, "rot").state_root, str(REPO_ROOT), create=True)
    keep, total = 3, 5
    for i in range(total):
        (layout.traces_dir / ("tick-%05d.md" % i)).write_text("留痕 %d" % i, encoding="utf-8")
    reports = rotate_files(layout, keep_files=keep, stamp="20260101-000001")
    assert sum(int(r.get("moved") or 0) for r in reports) == total - keep, reports
    assert len(list(layout.traces_dir.glob("*.md"))) == keep
    assert len(list((layout.archive_dir / "files" / "traces").glob("*.md"))) == total - keep
    assert _default("rotate_keep_files") == 200


def test_env_wins_over_file_and_caller_wins_over_env(tmp_path):
    """优先级链（默认 → 文件 → 环境变量 → 传参）也走同一个真源，别在派生之后写歪。"""
    cfg = tmp_path / "infinigrow.toml"
    cfg.write_text("lead_limit = 4\nstall_alert_ticks = 6\n", encoding="utf-8")
    from_file = load_settings(cfg, env={}, repo_root=str(REPO_ROOT))
    assert from_file.lead_limit == 4 and from_file.stall_alert_ticks == 6
    from_env = load_settings(cfg, env={"IG_LEAD_LIMIT": "8"}, repo_root=str(REPO_ROOT))
    assert from_env.lead_limit == 8
    from_caller = load_settings(cfg, env={"IG_LEAD_LIMIT": "8"}, repo_root=str(REPO_ROOT),
                                lead_limit=2)
    assert from_caller.lead_limit == 2
    assert "caller" in from_caller.sources
