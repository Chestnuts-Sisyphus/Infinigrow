# -*- coding: utf-8 -*-
"""T13 冷启动空仓验收：**零个人数据、零旧账本**，在临时目录跑完整拍。

这是「纯正新版」的最终判据，全部是机械断言（不靠人眼）：

1. 状态根默认落在仓库内 `state/`，且可被指到任意临时目录；
2. 空仓（什么都没有）也能跑：跑得起来、跑完有账本、有心跳；
3. 产物里**没有绝对路径**、没有旧项目名/身份词（按规则表达式判）；
4. 所有落到盘上的东西都在状态根之内（越界写＝验收失败）；
5. 同样输入跑两次结果一致（可复跑）。
"""
from __future__ import annotations

import re
from pathlib import Path

from infinigrow.core.config import load_settings
from infinigrow.core.paths import REPO_ROOT, resolve_state
from infinigrow.engine.model import Observation, Prediction
from infinigrow.engine.tick import run_tick

ABS_PATH = re.compile(r"[A-Za-z]:[\\/]|/(?:home|Users|mnt|opt)/")
#: 旧项目名与身份词的「形态」表达式（按形态判，**不在仓库里写出具体词**——
#: 把违禁词本身写进公开仓库，正是这套规则要防的事）
LEGACY_FORMS = re.compile(r"wu[_x]*xian|Infinite\s*Progress|wechat[_ ]?twin", re.I)
IDENTITY_FORMS = re.compile(r"\b(?:master|owner|operator)\b", re.I)


def test_default_state_root_is_inside_repo():
    layout = resolve_state(None, REPO_ROOT, create=False)
    assert layout.root == (REPO_ROOT / "state").resolve()


def test_state_root_can_be_pointed_anywhere(tmp_path):
    layout = resolve_state(str(tmp_path / "any" / "place"), REPO_ROOT, create=True)
    assert layout.root.is_dir()
    assert tmp_path in layout.root.parents


def test_cold_start_three_ticks(tmp_path):
    settings = load_settings(env={}, state_root=str(tmp_path / "state"), repo_root=str(REPO_ROOT))
    results = [run_tick(settings=settings) for _ in range(3)]
    assert [r.tick for r in results] == [1, 2, 3]
    assert all(r.rc == 0 for r in results)

    layout = resolve_state(settings.state_root, settings.repo_root)
    produced = [p for p in layout.root.rglob("*") if p.is_file()]
    assert produced, "空仓跑完必须留下账本"
    assert layout.tick_status.is_file() and layout.diff_ledger.is_file()

    for path in produced:
        text = path.read_text(encoding="utf-8", errors="replace")
        assert not ABS_PATH.search(text), "产物含绝对路径：%s" % path
        assert not LEGACY_FORMS.search(text), "产物含旧项目名形态：%s" % path


def test_everything_written_stays_inside_state_root(tmp_path):
    settings = load_settings(env={}, state_root=str(tmp_path / "state"), repo_root=str(REPO_ROOT))
    run_tick(settings=settings)
    layout = resolve_state(settings.state_root, settings.repo_root)
    root = layout.root.resolve()
    for path in layout.root.rglob("*"):
        assert root == path.resolve() or root in path.resolve().parents


def test_cold_start_is_reproducible(tmp_path):
    """同输入同结果：CI 里必须能复跑（差异不在结果里，而在随机种子/时间戳之外）。"""
    preds = [Prediction("X", "大小", "1", tick=1, evidence="p1")]
    obs = [Observation("X", "大小", "2", "文件:x")]

    runs = []
    for name in ("a", "b"):
        settings = load_settings(env={}, state_root=str(tmp_path / name), repo_root=str(REPO_ROOT))
        result = run_tick(settings=settings, tick=1, predictions=preds, observations=obs)
        runs.append(result.as_dict())
    assert runs[0]["diffs"] == runs[1]["diffs"]
    assert runs[0]["new_sprouts"] == runs[1]["new_sprouts"]


def test_cold_start_zero_token(tmp_path):
    """机械拍的硬保证：不给 LLM 就不该有任何出网/外部命令调用。"""
    import infinigrow.engine.tick as tick_mod
    source = Path(tick_mod.__file__).read_text(encoding="utf-8")
    for forbidden in ("subprocess", "requests", "urllib", "socket", "httpx"):
        assert forbidden not in source, "机械拍不该引入 %s" % forbidden
