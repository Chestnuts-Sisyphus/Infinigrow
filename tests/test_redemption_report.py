# -*- coding: utf-8 -*-
"""兑现率诚实呈现测试（T11/G6）：**无样本** ≠ 「0＝差」。

验收判据（可复跑）：两态各有测试——
  1. 没有执行者动过手 → 报告写「无样本」，并且**不出现**兑现率数字；
  2. 有执行者动过手 → 给真实兑现率与分桶，且**非样本行不进分母**。
"""
from __future__ import annotations

import json

from infinigrow.core.config import load_settings
from infinigrow.core.paths import REPO_ROOT, resolve_state
from infinigrow.engine.model import Observation, Prediction
from infinigrow.engine.reconcile import (executor_tick_failures, redemption_attribution,
                                        redemption_report, sampled, sprout_created_tick,
                                        sprout_prefix)
from infinigrow.engine.tick import run_tick


def _settings(tmp_path, subject=None):
    return load_settings(env={}, state_root=str(tmp_path / "state"),
                         repo_root=str(REPO_ROOT),
                         subject_root=str(subject or (tmp_path / "subject")))


def test_no_sample_is_not_zero():
    report = redemption_report([])
    assert report["判定"] == "无样本" and report["兑现率"] is None
    assert report["样本数"] == 0 and report["总行数"] == 0
    assert "不可计算" in report["说明"] and "不是 0" in report["说明"]


def test_mechanical_only_rows_are_not_samples(tmp_path):
    """机械拍的「打脸」行不算样本（那时候根本没有手在动）。"""
    rows = [{"redeemed": False, "sample": False, "sprout_id": "sp1-001-x",
             "predicted_edge": "判读", "actual_edge": None}]
    report = redemption_report(rows)
    assert report["判定"] == "无样本" and report["总行数"] == 1 and report["样本数"] == 0


def test_legacy_rows_without_the_field_are_not_samples():
    """v2.0 及更早的行没有 `sample` 字段 → 不当样本（那时候没有执行者通道）。"""
    assert sampled({"redeemed": True}) is False
    assert sampled({"redeemed": True, "sample": True}) is True
    assert sampled({"redeemed": True, "sample": "yes"}) is False
    assert redemption_report([{"redeemed": True}])["判定"] == "无样本"


def test_real_sample_gives_rate_and_buckets():
    rows = [
        {"redeemed": True, "sample": True, "sprout_id": "sp1-001-a",
         "predicted_edge": "判读", "actual_edge": "判读"},
        {"redeemed": False, "sample": True, "sprout_id": "sp2-002-b",
         "predicted_edge": "行动", "actual_edge": None},
        {"redeemed": False, "sample": False, "sprout_id": "sp3-003-c",
         "predicted_edge": "行动", "actual_edge": None},          # 不进分母
    ]
    report = redemption_report(rows)
    assert report["判定"] == "有样本" and report["样本数"] == 2
    assert report["兑现率"] == 0.5
    assert report["总行数"] == 3
    assert "非样本已排除" in report["说明"]


def test_tick_writes_sample_flag_accordingly(tmp_path):
    """真机两态：没有执行者的那拍写 sample=false；接上执行者后写 sample=true。"""
    subject = tmp_path / "subject"
    subject.mkdir()
    (subject / "notes.md").write_text("x", encoding="utf-8")
    settings = _settings(tmp_path, subject)
    preds = [Prediction("X", "大小", "1", tick=1, evidence="p1")]
    obs = [Observation("X", "大小", "2", "文件:x")]
    run_tick(settings=settings, tick=1, predictions=preds, observations=obs)   # 造出芽
    run_tick(settings=settings, tick=2, predictions=preds, observations=obs)   # 无执行者领题
    run_tick(settings=settings, tick=3, predictions=preds, observations=obs,
             llm=lambda prompt: "假执行者：不动手")                               # 有执行者
    layout = resolve_state(settings.state_root, settings.repo_root)
    rows = [json.loads(line) for line in
            layout.outcome_ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [r["sample"] for r in rows] == [False, True]
    report = redemption_report(rows)
    assert report["判定"] == "有样本" and report["样本数"] == 1 and report["总行数"] == 2


def test_report_renders_无样本_instead_of_zero(tmp_path):
    """对账报告里必须写「无样本」，不许写成 0 或「差」。"""
    subject = tmp_path / "subject"
    subject.mkdir()
    settings = _settings(tmp_path, subject)
    run_tick(settings=settings, tick=1,
             predictions=[Prediction("X", "大小", "1", tick=1, evidence="p1")],
             observations=[Observation("X", "大小", "2", "文件:x")])
    layout = resolve_state(settings.state_root, settings.repo_root)
    text = (layout.reconcile_dir / "reconcile-00001.md").read_text(encoding="utf-8")
    assert "判定：**无样本**" in text
    assert "不可计算" in text
    assert "兑现率：0" not in text

def test_unverifiable_rows_stay_out_of_the_denominator():
    """**读不到 ≠ 打脸**：维度机械层读不到的行（例如「应用面」这类语义维度）不计入兑现率。

    实测踩到过：成熟链封顶芽的维度是「应用面」，机械层永远读不到它，
    于是它们永远判「打脸」——兑现率被结构性假数字拖成 0%。
    """
    rows = [
        {"redeemed": True, "sample": True, "verifiable": True, "sprout_id": "sp1-001-a",
         "predicted_edge": "判读", "actual_edge": "判读"},
        {"redeemed": False, "sample": True, "verifiable": False, "sprout_id": "cap1-001-a",
         "predicted_edge": "固化", "actual_edge": None},        # 不可对账 → 不进分母
    ]
    report = redemption_report(rows)
    assert report["判定"] == "有样本"
    assert report["样本数"] == 1 and report["兑现率"] == 1.0
    assert report["不可对账"] == 1
    assert "读不到≠打脸" in report["说明"].replace(" ", "")


def test_cap_sprout_outcome_is_unverifiable_without_the_evidence_edge(tmp_path):
    """**未接证据边**的 cap 行仍须如实标 `verifiable=False`（读不到≠打脸）。

    这是「不带题面」的调用形态（`evaluate_outcome` 不给 `evidence_key`）——它守的是老口径的
    底线：机械层读不到的维度**不许**算进兑现率。接上证据边的形态在 `tests/test_app_edge.py`
    （Q2：cap 芽当题面时多下一条「证据件存在」的预测，那行才是可对账的）。
    """
    from infinigrow.engine.model import Sprout, SproutOrigin
    from infinigrow.engine.tick import evaluate_outcome
    cap = Sprout(id="cap0001-001-x", obj="主体/x.md", dimension="应用面", pointer="p",
                 origin=SproutOrigin.MATURITY_CAP, created_tick=1)
    row = evaluate_outcome(cap, [], tick=2, sampled=True, observable_keys=[],
                           evidence_key=None)
    assert row.verifiable is False and row.redeemed is False


# --------------------------------------------------- Q6：兑现分桶归因（可复跑的函数形态）
def test_sprout_id_prefix_and_created_tick_are_parsed_mechanically():
    """芽 ID 的拍号段与前缀是**机械锚**（`sp0326-001-…` → 前缀 sp／出生拍 326）。"""
    assert sprout_prefix("sp0326-001-主体_journal_") == "sp"
    assert sprout_prefix("cap0380-002-x") == "cap"
    assert sprout_prefix("") == "（无前缀）"
    assert sprout_created_tick("sp0326-001-主体_journal_") == 326
    assert sprout_created_tick("cap0380-002-x") == 380
    assert sprout_created_tick("没有拍号段的旧行") is None    # 取不到就不猜


def test_attribution_splits_leads_by_source_and_failure_by_sprout_age():
    """M10/B2/B3：按芽源分桶 + 打脸按**领做时芽龄**分桶（提议过期 vs 真没做）。

    芽龄 = 领做拍 − 出生拍（出生拍取自芽 ID）。≥ 阈值＝提议过期（[归纳待证] 的机械代理），
    < 阈值＝真没做。不可对账的行单独计数（读不到≠打脸）。
    """
    rows = [
        # 差异芽：出生 100、101 拍就被领做（芽龄 1）→ 兑现
        {"sprout_id": "sp0100-001-a", "tick": 101, "redeemed": True,
         "sample": True, "verifiable": True},
        # 差异芽：出生 10、390 拍才被领做（芽龄 380 ≥ 30）→ 打脸 → 提议过期
        {"sprout_id": "sp0010-002-b", "tick": 390, "redeemed": False,
         "sample": True, "verifiable": True},
        # 差异芽：出生 400、402 拍被领做（芽龄 2 < 30）→ 打脸 → 真没做
        {"sprout_id": "sp0400-003-c", "tick": 402, "redeemed": False,
         "sample": True, "verifiable": True},
        # 固化边：可对账 0（A3/N60 的现场形态：占取题位却永远判不出兑现）
        {"sprout_id": "cap0380-001-d", "tick": 433, "redeemed": False,
         "sample": True, "verifiable": False},
    ]
    report = redemption_attribution(rows, stale_after=30)
    assert report["领做"]["总"] == 4
    assert report["领做"]["按前缀"] == {"sp": 3, "cap": 1}
    assert report["可对账样本"] == 3 and report["兑现"] == 1 and report["打脸"] == 2
    assert report["不可对账"] == 1
    assert report["按芽源"]["cap"] == {"领做": 1, "可对账": 0, "兑现": 0, "打脸": 0,
                                       "不可对账": 1}
    attribution = report["打脸归因"]
    assert attribution["提议过期"]["n"] == 1 and attribution["真没做"]["n"] == 1
    stale = attribution["提议过期"]["行"][0]
    assert (stale["sprout_id"], stale["出生拍"], stale["等待拍数"]) == ("sp0010-002-b", 10, 380)
    undone = attribution["真没做"]["行"][0]
    assert (undone["sprout_id"], undone["等待拍数"]) == ("sp0400-003-c", 2)
    # 窗口：只看该拍及之后（长窗口复验收口用同一个函数复跑）
    windowed = redemption_attribution(rows, tick_from=400, stale_after=30)
    assert windowed["领做"]["总"] == 2 and windowed["领做"]["按前缀"] == {"sp": 1, "cap": 1}
    assert windowed["窗口"]["起拍"] == 402


def test_attribution_threshold_is_explicit_and_changeable():
    """阈值是**显式参数**（默认 30 拍），不是藏在代码里的魔数——判据可复核、可改口径。"""
    rows = [{"sprout_id": "sp0010-002-b", "tick": 40, "redeemed": False,
             "sample": True, "verifiable": True}]        # 芽龄 = 40 − 10 = 30
    assert redemption_attribution(rows)["打脸归因"]["提议过期"]["n"] == 1     # 30 ≥ 默认 30
    looser = redemption_attribution(rows, stale_after=31)
    assert looser["打脸归因"]["真没做"]["n"] == 1 and looser["打脸归因"]["提议过期"]["n"] == 0


def test_attribution_reports_no_sample_instead_of_zero():
    """零领做行 → 窗口为空、不假装有数据（与兑现率的诚实口径一致）。"""
    report = redemption_attribution([])
    assert report["领做"]["总"] == 0 and report["可对账样本"] == 0
    assert report["窗口"]["起拍"] is None and report["窗口"]["止拍"] is None
    assert report["打脸归因"]["提议过期"]["n"] == 0


def test_attribution_puts_unparsed_executor_output_in_its_own_bucket(tmp_path):
    """执行者侧「输出未解析」→ 单独一桶，**不记到提议的账上**（真机拍 449 的形态）。

    现场：模型回了带 `actions` 的 JSON，但开头少了 `{"` → 适配器解析失败 → 整条回复
    （含写入动作）被丢弃 → 引擎如实记打脸。芽龄是 59（≥30），按老口径会被记成「提议过期」，
    那是把执行者侧的解析故障记成提议的账。
    """
    from infinigrow.engine.reconcile import executor_output_unparsed
    traces = tmp_path / "traces"
    traces.mkdir()
    (traces / "tick-00449.md").write_text(
        "## 输出（原样）\n\n```text\n\"say\": \"…\"\n```\n"
        "留痕说明：第 1 轮输出不是 JSON，按最终留痕处理。\n", encoding="utf-8")
    (traces / "tick-00450.md").write_text("## 输出（原样）\n\n```text\n{}\n```\n",
                                          encoding="utf-8")
    assert executor_output_unparsed(traces, 449) is True
    assert executor_output_unparsed(traces, 450) is False
    assert executor_output_unparsed(None, 449) is False          # 不给目录 → 不猜
    rows = [
        # 拍 449：芽龄 59（按芽龄会被记成「提议过期」），但留痕说输出没解析
        {"sprout_id": "cap0390-001-a", "tick": 449, "redeemed": False, "sample": True,
         "verifiable": True, "obj": "主体/x.md", "predicted_edge": "固化"},
        # 拍 450：没有未解析标记、芽龄 31 → 提议过期
        {"sprout_id": "sp0419-002-b", "tick": 450, "redeemed": False, "sample": True,
         "verifiable": True, "obj": "主体/y.md", "predicted_edge": "判读"},
    ]
    with_traces = redemption_attribution(rows, traces_dir=traces)
    buckets = with_traces["打脸归因"]
    assert buckets["执行者侧未落地"]["n"] == 1
    assert buckets["执行者侧未落地"]["行"][0]["sprout_id"] == "cap0390-001-a"
    assert buckets["提议过期"]["n"] == 1
    assert buckets["提议过期"]["行"][0]["sprout_id"] == "sp0419-002-b"
    # 不给 traces_dir（旧调用形态）→ 行为与从前一致：全部按芽龄分
    legacy = redemption_attribution(rows)
    assert legacy["打脸归因"]["执行者侧未落地"]["n"] == 0
    assert legacy["打脸归因"]["提议过期"]["n"] == 2


def test_executor_tick_failures_only_counts_ticks_with_no_landing_attempt():
    """执行者退出码的**按拍聚合**口径：该拍每次 tick 调用都失败才算「没落地」。

    三条边界都来自真库形态（`state/executor.jsonl`）：① 重试成功（拍 3/4 的形态：先 rc=1
    再 rc=0）不能算执行者侧失败，否则把已落地的动作开脱掉；② 组织段调用（`kind` 非 tick）
    与芽无关，不能替芽的打脸开脱；③ 没给账本（旧调用形态／CI 冷启动空根）→ 空表，不猜。
    """
    rows = [
        {"tick": 723, "kind": "tick", "rc": 1, "timed_out": False, "attempt": 1},
        {"tick": 500, "kind": "tick", "rc": 1, "timed_out": False, "attempt": 1},
        {"tick": 500, "kind": "tick", "rc": 0, "timed_out": False, "attempt": 2},
        {"tick": 600, "kind": "tick", "rc": 0, "timed_out": False, "attempt": 1},
        {"tick": 700, "kind": "org-session", "rc": 1, "timed_out": False, "attempt": 1},
        {"tick": 800, "kind": "tick", "rc": 0, "timed_out": True, "attempt": 1},
    ]
    failures = executor_tick_failures(rows)
    assert sorted(failures) == [723, 800]
    assert failures[723]["rc"] == 1 and failures[723]["timed_out"] is False
    assert failures[800]["timed_out"] is True
    assert executor_tick_failures([]) == {}
    assert executor_tick_failures(None) == {}


def test_attribution_uses_executor_exit_code_before_the_sprout_age(tmp_path):
    """真机拍 723 的形态：执行者非零退出 → 记「执行者侧未落地」，**不记成主体没做**。

    现场：`state/executor.jsonl` 拍 723 有一行 rc=1、usage=unknown、note「非零退出（stderr
    见留痕）」，同拍 `outcomes.jsonl` 的 `sp0695-051-…` 是 verifiable=True、redeemed=False。
    现行三分规则只认留痕「输出未解析」标记、不看退出码 → 那一行被判成「真没做」，
    把执行者侧的失败记在主体的账上。留痕里没有标记（适配器如实写了 stderr 见留痕），
    所以必须有**第二条**执行者侧证据：同拍所有 tick 调用都非零退出／超时。
    """
    rows = [
        {"sprout_id": "sp0695-051-主体_journal_0690", "tick": 723, "redeemed": False,
         "sample": True, "verifiable": True, "obj": "主体/journal/x.md",
         "predicted_edge": "判读"},                      # 芽龄 28 < 30 → 老口径＝真没做
        {"sprout_id": "cap0470-001-主体_app_0466", "tick": 499, "redeemed": False,
         "sample": True, "verifiable": True, "obj": "主体/journal/y.md",
         "predicted_edge": "固化"},                      # 该拍 rc=0 → 仍是真没做
    ]
    executor_rows = [
        {"tick": 723, "kind": "tick", "rc": 1, "timed_out": False},
        {"tick": 499, "kind": "tick", "rc": 0, "timed_out": False},
    ]
    buckets = redemption_attribution(rows, stale_after=30,
                                    executor_rows=executor_rows)["打脸归因"]
    assert buckets["执行者侧未落地"]["n"] == 1
    assert buckets["执行者侧未落地"]["行"][0]["sprout_id"] == "sp0695-051-主体_journal_0690"
    assert buckets["执行者侧未落地"]["行"][0]["执行者退出码"] == 1
    assert buckets["真没做"]["n"] == 1
    assert buckets["真没做"]["行"][0]["sprout_id"] == "cap0470-001-主体_app_0466"
    assert buckets["提议过期"]["n"] == 0
    # 不给执行者账（旧调用形态）→ 行为与从前完全一致
    legacy = redemption_attribution(rows, stale_after=30)["打脸归因"]
    assert legacy["执行者侧未落地"]["n"] == 0 and legacy["真没做"]["n"] == 2


def test_executor_exit_code_outranks_the_stale_age_proxy():
    """退出码证据**优先于**「提议过期」的机械代理（与留痕标记同一条纪律）。

    芽龄 ≥30 只说明前提老，不说明主体做没做；同一拍执行者压根没成功返回时，
    记在「提议过期」上同样是记错账。分子分母（可对账样本／兑现／打脸）不受归因影响。
    """
    rows = [{"sprout_id": "sp0100-001-a", "tick": 400, "redeemed": False,
             "sample": True, "verifiable": True}]        # 芽龄 300 ≥ 30
    executor_rows = [{"tick": 400, "kind": "tick", "rc": 1, "timed_out": False}]
    report = redemption_attribution(rows, stale_after=30, executor_rows=executor_rows)
    buckets = report["打脸归因"]
    assert buckets["执行者侧未落地"]["n"] == 1 and buckets["提议过期"]["n"] == 0
    assert report["可对账样本"] == 1 and report["兑现"] == 0 and report["打脸"] == 1


def test_redemption_cli_prints_attribution(tmp_path, capsys):
    """`infinigrow redemption` 打出可复跑的读数（谁在领做／打脸归因／固化边占比）。"""
    from infinigrow.cli import main
    (tmp_path / "state").mkdir()
    rows = [{"sprout_id": "cap0380-001-d", "tick": 433, "redeemed": False,
             "sample": True, "verifiable": False, "obj": "主体/x", "predicted_edge": "固化"},
            {"sprout_id": "sp0430-002-e", "tick": 433, "redeemed": True,
             "sample": True, "verifiable": True, "obj": "主体/y", "predicted_edge": "判读"}]
    lines = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    (tmp_path / "state" / "outcomes.jsonl").write_text(lines + "\n", encoding="utf-8")
    rc_ = main(["--state-root", str(tmp_path / "state"), "redemption"])
    out = capsys.readouterr().out
    assert rc_ == 0
    assert "兑现分桶归因" in out and "固化边占取题位：1/2" in out
    assert "打脸归因：执行者侧未落地 0／提议过期 0／真没做 0" in out

