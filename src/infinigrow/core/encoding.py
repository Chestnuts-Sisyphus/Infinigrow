# -*- coding: utf-8 -*-
"""编码硬化：stdout/stderr 一律 UTF-8，写盘一律 UTF-8 无 BOM。

为什么要独立一层：引擎的输出会被三种消费者读——人眼（控制台）、LLM 通道（管道）、
账本文件（落盘）。三者编码不一致就是乱码；v1 现场踩过（GBK 控制台 + UTF-8 账本）。
「UTF-8 无 BOM」同时是仓库约定，由 `.gitattributes` 与测试双重固化。
"""
from __future__ import annotations

import sys

BOM = "\ufeff"


def harden_stdio() -> None:
    """把 stdout/stderr 切到 UTF-8（不支持的流静默跳过，不抛）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def strip_bom(text: str) -> str:
    """去掉可能被外部写入的 BOM——BOM 会让「首行」判据失配（v1 出过幽灵对象事故）。"""
    return text[1:] if text.startswith(BOM) else text


def read_text(path) -> str:
    """读文本：UTF-8 无 BOM，失败回退 GBK（历史账本有 GBK 存盘）。"""
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def write_text(path, text) -> None:
    """写文本：UTF-8 无 BOM、LF 换行（内容里的 BOM 会被剥掉，防幽灵首行）。"""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(strip_bom(text))
