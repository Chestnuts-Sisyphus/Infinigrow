# -*- coding: utf-8 -*-
"""CLI 读数面回归（M4）：`status`／`redemption --json`／`rotate --search`／`version --check`。

为什么要补：CI 的冷启动段只跑**写路径**（dry-run/tick/gardener/org-status），这四个**读数面**
从来没在任何 CI 上跑过——其中 `rotate --search` 更是正本回答「归档可检索」（正本把它写成公开
读数入口）却零用例。读数命令的契约就是「退出码为 0 ＋ 输出可解析」，所以这里既测命中也测
未命中，并把 `version --check` 的退出码语义（落后退 3）钉住（不打网络：monkeypatch 取最新版本）。
"""
from __future__ import annotations

import json

from infinigrow.core import version_check
from infinigrow.core.exit_codes import BEHIND, OK
from infinigrow.core.paths import REPO_ROOT, resolve_state
from infinigrow.cli import main


def _roots(tmp_path):
    """全局参数在主解析器上，必须放在子命令**之前**。"""
    state = tmp_path / "state"
    subject = tmp_path / "subject"
    subject.mkdir(parents=True, exist_ok=True)
    return ["--state-root", str(state), "--subject-root", str(subject)]


def test_status_and_redemption_run_on_a_fresh_state_root(tmp_path, capsys):
    """空状态根上两条读数命令都要 rc=0，且 `redemption --json` 的输出真能解析。"""
    flags = _roots(tmp_path)
    assert main(flags + ["status"]) == OK
    out = capsys.readouterr().out
    assert "拍号" in out and "兑现率" in out

    assert main(flags + ["redemption", "--json"]) == OK
    report = json.loads(capsys.readouterr().out)
    for key in ("窗口", "领做", "按芽源", "可对账样本", "兑现", "打脸", "打脸归因"):
        assert key in report, "redemption --json 缺字段：%s" % key
    assert set(report["打脸归因"]) == {"执行者侧未落地", "提议过期", "真没做"}


def test_rotate_search_hits_archived_lines_and_misses_quietly(tmp_path, capsys):
    """归档检索两向：命中的要报出来（含相对位置），没命中的报 0 命中而不是炸。"""
    flags = _roots(tmp_path)
    assert main(flags + ["rotate"]) == OK                      # 先建出状态与归档目录
    layout = resolve_state(flags[1], REPO_ROOT, create=True)
    archived = layout.archive_dir / "outcomes.jsonl"
    archived.write_text('{"sprout_id": "sp0100-001-a"}\n{"needle": "找不到"}\n',
                        encoding="utf-8")

    assert main(flags + ["rotate", "--search", "sp0100-001-a"]) == OK
    hit_out = capsys.readouterr().out
    assert "命中 1" in hit_out and "outcomes.jsonl:1" in hit_out

    assert main(flags + ["rotate", "--search", "根本没有这串"]) == OK
    assert "命中 0" in capsys.readouterr().out


def test_version_check_exit_code_says_behind_without_network(tmp_path, monkeypatch,
                                                             capsys):
    """`version --check` 的退出码是接口：落后＝BEHIND(3)，持平＝0（离线注入最新版本）。"""
    from infinigrow import __version__

    monkeypatch.setattr(version_check, "latest_release",
                        lambda *a, **k: ("v%d.0.0" % (int(__version__.split(".")[0]) + 1),
                                         "injected"))
    assert main(["version", "--check"]) == BEHIND
    capsys.readouterr()

    monkeypatch.setattr(version_check, "latest_release",
                        lambda *a, **k: ("v" + __version__, "injected"))
    assert main(["version", "--check"]) == OK
    assert "最新" in capsys.readouterr().out


def test_documented_python_matrix_matches_the_ci_matrix():
    """文档写的 Python 版本矩阵＝ci.yml 真跑的矩阵（漏一侧＝对使用者说谎或白跑）。"""
    import re

    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    versions = [v.strip().strip('"') for v in
                re.search(r"python-version:\s*\[([^\]]+)\]", ci).group(1).split(",")]
    assert versions and all(v.count(".") == 1 for v in versions)
    for rel in ("README.md", "README.zh-CN.md", "CONTRIBUTING.md"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        missing = [v for v in versions if v not in text]
        assert not missing, "%s 未列出 CI 矩阵里的 Python %s" % (rel, missing)


def test_stderr_is_clean_for_the_read_surface(tmp_path, capsys):
    """读数命令不许把警告/回溯写进 stderr（成功路径的 stderr 必须是空的）。"""
    flags = _roots(tmp_path)
    for argv in (flags + ["status"], flags + ["redemption"], flags + ["rotate", "--search", "x"]):
        assert main(argv) == OK
        err = capsys.readouterr().err
        assert err.strip() == "", "%s 的 stderr 不干净：%s" % (argv[0], err[:200])
