# -*- coding: utf-8 -*-
"""规则层测试：正/反用例自检（T7 验收）＋在真实仓库上跑一遍全套规则。"""
from pathlib import Path

import pytest

from infinigrow.rules.static_scan import (RULES, RuleContext, SYNC_TERMS, scan, selftest)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_selftest_all_rules_have_positive_and_negative_cases(tmp_path):
    report = selftest(tmp_path)
    assert report.ok, "\n".join(report.rows)


def test_prompt_code_sync_fails_when_code_definition_removed(tmp_path):
    """T7 验收判据：**故意删一处定义 → 脚本报错**。"""
    from infinigrow.rules.static_scan import rule_prompt_code_sync
    repo = tmp_path / "repo"
    (repo / "src" / "infinigrow" / "engine").mkdir(parents=True)
    (repo / "prompts").mkdir(parents=True)
    (repo / "prompts" / "tick.md").write_text("判读 行动\n", encoding="utf-8")
    (repo / "src" / "infinigrow" / "engine" / "model.py").write_text("判读\n", encoding="utf-8")
    ctx = RuleContext.from_repo(repo)
    detail, ok = rule_prompt_code_sync(ctx)
    assert ok is False and "代码侧缺" in detail


def test_selftest_negative_case_hits(tmp_path):
    """反向验证夹具本身有效：注入旧条款时 R3 必须 FAIL。"""
    from infinigrow.rules.static_scan import rule_no_self_sprout_clause
    root = tmp_path / "r"
    (root / "prompts").mkdir(parents=True)
    (root / "prompts" / "tick.md").write_text(
        "完成即分岔：本拍必须登记至少一个新芽候选", encoding="utf-8")
    ctx = RuleContext.from_repo(root)
    _, ok = rule_no_self_sprout_clause(ctx)
    assert ok is False


@pytest.mark.parametrize("name", [n for n, _ in RULES])
def test_every_rule_runs(name):
    """规则本身不许抛异常（抛了＝扫描器被拖崩）。"""
    fn = dict(RULES)[name]
    detail, passed = fn(RuleContext.from_repo(REPO_ROOT))
    assert isinstance(detail, str) and isinstance(passed, bool)


def test_repo_scan_is_green():
    """真实仓库自检：全部规则必须 PASS（CI 的第一道闸）。"""
    report = scan(RuleContext.from_repo(REPO_ROOT))
    assert report.ok, "\n".join(report.rows)


def test_sync_terms_cover_all_three_sprout_sources():
    """同源表必须覆盖三个芽源（机制词不能只在代码里、也不能只在提示词里）。"""
    joined = "\n".join(SYNC_TERMS)
    for term in ("差异", "成熟链封顶", "能力库未用", "零差异零芽"):
        assert term in joined
