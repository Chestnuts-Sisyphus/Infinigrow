# -*- coding: utf-8 -*-
"""静态规则扫描：全机械、零 token、可作 CI 闸。

| 规则 | 守住什么 |
|---|---|
| R1 零绝对路径 | 源码/提示词/脚本里不出现本机路径（开源红线 + 可搬运） |
| R2 提示词↔代码同源 | 机制关键词在提示词与代码两侧**双向**存在（缺一边即漂移） |
| R3 禁自造芽条款 | 提示词里不得再出现「每拍必须登记新芽」这类旧条款（T9 回归闸） |
| R4 状态根被忽略 | 状态目录进版本库＝把个人账本推上公开仓库 |
| R5 无凭据字面量 | key/token/私钥不得硬编码 |
| R6 无 BOM | 写盘统一 UTF-8 无 BOM（BOM 曾造出「幽灵首行」事故） |

自检（`selftest()`）给每条规则配**正反用例**：正例=正常态应 PASS，反例=病灶态应 FAIL。
规则自身的防退化靠它——规则改坏了不会静默。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

# ---------------------------------------------------------------- 扫描范围
SCAN_SUFFIXES = (".py", ".md", ".toml", ".cfg", ".txt", ".yml", ".yaml", ".sh",
                 # 一键件与计划任务脚本也要扫：它们**就是**发布内容的一部分
                 # （曾经因为不在这张表里，规则看不见它们）
                 ".bat", ".cmd", ".ps1", ".psm1")
SKIP_DIRS = {"__pycache__", ".git", "state", "archive", ".venv", "venv",
             "node_modules", ".pytest_cache", ".ruff_cache", "build", "dist"}

#: 允许行内放行的标记（显式豁免要留痕，不许无声放宽）
NOQA = "# noqa:"

#: 提示词↔代码同源的机制关键词表（单一事实源：**只在这里定义一次**）
SYNC_TERMS = {
    "判读": "engine/model.py",
    "行动": "engine/model.py",
    "原理": "engine/model.py",
    "固化": "engine/model.py",
    "成熟链": "engine/model.py",
    "差异": "engine/reconcile.py",
    "兑现账": "engine/model.py",
    "成熟链封顶": "engine/sprout_sources.py",
    "能力库未用": "engine/sprout_sources.py",
    "零差异零芽": "engine/sprout_sources.py",
    # 运转线新增（v2.1）：机制新长的每一样东西，都必须同时出现在提示词与代码里，
    # 否则就是「机制改了提示词没改」——上一代漂移病的起点。
    "生长主体": "engine/subject.py",
    "执行者": "engine/executor.py",
    "组织会话": "engine/org_session.py",
    "域饱和": "engine/domain_saturation.py",
    "轮转": "ledger/rotation.py",
}

#: 同源表的**覆盖下限**：这几条必须一直在表里（有人静默删词＝漂移面回来了）
MIN_SYNC_TERMS = (
    "判读", "行动", "原理", "固化", "成熟链", "差异", "兑现账", "成熟链封顶",
    "能力库未用", "零差异零芽", "生长主体", "执行者", "组织会话", "域饱和", "轮转",
)

#: 写盘白名单：只有这两个文件可以直接碰文件系统写动作（其余一律走 ledger/store）
WRITE_ALLOWLIST = ("ledger/store.py", "core/encoding.py")

#: 显式例外：规则模块自身含**正反用例夹具**——夹具必须能造病灶态（包括写一个带 BOM 的
#: 假文件、往源码里注入一行越界写盘），所以它自己必然有裸写盘动作。
#: 例外**进报告**（在 R8 的明细里点名），不是静默放宽。
WRITE_SCAN_EXCLUDE = ("rules/static_scan.py",)

#: 写盘动作的形态（**注意**：这里刻意用「方法名 + 模式参数」而不是拼出完整调用，
#: 免得规则文件自己命中自己——自匹配是这类扫描器最常见的假阳性来源）
WRITE_CALL_RX = re.compile(r"\.write_text\(|\.write_bytes\(|open\([^)]*['\"][wax]")
#: 裸退出码：cli 里出现 ≥2 的整数字面量＝退出码语义被写死（应改用 core/exit_codes）
RC_LITERAL_RX = re.compile(r"\breturn\s+([2-9]|\d{2,})\s*$")

#: 提示词里**禁止**出现的历史条款（T9：执行会话不得自造芽）
FORBIDDEN_PROMPT_PHRASES = (
    "必须登记至少一个新芽候选",
    "冒不出新芽",
    "本拍白干",
    "完成即分岔",
)

#: 提示词文件（约定名；缺文件＝规则无法判 → 记 FAIL，不静默跳过）
TICK_PROMPT = "tick.md"
ORG_PROMPT = "org-session.md"

#: 绝对路径形态（**注意**：这里的字符类刻意不含「字母:斜杠」的相邻组合，
#: 否则规则文件自身就会被自己命中——自匹配是这类扫描器最常见的假阳性来源）
ABS_PATH_RX = re.compile(r"(?<![\w/])(?:[A-Za-z]:[\\/]|/(?:home|Users|mnt|opt)/)")
SECRET_RX = [
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


#: 永不进入公共仓库的文件（扫描它们没有意义：它们本来就不发布，且会自匹配）
SKIP_FILES = {"privacy-deny.txt"}


@dataclass
class RuleContext:
    """扫描上下文：显式给出「扫哪儿」，模块自己不猜路径（可测性来源）。"""

    repo_root: Path
    src_dir: Path
    prompts_dir: Path
    state_root: Path
    gitignore: Path = None                     # type: ignore[assignment]

    @classmethod
    def from_repo(cls, repo_root) -> "RuleContext":
        root = Path(repo_root).resolve()
        return cls(repo_root=root, src_dir=root / "src", prompts_dir=root / "prompts",
                   state_root=root / "state", gitignore=root / ".gitignore")

    def ignored_names(self) -> set[str]:
        """`.gitignore` 里列出的顶层名字（不进库的东西不参与「入库内容」检查）。"""
        names = set(SKIP_FILES)
        if self.gitignore and self.gitignore.is_file():
            for line in _read(self.gitignore).splitlines():
                entry = line.strip()
                if not entry or entry.startswith("#") or entry.startswith("*"):
                    continue
                names.add(entry.strip("/").split("/")[0])
        return names


@dataclass
class ScanReport:
    rows: list[str] = field(default_factory=list)
    ok: bool = True

    def add(self, name: str, detail: str, passed: bool) -> None:
        self.rows.append("%s | %s | %s" % ("PASS" if passed else "FAIL", name, detail))
        self.ok = self.ok and passed


def iter_files(ctx: "RuleContext") -> Iterable[Path]:
    """遍历**会被发布**的文本文件（跳过二进制、运行时态、以及 .gitignore 里的顶层名字）。"""
    ignored = ctx.ignored_names()
    for path in sorted(ctx.repo_root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel_parts = path.relative_to(ctx.repo_root).parts
        if rel_parts and rel_parts[0] in ignored:
            continue
        if path.suffix.lower() in SCAN_SUFFIXES:
            yield path


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _code_lines(text: str) -> list[tuple[int, str]]:
    """去掉整行注释后的行（豁免标记必须体现在代码行上，不许藏在注释里）。"""
    out = []
    for no, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        out.append((no, line))
    return out


# ---------------------------------------------------------------- 规则本体
def rule_no_absolute_paths(ctx: RuleContext) -> tuple[str, bool]:
    hits = []
    for path in list(iter_files(ctx)):
        rel = path.relative_to(ctx.repo_root).as_posix()
        for no, line in _code_lines(_read(path)):
            if NOQA in line:
                continue
            m = ABS_PATH_RX.search(line)
            if m and "example" not in line:
                hits.append("%s:%d %s" % (rel, no, m.group(0)))
    return ("零绝对路径：命中 %d 处%s" % (len(hits), "（" + "; ".join(hits[:5]) + "）" if hits else ""),
            not hits)


def rule_prompt_code_sync(ctx: RuleContext) -> tuple[str, bool]:
    """双向检查：提示词提到的机制关键词，代码里得有定义；代码里定义的，提示词得提到。"""
    prompt_text = ""
    for name in (TICK_PROMPT, ORG_PROMPT):
        p = ctx.prompts_dir / name
        if p.is_file():
            prompt_text += _read(p)
    missing_in_code, missing_in_prompt = [], []
    for term, owner in SYNC_TERMS.items():
        owner_path = ctx.src_dir / "infinigrow" / owner
        if not owner_path.is_file() or term not in _read(owner_path):
            missing_in_code.append("%s(应见于 %s)" % (term, owner))
        if prompt_text and term not in prompt_text:
            missing_in_prompt.append(term)
    detail = "同源：代码侧缺 %d、提示词侧缺 %d" % (len(missing_in_code), len(missing_in_prompt))
    if missing_in_code:
        detail += "；代码侧缺：" + "、".join(missing_in_code)
    if missing_in_prompt:
        detail += "；提示词侧缺：" + "、".join(missing_in_prompt)
    return (detail, not missing_in_code and not missing_in_prompt)


def rule_no_self_sprout_clause(ctx: RuleContext) -> tuple[str, bool]:
    """T9 回归闸：执行会话提示词里不得再出现「自造芽」类旧条款。"""
    p = ctx.prompts_dir / TICK_PROMPT
    if not p.is_file():
        return ("执行会话提示词缺失（%s）：无法判定" % TICK_PROMPT, False)
    text = _read(p)
    hits = [ph for ph in FORBIDDEN_PROMPT_PHRASES if ph in text]
    return ("自造芽条款：命中 %d 条%s" % (len(hits), "（" + "、".join(hits) + "）" if hits else ""),
            not hits)


def rule_state_gitignored(ctx: RuleContext) -> tuple[str, bool]:
    """状态根必须被忽略；否则个人账本会随仓库一起公开。"""
    if ctx.gitignore is None or not ctx.gitignore.is_file():
        return ("无 .gitignore：状态根无法保证被忽略", False)
    text = _read(ctx.gitignore)
    try:
        rel = ctx.state_root.relative_to(ctx.repo_root).as_posix()
    except ValueError:
        return ("状态根在仓库之外（%s）：无需忽略" % ctx.state_root, True)
    ok = any(line.strip().rstrip("/") == rel for line in text.splitlines())
    return ("状态根 %s 已列入 .gitignore" % rel if ok else "状态根 %s **未**列入 .gitignore" % rel, ok)


def rule_no_secrets(ctx: RuleContext) -> tuple[str, bool]:
    hits = []
    for path in iter_files(ctx):
        rel = path.relative_to(ctx.repo_root).as_posix()
        for no, line in enumerate(_read(path).splitlines(), 1):
            if NOQA in line:
                continue
            for rx in SECRET_RX:
                if rx.search(line):
                    hits.append("%s:%d %s" % (rel, no, rx.pattern[:28]))
                    break
    return ("无凭据字面量：命中 %d 处%s" % (len(hits), "（" + "; ".join(hits[:5]) + "）" if hits else ""),
            not hits)


def rule_no_bom(ctx: RuleContext) -> tuple[str, bool]:
    hits = []
    for path in iter_files(ctx):
        try:
            head = path.open("rb").read(3)
        except OSError:
            continue
        if head.startswith(b"\xef\xbb\xbf"):
            hits.append(path.relative_to(ctx.repo_root).as_posix())
    return ("UTF-8 无 BOM：命中 %d 个带 BOM 文件%s"
            % (len(hits), "（" + "、".join(hits[:5]) + "）" if hits else ""), not hits)


def rule_exit_codes_single_source(ctx: RuleContext) -> tuple[str, bool]:
    """R7 rc 语义单一来源：CLI 里不许再出现裸的退出码整数（≥2）。

    退出码是**调用方契约**（计划任务、CI、守护脚本都读它）。写死一个 3 在 A 处是
    「落后」、在 B 处是「自检不过」，契约就没了。规矩：要用就 `from ..core import
    exit_codes as rc` 然后 `rc.BEHIND`。
    """
    cli = ctx.src_dir / "infinigrow" / "cli.py"
    codes = ctx.src_dir / "infinigrow" / "core" / "exit_codes.py"
    if not cli.is_file():
        return ("cli.py 缺失：无法判定退出码来源", False)
    hits = []
    for no, line in _code_lines(_read(cli)):
        if NOQA in line:
            continue
        if RC_LITERAL_RX.search(line.rstrip()):
            hits.append("cli.py:%d" % no)
    has_module = codes.is_file() and "BEHIND" in _read(codes)
    detail = ("rc 语义单一来源：裸整数 %d 处%s；exit_codes 模块 %s"
              % (len(hits), "（" + "、".join(hits[:5]) + "）" if hits else "",
                 "在位" if has_module else "**缺失**"))
    return (detail, not hits and has_module)


def rule_writes_go_through_store(ctx: RuleContext) -> tuple[str, bool]:
    """R8 写盘窗口一致性：`src/infinigrow/**` 里只有 `ledger/store.py` 与
    `core/encoding.py` 可以直接写文件。

    为什么值得一条规则：写盘一旦散落各处，「越界守卫」就只在被想起来的地方存在，
    而原子替换（防断电读到半个文件）更是没人会重复实现一遍。收成一条路，
    出事时只需要看一个文件。
    """
    hits = []
    base = ctx.src_dir / "infinigrow"
    for path in sorted(base.rglob("*.py")):
        rel = path.relative_to(base).as_posix()
        if rel in WRITE_ALLOWLIST or rel in WRITE_SCAN_EXCLUDE:
            continue
        for no, line in _code_lines(_read(path)):
            if NOQA in line:
                continue
            if WRITE_CALL_RX.search(line):
                hits.append("%s:%d" % (rel, no))
    return ("写盘窗口：越界写盘 %d 处%s（白名单：%s；显式例外：%s）"
            % (len(hits), "（" + "、".join(hits[:5]) + "）" if hits else "",
               "、".join(WRITE_ALLOWLIST), "、".join(WRITE_SCAN_EXCLUDE)), not hits)


def rule_sync_terms_coverage(ctx: RuleContext) -> tuple[str, bool]:
    """R9 同源表覆盖不得缩表：`MIN_SYNC_TERMS` 里的机制词必须同时在表里与提示词里。

    R2 管的是「表里的词两侧齐不齐」，这条管的是「表本身有没有被悄悄改小」——
    删一个词比改坏一处代码更隐蔽：机制还在跑，同源校验却已经不再覆盖它了。
    """
    missing_in_table = [t for t in MIN_SYNC_TERMS if t not in SYNC_TERMS]
    prompt_text = ""
    for name in (TICK_PROMPT, ORG_PROMPT):
        p = ctx.prompts_dir / name
        if p.is_file():
            prompt_text += _read(p)
    missing_in_prompt = [t for t in MIN_SYNC_TERMS if t not in prompt_text]
    detail = ("同源表覆盖：表内缺 %d、提示词缺 %d（下限 %d 词）"
              % (len(missing_in_table), len(missing_in_prompt), len(MIN_SYNC_TERMS)))
    if missing_in_table:
        detail += "；表内缺：" + "、".join(missing_in_table)
    if missing_in_prompt:
        detail += "；提示词缺：" + "、".join(missing_in_prompt)
    return (detail, not missing_in_table and not missing_in_prompt)


RULES: tuple[tuple[str, Callable[[RuleContext], tuple[str, bool]]], ...] = (
    ("R1 零绝对路径", rule_no_absolute_paths),
    ("R2 提示词代码同源", rule_prompt_code_sync),
    ("R3 禁自造芽条款", rule_no_self_sprout_clause),
    ("R4 状态根被忽略", rule_state_gitignored),
    ("R5 无凭据字面量", rule_no_secrets),
    ("R6 无 BOM", rule_no_bom),
    ("R7 rc 语义单一来源", rule_exit_codes_single_source),
    ("R8 写盘窗口一致", rule_writes_go_through_store),
    ("R9 同源表不缩表", rule_sync_terms_coverage),
)


def scan(ctx: RuleContext) -> ScanReport:
    """跑全部规则（规则自身抛异常＝该条 FAIL，不让扫描器被拖崩）。"""
    report = ScanReport()
    for name, fn in RULES:
        try:
            detail, passed = fn(ctx)
        except Exception as exc:                        # noqa: BLE001 — 逐条隔离
            detail, passed = "规则自身异常：%r" % exc, False
        report.add(name, detail, passed)
    return report


# ---------------------------------------------------------------- 自检夹具
# 夹具里的「病灶样本」**用拼装方式构造**，不在源码里留下真形态的字面量——
# 否则扫描器（本文件的 R1/R5）会把夹具自己判成病灶，假阳性又变成新的噪音源。
_POSIX_SAMPLE = "C" + ":" + "/" + "Users/" + "someone/data"
_FAKE_TOKEN = "ghp" + "_" + ("a" * 30)
_OLD_CLAUSE_WORDS = ("完成即分岔", "：本拍必须登记至少一个新芽候选（冒不出新芽=本拍白干）")


def _make_tree(root: Path) -> RuleContext:
    """造一个「正常态」最小仓库（正例）。"""
    (root / "src" / "infinigrow" / "engine").mkdir(parents=True, exist_ok=True)
    (root / "src" / "infinigrow" / "core").mkdir(parents=True, exist_ok=True)
    (root / "prompts").mkdir(parents=True, exist_ok=True)
    owners: dict[str, list[str]] = {}
    for term, owner in SYNC_TERMS.items():
        owners.setdefault(owner, []).append(term)
    for owner, terms in owners.items():
        p = root / "src" / "infinigrow" / owner
        p.parent.mkdir(parents=True, exist_ok=True)
        # 夹具必须自己造文件（它要造**病灶态**，含带 BOM 的假文件）——
        # 所以本规则模块自身在 R8 里是**显式例外**（见 rule_writes_go_through_store）。
        p.write_text("".join("# %s\n" % t for t in terms), encoding="utf-8")
    (root / "src" / "infinigrow" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    # 夹具 CLI：退出码走常量（R7 的正例形态）
    (root / "src" / "infinigrow" / "core" / "exit_codes.py").write_text(
        "OK = 0\nBEHIND = 3\n", encoding="utf-8")
    (root / "src" / "infinigrow" / "cli.py").write_text(
        "from .core import exit_codes as rc\n\n\ndef main():\n    return rc.OK\n",
        encoding="utf-8")
    (root / "prompts" / TICK_PROMPT).write_text(
        "本拍题面：按差异动手。\n" + "\n".join(SYNC_TERMS) + "\n", encoding="utf-8")
    (root / "prompts" / ORG_PROMPT).write_text("组织会话：只从差异生芽。\n", encoding="utf-8")
    (root / ".gitignore").write_text("state/\n", encoding="utf-8")
    return RuleContext.from_repo(root)


SELFTEST_CASES = (
    ("R1 正例（无路径）", "rule_no_absolute_paths", None, True),
    ("R1 反例（注入绝对路径）", "rule_no_absolute_paths", "src/infinigrow/__init__.py",
     "p = r'%s'\n" % _POSIX_SAMPLE),
    ("R3 正例（无旧条款）", "rule_no_self_sprout_clause", None, True),
    ("R3 反例（注回旧条款）", "rule_no_self_sprout_clause", "prompts/" + TICK_PROMPT,
     "".join(_OLD_CLAUSE_WORDS) + "\n"),
    ("R5 正例（无凭据）", "rule_no_secrets", None, True),
    ("R5 反例（注入 token）", "rule_no_secrets", "src/infinigrow/__init__.py",
     'TOKEN = "%s"\n' % _FAKE_TOKEN),
    ("R2 正例（同源齐）", "rule_prompt_code_sync", None, True),
    ("R2 反例（代码侧删关键词）", "rule_prompt_code_sync",
     "src/infinigrow/engine/model.py", "# 空文件\n"),
    ("R4 正例（状态根已忽略）", "rule_state_gitignored", None, True),
    ("R4 反例（清空 .gitignore）", "rule_state_gitignored", ".gitignore", ""),
    ("R6 正例（无 BOM）", "rule_no_bom", None, True),
    ("R6 反例（写入带 BOM 文件）", "rule_no_bom", "src/infinigrow/__init__.py",
     "\ufeffx = 1\n"),
    # v2.1 新增三条规则的正/反用例（T8 验收：每条规则都要能**真的红**）
    ("R7 正例（退出码走常量）", "rule_exit_codes_single_source", None, True),
    ("R7 反例（cli 写死裸整数）", "rule_exit_codes_single_source",
     "src/infinigrow/cli.py", "def main():\n    return 5\n"),
    ("R8 正例（写盘只在 store）", "rule_writes_go_through_store", None, True),
    ("R8 反例（引擎里直接写盘）", "rule_writes_go_through_store",
     "src/infinigrow/engine/model.py", "def leak(p):\n    p.write_text('x')\n"),
    ("R9 正例（同源表覆盖齐）", "rule_sync_terms_coverage", None, True),
    ("R9 反例（提示词丢机制词）", "rule_sync_terms_coverage",
     "prompts/" + TICK_PROMPT, "# 只剩一个词\n差异\n"),
)


def selftest(tmp_root: Path) -> ScanReport:
    """规则正/反用例自检：每条规则在「正常态」应 PASS、「病灶态」应 FAIL。

    T7 验收判据就在这里：**故意删一处定义 → R2 报错**（见「R2 反例」用例）。
    """
    fn_map = dict(RULES)
    fn_map.update({fn.__name__: fn for _, fn in RULES})   # 用例可按「规则名」或「函数名」引用
    report = ScanReport()
    for label, fn_name, rel_path, injection in SELFTEST_CASES:
        root = Path(tmp_root) / ("case-" + re.sub(r"\W+", "_", label))
        ctx = _make_tree(root)
        if rel_path and injection is not None:
            target = root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if label.startswith("R3 反例") else "w"
            # 注入内容以 U+FEFF 开头＝要求**带 BOM 落盘**（R6 的反例只能这么造）
            encoding = "utf-8-sig" if injection.startswith("\ufeff") else "utf-8"
            with open(target, mode, encoding=encoding) as fh:
                fh.write(injection)
        _, passed = fn_map[fn_name](ctx)
        expect_pass = "正例" in label
        good = passed == expect_pass
        report.add("自检 %s" % label,
                   "规则%s，期望%s" % ("PASS" if passed else "FAIL",
                                      "PASS" if expect_pass else "FAIL"), good)
    by_fn = {fn.__name__: name for name, fn in RULES}
    covered = {by_fn.get(n, n) for _, n, _, _ in SELFTEST_CASES}   # 用例可写规则名或函数名
    missing = [name for name, _ in RULES if name not in covered]
    if missing:
        report.add("自检覆盖", "规则无自检用例：%s" % "、".join(missing), False)
    else:
        report.add("自检覆盖", "全部 %d 条规则均已有用例" % len(RULES), True)
    return report
