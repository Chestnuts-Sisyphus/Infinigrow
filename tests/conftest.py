# -*- coding: utf-8 -*-
"""pytest 公共夹具：**每个测试都用临时状态根**（空仓），不碰真实运行目录。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture()
def settings(tmp_path):
    """默认配置 + 状态根/主体根都指向临时目录（＝「空仓」）。

    主体根也进临时目录：测试**不许**碰真实的生长主体（默认在仓库同级目录下，
    那是使用者真正要长东西的地方）。要有意测试「默认主体在仓库外」的规则，
    单独写测试并显式构造配置（见 `tests/test_subject.py`）。
    """
    from infinigrow.core.config import load_settings
    return load_settings(env={}, state_root=str(tmp_path / "state"),
                         repo_root=str(REPO_ROOT),
                         subject_root=str(tmp_path / "subject"))


@pytest.fixture()
def layout(settings):
    from infinigrow.core.paths import resolve_state
    return resolve_state(settings.state_root, settings.repo_root, create=True)
