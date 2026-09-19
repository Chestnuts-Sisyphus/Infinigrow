# -*- coding: utf-8 -*-
"""发布工具链（Q11）：tag → Release 的说明**只有一个来源**——`CHANGELOG.md`。

为什么锁这条：Release 正文此前靠人手工敲，敲漏一节就是公开面降级；
自动化的第一原则是「**抽不到就别发**」——宁可 CI 失败让人补，也不发空壳。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from tools.extract_changelog_section import MIN_CHARS, extract

REPO = Path(__file__).resolve().parents[1]
CHANGELOG = REPO / "CHANGELOG.md"


def test_extracts_the_section_for_a_real_tag():
    body = extract("v2.2.15", CHANGELOG)
    assert body.startswith("## v2.2.15")
    assert "solidify edge" in body
    assert len(body) > MIN_CHARS


def test_accepts_a_bare_version_too():
    assert extract("2.2.14", CHANGELOG).startswith("## v2.2.14")


def test_missing_tag_fails_loudly(tmp_path):
    """抽不到 → 抛错（工作流据此失败），**不静默发空**。"""
    fake = tmp_path / "CHANGELOG.md"
    fake.write_text("# Changelog\n\n## v1.0.0 — x\n\n- one line\n", encoding="utf-8")
    try:
        extract("v9.9.9", fake)
    except ValueError as exc:
        assert "没有 v9.9.9" in str(exc)
    else:                                             # pragma: no cover - 断言失败路径
        raise AssertionError("缺失 tag 必须抛 ValueError")


def test_too_short_section_is_rejected(tmp_path):
    """标题在、正文太短 → 同样拒绝（防「占位小节」被发成 Release）。"""
    fake = tmp_path / "CHANGELOG.md"
    fake.write_text("## v1.2.3 — stub\n\n- ok\n", encoding="utf-8")
    try:
        extract("v1.2.3", fake)
    except ValueError as exc:
        assert "太短" in str(exc)
    else:                                             # pragma: no cover
        raise AssertionError("过短小节必须抛 ValueError")


def test_release_workflow_uses_the_changelog_as_its_only_source():
    """工作流必须走这个工具、必须幂等（已存在的 Release 不覆盖）、必须有 contents: write。"""
    text = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "extract_changelog_section.py" in text
    assert "gh release view" in text and "found=no" in text      # 幂等：先查再发
    assert "permissions:" in text and "contents: write" in text


# --------------------------------------------------------------- R7/D2：运营脚本入库
def test_sync_release_notes_is_in_tools_and_covers_every_release():
    """R7：批量改写工具在 `tools/` 下可复跑，且标题表覆盖到**当前版本**（防静静过期）。"""
    from infinigrow import __version__
    from tools.sync_release_notes import TITLES
    assert "2.0.0" in TITLES and "2.2.13" in TITLES
    assert __version__ in TITLES, "发新版后忘了补 TITLES（工具会静默漏掉最新一条）"


def test_sync_release_notes_bodies_come_from_repo_sources():
    """正文来源：docs 英文版优先，否则 CHANGELOG 小节——都非空、都可复查。"""
    from tools.sync_release_notes import body_for
    body = body_for("2.2.0")
    assert body and "calibration" in body.lower()        # docs/release-notes-v2.2.0.md 路径
    cl = body_for("2.2.19")
    assert cl and "attribution" in cl.lower()            # CHANGELOG.md 路径
    assert body_for("9.9.9") == ""                       # 不存在 → 空（调用方跳过，不静默发）


def test_sync_release_notes_dry_run_never_calls_gh(tmp_path, monkeypatch, capsys):
    """默认（不 --apply）只打印——mistyped 的一跑不能改到线上页面。"""
    import tools.sync_release_notes as sync

    class _FakeSub:
        called = []

        @staticmethod
        def run(*a, **k):
            _FakeSub.called.append(a)

    monkeypatch.setattr(sync, "subprocess", _FakeSub)     # 只换本模块内的名字
    rc = sync.main([])
    out = capsys.readouterr().out
    assert rc == 0 and _FakeSub.called == []             # 一次 gh 都没调
    assert "v2.2.20" in out and "title:" in out


# ------------------------------------------- 标题只有一个来源：分界线两侧读不同的那一份
# 分界线（实测 2026-09-18，28 条 Release 逐条 `gh release view --json name` 比对）：
#   v2.2.15 及以前  线上标题 == 手写记录（不带日期）
#   v2.2.16 起      线上标题 == CHANGELOG 小节标题**原文**（带尾部日期），发布工作流写上去的
#: 分界线以前，措辞与今天的 CHANGELOG 不同的一批——**有意的发布记录，不是待修漂移**。
#: 把表里的值「对齐」成 CHANGELOG 措辞，`--apply` 就会改掉这 11 条已发布 Release 的标题。
RECORDED_TITLE_DIVERGENCE = ["2.2.2", "2.2.3", "2.2.4", "2.2.6", "2.2.7", "2.2.8",
                             "2.2.9", "2.2.10", "2.2.11", "2.2.12", "2.2.13"]


def _key(v: str):
    return tuple(int(x) for x in v.split("."))


def test_before_the_boundary_the_applied_title_is_the_recorded_one():
    """分界线以前：应用的是手写记录；措辞与 CHANGELOG 不同的那批必须还是那批。"""
    from tools.sync_release_notes import (TITLES, TITLES_UNTIL, changelog_title,
                                          title_for)

    def _strip_date(t):
        return re.sub(r"\s*\(\d{4}-\d{2}-\d{2}\)\s*$", "", t)

    pre = [v for v in TITLES if _key(v) <= _key(TITLES_UNTIL)]
    assert pre, "标题表整段落在分界线之后，分界判据已失效"
    for ver in pre:
        assert title_for(ver) == TITLES[ver], "分界线以前不该改从 CHANGELOG 读"
    diverging = sorted((v for v in pre if TITLES[v] != _strip_date(changelog_title(v))),
                       key=_key)
    assert diverging == sorted(RECORDED_TITLE_DIVERGENCE, key=_key), (
        "线上已发布标题与 CHANGELOG 小节标题的措辞差异集合变了——"
        "要么有人手改了表（会改写已发布 Release），要么 CHANGELOG 旧节被重写")


def test_after_the_boundary_the_applied_title_keeps_its_date():
    """分界线以后：应用的是 CHANGELOG 小节标题原文，**日期不能被手抄副本抹掉**。"""
    from tools.sync_release_notes import TITLES, TITLES_UNTIL, changelog_title, title_for

    def _strip_date(t):
        return re.sub(r"\s*\(\d{4}-\d{2}-\d{2}\)\s*$", "", t)

    post = [v for v in TITLES if _key(v) > _key(TITLES_UNTIL)]
    assert len(post) >= 10, "分界线以后的版本太少，这条判据还没被真实数据喂过"
    for ver in post:
        title = title_for(ver)
        assert title == changelog_title(ver)
        assert re.search(r"\(\d{4}-\d{2}-\d{2}\)$", title), "推导出的标题应当带日期"
        # 表里那份是镜像：措辞必须跟正本一致，只是没有日期（有日期那份才是线上写的）
        assert TITLES[ver] == _strip_date(title), (
            "v%s 的表内副本与 CHANGELOG 小节标题措辞不符——正本改了就要同步镜像" % ver)


def test_a_hand_copied_title_never_wins_after_the_boundary(tmp_path):
    """反例：表里塞一条不带日期的新副本，`--apply` 用的仍是 CHANGELOG 那一份（带日期）。"""
    from tools.sync_release_notes import title_for

    (tmp_path / "CHANGELOG.md").write_text(
        "## v2.2.97 — a derived heading (2026-09-19)\n\n- body line\n", encoding="utf-8")
    assert title_for("2.2.97", root=tmp_path) == "v2.2.97 — a derived heading (2026-09-19)"
    assert title_for("2.2.97", root=tmp_path) != "v2.2.97 — a derived heading"
    # 分界线以前反过来：CHANGELOG 说什么都不算，读的是记录
    assert title_for("2.2.13", root=tmp_path) != ""


def test_dry_run_prints_what_would_actually_be_applied(capsys):
    """打印的标题必须就是会写上线的标题——否则 dry run 骗人。"""
    import tools.sync_release_notes as sync
    from tools.sync_release_notes import title_for

    assert sync.main([]) == 0
    out = capsys.readouterr().out
    assert "title: %s" % title_for("2.2.25") in out


# --------------------------------------------------- 发布工具的退出码：抽不到就别发
def test_release_cli_exit_codes(tmp_path):
    """工具作为进程跑时的**退出码**才是工作流据以失败的东西，光测函数抛错不够。

    rc=0 抽到真 tag（含 `--title`）；rc=1 tag 不存在（发空壳的路要堵死）；
    rc=2 用法错（参数数量不对）。三档各钉一次。
    """
    script = REPO / "tools" / "extract_changelog_section.py"
    hit = subprocess.run([sys.executable, str(script), "v2.2.27"],
                         capture_output=True, text=True)
    assert hit.returncode == 0 and hit.stdout.startswith("## v2.2.27")
    titled = subprocess.run([sys.executable, str(script), "v2.2.27", "--title"],
                            capture_output=True, text=True)
    assert titled.returncode == 0 and titled.stdout.strip().startswith("v2.2.27")
    miss = subprocess.run([sys.executable, str(script), "v9.9.9"],
                          capture_output=True, text=True)
    assert miss.returncode == 1 and "没有 v9.9.9" in miss.stderr
    usage = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    assert usage.returncode == 2


def test_every_git_tag_has_a_changelog_section():
    """**每个 git tag 都得在 CHANGELOG 里有对应小节**（发布链的下界闸）。

    tag 打了但没写 CHANGELOG 节 = 那条 Release 会发成空壳；这里逐 tag 走 `extract`，
    抽不到或太短就抛错让本用例红。要求至少有一个 tag：CI 的 checkout 必须 fetch 标签
    （`fetch-depth: 0`），否则标签列表空——那正是这条闸要**响**的场景，不能静默通过。
    """
    listed = subprocess.run(["git", "tag", "--list", "v*"], cwd=REPO,
                            capture_output=True, text=True)
    assert listed.returncode == 0, "读 git tag 失败：%s" % listed.stderr
    tags = [t for t in listed.stdout.split() if t.startswith("v")]
    assert tags, "仓库里读不到任何 tag——CI 是否 fetch 了标签（需 fetch-depth: 0）？"
    for tag in tags:
        extract(tag, CHANGELOG)                                 # 抽不到 → 抛错 → 本用例红
