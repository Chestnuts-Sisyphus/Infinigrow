# -*- coding: utf-8 -*-
"""组织会话测试（T3/G3）：语义判断有运行体、进账、可被打脸。

验收判据（可复跑）：
  1. **N 差异 N 芽**：发现几条带指针的差异，就立几根芽；
  2. **零差异零芽**：没有发现（或指针全缺）→ 一根芽都不立；
  3. **无指针不成芽**：缺指针的发现照旧入账（`pending_pointer`），但不立芽；
  4. **产出走执行者通道**：调用在 `executor.jsonl` 有账、留痕在 `traces/`；
  5. **可被打脸**：`finding_status()` 能按后来的对账把每条发现判成 待验／被证实／被推翻；
  6. **输出不可解析＝本拍无产出**（写 `parse_error`，不从正文里猜差异）。
"""
from __future__ import annotations

import json

import pytest

from infinigrow.core.config import load_settings
from infinigrow.core.paths import REPO_ROOT, resolve_state
from infinigrow.engine import executor as exec_mod
from infinigrow.engine import org_session as org_mod
from infinigrow.engine.domain_saturation import DomainState
from infinigrow.engine.tick import run_tick
from infinigrow.ledger.store import append_jsonl, read_jsonl

GOOD = json.dumps({
    "findings": [
        {"kind": "预测外发现", "obj": "主体/growth-1.md", "dimension": "存在性",
         "expected": "（预测未提）", "actual": "缺失", "pointer": "主体清单:无 growth-1.md"},
        {"kind": "预测内错", "obj": "主体/notes.md", "dimension": "字节数",
         "expected": "5", "actual": "9", "pointer": "文件:主体/notes.md"},
    ],
    "predictions": [
        {"obj": "主体/growth-1.md", "dimension": "存在性", "expected": "存在",
         "pointer": "计划:本拍创建 growth-1.md"},
    ],
    "notes": "两处差异",
}, ensure_ascii=False)

NO_POINTER = json.dumps({"findings": [
    {"kind": "预测外发现", "obj": "主体/growth-1.md", "dimension": "存在性",
     "expected": "（预测未提）", "actual": "缺失", "pointer": ""},
]}, ensure_ascii=False)

EMPTY = json.dumps({"findings": [], "predictions": [], "notes": "没有差异"},
                   ensure_ascii=False)

GARBAGE = "我觉得这一拍还行，没什么要补的。"


def _settings(tmp_path):
    subject = tmp_path / "subject"
    subject.mkdir(parents=True, exist_ok=True)
    (subject / "notes.md").write_text("hello", encoding="utf-8")
    (subject / "growth-1.md").write_text("1", encoding="utf-8")
    return load_settings(env={}, state_root=str(tmp_path / "state"),
                         repo_root=str(REPO_ROOT), subject_root=str(subject))


def _runner_echo(output):
    def _call(prompt: str) -> exec_mod.ExecutorRun:
        return exec_mod.ExecutorRun(tick=1, kind=exec_mod.KIND_ORG, command_label="夹具",
                                    rc=0, duration_s=0.0, prompt_bytes=len(prompt),
                                    output_bytes=len(output), output=output)
    return _call


def _run(settings, tick, output, subject=None, domains=None, queue=None):
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    from infinigrow.engine.sprout_queue import SproutQueue
    q = queue or SproutQueue(cap=50, lead_limit=3, cold_start_ticks=0)
    return org_mod.run_org_session(
        settings=settings, layout=layout, tick=tick,
        subject_root=subject or settings.subject_path(), queue=q,
        domains=domains or DomainState(), runner=_runner_echo(output)), layout, q


def test_n_differences_means_n_sprouts(tmp_path):
    settings = _settings(tmp_path)
    run, layout, queue = _run(settings, 1, GOOD)
    assert len(run.findings) == 2
    assert len(run.sprouts) == 2
    assert [s for s in run.sprouts if s.startswith("sp")]        # 差异对账芽
    assert run.parse_error == ""


def test_zero_differences_means_zero_sprouts(tmp_path):
    settings = _settings(tmp_path)
    run, layout, queue = _run(settings, 1, EMPTY)
    assert run.findings == [] and run.sprouts == []
    assert queue.sprouts == []


def test_finding_without_pointer_is_recorded_but_never_sprouts(tmp_path):
    settings = _settings(tmp_path)
    run, layout, queue = _run(settings, 1, NO_POINTER)
    assert len(run.findings) == 1 and run.sprouts == []
    rows = read_jsonl(layout.diff_ledger)
    assert rows and rows[-1]["source"] == "org-session"
    assert rows[-1]["pending_pointer"] is True and rows[-1]["spawns"] is False


def test_findings_land_in_diff_ledger_with_source_and_pointer(tmp_path):
    settings = _settings(tmp_path)
    _run(settings, 7, GOOD)
    layout = resolve_state(settings.state_root, settings.repo_root)
    rows = [r for r in read_jsonl(layout.diff_ledger) if r.get("source") == "org-session"]
    assert len(rows) == 2
    assert all(r["tick"] == 7 and r["evidence"] for r in rows)
    findings = read_jsonl(layout.root / org_mod.FINDINGS_LEDGER)
    assert len(findings) == 2 and all(f["tick"] == 7 for f in findings)


def test_unparseable_output_is_recorded_as_no_output(tmp_path):
    settings = _settings(tmp_path)
    run, layout, queue = _run(settings, 1, GARBAGE)
    assert run.parse_error and run.findings == [] and run.sprouts == []
    assert queue.sprouts == []
    attempts = read_jsonl(layout.root / "org-llm.jsonl")
    assert attempts and attempts[-1]["tick"] == 1                # 尝试账仍带拍号
    assert "不可解析" in attempts[-1]["note"] or "失败" in attempts[-1]["note"]


def test_org_call_is_accounted_and_traced(tmp_path):
    settings = _settings(tmp_path)
    _run(settings, 1, GOOD)
    layout = resolve_state(settings.state_root, settings.repo_root)
    rows = read_jsonl(layout.executor_ledger)
    assert rows and rows[-1]["kind"] == exec_mod.KIND_ORG
    assert (layout.traces_dir / "org-session-00001.md").is_file()
    attempts = read_jsonl(layout.root / "org-llm.jsonl")
    assert attempts[-1]["tick"] == 1 and attempts[-1]["time"]   # 拍号 + 机械时间戳


def test_planned_predictions_override_defaults_in_the_tick(tmp_path):
    """组织会话写的预测会覆盖机械默认值——否则真动手的一拍会被判「没预测」。"""
    settings = _settings(tmp_path)

    def fake(prompt: str) -> str:
        if "组织会话" in prompt and "输出协议" in prompt:
            return GOOD
        return "执行者：不动手（夹具）"

    result = run_tick(settings=settings, tick=1, llm=fake)
    assert result.org is not None and result.org["predictions"] == 1
    assert result.predictions["planned"] == 1
    plan_key = ("主体/growth-1.md", "存在性")
    got = [d for d in result.diffs if (d.obj, d.dimension) == plan_key]
    assert got and got[0].expected == "存在"                     # 用的是规划值


def test_findings_can_be_refuted_or_confirmed_by_later_reconcile(tmp_path):
    """可被打脸：同一 (对象, 维度) 后来的对账说了算（判断不由引擎自述）。"""
    settings = _settings(tmp_path)
    _run(settings, 1, GOOD)
    layout = resolve_state(settings.state_root, settings.repo_root)
    # 拍 2：对账判「预测内对」（被证实）；拍 3：判「预测内错」（被推翻）
    append_jsonl(layout.diff_ledger, {"kind": "预测内对", "obj": "主体/growth-1.md",
                                      "dimension": "存在性", "evidence": "文件:主体/growth-1.md",
                                      "spawns": False, "tick": 2}, layout.root)
    append_jsonl(layout.diff_ledger, {"kind": "预测内错", "obj": "主体/notes.md",
                                      "dimension": "字节数", "evidence": "文件:主体/notes.md",
                                      "spawns": True, "tick": 2}, layout.root)
    rows = {r["obj"]: r["status"] for r in org_mod.finding_status(layout)}
    assert rows["主体/growth-1.md"] == "被证实"
    assert rows["主体/notes.md"] == "被推翻"


def test_finding_status_pending_when_nothing_later(tmp_path):
    settings = _settings(tmp_path)
    _run(settings, 1, GOOD)
    layout = resolve_state(settings.state_root, settings.repo_root)
    rows = org_mod.finding_status(layout)
    assert rows and all(r["status"] == "待验" for r in rows)


def test_bad_finding_shape_is_dropped_with_visible_error(tmp_path):
    """kind/obj/dimension 缺一 → 该条丢弃并记 parse_error（不猜）。"""
    payload = json.dumps({"findings": [{"kind": "第五类差异", "obj": "X",
                                        "dimension": "大小", "pointer": "p"}]},
                         ensure_ascii=False)
    settings = _settings(tmp_path)
    run, _layout, queue = _run(settings, 1, payload)
    assert run.findings == [] and run.sprouts == []
    assert "不合格" in run.parse_error


def test_finding_with_fabricated_object_is_dropped_with_error(tmp_path):
    """T5/A11 对象名机械闸：findings 引用**不可对账**的对象名 → 丢弃并记 parse_error（不产芽）。

    「发明机械层读不到的对象名」是组织会话空谈的来源——对象名纪律从此不只是提示词约定。
    """
    payload = json.dumps({"findings": [
        {"kind": "预测外发现", "obj": "主体/不存在的对象", "dimension": "存在性",
         "expected": "（预测未提）", "actual": "缺失", "pointer": "p"},
    ], "predictions": []}, ensure_ascii=False)
    settings = _settings(tmp_path)
    run, _layout, _queue = _run(settings, 1, payload)
    assert run.findings == [] and run.sprouts == []
    assert "对象名被拒" in run.parse_error


def test_prediction_can_propose_new_subject_path(tmp_path):
    """T5/A11：predictions 可以提议**主体内合法新相对路径**（预期=存在＝该创建它）——
    这是「提议者」职责的合法通道，不许被闸误伤。"""
    payload = json.dumps({"findings": [], "predictions": [
        {"obj": "主体/journal/0001.md", "dimension": "存在性", "expected": "存在",
         "pointer": "计划:提议创建"},
    ]}, ensure_ascii=False)
    settings = _settings(tmp_path)
    run, _layout, _queue = _run(settings, 1, payload)
    assert len(run.predictions) == 1
    assert run.predictions[0].obj == "主体/journal/0001.md"


def test_prediction_with_escaping_path_is_dropped(tmp_path):
    """T5/A11：predictions 带 `..`（越界相对路径）→ 丢弃并记 parse_error。"""
    payload = json.dumps({"findings": [], "predictions": [
        {"obj": "主体/../逃出.md", "dimension": "存在性", "expected": "存在",
         "pointer": "p"},
    ]}, ensure_ascii=False)
    settings = _settings(tmp_path)
    run, _layout, _queue = _run(settings, 1, payload)
    assert run.predictions == [] and "对象名被拒" in run.parse_error


@pytest.mark.parametrize("bad", ["", "not json at all", "{}"])
def test_missing_json_is_not_guessed(tmp_path, bad):
    settings = _settings(tmp_path)
    run, _layout, _queue = _run(settings, 1, bad)
    assert run.findings == [] and (run.parse_error or bad == "{}")
