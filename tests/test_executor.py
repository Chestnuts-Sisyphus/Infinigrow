# -*- coding: utf-8 -*-
"""执行者通道测试（T2/G2/G14）：提示词经 stdin 进、stdout 出，四种情形都可见。

验收判据（可复跑）：**成功／失败／超时／空输出**四况全部有账可查，
且「不给执行者」这条路仍然是零外部调用的机械拍。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


from infinigrow.core.config import load_settings
from infinigrow.core.paths import REPO_ROOT, resolve_state
from infinigrow.engine import executor as exec_mod
from infinigrow.engine.tick import run_tick

FAKE = Path(__file__).resolve().parent / "fake_executor.py"


def _cmd(mode: str, sleep: float = 30.0) -> str:
    return '"%s" "%s" --mode %s --sleep %s' % (sys.executable, FAKE, mode, sleep)


def _settings(tmp_path, subject=None):
    return load_settings(env={}, state_root=str(tmp_path / "state"),
                         repo_root=str(REPO_ROOT),
                         subject_root=str(subject or (tmp_path / "subject")))


def _seed_subject(tmp_path, name="notes.md"):
    subject = tmp_path / "subject"
    subject.mkdir(parents=True, exist_ok=True)
    (subject / name).write_text("seed", encoding="utf-8")
    return subject


# ---------------------------------------------------------------- 通道本身
def test_command_success_records_and_parses_usage(tmp_path):
    layout = resolve_state(str(tmp_path / "state"), str(REPO_ROOT), create=True)
    run = exec_mod.run_command(_cmd("ok"), "提示词", tick=1, kind="tick",
                               cwd=tmp_path, state_root=layout.root,
                               subject_root=tmp_path, timeout_s=30)
    assert run.ok and run.rc == 0
    assert "收到" in run.output
    assert run.usage == {"input_tokens": 11, "output_tokens": 22, "cost_usd": 0.001}
    exec_mod.record_executor_run(layout, run)
    rows = [json.loads(line) for line in
            layout.executor_ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[-1]["rc"] == 0 and rows[-1]["kind"] == "tick"
    assert rows[-1]["usage"]["cost_usd"] == 0.001


def test_command_failure_is_visible(tmp_path):
    layout = resolve_state(str(tmp_path / "state"), str(REPO_ROOT), create=True)
    run = exec_mod.run_command(_cmd("fail"), "提示词", tick=1, kind="tick", cwd=tmp_path,
                               state_root=layout.root, subject_root=tmp_path, timeout_s=30)
    assert run.rc == 2 and not run.ok and not run.timed_out
    assert "失败路径" in run.output                 # stderr 与 stdout 同路（可见）
    assert run.note


def test_command_timeout_is_marked_and_killed(tmp_path):
    layout = resolve_state(str(tmp_path / "state"), str(REPO_ROOT), create=True)
    run = exec_mod.run_command(_cmd("timeout"), "提示词", tick=1, kind="tick",
                               cwd=tmp_path, state_root=layout.root,
                               subject_root=tmp_path, timeout_s=1)
    assert run.timed_out and run.rc == exec_mod.TIMEOUT_RC
    assert "超时" in run.note


def test_command_empty_output_is_flagged(tmp_path):
    layout = resolve_state(str(tmp_path / "state"), str(REPO_ROOT), create=True)
    run = exec_mod.run_command(_cmd("empty"), "提示词", tick=1, kind="tick",
                               cwd=tmp_path, state_root=layout.root,
                               subject_root=tmp_path, timeout_s=30)
    assert run.rc == 0 and run.output_bytes == 0
    assert "空输出" in run.note


def test_missing_executor_binary_is_rc127(tmp_path):
    """执行者根本起不来（命令写错）也要有账，不许静默。"""
    layout = resolve_state(str(tmp_path / "state"), str(REPO_ROOT), create=True)
    run = exec_mod.run_command("definitely-not-a-real-program-xyz",
                               "提示词", tick=1, kind="tick", cwd=tmp_path,
                               state_root=layout.root, subject_root=tmp_path, timeout_s=10)
    assert run.rc == exec_mod.NOT_FOUND_RC and "起不来" in run.note


def test_trace_is_written_without_absolute_paths(tmp_path):
    layout = resolve_state(str(tmp_path / "state"), str(REPO_ROOT), create=True)
    subject = tmp_path / "subj"
    subject.mkdir()
    run = exec_mod.run_command(_cmd("ok"), "提示词 %s" % tmp_path, tick=3, kind="org-session",
                               cwd=subject, state_root=layout.root,
                               subject_root=subject, timeout_s=30)
    trace = exec_mod.write_trace(layout, run, "提示词 %s" % tmp_path, subject)
    text = trace.read_text(encoding="utf-8")
    assert trace.name == "org-session-00003.md"
    assert str(tmp_path) not in text                # 本机路径已被占位符替换
    assert exec_mod.PATH_PLACEHOLDER in text


# ---------------------------------------------------------------- 与拍合流
def test_tick_with_executor_records_call_and_trace(tmp_path):
    subject = _seed_subject(tmp_path)
    settings = _settings(tmp_path, subject)
    # 先造一根芽（拍 1 有差异 → 下一拍才有题可领）——执行者只在有题时被调用
    from infinigrow.engine.model import Observation, Prediction
    run_tick(settings=settings, tick=1,
             predictions=[Prediction("X", "大小", "1", tick=1, evidence="p1")],
             observations=[Observation("X", "大小", "2", "文件:x")])
    result = run_tick(settings=settings, tick=2, executor=_cmd("ok"), org_session=False)
    layout = resolve_state(settings.state_root, settings.repo_root)
    assert result.executor is not None and result.executor["rc"] == 0
    rows = [json.loads(line) for line in
            layout.executor_ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [r["kind"] for r in rows] == ["tick"]
    assert any(p.name.startswith("tick-") for p in layout.traces_dir.iterdir())
    # 提示词是**真发出去的**（含机制提示词原文里的红线）
    prompt = (layout.traces_dir / ("tick-%05d.md" % result.tick)).read_text(encoding="utf-8")
    assert "不要登记新芽" in prompt and "本拍 B猜" in prompt


def test_tick_without_executor_stays_mechanical(tmp_path):
    """不给执行者＝机械拍：没有执行者账、没有留痕、没有子进程。"""
    subject = _seed_subject(tmp_path)
    settings = _settings(tmp_path, subject)
    result = run_tick(settings=settings)
    layout = resolve_state(settings.state_root, settings.repo_root)
    assert result.executor is None
    assert not layout.executor_ledger.is_file()
    assert not list(layout.traces_dir.glob("*"))
    assert result.rc == 0


def test_tick_does_not_call_executor_without_a_sprout(tmp_path):
    """没有芽可领＝没有可消解的差异：不硬造活干（零差异零芽的推论）。"""
    subject = tmp_path / "empty-subject"          # 空主体：第一拍零差异零芽
    subject.mkdir()
    settings = _settings(tmp_path, subject)
    result = run_tick(settings=settings, executor=_cmd("echo"), org_session=False)
    assert result.topic_sprout is None
    assert result.executor is None
    assert any("无芽可领" in n for n in result.notes)


def test_executor_failures_are_counted_separately_in_heartbeat(tmp_path):
    """执行者失败与拍失败分开计（园丁的旗要能指出是哪儿坏了）。"""
    subject = _seed_subject(tmp_path)
    settings = _settings(tmp_path, subject)
    # 先造一根芽：让下一拍真的有题可领（显式给预测/观测，路径确定）
    from infinigrow.engine.model import Observation, Prediction
    run_tick(settings=settings, tick=1,
             predictions=[Prediction("X", "大小", "1", tick=1, evidence="p1")],
             observations=[Observation("X", "大小", "2", "文件:x")])
    result = run_tick(settings=settings, tick=2, executor=_cmd("fail"), org_session=False)
    assert result.executor is not None and result.executor["rc"] == 2
    layout = resolve_state(settings.state_root, settings.repo_root)
    status = json.loads(layout.tick_status.read_text(encoding="utf-8"))
    assert status["consecutive_executor_failures"] == 1
    assert status["consecutive_failures"] == 0        # 拍本身没失败


def test_run_callable_exception_is_recorded(tmp_path):
    """进程内执行者（llm=）抛异常：照样记账、照样可见（不崩掉一拍）。"""
    subject = _seed_subject(tmp_path)
    settings = _settings(tmp_path, subject)
    from infinigrow.engine.model import Observation, Prediction
    run_tick(settings=settings, tick=1,
             predictions=[Prediction("X", "大小", "1", tick=1, evidence="p1")],
             observations=[Observation("X", "大小", "2", "文件:x")])

    def boom(_prompt):
        raise RuntimeError("演示用异常")

    result = run_tick(settings=settings, tick=2, llm=boom, org_session=False)
    assert result.executor is not None and result.executor["rc"] == 1
    assert "抛异常" in (result.executor["label"] or "") or result.executor["rc"] == 1
