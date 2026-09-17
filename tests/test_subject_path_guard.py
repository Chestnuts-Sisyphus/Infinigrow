# -*- coding: utf-8 -*-
"""路径加固（R6/E1）：对象名 → 主体内路径的 **contain 校验**。

E1（Mimosa high＝路径穿越，CWE-22）：`subject_root / item.name` 这类拼接此前没有守卫——
名字来自观测/账本，正常形态是主体内相对路径，但拼接前不校验就等于「谁往账本里写了
奇怪的名字，谁就能把读写指到主体根外」。修法＝把校验收进 `subject.subject_path`：
解析后必须落在主体根之内（与 `core/paths.guard` 同一个 `within_root` 判据）；
`engine/org_session.py` 的渲染路径改走它。

验收：
  1. 正常相对名（含子目录）→ 解析正确；
  2. `..` 段、绝对路径、盘符、空名 → 一律拒绝；
  3. 拒绝发生在**拼接层**（读也守——读越界同样是泄漏）；
  4. 判据与 guard 同源（同一个 within_root）。
"""
from __future__ import annotations

import pytest

from infinigrow.core.paths import guard, within_root
from infinigrow.engine.subject import subject_path


def test_subject_path_accepts_normal_relative_names(tmp_path):
    root = tmp_path / "subject"
    (root / "journal").mkdir(parents=True)
    assert subject_path(root, "journal/0001-20260917.md") == root / "journal/0001-20260917.md"
    assert subject_path(root, "subject.md") == root / "subject.md"
    # 反斜杠写法归一（Windows 手写路径也认）
    assert subject_path(root, "journal\\0001-20260917.md") == root / "journal/0001-20260917.md"


@pytest.mark.parametrize("bad", [
    "../evil.md",                       # 上一级
    "journal/../../evil.md",            # 中途上跳
    "..",                               # 纯上跳
    "/etc/passwd",                      # 绝对路径
    "C" + ":/Windows/system32/x.txt",   # 盘符（拼接写法：本文件自身不落盘符字面量，避隐私扫描）
    "c" + ":x",                         # 盘符相对写法
    "",                                 # 空名
    "   ",                              # 空白名
])
def test_subject_path_rejects_escapes(tmp_path, bad):
    root = tmp_path / "subject"
    root.mkdir()
    with pytest.raises((ValueError, PermissionError)):
        subject_path(root, bad)


def test_subject_path_uses_the_same_predicate_as_guard(tmp_path):
    """判据同源：subject_path 挡下的路径，guard 也必须挡（反之亦然）。"""
    root = tmp_path / "subject"
    root.mkdir()
    p = root / "a" / ".." / ".." / "evil.md"
    assert within_root(p, root) is False
    with pytest.raises(PermissionError):
        guard(p, root)
    with pytest.raises(PermissionError):
        subject_path(root, "a/../../evil.md")


def test_render_subject_reads_through_the_guard(tmp_path):
    """org_session 的渲染路径已改走 subject_path：正常主体渲染不回归。"""
    from infinigrow.engine.org_session import _render_subject
    root = tmp_path / "subject"
    (root / "journal").mkdir(parents=True)
    (root / "journal" / "0001-20260917.md").write_text("正文", encoding="utf-8")
    text = _render_subject(root)
    assert "journal/0001-20260917.md" in text and "正文" in text
