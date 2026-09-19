# -*- coding: utf-8 -*-
"""项目层隐私禁列的**机制**必须在任何环境都真咬（M5）。

原状：真实禁列 `privacy-deny.txt` 按设计不进公共仓库（含本机路径与身份词，被 `.gitignore`
忽略），于是 `tests/test_privacy.py::test_repo_is_free_of_project_deny_hits` 在非本机环境
**永远 skip**——「项目层」这条机器判据在线上从未被证明过有效，也没人知道它什么时候坏掉。

本文件不修那条 skip（它确实是环境自适应），而是把**机制**钉住：仓库里带一份合成词样例
禁列＋一个故意留载荷的哨兵文件，两个方向各测一遍——

  - 必命中：给了 deny 就必须报命中（退出码 1，三条规则各有标签）；
  - 清零必不命中：把载荷拿掉就必须报零命中（退出码 0）——否则「必命中」是假的；
  - 哨兵本身不得污染通用层：只跑通用规则时它对全仓扫描贡献 0 命中；
  - 真实清单必须仍被忽略、样例必须不被忽略：样例进库是为了可验证，不是为了泄露清单。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER = REPO_ROOT / "tools" / "privacy_scan.py"
SAMPLE_DENY = REPO_ROOT / "tests" / "data" / "privacy-deny-sample.txt"
SENTINEL_DIR = REPO_ROOT / "tests" / "data" / "privacy-sentinel"


def _load_scanner():
    spec = importlib.util.spec_from_file_location("privacy_scan", SCANNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _scan(scan, root, deny=None):
    rules = list(scan.GENERIC_RULES) + (scan.load_deny(str(deny)) if deny else [])
    hits = []
    for full, rel in scan.walk(str(root)):
        hits.extend(scan.scan_file(full, rules, str(root), rel))
    return hits


def test_sentinel_and_sample_deny_exist_and_are_not_themselves_a_leak():
    """样例与哨兵都得在库里（否则 CI 又是在扫一个空目录），且通用层对它们零命中。"""
    scan = _load_scanner()
    assert SAMPLE_DENY.is_file(), "缺项目层禁列样例：CI 上这一层无从验证"
    assert (SENTINEL_DIR / "leaky-example.md").is_file(), "缺哨兵载荷"
    generic = _scan(scan, SENTINEL_DIR)
    assert generic == [], "哨兵样例触到通用层规则（会把全仓隐私闸搞脏）：%s" % generic[:3]


def test_project_layer_must_hit_the_sentinel():
    """**必命中**：三条合成规则都要咬到，退出码语义为 1（`main` 的契约）。"""
    scan = _load_scanner()
    rules = scan.load_deny(str(SAMPLE_DENY))
    assert len(rules) == 3, "样例禁列应是三条（改了要同步本用例）"
    hits = _scan(scan, SENTINEL_DIR, SAMPLE_DENY)
    assert hits, "给了项目层禁列却零命中＝这一层在 CI 上是空话"
    labels = {h["rule"] for h in hits}
    assert {"demo-secret-token", "demo-identity", "demo-infra"} <= labels, \
        "命中规则不齐：%s" % sorted(labels)
    assert scan.main(["--root", str(SENTINEL_DIR), "--deny", str(SAMPLE_DENY)]) == 1


def test_cleared_sentinel_must_not_hit(tmp_path):
    """**清零必不命中**：把载荷删掉就报 0——反证上一条不是「什么都报命中」。"""
    scan = _load_scanner()
    cleaned = tmp_path / "clean"
    cleaned.mkdir()
    text = (SENTINEL_DIR / "leaky-example.md").read_text(encoding="utf-8")
    for payload in ("TTL-DEMO-SECRET-0001", "not-a-real-collaborator-name",
                    "demo-private-infra-7"):
        assert payload in text, "哨兵载荷被删了：%s" % payload
        text = text.replace(payload, "")
    (cleaned / "clean.md").write_text(text, encoding="utf-8")
    assert _scan(scan, cleaned, SAMPLE_DENY) == []
    assert scan.main(["--root", str(cleaned), "--deny", str(SAMPLE_DENY)]) == 0


def test_real_deny_list_stays_ignored_while_the_sample_is_tracked():
    """.gitignore 必须仍忽略真实清单，且**不**忽略样例（两者名字只差后缀，规则要精确）。"""
    lines = [ln.strip() for ln in (REPO_ROOT / ".gitignore").read_text(
        encoding="utf-8").splitlines()]
    assert "privacy-deny.txt" in lines, "真实禁列清单不再被忽略＝本机路径会被发布出去"
    assert "privacy-deny-sample.txt" not in lines
    assert not any("*privacy-deny*" in ln or ln in ("privacy-deny*", "*-deny.txt")
                   for ln in lines), ".gitignore 的通配会连带忽略样例，CI 又回到扫空目录"
