#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_prompt_code_sync —— 提示词与代码的**同源校验机**（T7）。

要解决的问题：同一件事两处写（提示词一处、代码一处），改一处忘另一处就漂移。
本项目就是这么长出「芽源两套规则并存」的：提示词里写着「完成即分岔必须自造芽」，
代码/设计正本里写着「芽＝预测差异的产物」——两条规则互相打架，直到引擎原地打转才被看见。

本工具做**双向**检查：

    提示词里的机制关键词 → 必须在代码里有定义（哪条边、哪个来源、哪个账本）
    代码里定义的机制关键词 → 必须在提示词里出现（否则运行时会话不知道有这回事）

判据是机械的：关键词表 `SYNC_TERMS` 定义在 `src/infinigrow/rules/static_scan.py`
（单一事实源），本工具只是它的命令行入口，**不另抄一份表**。

用法：
    python tools/check_prompt_code_sync.py            # 扫本仓库
    python tools/check_prompt_code_sync.py --repo <路径>
退出码：0=同源；2=有漂移（可直接当 CI 闸）。
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="提示词↔代码同源校验")
    ap.add_argument("--repo", default=str(REPO_ROOT))
    args = ap.parse_args(argv)

    from infinigrow.rules.static_scan import RuleContext, rule_prompt_code_sync, SYNC_TERMS

    repo = Path(args.repo).resolve()
    ctx = RuleContext.from_repo(repo)
    detail, ok = rule_prompt_code_sync(ctx)

    print("同源校验机 · 关键词表 %d 项" % len(SYNC_TERMS))
    for term, owner in sorted(SYNC_TERMS.items()):
        print("  %-8s → %s" % (term, owner))
    print("\n判定：%s" % ("同源" if ok else "漂移"))
    print("明细：%s" % detail)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
