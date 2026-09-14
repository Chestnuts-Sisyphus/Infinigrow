# -*- coding: utf-8 -*-
"""版本比对与「是否落后于最新发布」的机械判定。

为什么要它：**运行中的引擎必须是当前最新版**（定规）。要做到这点，
首先得有一个不问人、不靠记忆的判据——「我现在这版，跟最新发布比，是同一版还是落后」。

四条设计约束：

1. **判定是纯函数**（`parse_version` + `compare`），可单测、可复跑，不需要网络。
2. **查询失败不算落后**（fail-soft）：查不到就报 `unknown` 并说明原因，
   绝不把「网络不通」伪装成「已是最新」——那是把不知道说成知道的病。
3. **零凭据**：只读公开的 releases 接口，不带任何 token（公开仓库无需鉴权）。
4. **请求面收窄**（SSRF 防护，机械可查）：协议锁死 `https`、主机锁死白名单、
   仓库名过严格字符集、**不跟随重定向**、并把解析出的 IP 逐个拒掉私网/环回/链路本地
   ——一个只查版本号的工具，没有任何理由能访问内网地址。
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

DEFAULT_REPO = "Chestnuts-Sisyphus/Infinigrow"
API_HOST = "api.github.com"
API_PATH = "/repos/%s/releases/latest"
UA = "infinigrow-version-check"

_VER_RX = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")
_REPO_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")


class BlockedRequest(ValueError):
    """请求被安全校验拦下（协议/主机/地址越界）——显式报出，不静默降级。"""


def _proxy_configured() -> bool:
    """环境里配了 http(s) 代理吗？

    这件事决定了「解析出的 IP」是否有意义：**配了代理时，连接是发给代理的**，
    目标域名的解析结果根本不会被连——本机实测就有这种情况（`api.github.com`
    被本地代理解析成 127.0.0.1）。此时按 IP 判「内网地址」是误报。
    没有代理时（真正的直连场景），IP 检查才是有效的 SSRF 闸。
    """
    try:
        proxies = urllib.request.getproxies()
    except Exception:                                    # noqa: BLE001 — 拿不到就当没配
        return False
    return bool(proxies.get("https") or proxies.get("http"))


def _assert_target_public(host: str, port: int = 443, allow_local: bool = False) -> None:
    """解析主机名并拒绝私网/环回/链路本地/保留地址（防 SSRF 与 DNS rebinding）。

    `allow_local=True`（环境里配了代理）时跳过——见 `_proxy_configured` 的理由。
    """
    if allow_local:
        return
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise BlockedRequest("域名解析失败：%s（%s）" % (host, exc)) from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise BlockedRequest("拒绝：%s 解析到非公网地址 %s" % (host, ip))


def _safe_url(repo: str) -> str:
    """构造并校验请求 URL：协议 https、主机白名单、仓库名严格、解析地址必须公网。"""
    if not _REPO_RX.match(repo or ""):
        raise BlockedRequest("仓库名不合规（应为 owner/name）：%r" % repo)
    url = "https://%s%s" % (API_HOST, API_PATH % repo)
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname != API_HOST:
        raise BlockedRequest("拒绝：协议或主机不符白名单（scheme=%s host=%s）"
                             % (parts.scheme, parts.hostname))
    _assert_target_public(parts.hostname, parts.port or 443,
                          allow_local=_proxy_configured())
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """不跟随重定向：跳走即失败（否则白名单等于没设）。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        raise BlockedRequest("拒绝跟随重定向 → %s" % newurl)


def parse_version(text: str) -> Optional[tuple[int, int, int]]:
    """把 "v2.0.0" / "2.1.3" 解析成 (2,0,0)。解析不出返回 None（不猜）。"""
    m = _VER_RX.match(str(text).strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def compare(local: str, latest: str) -> str:
    """返回 `same`｜`behind`｜`ahead`｜`unknown`。unknown=有一边解析不出（不含糊其辞）。"""
    a, b = parse_version(local), parse_version(latest)
    if a is None or b is None:
        return "unknown"
    if a == b:
        return "same"
    return "behind" if a < b else "ahead"


def latest_release(repo: str = DEFAULT_REPO, timeout: float = 6.0) -> tuple[Optional[str], str]:
    """查最新发布 tag。返回 (tag 或 None, 说明)。失败必有说明，不静默。"""
    try:
        url = _safe_url(repo)
    except BlockedRequest as exc:
        return None, "查询被拦：%s" % exc
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/vnd.github+json"})
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except BlockedRequest as exc:
        return None, "查询被拦：%s" % exc
    except urllib.error.HTTPError as exc:
        return None, "查询失败：HTTP %s（仓库或发布不可见？）" % exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, "查询失败：网络不可达（%s）" % type(exc).__name__
    except (ValueError, json.JSONDecodeError):
        return None, "查询失败：响应不是合法 JSON"
    tag = data.get("tag_name") or data.get("name")
    if not tag:
        return None, "查询失败：响应里没有 tag_name"
    return str(tag), "ok"


def verdict(local: str, repo: str = DEFAULT_REPO, timeout: float = 6.0) -> dict:
    """给 CLI/脚本用的合成判定：{local, latest, status, note, upgrade_hint}。"""
    tag, note = latest_release(repo, timeout)
    status = "unknown" if tag is None else compare(local, tag)
    if status == "behind":
        hint = ("本地 %s 落后于最新发布 %s —— 升级：python tools/update_local.py"
                % (local, tag))
    elif status == "same":
        hint = "本地即最新发布"
    elif status == "ahead":
        hint = "本地比最新发布还新（未发布的开发版？）"
    else:
        hint = "%s（无法判定是否最新）" % note
    return {"local": local, "latest": tag, "status": status, "note": note,
            "upgrade_hint": hint}
