# -*- coding: utf-8 -*-
"""命令行入口：`python -m infinigrow <子命令>`。

子命令刻意做得少——每个都对应一条「人真会手敲」的命令：

    version          版本与代号（--check 与最新发布比对）
    tick             跑一拍（不给执行者＝机械拍，零 token）
    dry-run          只解析配置与路径，不跑、不写（冒烟）
    gardener         跑一次机械园丁（含账本轮转与看护）
    rotate           账本轮转（只移动不删；也可由园丁顺手做）
    scan             静态规则扫描（CI 用的就是它）
    selftest         规则自检（正/反用例）
    org-check        看组织会话该不该触发（打印判据明细）
    org-session      跑一次组织会话（需要执行者；独立于拍）
    org-status       看组织会话发现账的**结局**（待验/被证实/被推翻）
    status           一键总览（拍号/主体/队列/兑现率/能力库候选池/告警）
    redemption       兑现分桶归因（谁在领做／打脸里「提议过期」与「真没做」各几条）

退出码语义见 `core/exit_codes.py`（单一来源；R7 守「cli 里不出现裸整数」）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from . import __codename__, __version__
from .core import exit_codes as rc
from .core.config import load_settings
from .core.encoding import harden_stdio
from .core.paths import resolve_state
from .engine.tick import run_tick
from .garden.gardener import run_gardener
from .rules.static_scan import RuleContext, scan, selftest
from .scheduler.triggers import should_run_org_session, DEFAULT_GAP_TICKS


def _ctx(settings) -> RuleContext:
    ctx = RuleContext.from_repo(settings.repo_root)
    ctx.state_root = resolve_state(settings.state_root, settings.repo_root, create=False).root
    return ctx


def main(argv=None) -> int:
    harden_stdio()
    ap = argparse.ArgumentParser(prog="infinigrow", description="Infinigrow 引擎 CLI")
    ap.add_argument("--state-root", default=None, help="状态根（默认 <repo>/state）")
    ap.add_argument("--subject-root", default=None,
                    help="生长主体根（默认 <repo 同级>/<仓库名>-subject）")
    ap.add_argument("--config", default=None, help="配置文件（toml/json）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_ver = sub.add_parser("version", help="打印版本（--check 与最新发布比对）")
    p_ver.add_argument("--check", action="store_true",
                       help="查 GitHub 最新发布并比对（只读公开接口、零凭据；离线则报 unknown）")
    p_tick = sub.add_parser("tick", help="跑一拍")
    p_tick.add_argument("--tick", type=int, default=None, help="指定拍号（默认自增）")
    p_tick.add_argument("--probe", action="store_true", help="打印芽源判定明细")
    p_tick.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    p_tick.add_argument("--executor", default=None,
                        help="执行者命令（提示词经 stdin 进、stdout 出；不给＝机械拍）")
    p_tick.add_argument("--executor-timeout", type=int, default=None,
                        help="单次执行者调用超时（秒，默认取配置）")
    p_tick.add_argument("--no-executor", action="store_true",
                        help="强制机械拍（即使配置里设了执行者）")
    p_tick.add_argument("--no-org", action="store_true", help="本拍不跑组织会话")
    sub.add_parser("dry-run", help="只解析配置与路径（零写盘）")
    sub.add_parser("gardener", help="跑一次机械园丁（含轮转与看护）")
    p_rot = sub.add_parser("rotate", help="账本与留痕/报告轮转（只移动不删）")
    p_rot.add_argument("--max-bytes", type=int, default=None, help="超过这么多字节才轮转")
    p_rot.add_argument("--keep-tail", type=int, default=None, help="主账本保留尾部行数")
    p_rot.add_argument("--keep-files", type=int, default=None, help="留痕/报告保留最近份数")
    p_rot.add_argument("--search", default=None, help="在归档区检索关键词（可检索性）")
    p_scan = sub.add_parser("scan", help="静态规则扫描")
    p_scan.add_argument("--json", action="store_true")
    sub.add_parser("selftest", help="规则自检（正/反用例）")
    sub.add_parser("org-check", help="看组织会话该不该触发")
    p_org = sub.choices["org-check"]
    p_org.add_argument("--tick", type=int, required=True)
    p_org.add_argument("--gap", type=int, default=DEFAULT_GAP_TICKS)
    p_orgs = sub.add_parser("org-session", help="跑一次组织会话（需要执行者）")
    p_orgs.add_argument("--tick", type=int, required=True)
    p_orgs.add_argument("--executor", default=None, help="执行者命令（同 tick）")
    p_orgs.add_argument("--json", action="store_true")
    sub.add_parser("org-status", help="看组织会话发现的结局（可被打脸的机械形态）")
    sub.add_parser("status", help="一键总览：拍号/主体/队列/兑现率/告警一行看完")
    p_red = sub.add_parser("redemption", help="兑现分桶归因：谁在领做／打脸归因（可复跑）")
    p_red.add_argument("--from-tick", type=int, default=None, help="只看该拍及之后的领做行")
    p_red.add_argument("--stale-after", type=int, default=None,
                       help="「提议过期」的芽龄阈值（拍；默认 30）")
    p_red.add_argument("--json", action="store_true")
    p_pause = sub.add_parser("pause", help="暂停引擎（停计划任务，**不删**；可 resume 恢复）")
    p_pause.add_argument("--task", default=None, help="计划任务名（默认 Infinigrow_tick）")
    p_resume = sub.add_parser("resume", help="恢复引擎（启用计划任务）")
    p_resume.add_argument("--task", default=None, help="计划任务名（默认 Infinigrow_tick）")

    args = ap.parse_args(argv)
    settings = load_settings(args.config, state_root=args.state_root,
                             subject_root=args.subject_root)

    if args.cmd == "version":
        print("%s %s" % (__codename__, __version__))
        if args.check:
            from .core.version_check import verdict
            v = verdict(__version__)
            print("最新发布：%s（%s）" % (v["latest"] or "未知", v["note"]))
            print(v["upgrade_hint"])
            # 落后 = rc 3（可被脚本/守护脚本当闸用）；离线 unknown = 0，不误报
            return rc.BEHIND if v["status"] == "behind" else rc.OK
        return rc.OK

    if args.cmd == "dry-run":
        layout = resolve_state(settings.state_root, settings.repo_root, create=False)
        subject = settings.subject_path()
        executor = settings.executor_command()
        print("配置来源：%s" % "、".join(settings.sources))
        print("仓库根：%s" % settings.repo_root)
        print("状态根：%s（存在=%s）" % (layout.root, layout.root.exists()))
        print("**生长主体根**：%s（存在=%s）" % (subject, subject.is_dir()))
        print("提示词目录：%s（存在=%s）" % (settings.prompts_path(),
                                          settings.prompts_path().exists()))
        print("执行者：%s" % (("已配置（%s），超时 %ds"
                            % (executor.split()[0] if executor else "",
                               settings.executor_timeout_s)) if executor
                            else "（无：机械拍，零 token、零凭据、不出网）"))
        print("外部凭据目录：%s" % (settings.key_dir or "（无：本跑不需要凭据）"))
        print("出网代理：%s" % (settings.proxy_url or "（无）"))
        print("队列上限=%d｜连领上限=%d｜冷启动拍数=%d｜组织段空窗=%d 拍｜"
              "组织段冷却=%d 分｜调度间隔=%d 分"
              % (settings.queue_cap, settings.lead_limit, settings.cold_start_ticks,
                 settings.org_gap_ticks, settings.org_cooldown_min, settings.tick_minutes))
        return rc.OK

    if args.cmd == "tick":
        executor = None if args.no_executor else (
            args.executor if args.executor is not None else settings.executor_command())
        if args.executor_timeout is not None:
            settings.executor_timeout_s = args.executor_timeout
        if args.no_executor:
            settings.executor = ""
            settings.llm_command = ""
        result = run_tick(settings=settings, tick=args.tick, probe=args.probe,
                          executor=executor, org_session=not args.no_org)
        if args.json:
            print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        else:
            print("拍 %d 完成 rc=%d%s｜差异 %s｜新生芽 %d｜报告见 state/reconcile/"
                  % (result.tick, result.rc, "（跳过：并发）" if result.skipped else "",
                     json.dumps(result.diff_summary, ensure_ascii=False),
                     len(result.new_sprouts)))
            if result.subject:
                print("主体：%s（文件 %s，共 %s 字节）"
                      % (result.subject.get("root_name"), result.subject.get("file_count"),
                         result.subject.get("total_bytes")))
            if result.executor:
                print("执行者：%s" % result.executor["label"])
            elif result.skipped:
                pass
            else:
                # 三态分开说：未接执行者 ≠ 接了但本拍无芽可领（后者不该被说成「机械拍」）
                print("执行者：%s" % result.executor_line())
            if result.org:
                print("组织会话：%s" % result.org.get("summary"))
            if result.org_decision:
                print("组织段到期判据：%s（%s）"
                      % ("**该跑了**" if result.org_decision["should_run"] else "不需要",
                         result.org_decision["reason"]))
        return rc.OK if result.rc == 0 else result.rc

    if args.cmd == "gardener":
        report = run_gardener(settings=settings)
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
        return rc.RULES_FAIL if report.fatal else rc.OK

    if args.cmd == "rotate":
        from .ledger.rotation import (archived_files, rotate_all, rotate_files,
                                      search_archive)
        layout = resolve_state(settings.state_root, settings.repo_root, create=True)
        if args.search:
            hits = search_archive(layout, args.search)
            print("归档区检索 %r：命中 %d" % (args.search, len(hits)))
            for hit in hits:
                print("  - %s" % hit)
            return rc.OK
        reports = rotate_all(layout,
                            max_bytes=(args.max_bytes if args.max_bytes is not None
                                       else settings.rotate_max_bytes),
                            keep_tail=(args.keep_tail if args.keep_tail is not None
                                       else settings.rotate_keep_tail))
        file_reports = rotate_files(layout,
                                    keep_files=(args.keep_files if args.keep_files is not None
                                                else settings.rotate_keep_files),
                                    log_max_bytes=(args.max_bytes if args.max_bytes is not None
                                                   else settings.rotate_max_bytes))
        if not reports and not file_reports:
            print("无账本/留痕超阈值：不动（账本阈值 %d 字节，保留尾部 %d 行；"
                  "留痕/报告保留最近 %d 份）"
                  % (settings.rotate_max_bytes, settings.rotate_keep_tail,
                     settings.rotate_keep_files))
        for r in reports:
            print("轮转 %s：移动 %d 行 → %s（%d→%d 字节）"
                  % (r["name"], r["moved"], r["archive"], r["bytes_before"],
                     r["bytes_after"]))
        for r in file_reports:
            print("轮转 %s：移动 %d 份 → %s（保留 %d 份）"
                  % (r["name"], r["moved"], r["archive"], r["kept"]))
        print("归档区现有：%s" % ("、".join(archived_files(layout)) or "（空）"))
        return rc.OK

    if args.cmd == "scan":
        report = scan(_ctx(settings))
        print(json.dumps({"ok": report.ok, "rows": report.rows}, ensure_ascii=False, indent=2)
              if args.json else "\n".join(report.rows))
        return rc.OK if report.ok else rc.RULES_FAIL

    if args.cmd == "selftest":
        import tempfile
        with tempfile.TemporaryDirectory(prefix="infinigrow-selftest-") as tmp:
            report = selftest(Path(tmp))
        print("\n".join(report.rows))
        print("自检总判定：%s" % ("全绿" if report.ok else "有 FAIL"))
        return rc.OK if report.ok else rc.RULES_FAIL

    if args.cmd == "org-check":
        layout = resolve_state(settings.state_root, settings.repo_root, create=False)
        decision = should_run_org_session(layout, args.tick, gap=args.gap,
                                         cooldown_min=settings.org_cooldown_min)
        print(json.dumps(decision.as_dict(), ensure_ascii=False, indent=2))
        return rc.OK if decision.should_run else rc.USAGE

    if args.cmd == "org-session":
        from .engine.domain_saturation import DomainState
        from .engine.executor import KIND_ORG, make_runner
        from .engine.org_session import run_org_session
        from .engine.sprout_queue import SproutQueue
        layout = resolve_state(settings.state_root, settings.repo_root, create=True)
        subject = settings.subject_path()
        queue = SproutQueue.load(layout.sprouts, layout.frozen_sprouts,
                                 cap=settings.queue_cap, lead_limit=settings.lead_limit,
                                 cold_start_ticks=settings.cold_start_ticks)
        domains = DomainState.load(layout.domains)
        command = (args.executor if args.executor is not None
                   else settings.executor_command())
        runner = make_runner(command=command, callable_fn=None, tick=args.tick,
                             kind=KIND_ORG, cwd=settings.repo_path,
                             state_root=layout.root, subject_root=subject,
                             timeout_s=settings.executor_timeout_s,
                             model=settings.llm_model)
        if runner is None:
            print("未接执行者：组织会话需要执行者通道（--executor 或配置 IG_EXECUTOR）。"
                  "机制不会自己长出手来。")
            return rc.USAGE
        run = run_org_session(settings=settings, layout=layout, tick=args.tick,
                              subject_root=subject, queue=queue, domains=domains,
                              runner=runner)
        queue.save(layout.sprouts, layout.frozen_sprouts, layout.root)
        domains.save(layout)
        if args.json:
            print(json.dumps({"ran": run.ran, "summary": run.summary(),
                              "findings": [f.as_record(args.tick) for f in run.findings],
                              "sprouts": run.sprouts, "absorbed": run.absorbed,
                              "predictions": [p.__dict__ for p in run.predictions],
                              "parse_error": run.parse_error,
                              "trace": run.trace.name if run.trace else ""},
                             ensure_ascii=False, indent=2))
        else:
            print("组织会话：%s" % run.summary())
            for note in run.notes:
                print("  - %s" % note)
            print("留痕：%s" % (run.trace.name if run.trace else "（无）"))
        if run.parse_error and not run.findings:
            return rc.RULES_FAIL
        return rc.OK

    if args.cmd == "org-status":
        from .engine.org_session import finding_status
        layout = resolve_state(settings.state_root, settings.repo_root, create=False)
        rows = finding_status(layout)
        counts: dict[str, int] = {}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        print("组织会话发现 %d 条：%s"
              % (len(rows), json.dumps(counts, ensure_ascii=False)))
        for row in rows[-10:]:
            print("  - 拍%s｜%s｜%s｜%s｜指针=%s → %s"
                  % (row.get("tick"), row.get("kind"), row.get("obj"),
                     row.get("dimension"), row.get("pointer") or "（缺）", row["status"]))
        return rc.OK

    if args.cmd == "status":
        return _cmd_status(settings)

    if args.cmd == "redemption":
        from .engine.reconcile import STALE_LEAD_TICKS, redemption_attribution
        from .ledger.store import read_jsonl
        layout = resolve_state(settings.state_root, settings.repo_root, create=False)
        report = redemption_attribution(
            read_jsonl(layout.outcome_ledger), tick_from=args.from_tick,
            stale_after=(args.stale_after if args.stale_after is not None
                         else STALE_LEAD_TICKS))
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return rc.OK
        win = report["窗口"]
        print("兑现分桶归因（拍 %s→%s，%d 行领做）"
              % (win["起拍"], win["止拍"], win["行数"]))
        print("  领做：总 %d（按芽源前缀 %s）"
              % (report["领做"]["总"],
                 json.dumps(report["领做"]["按前缀"], ensure_ascii=False)))
        for source, stat in sorted(report["按芽源"].items()):
            print("  - %s：领做 %d／可对账 %d（兑现 %d、打脸 %d）／不可对账 %d"
                  % (source, stat["领做"], stat["可对账"], stat["兑现"],
                     stat["打脸"], stat["不可对账"]))
        attribution = report["打脸归因"]
        print("  打脸归因：提议过期 %d／真没做 %d（芽龄阈值 %d 拍）"
              % (attribution["提议过期"]["n"], attribution["真没做"]["n"],
                 attribution["提议过期"]["阈值拍"]))
        total = report["领做"]["总"]
        if total:
            cap_leads = (report["按芽源"].get("cap") or {}).get("领做", 0)
            print("  固化边占取题位：%d/%d = %.2f"
                  % (cap_leads, total, cap_leads / total))
        return rc.OK

    if args.cmd in ("pause", "resume"):
        return _toggle_task(args.cmd, args.task)

    return rc.USAGE


def _cmd_status(settings) -> int:
    """T8/A15 一键总览：拍号／主体文件数／队列／兑现率判定／ALERT 首行／今日执行者用量。"""
    from .core.paths import resolve_state as _resolve
    from .engine.reconcile import redemption_report
    from .engine.tick import read_tick_status
    from .ledger.store import read_jsonl
    layout = _resolve(settings.state_root, settings.repo_root, create=False)
    status = read_tick_status(layout)
    print("Infinigrow 状态（状态根 %s）" % layout.root)
    print("  拍号：%s（心跳 %s；连续失败 %d；执行者连续失败 %d）"
          % (status.get("tick", "?"), status.get("last_time") or "（无）",
             int(status.get("consecutive_failures") or 0),
             int(status.get("consecutive_executor_failures") or 0)))

    # K8/A6 空转成本显形：连续「无芽可领」拍数（接了执行者但没活干，零 token 但空转）。
    # 机械拍（未接执行者）不算——零 token 本来就是它的预期。
    stall = int(status.get("no_ticket_streak", 0) or 0)
    if stall > 0:
        print("  空转：连续 %d 拍无芽可领（零 token；阈值 %d 拍≈%.0f 小时告警）"
              % (stall, settings.stall_alert_ticks,
                 settings.stall_alert_ticks * settings.tick_minutes / 60.0))
    else:
        print("  空转：0 拍（有芽可领或未接执行者）")

    snapshot = {}
    if layout.subject_snapshot.is_file():
        try:
            snapshot = json.loads(layout.subject_snapshot.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            snapshot = {}
    print("  主体：%s（存在=%s，文件 %s 个，共 %s 字节）"
          % (snapshot.get("root_name") or "（无快照）",
             snapshot.get("exists"), snapshot.get("file_count"),
             snapshot.get("total_bytes")))

    from .engine.sprout_queue import SproutQueue
    queue = SproutQueue.load(layout.sprouts, layout.frozen_sprouts,
                             cap=settings.queue_cap, lead_limit=settings.lead_limit,
                             cold_start_ticks=settings.cold_start_ticks)
    s = queue.summary()
    # K4/A5：可领数＝`leads<3` 且非冻结（长任务芽豁免连领上限，也算可领）。
    # 「活跃」只是非冻结行数，**不等于可领**——空转期 25 根全 leads=3，可领 0
    # （状态面曾因此误导过：显示「活跃 25」让人以为有 25 个活可干）。
    eligible = len(queue.eligible(0))
    print("  队列：可领 %d 根／共 %d 根（活跃 %d／冻结 %d，芽源分布 %s）"
          % (eligible, s["active"] + s["frozen"], s["active"], s["frozen"],
             json.dumps(s["by_origin"], ensure_ascii=False)))

    report = redemption_report(read_jsonl(layout.outcome_ledger))
    rate = report.get("兑现率")
    print("  兑现率：%s（样本 %d 条；%s）"
          % (report["判定"], report["样本数"],
             "%.2f" % rate if rate is not None else "不可计算"))
    cap = report.get("固化边") or {}
    if cap.get("n"):
        print("  固化边（应用面，未接证据边的行）：%d 条" % cap["n"])

    # N62/A8：能力库候选池组成——渠道静默是**预期**（池已空）还是**故障**（池有货却不出芽），
    # 这两种状态在状态面上必须能分开；此前没有任何读数说明这件事。
    from .engine.sprout_sources import library_entries, library_pool_summary
    tick_now = int(status.get("tick") or 0)
    pool = library_pool_summary(library_entries(read_jsonl(layout.library)), tick_now,
                                known_objects=queue.known_objects(
                                    tick_now, settings.frozen_requestion_ticks))
    print("  能力库候选池：未结案且未消费 %d 条／已结案 %d 条／已消费 %d 条"
          "（本可出芽 %d；重问冷却挡 %d／未到闲置阈值 %d）"
          % (pool["未结案未消费"], pool["已结案"], pool["已消费"],
             pool["本可出芽"], pool["重问冷却中"], pool["未到闲置阈值"]))
    print("  能力库渠道判定：%s" % pool["判定"])

    alert_line = "（无 ALERT.md）"
    alert_path = layout.root / "ALERT.md"
    if alert_path.is_file():
        for line in alert_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                alert_line = line
                break
    print("  ALERT 首行：%s" % alert_line)

    _print_usage_line(layout)
    return rc.OK


def _print_usage_line(layout) -> None:
    """T9/A16 成本与用量：只汇总**执行者自报**的用量（`IG_USAGE`），不拿长度冒充 token。

    **K9/A10**：失败调用（rc≠0/超时）即使没自报也显式记 `usage="unknown"`，
    在统计里**单列**「N 次失败未计费/未知」——成本账不许假装失败不存在。
    """
    from .ledger.store import read_jsonl as _read
    import datetime as _dt
    rows = _read(layout.executor_ledger)
    today = _dt.date.today().isoformat()
    calls = [r for r in rows if str(r.get("time", "")).startswith(today)]
    total_tokens = 0
    reported = 0
    failed_unknown = 0
    for r in calls:
        usage = r.get("usage")
        if usage == "unknown":                       # K9：失败未计费/未知，单列
            failed_unknown += 1
            continue
        if isinstance(usage, dict):
            reported += 1
            # 接受两种自报形态：`tokens`/`total_tokens`（合并口径）或
            # prompt/completion_tokens（分项口径）；不拿输出长度冒充 token
            t = usage.get("tokens") or usage.get("total_tokens")
            if t is not None:
                total_tokens += int(t)
            else:
                total_tokens += int(usage.get("prompt_tokens") or 0)
                total_tokens += int(usage.get("completion_tokens") or 0)
    if not calls:
        print("  今日执行者调用：0 次（今日尚未调用）")
        return
    if not reported and failed_unknown == 0:
        print("  今日执行者调用：%d 次；执行者**未自报用量**（IG_USAGE），token/花费不可估算"
              % len(calls))
        return
    base = ("  今日执行者调用：%d 次；自报用量 %d 次，token 合计 %d"
            % (len(calls), reported, total_tokens))
    if failed_unknown:
        base += "；**%d 次失败未计费/未知（usage=unknown）**" % failed_unknown
    print(base)


def _toggle_task(action: str, task: Optional[str]) -> int:
    """T8/A15 pause/resume：停/起计划任务（**不删**；任务仍在，resume 可恢复）。

    走 `Disable-ScheduledTask`/`Enable-ScheduledTask`，与 `scheduled_task.ps1` 同名约定
    （`IG_TASK_NAME` 或默认 `Infinigrow_tick`）。非 Windows 上报「环境不满足」（rc=4）。
    """
    import subprocess as _sp
    import os as _os
    task = task or _os.environ.get("IG_TASK_NAME") or "Infinigrow_tick"
    if sys.platform != "win32":
        print("计划任务仅 Windows（本机：%s）；未做任何动作。"
              "想停引擎可 Disable-ScheduledTask 或删除调度（见 docs/running.md）。" % sys.platform)
        return rc.REFUSE
    verb = "Disable" if action == "pause" else "Enable"
    cmd = ["powershell", "-NoProfile", "-Command",
           "%s-ScheduledTask -TaskName '%s' | Out-Null; "
           "(Get-ScheduledTask -TaskName '%s').State" % (verb, task, task)]
    proc = _sp.run(cmd, capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=60)
    out = (proc.stdout or "").strip()
    if proc.returncode != 0 or "Disabled" not in out and "Ready" not in out:
        print("FAIL：%s-ScheduledTask '%s' 失败（rc=%d）：%s%s"
              % (verb, task, proc.returncode, out, proc.stderr or ""))
        return rc.USAGE
    print("%s 计划任务 '%s' → %s" % ("暂停" if action == "pause" else "恢复",
                                     task, out))
    return rc.OK


if __name__ == "__main__":
    sys.exit(main())
