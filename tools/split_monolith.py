#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""split_monolith —— 单体拆分**分析器**（零写盘：把拆分清单打到 stdout，由调用方落盘/执行）。

为什么是「零写盘」：本项目约定——会写盘的脚本一律走「分析输出 stdout + 调用方重定向」，
避免脚本自身持有任意路径写权限（安全姿态）。本工具只 **读** 一个源文件、**打印** 一份
可复跑清单；真正切片由清单里的 `sed` 命令执行（路径全为字面量，可人工核对）。

设计要点（为什么这样拆）：
  - 单体 `引擎共享基建.py` 是**一个扁平命名空间**：函数之间靠模块级名字互调。
    粗暴按行切会让跨模块引用断裂；因此拆出的模块采用**线性依赖链 + 星号导入**
    （core → ledger → rules），调用发生在运行期，链内前向引用全部可用。
  - 顶层块用 `ast` 取**精确行区间**（含装饰器与多行字符串），不靠正则猜边界。
  - 归属靠**显式表**（前缀/全名），无法归属的块**显式报错**，绝不静默塞进默认模块
    （静默归属＝漂移点，本项目的诚实纪律）。

用法：
    python tools/split_monolith.py --src <v1 单体> --table          # 只打印归属表
    python tools/split_monolith.py --src <v1 单体> --manifest        # 打印切片脚本（stdout）
    # 落盘后执行：bash state/split-manifest.sh   （在仓库根运行）
"""
import argparse
import ast
import os
import sys

# 归属表：按顺序匹配，先命中先归属。key=目标模块（相对包根），value=名前缀/全名集合。
ASSIGN = [
    ("core/base.py", {
        "names": {
            "force_utf8_stdio", "read_key", "resolve_opencode", "default_config_path",
            "strip_jsonc_comments", "load_config_model", "key_dir_smoke", "provider_key_spec",
            "unmapped_key_files", "build_chain", "run_chain_assert", "run_chain_assert_selftest",
            "probe_prompt_text", "add_self_to_sys_path", "TickHeartbeatError",
            "record_tick_result", "read_tick_status", "rc_semantics",
            "OPENCODE_FALLBACKS", "TAG_FOR_FILE", "PROVIDER_KEY_SOURCES", "KNOWN_OTHER_KEYS",
            "PROBE_EXPECT_MARKER", "TREE_DIR", "RC_OK", "RC_WRAPPER_ERROR", "RC_CONFIG_MISSING",
            "RC_CHANNELS_DEAD", "MAINT_RESIDUAL_RC", "RC_SEMANTICS",
            "MODEL_FALLBACKS", "TICK_STATUS", "TICK_FAIL_THRESHOLD", "STATE_MD",
            "LIUHEN_END_ANCHOR", "CAPABILITY_LIB", "STATE_REQUIRE_MARKERS",
            "maintenance_residual_verdict",
        },
        "prefixes": (),
    }),
    ("ledger/safe_io.py", {
        "names": {
            "same_file_guard", "health_event_line", "parse_health_ledger",
            "gardener_health_events", "bench_last_record_fails", "surprise_line",
            "parse_surprise_ledger", "trigger_line", "parse_trigger_ledger",
            "battle_line", "parse_battle_ledger", "rule_record", "liveness_verdict",
            "sleeping_rules", "bb_prophecy_check", "birth_proof_check",
            "protocol_revision_check", "transplant_check", "late_expect_check",
            "blind_review_check", "pickup_tier", "m3_pickup_rewrite", "apex_should_cut",
            "HEALTH_LEDGER_HEADER", "HEALTH_EVENT_COOLDOWN_MIN",
            "SURPRISE_LEDGER", "SURPRISE_LEDGER_HEADER", "_SURPRISE_RX",
            "TRIGGER_LEDGER", "TRIGGER_LEDGER_HEADER", "_TRIGGER_RX",
            "BATTLE_LEDGER", "BATTLE_LEDGER_HEADER", "_BATTLE_RX",
        },
        "prefixes": ("safe_", "append_", "_surprise_rx", "_trigger_rx", "_battle_rx",
                     "_health_", "_safe_tmp_replace", "_HEALTH_RX", "_SURPRISE_RX",
                     "_TRIGGER_RX", "_BATTLE_RX"),
    }),
    ("rules/fixtures.py", {
        "names": {"_SELFTEST_CASES", "_REALFILE_INJECT_RECIPES"},
        "prefixes": ("_SELFTEST_CASES", "_REALFILE_INJECT"),
    }),
    ("rules/static_scan.py", {
        "names": {
            "run_static_scan", "run_static_scan_selftest", "maintenance_override_note",
            "bench_ledger_status", "bench_runtime_currency", "run_real_file_inject",
            "run_four_place_consistency", "_RfBreakError", "_rf_scope_text", "_load_scope",
            "SCAN_SCOPE", "SCAN_PROBE_ASSET", "BENCH_LEDGER", "BENCH_RECORD_MARK",
            "BENCH_WATCH", "HEALTH_LEDGER", "RULE_SOURCE_CARD", "CARD_SOURCE_RULE",
            "BENCH_SIGNAL_WEIGHT", "_RECIPE_COUNT_PER_RULE", "_STATIC_RULES",
            "_REGISTRY_GUARD_WINDOWS", "_MAIN_SELFTEST_CHECKS",
            "_DRYRUN_WIN_START", "_MAIN_SELFTEST_WIN_START", "_ENGINE_DIR",
        },
        "prefixes": ("_scan_r", "_rf_", "_is_", "_eat_", "_strip_py", "_py_code",
                     "_bat_", "_STATIC_", "_R4_", "_R9_", "_RC_", "_R18_",
                     "_T12", "_PROBE_"),
    }),
]

# 行号级兜底：无法按名字归属的块（模块级 for/if 等）按起始行显式登记，仍不设默认归属。
LINE_OVERRIDE = {
    2: None,                        # 模块 docstring：由新文件头取代，不搬运
    2022: "rules/static_scan.py",   # for _r, _cards in RULE_SOURCE_CARD.items():
    2023: "rules/static_scan.py",   # 续行保护（ast 已并入同一块时无副作用）
}

ORDER = ["core/base.py", "ledger/safe_io.py", "rules/static_scan.py", "rules/fixtures.py"]

HEADER = '''# -*- coding: utf-8 -*-
"""infinigrow · %s（v2 拆分包的一层）

由 tools/split_monolith.py 从 v1 单体机械拆出的**一层**（清单可复跑：该工具 --manifest）。
拆分保持原文件的定义顺序；跨层引用按 core → ledger → rules 线性链星号导入，
调用发生在运行期，链内前向引用全部可用（语义与单体一致）。
"""

'''


def top_blocks(src_text, filename="<src>"):
    """返回 [(start_line, end_line, kind, name)]，按原文件顺序，1-based 闭区间。"""
    tree = ast.parse(src_text, filename=filename)
    blocks = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            kind, name = type(node).__name__, node.name
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            start, kind, name = node.lineno, "Import", "_import"
        elif isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            start, kind, name = node.lineno, "Assign", (targets[0] if targets else "_assign")
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            start, kind, name = node.lineno, "AnnAssign", node.target.id
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            start, kind, name = node.lineno, "Docstring", "_docstring"
        elif isinstance(node, ast.If):
            start, kind, name = node.lineno, "IfMain", "__main__"
        else:
            start, kind, name = node.lineno, "Other:" + type(node).__name__, "_other"
        blocks.append([start, node.end_lineno, kind, name])
    return blocks


def classify(name, kind, start=None):
    """返回目标模块；None=不搬运（如模块 docstring）。未登记 → 抛 KeyError 由调用方报告。"""
    if start is not None and start in LINE_OVERRIDE:
        return LINE_OVERRIDE[start]
    if kind == "Docstring":
        return None                    # 模块 docstring 由新文件头取代，不搬运
    if kind == "Import":
        return "core/base.py"          # 全部 import 放链头，下游星号导入一并可见
    for mod, spec in ASSIGN:
        if name in spec["names"]:
            return mod
        for pre in spec["prefixes"]:
            if name.startswith(pre):
                return mod
    if kind == "IfMain":
        return "rules/static_scan.py"  # 入口 main 段（--selftest 走 rules 自检）
    return _UNASSIGNED


_UNASSIGNED = object()


def build(src):
    text = open(src, encoding="utf-8").read()
    lines = text.splitlines()
    buckets, unassigned, order_seen = {}, [], []
    for start, end, kind, name in top_blocks(text, src):
        mod = classify(name, kind, start)
        if mod is _UNASSIGNED:
            unassigned.append((start, end, kind, name))
            continue
        if mod is None:
            continue                   # 显式跳过
        if mod not in buckets:
            order_seen.append(mod)
        buckets.setdefault(mod, []).append((start, end, kind, name))
    return lines, buckets, unassigned, order_seen


def main(argv=None):
    ap = argparse.ArgumentParser(description="单体外壳拆分分析器（零写盘）")
    ap.add_argument("--src", required=True)
    ap.add_argument("--table", action="store_true", help="打印归属表")
    ap.add_argument("--manifest", action="store_true", help="打印切片 shell 脚本")
    ap.add_argument("--pkg", default="src/infinigrow", help="包根（清单里用，相对仓库根）")
    args = ap.parse_args(argv)

    src = os.path.realpath(os.path.abspath(args.src))
    if not os.path.isfile(src):
        raise SystemExit("源文件不存在：%s" % src)

    lines, buckets, unassigned, order_seen = build(src)

    print("# 源：%s（%d 行）" % (src, len(lines)), file=sys.stderr)
    print("# %-24s %s" % ("目标模块", "块数"), file=sys.stderr)
    for mod in order_seen:
        print("# %-24s %d" % (mod, len(buckets[mod])), file=sys.stderr)
    if unassigned:
        print("\n!! 未归属块（必须显式处理，不许默认归属）：", file=sys.stderr)
        for start, end, kind, name in unassigned:
            print("   L%d-L%d %s %s | %s" % (start, end, kind, name, lines[start - 1][:70]),
                  file=sys.stderr)
        return 2
    if args.table:
        return 0
    if not args.manifest:
        print("提示：加 --manifest 打印切片脚本。", file=sys.stderr)
        return 0

    # ---- 打印切片脚本（stdout；由调用方重定向为 .sh 后 bash 执行）----
    src_sh = src.replace("\\", "/")
    print("#! /usr/bin/env bash")
    print("# 由 tools/split_monolith.py --manifest 生成；在仓库根执行。")
    print("# 语义：把 v1 单体按顶层块切进 %s/ 的线性链各层（core → ledger → rules）。" % args.pkg)
    print("set -euo pipefail")
    print('SRC="%s"' % src_sh)
    print('PKG="%s"' % args.pkg)
    print('mkdir -p "$PKG/core" "$PKG/ledger" "$PKG/rules"')
    prev = None
    for mod in ORDER:
        if mod not in buckets:
            continue
        print('\n: > "$PKG/%s"' % mod)
        print("cat > \"$PKG/%s\" <<'IGHEADER'" % mod)
        sys.stdout.write(HEADER % mod.replace(".py", "").replace("/", " · "))
        if prev:
            print("from .%s import *  # noqa: F401,F403 —— 线性链：上游全部名字对本层可见"
                  % prev.replace("/", ".").replace(".py", ""))
        print("IGHEADER")
        first = True
        for start, end, kind, name in buckets[mod]:
            if not first:
                print('printf \'\\n\\n\\n\' >> "$PKG/%s"' % mod)
            print("sed -n '%d,%dp' \"$SRC\" >> \"$PKG/%s\"   # %s %s" % (start, end, mod, kind, name))
            first = False
        prev = mod
    print('\necho "拆分完成：$(wc -l "$PKG"/*/*.py | tail -1)"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
