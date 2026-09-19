# -*- coding: utf-8 -*-
"""兑现率取证节的数字回归（M1）：双语正本的每个数字必须等于**同一次** `redemption --json` 输出。

为什么要有这个文件：v2.2.27 把拍 624 的快照当结论发布，账本涨到拍 731 后两条判定已失效
（`lib*`「无样本」、打脸「真没做 0 例」），却没有任何用例盯住文档里的数字——于是「现算」只
出现在代码里，正本还是能说谎。这里把**正本 ↔ 快照**钉死：把文档数字改坏必须红。

快照来自 `PYTHONIOENCODING=utf-8 python -m infinigrow redemption --json`（止拍记在文件名与正文里），
不依赖活体 `state/`，因此 CI 上可复跑。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = REPO_ROOT / "tests" / "data" / "redemption-tick-00731.json"
ZH_DOC = REPO_ROOT / "docs" / "zh" / "mechanism.md"
EN_DOC = REPO_ROOT / "docs" / "mechanism.md"


def _flat(path: Path) -> str:
    """整篇正文压成单行（折行是排版，不是数字的边界）。"""
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def report() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def _figures(rep: dict) -> dict:
    """把快照里**该被文档引用**的读数取出来（一个数字都不手写）。"""
    lib = rep["按芽源"]["lib"]
    attr = rep["打脸归因"]
    return {
        "tick": rep["窗口"]["止拍"],
        "leads": rep["领做"]["总"],
        "checkable": rep["可对账样本"],
        "redeemed": rep["兑现"],
        "failed": rep["打脸"],
        "unverifiable": rep["不可对账"],
        "unverifiable_pct": int(100 * rep["不可对账"] / rep["领做"]["总"]),
        "lib_leads": lib["领做"],
        "lib_checkable": lib["可对账"],
        "lib_redeemed": lib["兑现"],
        "lib_failed": lib["打脸"],
        "lib_unverifiable": lib["不可对账"],
        "side": attr["执行者侧未落地"]["n"],
        "stale": attr["提议过期"]["n"],
        "undone": attr["真没做"]["n"],
    }


def _zh_phrases(f: dict) -> list:
    return [
        "拍 %s 现跑快照" % f["tick"],
        "%d 行领做" % f["leads"],
        "**%d 行可对账样本**" % f["checkable"],
        "兑现 %d" % f["redeemed"],
        "**%d 行（%d%%）`verifiable=false`**" % (f["unverifiable"], f["unverifiable_pct"]),
        "`lib {领做 %d, 可对账 %d, 兑现 %d, 打脸 %d, 不可对账 %d}`"
        % (f["lib_leads"], f["lib_checkable"], f["lib_redeemed"], f["lib_failed"],
           f["lib_unverifiable"]),
        "样本拍 654、656、657、658、659、660、661、662",
        "**%d 行打脸**" % f["failed"],
        "**执行者侧未落地 %d ＋ 提议过期 %d ＋ 真没做 %d**"
        % (f["side"], f["stale"], f["undone"]),
        "tests/data/redemption-tick-00731.json",
    ]


def _en_phrases(f: dict) -> list:
    return [
        "live snapshot at tick %s" % f["tick"],
        "%d led rows" % f["leads"],
        "**%d checkable sample rows**" % f["checkable"],
        "%d redeemed" % f["redeemed"],
        "**%d rows (%d%%) are `verifiable=false`**"
        % (f["unverifiable"], f["unverifiable_pct"]),
        "`lib {%d leads, %d checkable, %d redeemed, %d failed, %d unverifiable}`"
        % (f["lib_leads"], f["lib_checkable"], f["lib_redeemed"], f["lib_failed"],
           f["lib_unverifiable"]),
        "ticks 654, 656, 657, 658, 659, 660, 661, 662",
        "there are **%d failed rows**" % f["failed"],
        "**%d dropped on the executor side + %d proposal went stale + %d genuinely not done**"
        % (f["side"], f["stale"], f["undone"]),
        "tests/data/redemption-tick-00731.json",
    ]


def test_zh_evidence_section_matches_the_snapshot(report):
    """中文正本 §5 的每个数字＝快照现算（缺一个就是漂移）。"""
    flat = _flat(ZH_DOC)
    missing = [p for p in _zh_phrases(_figures(report)) if p not in flat]
    assert not missing, "中文正本与 redemption --json 快照不符：%s" % missing


def test_en_evidence_section_matches_the_snapshot(report):
    """英文册同段同数（双语同源到正文级，不止标题骨架）。"""
    flat = _flat(EN_DOC)
    missing = [p for p in _en_phrases(_figures(report)) if p not in flat]
    assert not missing, "英文册与 redemption --json 快照不符：%s" % missing


def test_retired_verdicts_stay_out_of_both_docs(report):
    """拍 624 的绝对读数不许再以「现况」形式留在正本里；两条更正必须双语都在。

    注：正本要**引用**被推翻的原话才能叫公开更正，所以这里禁的是旧快照的绝对数字
    （575 行领做／212 样本／208 兑现／63% 占比），不是含「更正」字样的引句。
    """
    f = _figures(report)
    assert f["lib_checkable"] > 0 and f["undone"] > 0        # 前提：快照本身已非零
    zh, en = _flat(ZH_DOC), _flat(EN_DOC)
    for bad in ("575 行领做", "**212 行可对账样本**", "兑现 208", "（63%）"):
        assert bad not in zh, "中文正本仍保留拍 624 的绝对读数：%s" % bad
    for bad in ("575 led rows", "**212 checkable sample rows**", "208 redeemed",
                "(63%) are `verifiable=false`"):
        assert bad not in en, "英文册仍保留拍 624 的绝对读数：%s" % bad
    assert "更正①" in zh and "更正②" in zh, "中文正本缺公开更正标记"
    assert "correction 1" in en and "correction 2" in en, "英文册缺公开更正标记"


def test_a_corrupted_figure_in_the_docs_turns_the_check_red(tmp_path, report):
    """反证：把正本里的兑现数改坏一个数字，检查器必须报缺（否则这闸是装饰性的）。"""
    f = _figures(report)
    flat = _flat(ZH_DOC).replace("兑现 %d" % f["redeemed"],
                                 "兑现 %d" % (f["redeemed"] + 1))
    missing = [p for p in _zh_phrases(f) if p not in flat]
    assert "兑现 %d" % f["redeemed"] in missing


def test_snapshot_is_the_only_source_of_these_numbers():
    """快照文件名里的拍号必须与快照内容止拍一致（防止换快照却留着旧拍号）。"""
    tick_in_name = int(re.search(r"tick-(\d+)", SNAPSHOT.name).group(1))
    rep = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert tick_in_name == rep["窗口"]["止拍"]
    assert "redemption-tick-%05d.json" % tick_in_name in _flat(ZH_DOC)
    assert "redemption-tick-%05d.json" % tick_in_name in _flat(EN_DOC)
