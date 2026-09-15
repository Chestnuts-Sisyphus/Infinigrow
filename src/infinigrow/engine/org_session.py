# -*- coding: utf-8 -*-
"""组织会话运行体：把「芽由组织会话登记」从判据变成**真有东西在跑**（T3/G3 的实现层）。

上一代的病：语义判断段的判据与提示词都写好了，**没有调度入口**——诊断产出后没人回灌，
就地过期（v2 自查又发现同型病：判据写好了但拍循环从不查它，见 `engine/org_trigger.py`）。
本模块补的是那层「运行体」，链路如下：

```
    输入（B猜 ＋ 留痕 ＋ W回）           ← 全部读账本/留痕文件，不靠模型自述
        ↓  prompts/org-session.md 原文 ＋ 本拍输入块（stdin）
    执行者通道（engine/executor.py）      ← 与拍同一条通道：不给执行者就整段不跑
        ↓  stdout（JSON 契约，见提示词 §8）
    四类差异（找差异）＋ 规划预测（写承诺）
        ↓  差异账（`source=org-session`）＋ 组织发现账（可被打脸）
    芽（走域饱和闸 → 队列）                ← 生芽权在组织会话；执行会话依旧不能自产芽
        ↓
    兑现判定（后续各拍的对账来判：同样的 (对象, 维度) 恢复一致＝消解）
```

三条不许含糊的地方：

1. **无指针不成芽**：发现缺证据指针 → 进「待补指针」（照旧入账，`spawns=False`），不立芽。
2. **输出不可解析＝这一拍没产出**：记账写明（`rc` 与 `parse_error`），**不许**从自由文本里
   猜差异（猜出来的差异无法对账，等于把噪声写进历史）。
3. **判断进账可被打脸**：发现行带拍号与指针落到 `state/org-findings.jsonl`；
   `finding_status()` 用后续差异账现算每条发现的结局（待验／被证实／被推翻）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Sequence

from ..core.config import Settings
from ..core.encoding import read_text
from ..core.paths import StateLayout
from ..ledger.store import append_jsonl, read_jsonl
from . import executor as exec_mod
from . import sprout_sources
from . import subject as subject_mod
from .domain_saturation import DomainState, domain_key, value_at_freeze
from .model import Diff, DiffKind, Prediction
from .org_trigger import record_org_session

#: 提示词文件（机制正本的一部分；缺文件＝组织会话无法建提示词 → 失败必须可见）
ORG_PROMPT_FILE = "org-session.md"

#: 输入块的规模上限（一拍要**有界**：账本可以很长，提示词不能无界）
ORG_INPUT_MAX_CHARS = 8000
ORG_TRACE_MAX_CHARS = 4000
ORG_DIFF_ROWS = 12
#: 主体内容摘录的上限（没有它，组织会话只能靠文件名猜主体要什么——
#: 实测它因此凭空发明了一个「要点名建 notes.md」的提议，而主体声明里写的是 journal/）
SUBJECT_CONTENT_CHARS = 1200
SUBJECT_CONTENT_TOTAL = 3000

#: 组织会话发现账
FINDINGS_LEDGER = "org-findings.jsonl"

#: 发现行里的来源标记（差异账里靠它区分「机械对账」与「语义判断」）
SOURCE = "org-session"


@dataclass
class OrgFinding:
    """一条语义发现（＝一个差异点，判据与机械对账同构，只是来源不同）。"""

    kind: DiffKind
    obj: str
    dimension: str
    expected: str
    actual: str
    pointer: str

    @property
    def spawns(self) -> bool:
        return bool(self.pointer)

    def as_diff(self, tick: int) -> Diff:
        return Diff(kind=self.kind, obj=self.obj, dimension=self.dimension,
                    expected=self.expected, actual=self.actual,
                    evidence=self.pointer, tick=tick)

    def as_record(self, tick: int) -> dict:
        return {"tick": tick, "source": SOURCE, "kind": self.kind.value, "obj": self.obj,
                "dimension": self.dimension, "expected": self.expected,
                "actual": self.actual, "pointer": self.pointer,
                "spawns": self.spawns}


@dataclass
class OrgOutput:
    """执行者输出的结构化结果（解析成功与否**都要**能说清）。"""

    findings: list[OrgFinding] = field(default_factory=list)
    predictions: list[Prediction] = field(default_factory=list)
    notes: str = ""
    parse_error: str = ""


@dataclass
class OrgRun:
    """一次组织会话运行的全部可查事实。"""

    ran: bool = False
    tick: int = 0
    executor: Optional[exec_mod.ExecutorRun] = None
    findings: list[OrgFinding] = field(default_factory=list)
    predictions: list[Prediction] = field(default_factory=list)
    sprouts: list[str] = field(default_factory=list)
    absorbed: list[str] = field(default_factory=list)
    parse_error: str = ""
    notes: list[str] = field(default_factory=list)
    trace: Optional[Path] = None

    def summary(self) -> str:
        if not self.ran:
            return "未跑（无执行者）"
        if self.parse_error:
            return "跑了但输出不可解析：%s" % self.parse_error
        return ("跑了：发现 %d 条（立芽 %d、域饱和吸收 %d）、规划预测 %d 条"
                % (len(self.findings), len(self.sprouts), len(self.absorbed),
                   len(self.predictions)))


# ------------------------------------------------------------------ 提示词
def _render_subject(subject_root: Path) -> str:
    from .subject import SUBJECT_PREFIX, subject_files, subject_leaf
    files = subject_files(subject_root)
    lines = ["主体根名：%s（存在=%s）" % (subject_leaf(subject_root),
                                     subject_root.is_dir())]
    if files:
        lines.append("主体文件（最多列 20 个）：")
        lines += ["  - %s（%d 字节）" % (f.name, f.bytes) for f in files]
    else:
        lines.append("主体文件：（空）")
    lines.append("")
    lines.append("### 主体里现有文件的内容（有界摘录；判断要依据它，不要凭文件名猜）")
    lines.append("")
    if not files:
        lines.append("（空：主体里只有目录本身）")
        return "\n".join(lines)
    used = 0
    for item in files[:3]:                       # 最多读 3 个文件的内容
        path = subject_root / item.name
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        body = text[:SUBJECT_CONTENT_CHARS]
        if len(text) > SUBJECT_CONTENT_CHARS:
            body += "\n……（更长，已截断）"
        block = "#### %s%s（%d 字节）\n```text\n%s\n```" % (
            SUBJECT_PREFIX, item.name, item.bytes, body)
        if used + len(block) > SUBJECT_CONTENT_TOTAL:
            lines.append("（其余文件内容略）")
            break
        used += len(block)
        lines.append(block)
    return "\n".join(lines)


def _render_recent_diffs(records: Sequence[dict]) -> str:
    rows = records[-ORG_DIFF_ROWS:]
    if not rows:
        return "（差异账为空：这是第一次对账）"
    out = []
    for rec in rows:
        out.append("  - 拍%s｜%s｜%s｜%s｜预期=%s｜实际=%s｜指针=%s"
                   % (rec.get("tick"), rec.get("kind"), rec.get("obj"),
                      rec.get("dimension"), rec.get("expected"), rec.get("actual"),
                      rec.get("evidence") or "（缺）"))
    return "\n".join(out)


def _last_trace(layout: StateLayout) -> str:
    traces = sorted(layout.traces_dir.glob("tick-*.md"))
    if not traces:
        return "（尚无执行会话留痕）"
    text = read_text(traces[-1])
    if len(text) > ORG_TRACE_MAX_CHARS:
        text = text[:ORG_TRACE_MAX_CHARS] + "\n……（留痕过长，已截断）"
    return text


def build_org_prompt(settings: Settings, layout: StateLayout, tick: int,
                     subject_root: Path, queue_summary: Optional[dict] = None) -> str:
    """组织会话提示词＝机制提示词原文 ＋ 本拍输入块（B猜/留痕/W回 都在里面）。

    缺提示词文件＝**响亮失败**（不悄悄用内置兜底文本：那会让「机制改了但提示词没改」
    这类漂移永远发现不了——那正是上一代的老病）。
    """
    prompt_path = settings.prompts_path() / ORG_PROMPT_FILE
    if not prompt_path.is_file():
        raise FileNotFoundError("组织会话提示词缺失：%s" % ORG_PROMPT_FILE)
    base = read_text(prompt_path)
    diffs = read_jsonl(layout.diff_ledger)
    pending = [d for d in diffs if not d.get("evidence") and d.get("spawns") is False]
    block = [
        "",
        "---",
        "",
        "## 本拍输入（机器填，勿改）",
        "",
        "- 拍号：%d" % tick,
        "- 状态根名：%s" % layout.root.name,
        "- 队列：%s" % json.dumps(queue_summary or {}, ensure_ascii=False),
        "- 待补指针条目数：%d" % len(pending),
        "",
        "### 主体（W回：现实侧）",
        "",
        _render_subject(subject_root),
        "",
        "### 最近差异账（W回：现实对上承诺的回答）",
        "",
        _render_recent_diffs(diffs),
        "",
        "### 上一拍执行会话留痕（含它的 B猜）",
        "",
        "```text",
        _last_trace(layout),
        "```",
        "",
        "### 提醒",
        "",
        "- 你输出的 `predictions` 会**覆盖**本拍机械默认预测（默认是「不变」）——",
        "  写了它，本拍对账就按你的预期承诺判对错（兑现账判的就是这一条）。",
        "- 主体对象的命名约定：`%s<相对路径>`。" % "主体/",
        "- 输出严格按 §8 的 JSON 契约；解析不了＝本拍无产出（不会从正文里猜）。",
    ]
    text = base + "\n".join(block)
    if len(text) > ORG_INPUT_MAX_CHARS + len(base):
        text = text[:ORG_INPUT_MAX_CHARS + len(base)] + "\n（输入过长，已截断）\n"
    return text


# ------------------------------------------------------------------ 解析
def _extract_json(text: str) -> Optional[dict]:
    """从输出里取出 JSON 对象：容忍 ```json 围栏与前后废话（**不猜**结构，只取一个对象）。"""
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(line for line in lines if not line.strip().startswith("```")).strip()
    start, end = raw.find("{"), raw.rfind("}")
    while start != -1 and end > start:
        try:
            data = json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            end = raw.rfind("}", 0, end)
            continue
        return data if isinstance(data, dict) else None
    return None


def parse_org_output(text: str, tick: int,
                     allowed_objs: Optional[set] = None) -> OrgOutput:
    """解析组织会话输出 → 发现 ＋ 规划预测。解析失败**不猜**（返回 parse_error）。

    对象名**机械闸**（T5/A11）：给了 `allowed_objs`（本拍主体观测集）时，
    findings 的对象必须在该清单里（描述现实的发现不许发明对象名）；
    predictions 的对象可在清单里，也可以是**主体内合法新相对路径**（提议创建）。
    不合规的条目**丢弃并记 parse_error**（不产芽）；不产芽比产错芽诚实。
    """
    data = _extract_json(text)
    if data is None:
        return OrgOutput(parse_error="输出里没有可解析的 JSON 对象")
    out = OrgOutput(notes=str(data.get("notes") or ""))
    kinds = {k.value: k for k in DiffKind}
    for i, rec in enumerate(data.get("findings") or [], 1):
        if not isinstance(rec, dict):
            continue
        kind = kinds.get(str(rec.get("kind") or "").strip())
        obj = str(rec.get("obj") or "").strip()
        dimension = str(rec.get("dimension") or "").strip()
        if kind is None or not obj or not dimension:
            out.parse_error = ("第 %d 条发现不合格（kind/obj/dimension 三者缺一）：%s"
                               % (i, json.dumps(rec, ensure_ascii=False)[:120]))
            continue
        if allowed_objs is not None:
            ok, why = subject_mod.valid_subject_object(obj, allowed_objs)
            if not ok:
                out.parse_error = ("第 %d 条发现对象名被拒（%s）：%s"
                                   % (i, why, json.dumps(rec, ensure_ascii=False)[:120]))
                continue
        out.findings.append(OrgFinding(
            kind=kind, obj=obj, dimension=dimension,
            expected=str(rec.get("expected") or "（未说）"),
            actual=str(rec.get("actual") or "（未说）"),
            pointer=str(rec.get("pointer") or rec.get("evidence") or "").strip()))
    for j, rec in enumerate(data.get("predictions") or [], 1):
        if not isinstance(rec, dict):
            continue
        obj = str(rec.get("obj") or "").strip()
        dimension = str(rec.get("dimension") or "").strip()
        if not obj or not dimension:
            continue
        if allowed_objs is not None:
            ok, why = subject_mod.valid_subject_object(obj, allowed_objs,
                                                       for_proposal=True)
            if not ok:
                out.parse_error = ("第 %d 条预测对象名被拒（%s）：%s"
                                   % (j, why, json.dumps(rec, ensure_ascii=False)[:120]))
                continue
        out.predictions.append(Prediction(
            obj=obj, dimension=dimension, expected=str(rec.get("expected") or ""),
            tick=tick,
            evidence=str(rec.get("pointer") or rec.get("evidence") or "").strip()))
    return out


# ------------------------------------------------------------------ 运行
def run_org_session(*, settings: Settings, layout: StateLayout, tick: int,
                    subject_root: Path, queue, domains: DomainState,
                    runner: Callable[[str], exec_mod.ExecutorRun]) -> OrgRun:
    """跑一次组织会话：建提示词 → 过执行者通道 → 解析 → 立芽 → 记账。

    `runner` 由调用方绑定用途（`kind=executor.KIND_ORG`）——命令模式与进程内可调用模式
    走同一条路，账本与留痕的形态完全一致。
    """
    run = OrgRun(tick=tick)
    queue_summary = queue.summary() if queue is not None else {}
    try:
        prompt = build_org_prompt(settings, layout, tick, subject_root, queue_summary)
    except FileNotFoundError as exc:
        run.ran = True
        run.parse_error = str(exc)
        run.notes.append("提示词缺失，本拍未调用执行者（失败可见）")
        record_org_session(layout, tick, "提示词缺失：%s" % exc)
        return run

    call = runner(prompt)
    run.ran = True
    run.executor = call
    exec_mod.record_executor_run(layout, call)
    run.trace = exec_mod.write_trace(layout, call, prompt, subject_root)

    if not call.ok:
        run.parse_error = "执行者未成功（rc=%d%s）" % (call.rc, "，超时" if call.timed_out else "")
        record_org_session(layout, tick, "失败：rc=%d %s" % (call.rc, call.note))
        return run

    parsed = parse_org_output(call.output, tick,
                              allowed_objs={k[0] for k
                                            in subject_mod.subject_readings(subject_root)})
    run.findings = parsed.findings
    run.predictions = parsed.predictions
    run.parse_error = parsed.parse_error

    # 发现 → 差异账（**照旧入账**：无指针的也记，只是不立芽）＋ 组织发现账（可被打脸）
    diffs: list[Diff] = []
    for finding in parsed.findings:
        diff = finding.as_diff(tick)
        record = diff.as_record()
        record["source"] = SOURCE
        record["pending_pointer"] = not finding.spawns
        append_jsonl(layout.diff_ledger, record, layout.root)
        append_jsonl(layout.root / FINDINGS_LEDGER, finding.as_record(tick), layout.root)
        if not finding.spawns:
            run.notes.append("无指针发现（进待补指针，不立芽）：%s" % finding.obj)
        diffs.append(diff)

    # 域饱和闸 → 立芽（生芽权在组织会话；执行会话依旧不能自产芽）
    if queue is not None and diffs:
        exhausted_ids = {s.id for s in queue.sprouts
                         if not s.long_task and s.leads >= queue.lead_limit}
        gate = domains.gate(diffs, tick, exhausted_sprout_ids=exhausted_ids)
        run.absorbed = ["%s|%s" % domain_key(d.obj, d.dimension) for d in gate.absorbed]
        for sprout in sprout_sources.from_diffs(gate.kept, tick,
                                               start_seq=len(queue.sprouts) + 1):
            action, _evicted = queue.add(sprout)
            domains.claim(sprout.obj, sprout.dimension, sprout.id,
                          value_at_freeze=value_at_freeze(gate.kept, sprout.obj,
                                                          sprout.dimension),
                          tick=tick, pointer=sprout.pointer)
            run.sprouts.append("%s(%s)" % (sprout.id, action))

    note = run.summary()
    record_org_session(layout, tick, note)          # org-llm.jsonl：带拍号与机械时间戳
    run.notes.append(note)
    return run


# ------------------------------------------------------------------ 可被打脸
def finding_status(layout: StateLayout) -> list[dict]:
    """现算每条组织发现的结局：`待验`（之后没再对账到）／`被证实`（同键判对）／`被推翻`。

    这就是「语义判断进账可被打脸」的机械形态：**判断不由引擎自述**，
    而由后来的现实对账（差异账里同一 (对象, 维度) 的下一行）定。
    """
    findings = read_jsonl(layout.root / FINDINGS_LEDGER)
    diffs = read_jsonl(layout.diff_ledger)
    out = []
    for rec in findings:
        key = (rec.get("obj"), rec.get("dimension"))
        tick = int(rec.get("tick") or 0)
        status = "待验"
        for diff in diffs:
            if (diff.get("obj"), diff.get("dimension")) != key:
                continue
            if int(diff.get("tick") or 0) <= tick:
                continue
            status = "被证实" if diff.get("kind") == DiffKind.OK.value else "被推翻"
            break
        out.append({**rec, "status": status})
    return out
