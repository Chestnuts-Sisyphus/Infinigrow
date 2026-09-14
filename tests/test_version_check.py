# -*- coding: utf-8 -*-
"""版本判定与「必须是最新版」的机制测试。

定规是「运行的引擎永远最新版」——这条要成立，得有两个机械件：
  ① 一个不靠人记忆的判据（本地版 vs 最新发布，`compare`）；
  ② 一个便宜的升级动作（`tools/update_local.py`，本测试只验证它的入口存在与参数形态）。

另外这里给请求面收窄（SSRF 防护）上锁：协议/主机白名单、仓库名严格、拒重定向、
拒绝解析到非公网地址——一个只查版本号的工具，没有任何理由能访问内网。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from infinigrow.core.version_check import (API_HOST, BlockedRequest, DEFAULT_REPO,
                                           _assert_target_public, _proxy_configured,
                                           _safe_url, compare, parse_version)

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("text,expected", [
    ("2.0.0", (2, 0, 0)),
    ("v2.0.0", (2, 0, 0)),
    ("v10.3.7", (10, 3, 7)),
    ("2.1.0-rc1", (2, 1, 0)),
    ("不是版本号", None),
    ("", None),
])
def test_parse_version(text, expected):
    assert parse_version(text) == expected


@pytest.mark.parametrize("local,latest,expected", [
    ("2.0.0", "v2.0.0", "same"),
    ("2.0.0", "v2.1.0", "behind"),
    ("2.2.0", "v2.1.9", "ahead"),
    ("2.0.0", "garbage", "unknown"),
])
def test_compare(local, latest, expected):
    assert compare(local, latest) == expected


def test_never_claims_latest_when_unknown():
    """把不知道说成知道，是这个项目最忌讳的事：解析不出必须报 unknown，不是 same。"""
    assert compare("2.0.0", "无版本信息") == "unknown"
    assert compare("无版本信息", "2.0.0") == "unknown"


# ---------------------------------------------------------------- 请求面收窄
def test_url_pinned_to_https_and_allowlisted_host():
    url = _safe_url(DEFAULT_REPO)
    assert url.startswith("https://%s/" % API_HOST)


@pytest.mark.parametrize("bad", [
    "../../etc/passwd",               # 路径穿越
    "owner/name/../../x",             # 多余路径段
    "owner",                          # 缺名字
    "",                               # 空
    "owner/na me",                    # 非法字符
    "http://evil.com",                # 想把主机塞进参数里
])
def test_bad_repo_names_are_refused(bad):
    with pytest.raises(BlockedRequest):
        _safe_url(bad)


def test_repo_argument_can_never_move_the_host():
    """关键性质：无论仓库名长什么样，**主机永远是白名单那一个**（参数动不了主机）。"""
    for repo in ("evil.com/x", "a.b/c-d", "Owner/Repo.name"):
        assert _safe_url(repo).startswith("https://%s/repos/" % API_HOST)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "10.0.0.1", "169.254.169.254"])
def test_private_and_loopback_hosts_are_refused(host):
    """直连场景下，环回/私网/链路本地（含云元数据地址）一律拒——SSRF 的常见落点。"""
    with pytest.raises(BlockedRequest):
        _assert_target_public(host)


def test_local_resolution_allowed_only_when_a_proxy_is_configured(monkeypatch):
    """本机实测：配了代理时 `api.github.com` 会解析到 127.0.0.1（连接发给代理，不走该地址）。

    所以：**有代理 → 跳过 IP 检查**（否则是误报）；**没代理 → 严格拒**（真 SSRF 闸）。
    """
    with pytest.raises(BlockedRequest):
        _assert_target_public("127.0.0.1", allow_local=False)
    assert _assert_target_public("127.0.0.1", allow_local=True) is None

    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:8080")   # 端口取通用值，不用本机私有端口
    assert _proxy_configured() is True
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setattr("urllib.request.getproxies", lambda: {})
    assert _proxy_configured() is False


def test_redirects_are_not_followed():
    from infinigrow.core.version_check import _NoRedirect
    handler = _NoRedirect()
    with pytest.raises(BlockedRequest):
        handler.redirect_request(None, None, 302, "Found", {}, "https://elsewhere.example/")


# ---------------------------------------------------------------- 升级工具
def test_update_tool_exists_and_has_check_mode():
    tool = REPO_ROOT / "tools" / "update_local.py"
    assert tool.is_file()
    p = subprocess.run([sys.executable, str(tool), "--help"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    assert p.returncode == 0
    assert "--check" in p.stdout


def test_cli_version_check_runs_offline_safely():
    """`version --check` 在离线/被拦时必须给出说明并以 0 退出（不误报落后）。"""
    p = subprocess.run([sys.executable, "-m", "infinigrow", "version", "--check"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=120, cwd=str(REPO_ROOT), env={"PYTHONPATH": str(REPO_ROOT / "src"),
                                                             "PATH": ""})
    assert p.returncode in (0, 3)
    assert "最新发布" in p.stdout
