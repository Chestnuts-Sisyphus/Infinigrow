# 编号登记表（Marker registry）

> 编号是给「一条命题」起的机械锚。此前**没有登记表**：文档里写一句「（M7/N45）」，
> 读者既查不到这条命题是什么、也查不到它在哪儿执法、更不知道它是否还生效。
> 本表补这个洞——**引用即登记**。
>
> 判据（`tests/test_docs_bilingual.py`）：
> ① `docs/` 与 `docs/zh/` 里出现的每个编号，都必须在本表（两册）里有一行；
> ② 四个格（编号｜命题｜执法落点｜状态）不许留空；
> ③ 仓内已无引用的编号，状态必须如实写「孤儿」，**不许伪装成生效**。
>
> 落点＝该编号在仓内被引用/执法的锚（文件级；行号会漂，所以不写行号）。
> 状态取值：`生效`｜`已清（见 superseded Sx）`｜`未定（待拍板）`｜`歧义·已注明`｜`孤儿·仓内无引用`。

---

## 一、登记表（按编号排序）

| 编号 | 命题 | 执法落点 | 状态 |
|---|---|---|---|
| A1 | 重提不改问题的年龄：合并后的芽继承旧芽的出生拍 | `src/infinigrow/engine/sprout_queue.py`（`add` 的 replaced 分支）＋ `tests/test_sprout_queue.py` | 生效 |
| A2 | 判读边与可用性边靠「留痕点名」进入对账 | `src/infinigrow/engine/tick.py` ＋ `tests/test_read_edge.py` | 生效 |
| A3 | 固化边（`cap*`）的应用面接「应用证据件」后可对账 | `src/infinigrow/engine/tick.py` ＋ `tests/test_redemption_report.py` | 生效 |
| A5 | 冻结区每 `frozen_review_every` 拍重看一次 | `src/infinigrow/engine/sprout_queue.py`（`review_frozen`）＋ `tests/test_tick.py` | 生效 |
| A7 | 「应用面」是语义维度：读不到≠打脸，单独列出不进分母 | `src/infinigrow/engine/reconcile.py`（`redemption_report`）＋ `tests/test_rotation.py` | 生效 |
| A8 | `journal/` 新文件命名规则定死：`<创建拍4位>-<YYYYMMDD>.md` | `src/infinigrow/engine/tick.py` ＋ `tests/test_subject.py` | 生效 |
| A10 | 运行时文案是中文；英文 CLI 模式未实现（语言边界） | `docs/zh/running.md` ＋ `src/infinigrow/engine/executor.py`（用量行口径） | 生效（决定；实现待拍板） |
| A15 | 一键总览与暂停/恢复：`status`／`pause`／`resume` | `src/infinigrow/cli.py` ＋ `tests/test_cli.py` | 生效 |
| A17 | 执行者超时 × 每拍调用次数必须明显小于计划任务时限 | `tools/scheduled_task.ps1`（`-ExecutionTimeLimit`）＋ `tests/test_config_single_source.py`（超时真杀） | 生效（关系成文；乘积闸见 K12 行） |
| B2 | 打脸行按**原因**三分归因，不许只报一个数 | `src/infinigrow/engine/reconcile.py`（`redemption_attribution`）＋ `tests/test_redemption_report.py` | 生效 |
| B3 | 归因按「领做时芽龄」机械分桶，芽龄取自芽 ID 拍号段 | 同上（`sprout_created_tick`）＋ `tests/test_rules.py` | 生效（芽龄桶＝机械代理·待证） |
| G1 | 轮转搬走的内容**真的**离开生长面（归档不进观测面） | `src/infinigrow/ledger/rotation.py`（`rotate_journal`）＋ `tests/test_subject.py` | 生效 |
| G2 | 证据件缺失分三类归因，不许混成一桶 | `src/infinigrow/engine/sprout_sources.py` ＋ `tests/test_tick.py` | 生效 |
| G3 | 组织会话要有运行体；命名闸在 `valid_subject_object` 的提议分支执法 | `src/infinigrow/engine/subject.py` ＋ `tests/test_subject.py` | 生效 |
| G5 | 容量轮转跑不到重问窗前面（归档必然已跨过窗口） | `src/infinigrow/engine/subject.py` 观测面读数 ＋ `tests/test_mechanism_docs.py` | 生效（副本实测） |
| G6 | 兑现率＝现算，且**诚实呈现**（无样本说无样本） | `src/infinigrow/engine/tick.py` ＋ `tests/test_redemption_report.py` | 生效 |
| G7 | **一号两义**：① ETA 剩下的部分（能力库待问账）②轮转（账本只增、历史搬进归档） | ①`docs/zh/mechanism.md` §5 读数节 ②`src/infinigrow/ledger/rotation.py` | 歧义·已注明（两处含义分开引用，新引用须带语境） |
| G9 | 冻结不是永久封存：冻结满 `frozen_requestion_ticks` 可重问 | `src/infinigrow/engine/sprout_queue.py`（`known_objects`）＋ `tests/test_sprout_queue.py` | 生效 |
| K1 | 域饱和解冻判据③④补上：有穷枚举维度不再死锁 | `src/infinigrow/engine/tick.py` ＋ `tests/test_domain_saturation.py` | 生效 |
| K2 | 观测名额按 mtime 取最新 N＝20，自报数字必须如实 | `src/infinigrow/engine/subject.py` ＋ `tests/test_subject.py` | 生效 |
| K7 | 提议方猜不到未来的创建拍 → 不许在题面里点名新文件 | `src/infinigrow/engine/tick.py` ＋ `tests/test_tick.py` | 生效 |
| K12 | 别把调度窗口烧满：留 ≥1/3 余量（经验法则） | `tools/scheduled_task.ps1`（时限）＋ `docs/zh/running.md` 接法节 | 生效（关系；机械闸由 M10 落） |
| K14 | 扫现实的对比窗口＝「自上次组织会话以来」 | `src/infinigrow/engine/tick.py` ＋ `tests/test_org_session.py` | 生效 |
| K15 | 取题排序键是否要改（连领平局后的次序）**未定** | `src/infinigrow/engine/sprout_queue.py`（`order_key` 注释）＋ `tests/test_sprout_queue.py` | 未定（待拍板；本轮不动排序键） |
| K16 | 曾登记为「预留」的 `long_task` 豁免 | `docs/superseded.md` S9 ＋ `tests/test_sprout_queue.py` | 已清（随 S9 关闭，不重开） |
| M3 | 「留痕命中＝已用」与判读边共用同一段输出与同一判据 | `src/infinigrow/engine/tick.py` ＋ `tests/test_tick.py` | 生效 |
| M4 | 重问判据锚在 `frozen_tick`（被挤出那一拍），旧行回退 `created_tick` | `src/infinigrow/ledger/rotation.py` ＋ `tests/test_sprout_queue.py` | 生效 |
| M5 | 冻结区有容量判据：超 `frozen_cap` 移最旧的进归档 | `src/infinigrow/ledger/rotation.py`（`rotate_frozen_sprouts`）＋ `tests/test_rotation.py` | 生效 |
| M6 | 目录也是观测对象：名额按名字升序前 10（`SUBJECT_DIR_LIMIT`） | `src/infinigrow/engine/subject.py` ＋ `tests/test_subject.py` | 生效 |
| M7 | 定键补观测：预测里出现过的键被挤出边界时补读 | `src/infinigrow/engine/tick.py`（`augment_observations`）＋ `tests/test_subject.py` | 生效 |
| M10 | 领做与兑现的分桶归因做成可复跑的命令形态 | `src/infinigrow/engine/reconcile.py` ＋ `tests/test_redemption_report.py` | 生效 |
| N41 | 死锁案例：只养一根未完成芽的域被穷举维度堵死 | `src/infinigrow/engine/tick.py` ＋ `tests/test_domain_saturation.py` | 生效（由 K1 修） |
| N42 | 「文件数」维度始终是真实总数，不受名额上限影响 | `src/infinigrow/engine/subject.py` ＋ `tests/test_subject.py` | 生效 |
| N43 | 子目录也是对象，结尾 `/` 是判据；差额预期写 `+N` | `src/infinigrow/engine/tick.py` ＋ `tests/test_tick.py` | 生效 |
| N45 | 补观测只针对预测里出现过的键，不扩大观测面 | `src/infinigrow/engine/tick.py` ＋ `tests/test_subject.py` | 生效 |
| N48 | 芽源三类的判据输入必须是真读数（去重含冻结区） | `src/infinigrow/rules/static_scan.py` ＋ `tests/test_tick.py` | 生效 |
| N48-1 | `last_used_tick` 必须有真实更新方（不能创建时写死） | `src/infinigrow/engine/tick.py` ＋ `tests/test_read_edge.py` | 生效 |
| N48-2 | 「本拍用过」读留痕输出段（旧实现读 `note`，19 个字符恒不生效） | `src/infinigrow/engine/tick.py`（`recent_trace_output`）＋ `tests/test_config_single_source.py` | 生效 |
| N48-3 | 提醒必须有出口：只修去重＝把这条渠道断电 | `src/infinigrow/engine/sprout_sources.py` ＋ `tests/test_tick.py` | 生效 |
| N48-4 | 冻结区容量判据与轮转同纪律：只移动不删 | `src/infinigrow/ledger/rotation.py` ＋ `tests/test_rotation.py` | 生效 |
| N48-5 | 目录名额按名字升序取前 10，判据写死 | `src/infinigrow/engine/subject.py` ＋ `tests/test_subject.py` | 生效 |
| N55 | 「上一拍快照 vs 本拍清单」之间什么也没发生 → 恒为空 | `src/infinigrow/engine/tick.py` ＋ `tests/test_org_session.py` | 生效（由 K14 修） |
| N56 | 单位诚实：判据④数的是**账本行数**不是拍数 | `src/infinigrow/engine/org_trigger.py` ＋ `tests/test_org_trigger.py` | 生效 |
| N58 | 触发判据与实测节奏的关系（④只认「上一拍安静」） | `src/infinigrow/engine/tick.py` ＋ `tests/test_org_session.py` | 生效（**无仓内定义表**，语义见 mechanism §2.3） |
| Q1 | 队列纪律问题：被反复重提的问题不该被刷成新芽 | `docs/zh/mechanism.md` 队列节 ＋ `tests/test_mechanism_docs.py` | 生效 |
| Q2 | 固化边占取题位是刻意的：要能判它有没有真被应用 | `src/infinigrow/engine/tick.py` ＋ `tests/test_redemption_report.py` | 生效 |
| Q6 | 兑现分桶归因做成可复跑的函数形态 | `src/infinigrow/engine/reconcile.py` ＋ `tests/test_redemption_report.py` | 生效 |
| Q13 | 公开面的语言边界：Release 说明只做英文 | `docs/release-notes-*.md` ＋ `tests/test_docs_bilingual.py`（`ENGLISH_ONLY`） | 生效 |
| R1 | 源码零绝对路径 | `src/infinigrow/rules/static_scan.py` ＋ `tests/test_status_gates.py` | 生效 |
| R2 | 提示词↔代码同源（双向） | `src/infinigrow/rules/static_scan.py` ＋ `tests/test_status_gates.py` | 生效 |
| R3 | 提示词里不许出现自造芽条款 | `src/infinigrow/rules/static_scan.py` ＋ `tests/test_rules.py` | 生效 |
| R5 | 无凭据字面量 | `src/infinigrow/rules/static_scan.py` ＋ `tests/test_status_gates.py` | 生效 |
| R7 | 退出码单一来源（CLI 不许裸整数） | `src/infinigrow/rules/static_scan.py` ＋ `src/infinigrow/core/exit_codes.py` | 生效 |
| R8 | 写盘窗口一致（只有 `ledger/store` 触盘） | `src/infinigrow/rules/static_scan.py` ＋ `tests/test_status_gates.py` | 生效 |
| R9 | 同源表不缩表（覆盖下限） | `src/infinigrow/rules/static_scan.py` ＋ `tools/check_prompt_code_sync.py` | 生效 |
| R10 | 计划任务走隐藏启动器（vbs 窗口样式 0） | `src/infinigrow/rules/static_scan.py` ＋ `tests/test_scheduler_artifacts.py` | 生效 |
| S1 | 「每拍必须登记一颗新芽候选」 | `docs/superseded.md` S1 ＋ `src/infinigrow/engine/tick.py`（现行零差异零芽） | 已清 |
| S2 | 摘顶 / apex 裁剪生长方向 | `docs/superseded.md` S2 | 已清 |
| S3 | 三档 / 盲考阅卷（给产出打档） | `docs/superseded.md` S3 | 已清 |
| S4 | 生长素四机制 / 四集合 / 节点判据 | `docs/superseded.md` S4 | 已清 |
| S5 | 双重时间口径（模型留痕时间戳当判据） | `docs/superseded.md` S5 ＋ 心跳 `tick_status.json` | 已清 |
| S6 | 自评式「能力卡/原理卡」台账 | `docs/superseded.md` S6 | 已清 |
| S7 | 宿主耦合的状态根 | `docs/superseded.md` S7 ＋ `src/infinigrow/core/paths.py` | 已清 |
| S8 | 单体巨石 ＋ 内嵌夹具 | `docs/superseded.md` S8 ＋ 六层包结构 | 已清 |
| S9 | `long_task` 豁免连领上限 | `src/infinigrow/engine/sprout_queue.py`（`eligible`）＋ `tests/test_sprout_queue.py` | 已清 |
| S10 | 五个从未被调用的定义按死码清除 | `docs/superseded.md` S10 ＋ 删除处 `core/paths.py`／`engine/sprout_queue.py`／`ledger/rotation.py` | 已清 |
| T3 | 判据与提示词写好了还得有人调用 | `src/infinigrow/engine/tick.py` ＋ `tests/test_tick.py` | 生效 |
| T4 | 冻结区重看节奏（与重问分工不同） | `src/infinigrow/engine/sprout_queue.py` ＋ `tests/test_tick.py` | 生效 |
| T6 | 轮转与容量：账本只增不减，历史由轮转搬进归档 | `src/infinigrow/ledger/rotation.py` ＋ `tests/test_rotation.py` | 生效 |
| T7 | 域饱和：同一「对象域 × 标准可验证量」只养一根未完成芽 | `src/infinigrow/engine/domain_saturation.py` ＋ `tests/test_rules.py` | 生效 |
| T8 | 调度与看护的对外入口（总览/暂停/恢复） | `src/infinigrow/cli.py` ＋ `tests/test_cli.py` | 生效 |
| T11 | 兑现率的诚实口径（无样本≠0≠差） | `src/infinigrow/engine/tick.py` ＋ `tests/test_tick.py` | 生效 |
| H8 | 早期编号：Release 说明只做英文这一语言边界决定 | `tests/test_docs_bilingual.py`（`ENGLISH_ONLY` 注释）——命题已并入 **Q13/A10** | 孤儿·仓内无定义处（引用已在，定义仅此一行） |
| O5 | 命题**不可考**：全仓（含 `.qoder/handoff/`）检索 0 命中 | `tools/check_markers.py` 的清点输出（脚本自身的运行结果即证据） | 孤儿·仓内无引用（不再作为依据引用它） |

---

## 二、系列前缀的含义**未成文**

诚实记录一件实测到的事：`docs`/`src`/`tests` 里出现的编号前缀实测有 **K、A、N、Q、T、M、G、B、S、R、H、O、C、U**
（清点命令见末节，2026-09-19 现跑）。它们来自历次会话的口头编号习惯，**本仓库里没有一份「前缀＝什么系列」的权威定义**——
所以本表只登记**具体编号**（命题从首现处摘，不改写、不补写），不假装知道每个前缀的命名规则。
要把系列语义补全，属编号体系的**待拍板项**（见 `docs/superseded.md` 之外的呈报清单）。

---

## 三、复跑本表的清点

```bash
python tools/check_markers.py           # 打印 docs 引用编号 与 本表登记行的差集
python -m pytest tests/test_docs_bilingual.py -q   # 引用即登记（缺行即红）
```

`tools/check_markers.py` 与用例用的是同一套正则与同一套判据；改编号的人跑第一条就能看见差在哪。
