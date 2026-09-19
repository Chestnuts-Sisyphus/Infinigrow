# -*- coding: utf-8 -*-
"""M3：「观测面构成」的现算读数 + 正反用例。

上一轮的触发器（docs/zh/growth-subject.md §4）说：等 `app/` 证据件多到开始挤占观测面
那天，先设计结案判据。它一直在等一条**能读出来的数**——此前 status/trace 只报「观测 20 个」，
看不出这 20 个里 app 与 journal 各占几格。这里把构成做成现算读数（按顶层目录归类），
用正反用例钉住：① 真实分类、② 归档子树不入观测面、③ app 多到把 journal 挤出名额时读数能反映。
"""
from __future__ import annotations

import os

from infinigrow.engine.subject import (observation_composition, subject_files,
                                       subject_snapshot)


def _touch(root, rel, mtime):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def test_composition_groups_observed_files_by_top_dir(tmp_path):
    """正例：app/ 与 journal/ 各按顶层目录计数，直接躺在根下的归 (根)。"""
    base = 1_700_000_000
    for i in range(5):
        _touch(tmp_path, "app/000%d-x.md" % i, base + i)
    for i in range(3):
        _touch(tmp_path, "journal/010%d.md" % i, base + 10 + i)
    _touch(tmp_path, "top.md", base + 20)

    comp = observation_composition(tmp_path, limit=20)
    assert comp["by_dir"] == {"app": 5, "journal": 3, "(根)": 1}, comp["by_dir"]
    assert comp["observed"] == 9 and comp["limit"] == 20
    # 按数量降序、再按名字：app 最多排第一
    assert next(iter(comp["by_dir"])) == "app"


def test_archived_subtree_never_counts(tmp_path):
    """反例（归档不算生长面）：`archive/…` 由轮转搬入、mtime 最新，也不得进观测构成。"""
    base = 1_700_000_000
    _touch(tmp_path, "journal/0001.md", base)                 # 真内容（旧）
    _touch(tmp_path, "archive/journal/9999.md.j2", base + 99)  # 归档件，mtime 最新
    comp = observation_composition(tmp_path, limit=20)
    assert comp["by_dir"] == {"journal": 1}, comp["by_dir"]
    assert "archive" not in comp["by_dir"], "归档子树混进了观测构成＝没守住生长面边界"


def test_app_can_crowd_journal_out_of_the_window(tmp_path):
    """反例（触发器成立的那一面）：app 证据件更新更密时，journal 被挤出观测名额——
    构成读数必须如实反映「谁占了格」，这正是结案判据要盯的信号。"""
    base = 1_700_000_000
    for i in range(25):
        _touch(tmp_path, "app/%04d-x.md" % (2000 + i), base + i)   # 25 个更新的 app
    _touch(tmp_path, "journal/0001.md", base - 1000)               # 一个很旧的 journal
    files = subject_files(tmp_path, limit=20)                       # 观测窗口 20
    comp = observation_composition(tmp_path, limit=20)
    assert len(files) == 20
    assert comp["by_dir"].get("journal") is None, "journal 已被挤出，读数就该看不到它"
    assert comp["by_dir"]["app"] == 20

    # 放宽窗口（只证明「构成」随名额变化，不改引擎默认常量）：journal 才回到读数里
    wide = observation_composition(tmp_path, limit=30)
    assert wide["by_dir"].get("journal") == 1


def test_snapshot_carries_composition(tmp_path):
    """status/trace 复用同一读数：快照里必须带 composition，且与函数结果一致。"""
    _touch(tmp_path, "app/0001-x.md", 1_700_000_000)
    _touch(tmp_path, "journal/0002.md", 1_700_000_001)
    snap = subject_snapshot(tmp_path, tick=1, limit=20)
    assert snap["composition"] == observation_composition(tmp_path, limit=20)
    assert snap["composition"]["by_dir"] == {"app": 1, "journal": 1}
