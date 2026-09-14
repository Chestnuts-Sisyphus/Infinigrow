#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""privacy_scan —— 仓库发布前的隐私/身份清场扫描器（规则是通用的，不含任何私人名单）。

用途：在开源发布前，扫描一棵源码树里**不该进公共仓库**的东西：
  1. 绝对路径（Windows 盘符路径 / POSIX 家目录路径）——应为可配置项；
  2. 凭据型字面量（各家 API key 前缀、Bearer、私钥块、疑似密钥赋值）；
  3. 电子邮箱与个人身份线索；
  4. 项目私有依赖（本机密钥目录、私有代理端口、他项目名等）。

规则分两层（这是本工具的设计要点）：
  - **通用层**（内置，随仓库发布）：任何项目都不该有的东西（绝对路径/凭据/邮箱）。
  - **项目层**（`--deny <file>`，**不进公共仓库**，放仓库外或 gitignore）：
    具体人名、机器路径、他项目名、密钥文件名。格式一行一条：`<正则>` 或
    `<正则>\t<标签>`，`#` 开头为注释。

**本脚本零写盘**（项目约定：脚本只做只读扫描，结果走 stdout，需要落盘由调用方重定向）。
路径安全：`--root` 与 `--deny` 先 realpath 规范化，并拒绝含 `..` 上跳段的原始输入。

输出：人类可读清单（默认）或 JSON（`--json`）；命中即 rc=1（可直接当 CI 闸）。

用法：
    python tools/privacy_scan.py --root .
    python tools/privacy_scan.py --root . --deny deny.txt --json > scan.json
"""
import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------- 通用规则
# 每项：(标签, 正则, 说明)。正则在文本行上匹配。
GENERIC_RULES = [
    ("abs-win-path",
     re.compile(r"\b[A-Za-z]:[\\/](?:[^\\/\s\"'<>|]+[\\/]){0,6}"),
     "Windows 绝对路径：进公共仓库＝泄漏本机目录结构；应改配置项"),
    ("abs-posix-path",
     re.compile(r"(?<![\w/])/(?:home|Users|root|mnt|opt)/[\w.-]+"),
     "POSIX 家目录/挂载绝对路径：同上"),
    ("aws-key",
     re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
     "AWS Access Key ID 形态"),
    ("github-token",
     re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
     "GitHub token 形态"),
    ("openai-style-key",
     re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
     "OpenAI 风格 key 形态"),
    ("bearer-literal",
     re.compile(r"\bBearer\s+[A-Za-z0-9_\-.]{20,}"),
     "Bearer 字面量"),
    ("private-key-block",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
     "私钥块"),
    ("credential-assign",
     re.compile(r"""(?i)\b(?:api[_-]?key|secret|passwd|password|token)\s*[:=]\s*["'][^"'\s]{12,}["']"""),
     "疑似硬编码凭据赋值"),
    ("email",
     re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b"),
     "邮箱：个人身份线索（示例可用 example.com）"),
]

# 允许出现的白名单（示例/文档里常见且无害）
ALLOWLIST = [
    re.compile(r"[\w.+-]+@(?:example\.(?:com|org|net)|test\.local)"),
    re.compile(r"sk-xxx+", re.I),
    re.compile(r"<[^>]*key[^>]*>", re.I),          # <your-api-key> 之类的占位
    re.compile(r"\$\{?[A-Z_]+\}?"),                 # 环境变量引用
]

# 默认跳过的目录/文件后缀（二进制与运行时态）。
# 工具缓存目录必须跳过：linter/测试框架的缓存里会写下**本机绝对路径**，
# 而 CI 的顺序恰好是「先 ruff 后隐私扫描」——缓存不跳过就会把自家 CI 判红。
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache",
             ".pytest_cache", ".ruff_cache", ".tox", ".nox", ".hypothesis",
             "state", "archive", ".idea", ".vscode", "build", "dist", ".eggs"}
SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz",
               ".xmind", ".mmdb", ".db", ".pyc", ".exe", ".woff", ".woff2", ".ttf"}

#: 扫描器自己的禁列清单（不进公共仓库；扫它必然自匹配，且它本来就不发布）
SKIP_FILES = {"privacy-deny.txt"}


def normalize(path):
    """规范化路径；拒绝含 `..` 上跳段的原始输入（防越权读）。"""
    path = os.fspath(path)
    if any(seg == ".." for seg in path.replace("\\", "/").split("/")):
        raise SystemExit("拒绝：路径含 `..` 上跳段 → %s" % path)
    return os.path.realpath(os.path.abspath(path))


def inside(path, root):
    """判断 path 是否落在 root 之内（规范化后比较）。"""
    p, r = os.path.realpath(path), os.path.realpath(root)
    return p == r or p.startswith(r + os.sep)


def load_deny(path):
    rules = []
    if not path:
        return rules
    real = normalize(path)
    with open(real, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            # 分隔符支持三种写法：真实 TAB、字面 `\t` 两字符、以及 `::`（防编辑期转义丢失）
            parts = re.split(r"\t|\\t|\s+::\s+", line, maxsplit=1)
            pattern = parts[0]
            label = parts[1] if len(parts) > 1 else "deny-rule"
            try:
                rules.append((label, re.compile(pattern),
                              "项目层禁列（%s:%d）" % (os.path.basename(real), lineno)))
            except re.error as exc:
                print("WARN: deny 规则 %d 正则无效，已跳过：%r（%s）" % (lineno, pattern, exc),
                      file=sys.stderr)
    return rules


def allowed(text):
    return any(rx.search(text) for rx in ALLOWLIST)


def scan_file(path, rules, root, rel):
    hits = []
    if os.path.basename(path) in SKIP_FILES:
        return hits
    if not inside(path, root):          # 只读扫描根之内的文件（越界一律跳过）
        return hits
    try:
        with open(os.path.realpath(path), encoding="utf-8", errors="replace") as fh:
            for lineno, line in enumerate(fh, 1):
                if allowed(line):
                    continue
                for label, rx, why in rules:
                    m = rx.search(line)
                    if m:
                        # 一行可同时命中多类规则（身份词常与路径同行），逐类记录，不遮蔽
                        hits.append({"file": rel, "line": lineno, "rule": label,
                                     "why": why, "match": m.group(0)[:120]})
    except (OSError, UnicodeError) as exc:
        hits.append({"file": rel, "line": 0, "rule": "read-error",
                     "why": "无法读取", "match": str(exc)[:120]})
    return hits


def walk(root, extra_skip=()):
    skip_dirs = SKIP_DIRS | set(extra_skip)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for name in filenames:
            if os.path.splitext(name)[1].lower() in SKIP_SUFFIX:
                continue
            full = os.path.join(dirpath, name)
            yield full, os.path.relpath(full, root).replace("\\", "/")


def main(argv=None):
    ap = argparse.ArgumentParser(description="发布前隐私/身份清场扫描（只读、零写盘）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--deny", default=None, help="项目层禁列文件（不进公共仓库）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出（调用方重定向落盘）")
    ap.add_argument("--skip-dir", action="append", default=[], help="额外跳过目录名")
    args = ap.parse_args(argv)

    root = normalize(args.root)
    rules = list(GENERIC_RULES) + load_deny(args.deny)

    hits = []
    files = 0
    for full, rel in walk(root, args.skip_dir):
        files += 1
        hits.extend(scan_file(full, rules, root, rel))

    by_rule = {}
    for h in hits:
        by_rule[h["rule"]] = by_rule.get(h["rule"], 0) + 1

    if args.json:
        print(json.dumps({"root": root, "files": files, "by_rule": by_rule, "hits": hits},
                         ensure_ascii=False, indent=2))
    else:
        for h in hits:
            print("%s:%s  [%s] %s  ← %s" % (h["file"], h["line"], h["rule"], h["match"], h["why"]))
        print("\n=== 扫描汇总 ===")
        print("根目录：%s" % root)
        print("扫描文件数：%d｜规则数：%d（通用 %d ＋ 项目层 %d）"
              % (files, len(rules), len(GENERIC_RULES), len(rules) - len(GENERIC_RULES)))
        if by_rule:
            for rule, cnt in sorted(by_rule.items(), key=lambda kv: -kv[1]):
                print("  %-22s %d" % (rule, cnt))
        else:
            print("  无命中")

    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
