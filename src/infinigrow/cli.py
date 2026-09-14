# -*- coding: utf-8 -*-
"""命令行入口：`python -m infinigrow <子命令>`。

子命令刻意做得很少——每个都对应一条「人真会手敲」的命令：

    version          版本与代号
    tick             跑一拍（默认机械拍，零 token）
    dry-run          只解析配置与路径，不跑、不写（冒烟）
    gardener         跑一次机械园丁
    scan             静态规则扫描（CI 用的就是它）
    selftest         规则自检（正/反用例）
    org-check        看组织会话该不该触发（打印判据明细）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __codename__, __version__
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
    ap.add_argument("--config", default=None, help="配置文件（toml/json）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("version", help="打印版本")
    p_tick = sub.add_parser("tick", help="跑一拍")
    p_tick.add_argument("--tick", type=int, default=None, help="指定拍号（默认自增）")
    p_tick.add_argument("--probe", action="store_true", help="打印芽源判定明细")
    p_tick.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    sub.add_parser("dry-run", help="只解析配置与路径（零写盘）")
    sub.add_parser("gardener", help="跑一次机械园丁")
    p_scan = sub.add_parser("scan", help="静态规则扫描")
    p_scan.add_argument("--json", action="store_true")
    sub.add_parser("selftest", help="规则自检（正/反用例）")
    sub.add_parser("org-check", help="看组织会话该不该触发")
    p_org = sub.choices["org-check"]
    p_org.add_argument("--tick", type=int, required=True)
    p_org.add_argument("--gap", type=int, default=DEFAULT_GAP_TICKS)

    args = ap.parse_args(argv)
    settings = load_settings(args.config, state_root=args.state_root)

    if args.cmd == "version":
        print("%s %s" % (__codename__, __version__))
        return 0

    if args.cmd == "dry-run":
        layout = resolve_state(settings.state_root, settings.repo_root, create=False)
        print("配置来源：%s" % "、".join(settings.sources))
        print("仓库根：%s" % settings.repo_root)
        print("状态根：%s（存在=%s）" % (layout.root, layout.root.exists()))
        print("提示词目录：%s（存在=%s）" % (settings.prompts_path(),
                                          settings.prompts_path().exists()))
        print("外部凭据目录：%s" % (settings.key_dir or "（无：本跑不需要凭据）"))
        print("出网代理：%s" % (settings.proxy_url or "（无）"))
        print("队列上限=%d｜连领上限=%d｜冷启动拍数=%d"
              % (settings.queue_cap, settings.lead_limit, settings.cold_start_ticks))
        return 0

    if args.cmd == "tick":
        result = run_tick(settings=settings, tick=args.tick, probe=args.probe)
        if args.json:
            print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        else:
            print("拍 %d 完成 rc=%d%s｜差异 %s｜新生芽 %d｜报告见 state/reconcile/"
                  % (result.tick, result.rc, "（跳过：并发）" if result.skipped else "",
                     json.dumps(result.diff_summary, ensure_ascii=False),
                     len(result.new_sprouts)))
            if result.org_decision:
                print("组织段：%s（%s）"
                      % ("**该跑了**" if result.org_decision["should_run"] else "不需要",
                         result.org_decision["reason"]))
        return 0 if result.rc == 0 else result.rc

    if args.cmd == "gardener":
        report = run_gardener(settings=settings)
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
        return 2 if report.fatal else 0

    if args.cmd == "scan":
        report = scan(_ctx(settings))
        print(json.dumps({"ok": report.ok, "rows": report.rows}, ensure_ascii=False, indent=2)
              if args.json else "\n".join(report.rows))
        return 0 if report.ok else 2

    if args.cmd == "selftest":
        import tempfile
        with tempfile.TemporaryDirectory(prefix="infinigrow-selftest-") as tmp:
            report = selftest(Path(tmp))
        print("\n".join(report.rows))
        print("自检总判定：%s" % ("全绿" if report.ok else "有 FAIL"))
        return 0 if report.ok else 2

    if args.cmd == "org-check":
        layout = resolve_state(settings.state_root, settings.repo_root, create=False)
        decision = should_run_org_session(layout, args.tick, gap=args.gap)
        print(json.dumps(decision.as_dict(), ensure_ascii=False, indent=2))
        return 0 if decision.should_run else 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
