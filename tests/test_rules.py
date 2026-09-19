# -*- coding: utf-8 -*-
"""规则层测试：正/反用例自检（T7 验收）＋在真实仓库上跑一遍全套规则。"""
from pathlib import Path

import pytest

from infinigrow.rules.static_scan import (MIN_SYNC_TERMS, RULES, RuleContext, SYNC_TERMS,
                                          scan, selftest)

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


def test_vbs_files_are_scanned_by_static_rules(tmp_path):
    """T10/B3：`.vbs` 已进 `SCAN_SUFFIXES` → 隐藏启动器里的病灶也会被 R1/R5 看见。"""
    from infinigrow.rules.static_scan import rule_no_absolute_paths, rule_no_secrets
    root = tmp_path / "v"
    (root / "tools").mkdir(parents=True)
    # 病灶样本按**拼装**构造：源码里不出现完整的「盘符:斜杠」形态（自匹配假阳性）
    drive = "C" + ":" + "/" + "Users/" + "someone/launcher.vbs"
    (root / "tools" / "run.vbs").write_text(
        'sh.Run "%s", 0, False\n' % drive, encoding="utf-8")
    ctx = RuleContext.from_repo(root)
    detail, ok = rule_no_absolute_paths(ctx)
    assert ok is False and "run.vbs" in detail
    fake = "ghp" + "_" + ("a" * 30)
    (root / "tools" / "run.vbs").write_text('TOKEN = "%s"\n' % fake, encoding="utf-8")
    _, ok2 = rule_no_secrets(ctx)
    assert ok2 is False


@pytest.mark.parametrize("name", [n for n, _ in RULES])
def test_every_rule_passes_on_the_clean_repo(name):
    """每条规则在干净仓库上必须**真的 PASS**（不是「没抛异常就算过」）。

    旧写法只断言返回类型，于是「规则悄悄判 FAIL」也能蒙过去；这里把它升级成
    对 REPO_ROOT 现跑并要求 `passed is True`（与 `test_repo_scan_is_green` 同向、但逐条点名）。
    """
    fn = dict(RULES)[name]
    detail, passed = fn(RuleContext.from_repo(REPO_ROOT))
    assert isinstance(detail, str) and detail, "规则必须给出非空说明（判词不能空）"
    assert passed is True, "%s 在干净仓库上应 PASS，实际 FAIL：%s" % (name, detail)


def test_repo_scan_is_green():
    """真实仓库自检：全部规则必须 PASS（CI 的第一道闸）。"""
    report = scan(RuleContext.from_repo(REPO_ROOT))
    assert report.ok, "\n".join(report.rows)


def test_sync_terms_cover_all_three_sprout_sources():
    """同源表必须覆盖三个芽源（机制词不能只在代码里、也不能只在提示词里）。"""
    joined = "\n".join(SYNC_TERMS)
    for term in ("差异", "成熟链封顶", "能力库未用", "零差异零芽"):
        assert term in joined


def test_prompt_code_sync_fails_when_prompts_missing(tmp_path):
    """R2 反例：**提示词为空/缺失即红**（旧版靠 `prompt_text and` 短路，静默放行）。

    造一个「代码侧齐、提示词侧一册都没有」的仓库——若规则还在「没提示词就当没事」，
    这条必 PASS；修好后它必须 FAIL 并点名提示词侧缺。
    """
    from infinigrow.rules.static_scan import rule_prompt_code_sync
    repo = tmp_path / "repo"
    owners: dict[str, list[str]] = {}
    for term, owner in SYNC_TERMS.items():
        owners.setdefault(owner, []).append(term)
    for owner, terms in owners.items():
        p = repo / "src" / "infinigrow" / owner
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("".join("# %s\n" % t for t in terms), encoding="utf-8")
    (repo / "prompts").mkdir(parents=True)                 # 空提示词目录
    ctx = RuleContext.from_repo(repo)
    detail, ok = rule_prompt_code_sync(ctx)
    assert ok is False and "提示词侧缺" in detail


def test_min_sync_terms_is_a_registered_floor():
    """`MIN_SYNC_TERMS` 是**下限**：词数不得缩水，且每个下限词都必须在覆盖表里。

    R9 靠「MIN ⊆ SYNC_TERMS」拦缩表；这里把下限本身钉住（17 词，实测非编造），
    少一个词或被删一条都要红。
    """
    assert len(MIN_SYNC_TERMS) >= 17, "同源表下限被悄悄改小（曾经 17 词）"
    for term in MIN_SYNC_TERMS:
        assert term in SYNC_TERMS, "%s 是下限词却不在覆盖表里——R9 就拦不住它消失" % term
