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
    这是「提议者」职责的合法通道，不许被闸误伤。

    G3 之后这条通道有了边界：点名 `journal/` 里的新文件时，名字必须合 K7/A8 的规格
    （拍号段＋日期段），否则当场拒收——原来那个 `journal/0001.md` 就是不合规格的，
    它作为「合法提议」被收下过，正是这条判据当时没牙的证据。
    """
    settings = _settings(tmp_path)
    payload = json.dumps({"findings": [], "predictions": [
        {"obj": "主体/journal/0001-20260915.md", "dimension": "存在性", "expected": "存在",
         "pointer": "计划:提议创建"},
        {"obj": "主体/notes/idea.md", "dimension": "存在性", "expected": "存在",
         "pointer": "计划:提议创建"},
    ]}, ensure_ascii=False)
    run, _layout, _queue = _run(settings, 1, payload)
    assert [p.obj for p in run.predictions] == ["主体/journal/0001-20260915.md",
                                                "主体/notes/idea.md"]
    # 反证：journal 下不合规格的点名被拒，理由点名约定本身
    bad = json.dumps({"findings": [], "predictions": [
        {"obj": "主体/journal/0001.md", "dimension": "存在性", "expected": "存在",
         "pointer": "p"}]}, ensure_ascii=False)
    run2, _l2, _q2 = _run(settings, 2, bad)
    assert run2.predictions == [] and "对象名被拒" in run2.parse_error
    assert "YYYYMMDD" in run2.parse_error


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


# ---------------------------------------------------------------- N43 / K14
def test_prompt_shows_dir_objects_and_reality_delta(tmp_path):
    """N43/K14 的输入块：目录对象（可对账量＝文件数）＋「自上次组织会话以来」的对比。

    没有这两块，组织会话既无法提议「往 journal/ 里再长一格」（N43），
    也看不见新出现的现实（K14）。

    **N55＋N58（本会话抓到的两个真缺陷）**：对比窗口必须是**锚点 → 此刻**
    （锚点＝上次组织会话读到的清单）——①原先比「上一拍快照 vs 本拍清单」，两者之间
    什么也没发生，恒为空；②改成「上一拍动手前后」后窗口仍只有 1 拍，而组织会话
    每 3~5 拍才跑一次 → 天然错过其余几拍（实测七次全空）。
    """
    settings = _settings(tmp_path)
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    subject = settings.subject_path()
    (subject / "journal").mkdir(parents=True, exist_ok=True)
    (subject / "journal" / "0001-20260916.md").write_text("x", encoding="utf-8")
    # 锚点＝上次组织会话时看到的清单（那会儿还没有 journal/0001）
    layout.subject_org_anchor.write_text(json.dumps({
        "tick": 1, "root_name": "subject", "exists": True, "file_count": 2,
        "total_bytes": 6, "files": [{"name": "notes.md", "bytes": 5},
                                    {"name": "growth-1.md", "bytes": 1}],
        "dirs": [{"name": "journal", "files": 0}],
    }, ensure_ascii=False), encoding="utf-8")
    layout.subject_before_snapshot.write_text("{}", encoding="utf-8")
    layout.subject_snapshot.write_text("{}", encoding="utf-8")
    prompt = org_mod.build_org_prompt(settings, layout, 5, subject, {})
    assert "主体/journal/（1 格）" in prompt                        # 目录对象＋格数
    delta = prompt.split("### 本拍现实变化")[1]
    assert "自上次组织会话以来" in delta                            # 对比窗口写清楚
    assert "主体/journal/0001-20260916.md" in delta                # 新出现的对象被点名
    assert "新出现" in delta and "从清单里消失" in delta
    assert "不等于被删" in delta                                   # 有界清单的诚实声明


def test_reality_delta_reports_byte_level_changes(tmp_path):
    """N59：提示词承诺「新出现／**有变化**的东西是候选」，而对比原先只比名字集合与格数
    ——**改名没改的改写/追加**（字节数变了）一条都不报，等于漏掉「有变化」这半边。
    现在多一行「有变化（前后字节数不同、名字没变）」。"""
    settings = _settings(tmp_path)
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    subject = settings.subject_path()
    (subject / "journal").mkdir(parents=True, exist_ok=True)
    (subject / "journal" / "0001-20260916.md").write_text("xx", encoding="utf-8")
    layout.subject_org_anchor.write_text(json.dumps({
        "tick": 1, "root_name": "subject", "exists": True, "file_count": 3,
        "total_bytes": 7, "files": [{"name": "journal/0001-20260916.md", "bytes": 1},
                                    {"name": "notes.md", "bytes": 5},
                                    {"name": "growth-1.md", "bytes": 1}],
        "dirs": [{"name": "journal", "files": 1}],
    }, ensure_ascii=False), encoding="utf-8")
    text = org_mod._render_reality_delta(layout, subject)
    assert "有变化（前后字节数不同、名字没变）：主体/journal/0001-20260916.md（1→2 字节）" in text
    assert "新出现（锚点里没有、本拍清单里有）：（无）" in text     # 名字没变 → 不算新出现


def test_reality_delta_window_covers_every_tick_since_the_last_org_session(tmp_path):
    """N58 的判据：组织会话**每 3~5 拍才跑一次**，窗口就得覆盖「自上次它跑以来」的全部变化
    ——1 拍窗口时它天然错过其余几拍（实测拍 340/344/348/352/357/362/367 七次全空）。"""
    settings = _settings(tmp_path)
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    subject = settings.subject_path()
    (subject / "journal").mkdir(parents=True, exist_ok=True)
    for i in (1, 2, 3):                      # 上次组织会话之后连长了三格
        (subject / "journal" / ("00%02d-20260917.md" % i)).write_text("x", encoding="utf-8")
    layout.subject_org_anchor.write_text(json.dumps({
        "tick": 10, "root_name": "subject", "exists": True, "file_count": 3,
        "total_bytes": 7, "files": [{"name": "journal/0000-20260917.md", "bytes": 1},
                                    {"name": "notes.md", "bytes": 5},
                                    {"name": "growth-1.md", "bytes": 1}],
        "dirs": [{"name": "journal", "files": 1}],
    }, ensure_ascii=False), encoding="utf-8")
    text = org_mod._render_reality_delta(layout, subject)
    assert "自上次组织会话以来" in text and "起点＝拍 10" in text
    assert "主体/journal/0001-20260917.md" in text
    assert "主体/journal/0002-20260917.md" in text
    assert "主体/journal/0003-20260917.md" in text                 # 中间几拍也不漏
    assert "主体/journal/：1 → 3 格" in text                       # 格数变化同样按新窗口算
    assert "主体/journal/0000-20260917.md" in text                 # 锚点里有、现在没有的也被点名


def test_reality_delta_falls_back_to_one_tick_and_says_so(tmp_path):
    """锚点缺失（首次跑／旧状态根）→ 退回「上一拍动手前 → 动手后」，并把窗口如实写在行里，
    不假装看过更长的窗口。"""
    settings = _settings(tmp_path)
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    subject = settings.subject_path()
    (subject / "journal").mkdir(parents=True, exist_ok=True)
    (subject / "journal" / "0001-20260917.md").write_text("x", encoding="utf-8")
    layout.subject_before_snapshot.write_text(json.dumps({
        "tick": 3, "root_name": "subject", "exists": True, "file_count": 0,
        "total_bytes": 0, "files": [], "dirs": [{"name": "journal", "files": 0}],
    }, ensure_ascii=False), encoding="utf-8")
    layout.subject_snapshot.write_text("{}", encoding="utf-8")
    text = org_mod._render_reality_delta(layout, subject)
    assert "上一拍动手前 → 动手后" in text and "无锚点" in text
    assert "主体/journal/0001-20260917.md" in text


def test_reality_delta_is_honest_when_nothing_is_readable(tmp_path):
    """N55/N58 的诚实面：锚点与动手前快照都没有 → 如实说这块空着，
    不许拿别的读数凑一个假对比（这正是恒为空那条判据的教训）。"""
    settings = _settings(tmp_path)
    layout = resolve_state(settings.state_root, settings.repo_root, create=True)
    subject = settings.subject_path()
    (subject / "journal").mkdir(parents=True, exist_ok=True)
    text = org_mod._render_reality_delta(layout, subject)
    assert "这块本轮空着" in text and "不拿别的读数凑" in text


def test_delta_proposal_on_dir_object_spawns_a_sprout(tmp_path):
    """N43：组织会话对目录对象下**差额**预测（`+1`）→ 现实没长 → 差异 → 一支芽。

    芽带的是差额（领做那拍才锚定），所以不会出现「提议拍 ≠ 创建拍」的名字错位。
    """
    payload = json.dumps({"findings": [], "predictions": [
        {"obj": "主体/journal/", "dimension": "文件数", "expected": "+1",
         "pointer": "计划：本拍在 journal/ 里再长一格（文件名由执行者按创建拍定）"},
    ], "notes": "提议长一格"}, ensure_ascii=False)
    settings = _settings(tmp_path)
    subject = settings.subject_path()
    (subject / "journal").mkdir(parents=True, exist_ok=True)
    (subject / "journal" / "0001-20260916.md").write_text("x", encoding="utf-8")

    # 组织的规划值只在**它自己那一拍**生效（预测是那一拍的承诺）——所以走 run_tick 默认路径
    def fake(prompt: str) -> str:
        if "组织会话" in prompt and "输出协议" in prompt:
            return payload
        return "执行者：不动手（夹具）"

    result = run_tick(settings=settings, tick=1, llm=fake)
    assert result.org is not None and result.org["predictions"] == 1
    diff = [d for d in result.diffs if d.key == ("主体/journal/", "文件数")][0]
    assert diff.expected == "2" and diff.kind.value == "预测内错"   # 锚定成 1+1
    rows = read_jsonl(resolve_state(settings.state_root, settings.repo_root).sprouts)
    assert rows and rows[-1]["expected_value"] == "+1"             # 芽带差额，不带快照
    assert rows[-1]["dimension"] == "文件数"
