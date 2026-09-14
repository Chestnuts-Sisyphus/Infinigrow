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

退出码语义见 `core/exit_codes.py`（单一来源；R7 守「cli 里不出现裸整数」）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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
    p_rot = sub.add_parser("rotate", help="账本轮转（只移动不删）")
    p_rot.add_argument("--max-bytes", type=int, default=None, help="超过这么多字节才轮转")
    p_rot.add_argument("--keep-tail", type=int, default=None, help="主账本保留尾部行数")
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
                print("执行者：（无：机械拍，零 token）")
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
        from .ledger.rotation import archived_files, rotate_all, search_archive
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
        if not reports:
            print("无账本超阈值：不动（阈值 %d 字节，保留尾部 %d 行）"
                  % (settings.rotate_max_bytes, settings.rotate_keep_tail))
        for r in reports:
            print("轮转 %s：移动 %d 行 → %s（%d→%d 字节）"
                  % (r["name"], r["moved"], r["archive"], r["bytes_before"],
                     r["bytes_after"]))
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

    return rc.USAGE


if __name__ == "__main__":
    sys.exit(main())
