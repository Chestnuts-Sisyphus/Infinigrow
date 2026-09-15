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
    """留痕要能分享/迁移：引擎自己知道的那几个根（状态根/主体根）绝不落进留痕。

    判据口径与 `tools/check_no_abs_paths.py` 一致（盘符 ＋ 家目录/挂载点前缀），
    再加一条更强的：**已知的根**整串被替换成占位符（这是实际会泄漏的那一类）。
    """
    layout = resolve_state(str(tmp_path / "state"), str(REPO_ROOT), create=True)
    subject = tmp_path / "subj"
    subject.mkdir()
    prompt = "提示词里带上主体根 %s 与状态根 %s" % (subject, layout.root)
    run = exec_mod.run_command(_cmd("ok"), prompt, tick=3, kind="org-session",
                               cwd=subject, state_root=layout.root,
                               subject_root=subject, timeout_s=30)
    trace = exec_mod.write_trace(layout, run, prompt, subject)
    text = trace.read_text(encoding="utf-8")
    assert trace.name == "org-session-00003.md"
    assert str(subject) not in text and str(layout.root) not in text
    assert exec_mod.PATH_PLACEHOLDER in text
    # 经典前缀（跨平台兜底）也要被替换：样本按拼装构造，免得测试文件自己命中规则
    home_like = "/" + "home/" + "someone/data"
    assert exec_mod.redact_paths("看这个 %s" % home_like) == "看这个 （本机路径已省略）"


def test_redact_roots_are_replaced_longest_first(tmp_path):
    """父目录与子目录同时在列表里时先替换长的（否则子目录只剩半截，仍算泄漏）。"""
    parent = tmp_path / "outer"
    child = parent / "inner"
    text = "A=%s B=%s" % (child, parent)
    out = exec_mod.redact_paths(text, roots=(parent, child))
    assert out.count(exec_mod.PATH_PLACEHOLDER) == 2
    assert str(child) not in out and str(parent) not in out


def test_urls_survive_redaction(tmp_path):
    """URL 不许被 redact 糊掉：URL 的「冒号 ＋ 双斜杠」前面接一个字母时，
    那个片段长得像盘符路径（这正是这条规则最容易出的假阳性）。"""
    url = "https" + ":" + "//" + "example.com/docs/api"
    assert exec_mod.redact_paths("见 %s" % url) == "见 %s" % url
    drive = "C" + ":" + "/" + "Users/" + "someone"
    assert drive not in exec_mod.redact_paths("路径 %s 结束" % drive)


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


def test_tick_prompt_carries_mechanical_facts(tmp_path):
    """题面里要带**机械事实摘录**：执行者只拿到一句题面时写出来的只能是空话。

    判据是具体状态：这一段存在，且里面的数字与账本/主体对得上
    （拍号、队列读数、兑现账判定、主体文件数）。
    """
    subject = _seed_subject(tmp_path)
    settings = _settings(tmp_path, subject)
    from infinigrow.engine.model import Observation, Prediction
    run_tick(settings=settings, tick=1,
             predictions=[Prediction("X", "大小", "1", tick=1, evidence="p1")],
             observations=[Observation("X", "大小", "2", "文件:x")])
    result = run_tick(settings=settings, tick=2, executor=_cmd("ok"), org_session=False)
    layout = resolve_state(settings.state_root, settings.repo_root)
    prompt = (layout.traces_dir / ("tick-%05d.md" % result.tick)).read_text(encoding="utf-8")
    assert "本拍事实（机械摘录" in prompt
    assert "拍号 2" in prompt and "队列：" in prompt and "兑现账：" in prompt
    assert "主体读数：文件 1 个" in prompt              # 种子里就一个 notes.md
    assert "兑现率" not in prompt or "无样本" in prompt or "有样本" in prompt


def test_tick_facts_are_all_checkable(tmp_path):
    """事实摘录函数：每个字段都能在账本/主体里查到（不生成任何判断性文字）。"""
    from infinigrow.engine.sprout_queue import SproutQueue
    from infinigrow.engine.tick import tick_facts
    subject = _seed_subject(tmp_path)
    settings = _settings(tmp_path, subject)
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    facts = tick_facts(layout, SproutQueue(), tick=7, topic=None, subject_root=subject)
    text = "\n".join(facts["lines"])
    assert "拍号 7" in text and "队列：活跃 0／冻结 0" in text
    assert "本拍领到的芽：（无）" in text and "主体读数：文件 1 个" in text
    for banned in ("不错", "很好", "进展", "应该"):     # 事实里不掺判断
        assert banned not in text


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


def test_executor_env_forces_utf8_stdio(tmp_path):
    """A20 根因硬化：执行者子进程必须带 `PYTHONIOENCODING=utf-8`。

    提示词经 stdin 以 UTF-8 写入；计划任务上下文的进程 stdin 默认编码非 UTF-8，
    会把提示词读坏、混入孤立代理字符 → 上游报「lone leading surrogate」→ 400
    （实测：只有计划任务上下文命中）。引擎侧强制 UTF-8 stdio 是防御性硬化。
    """
    env = exec_mod.executor_env(
        subject_root=tmp_path / "subject", state_root=tmp_path / "state",
        tick=1, kind="tick")
    assert env["PYTHONIOENCODING"] == "utf-8"
    # 其余注入上下文仍在（不回归）
    assert env["IG_TICK"] == "1" and env["IG_PASS_KIND"] == "tick"
    assert env["IG_SUBJECT_ROOT"] == str(tmp_path / "subject")


# ---------------------------------------------------------------- K5/A9 传输层重试
def test_transport_cut_is_retried_and_succeeds(tmp_path):
    """K5/A9：首次 `IncompleteRead`（传输层截断）→ 自动重试 → 第二次成功 rc=0。

    计数文件跨进程记次数（子进程间不共享内存）；`attempt=2` 进账本。
    """
    count_file = tmp_path / "flaky-count.txt"
    layout = resolve_state(str(tmp_path / "state"), str(REPO_ROOT), create=True)
    cmd = _cmd("flaky") + ' --count-file "%s"' % count_file
    run = exec_mod.run_command(cmd, "提示词", tick=1, kind="tick", cwd=tmp_path,
                               state_root=layout.root, subject_root=tmp_path,
                               timeout_s=30)
    assert run.ok and run.rc == 0
    assert run.attempt == 2                                # 第二次尝试成功
    assert "重试" in run.output or "成功" in run.output
    exec_mod.record_executor_run(layout, run)
    rows = [json.loads(line) for line in
            layout.executor_ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[-1]["attempt"] == 2                        # 账本记 attempt，不破坏旧行


def test_transport_cut_failure_records_attempt_count(tmp_path):
    """K5/A9：截断持续失败时如实记尝试次数（不把重试藏起来）。"""
    layout = resolve_state(str(tmp_path / "state"), str(REPO_ROOT), create=True)
    # 用「总是截断」的命令：起不来/失败与截断无关，这里直接造一个输出恒含签名的
    run = exec_mod.run_command(
        'python -c "import sys; sys.stderr.write(\'EXECUTOR-ERROR: IncompleteRead(1 bytes read, 9 more expected)\n\'); sys.exit(1)"',
        "提示词", tick=2, kind="tick", cwd=tmp_path,
        state_root=layout.root, subject_root=tmp_path, timeout_s=30)
    assert not run.ok
    assert run.attempt == exec_mod.TRANSPORT_RETRY_MAX     # 试满上限次数


def test_non_transport_failure_is_not_retried(tmp_path):
    """K5/A9：非传输层失败（普通 rc≠0，无截断签名）不重试——一次记清。"""
    layout = resolve_state(str(tmp_path / "state"), str(REPO_ROOT), create=True)
    run = exec_mod.run_command(_cmd("fail"), "提示词", tick=3, kind="tick",
                               cwd=tmp_path, state_root=layout.root,
                               subject_root=tmp_path, timeout_s=30)
    assert run.rc == 2 and run.attempt == 1                # 不重试


def test_failed_run_records_usage_unknown(tmp_path):
    """K9/A10：失败调用（无自报用量）→ 账本显式记 `usage="unknown"`。"""
    layout = resolve_state(str(tmp_path / "state"), str(REPO_ROOT), create=True)
    run = exec_mod.run_command(_cmd("fail"), "提示词", tick=4, kind="tick",
                               cwd=tmp_path, state_root=layout.root,
                               subject_root=tmp_path, timeout_s=30)
    exec_mod.record_executor_run(layout, run)
    rows = [json.loads(line) for line in
            layout.executor_ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[-1]["rc"] == 2 and rows[-1]["usage"] == "unknown"


def test_success_without_usage_stays_null(tmp_path):
    """K9/A10：成功但执行者没自报用量 → 仍是 null（不拿长度冒充 token 的纪律不变）。"""
    layout = resolve_state(str(tmp_path / "state"), str(REPO_ROOT), create=True)
    run = exec_mod.run_command(_cmd("empty"), "提示词", tick=5, kind="tick",
                               cwd=tmp_path, state_root=layout.root,
                               subject_root=tmp_path, timeout_s=30)
    exec_mod.record_executor_run(layout, run)
    rows = [json.loads(line) for line in
            layout.executor_ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[-1]["rc"] == 0 and rows[-1]["usage"] is None
