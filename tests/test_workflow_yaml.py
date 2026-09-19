# -*- coding: utf-8 -*-
"""工作流 YAML 哨兵测试（补 v2.2.28 冷启动时踩到的坑）。

背景：把 ci.yml 一步的 name 从全角冒号改写成半角冒号（`... layer: paths ...`）
后，YAML 把那行读成嵌套映射，整份工作流在 GitHub 上 0 秒挂——而本地全套闸全绿，
因为没有任何测试解析过工作流文件本身。这里补上这道闸，并带正反两向。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "tools" / "check_workflow_yaml.py"
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"


def _load():
    spec = importlib.util.spec_from_file_location("check_workflow_yaml", CHECKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_workflow_dir_has_files():
    assert list(WORKFLOW_DIR.glob("*.yml")), "工作流目录不应为空"


def test_all_workflows_pass_the_sentinel():
    """仓库里真实的工作流文件必须一坑没有。"""
    mod = _load()
    for path in sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml")):
        problems = mod.check_workflow_text(path.read_text(encoding="utf-8"))
        assert not problems, "%s 有问题：%s" % (path.name, problems)


def test_sentinel_flags_unquoted_colon_in_scalar():
    """反向：当初那行半角冒号的 name 必须被判红。"""
    mod = _load()
    bad = "- name: Privacy scan (generic layer: paths / credentials / emails)\n"
    assert mod.check_workflow_text(bad), "未加引号标量含 ': ' 必须被抓到"


def test_sentinel_accepts_quoted_scalar():
    """正向：加引号即安全。"""
    mod = _load()
    good = '- name: "Privacy scan (generic layer: paths / credentials / emails)"\n'
    assert not mod.check_workflow_text(good)


def test_sentinel_flags_tab_indentation():
    mod = _load()
    assert mod.check_workflow_text("jobs:\n\ttest:\n")


def test_sentinel_ignores_block_scalar_bodies():
    """`run: |` 里的脚本正文含 ': ' 不算坑。"""
    mod = _load()
    text = (
        "      - name: cold\n"
        "        run: |\n"
        "          echo \"msg: hello world\"\n"
        "          python -m x\n"
    )
    assert not mod.check_workflow_text(text)
