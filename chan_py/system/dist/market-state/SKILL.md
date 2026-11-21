---
name: market-state
description: Use when the user asks what the market or a sector looks like right now, or asks for a comparison or an event calendar under the 全景客观金融分析 framework — e.g. "现在市场什么状态", "把六环拉一遍", "半导体板块怎么样", "M2 减 M1 的剪刀差", "未来 30 天有什么数据发布". Produces evidence-line state descriptions with empty rings marked 不可读, and never turns them into judgments. Loading it grants no permission to modify files outside its own directory and the user's chosen output directory.
---

# market-state · 市场状态

> **规则版本 V2.33.0**（与 `docs/` 同步；改规则须同时升此版本，并在 CHANGELOG 记一条）

把当前数据压缩成 **六环 + 证据行** 的客观状态描述。不做判断、不给建议、不预测、不解释涨跌原因。

规则与样例全部在本目录内（`references/`），自包含，不依赖任何外部仓库。

## 先读什么（按需，不必全读）

| 文件 | 什么时候读 |
|---|---|
| `references/data-layer.md` | **每次都要**：落盘数据的目录、指标、档位、as-of 与标注规则 |
| `references/framework.md` | 不确定某环放什么、为什么排这个位置时 |
| `references/reading-rules.md` | **几乎每次都要**：生成状态词、判断能不能说、怎么写"边界" |
| `references/anchors.md` | 涉及比价（比值 / 差值 / 排名 / 分位）时 |
| `references/events.md` | 要做事件日历或事件分支时（`include_events=true`） |
| `references/registry.json` | 校验指标 id、attribute / transform / 量纲时 |
| `references/schema/*.json` | 落盘记录前 |
| `references/render.md` | 要出图时（默认只出六环覆盖条；折线按需） |
| `references/examples/` | 需要照格式写时（含真实数据样例 `render-01.md`：带覆盖条的真实输出） |
| `check.py` | 输出前自检（记录与页面两种模式） |


## 数据来源（严格按此顺序，不得跳级）

1. **落盘事实（首选）**：工作区若有 `data/facts/`，先取其记录——
   - 最省事：`python scripts/state.py --policy traceable`（会直接产出六环证据行 + 溯源表）；
   - 或直接读 `data/facts/<数据期>/<indicator_id>.json`（字段见 `references/schema/fact.schema.json`）。
   **以落盘记录为准**；其 `data_period`、`source_tier`、`fallback_flag` 必须原样带进输出。
2. **实时端点（次选）**：落盘里没有该指标时，才调用 MCP 实时端点取一次，并在元信息注明「未落盘」。
3. **不可读（兜底）**：两者都取不到 → 该环写 `不可读`，注明缺什么；**不得用别的指标顶替**。

**必须遵守的三条标注规则**（详见 `references/data-layer.md`）：

- **档位**：`B` 行不标注；`C` 行必须带 `〔C 类·<理由>…〕`（理由取 `data/c_reasons.json`，未登记用"唯一可得来源，未对账"）；同一指标已有 A/B 时不得用 C。
- **as-of**：取**最新交易日**（日频里最大的数据期），只给数据期更早的行加 `〔非最新：YYYY-MM-DD〕`。
- **修订**：同一（指标, 数据期）改过值时，`data/revisions/<指标>/<数据期>.jsonl` 里能查到历史；报告不必展示，但被问"这个数改过吗"必须能回答。

## 输入参数

| 参数 | 必填 | 默认 | 说明 |
|---|---|---|---|
| layer | 是 | — | `market`（市场层）/ `sector`（板块层） |
| scope | 否 | 该层全部 | 板块 id 或标的范围 |
| rings | 否 | C1–C6 | 六环子集，仍按 C1→C6 输出 |
| as_of | 否 | 最新交易日 | 页首 as-of = 最新交易日；更早的行逐行标「非最新」 |
| window | 否 | 见 anchors.md | 只影响比价环节 |
| include_events | 否 | false | `true` 时附事件段（日历 + 可选分支）；需官方日历或用户给日期 |

**任何一层级、标的、窗口的歧义，先问一句再执行**，不自行选定后附带说明。

## 八步流程（不得跳步）

1. **判层与标的**：确定 market / sector 与具体范围；板块须有成分表版本（R1）。
2. **六环取数**：按上节「数据来源」优先级取数（落盘 → 实时端点 → 不可读），C1→C6 逐环落证据；每环要么至少一条已落地事实，要么标 `不可读`。
3. **生成状态词**：只判方向，不设幅度阈值（唯一例外：广度用上涨家数占比 50%）；词表见 `reading-rules.md`。
4. **需要时做比价**：比值 / 差值 / 排名 / 分位必须先过七锚（`anchors.md`）；不通过就不出该比价。
5. **需要时做事件**（`include_events=true`）：按 `events.md` 出日历 + 可选分支；确定性不满足的只列"未确认线索"；**事件层不参与 as-of**，另标 `horizon=30d`。
6. **标注空环与时效**：空环保留环名 + 缺什么；`stale` 按 2×/3× 阈值判。
7. **输出**：证据行 + 事件段（如启用）+ 元信息 + 固定尾句（格式见下）。
8. **自检**：`python check.py --page <你的输出.md>`；有错就改，不"先输出再提醒"。

## 输出格式

```
as-of <最新交易日>（数据期早于它的行已标注「非最新」）
C1 <状态词>（<数据期>）｜依据：<字段 = 数值 + 比较>｜边界：<不说明…>
C2 …
C6 <状态词>（<数据期>）｜依据：…｜边界：…
```

- 每环一行；同一环有多个判据时分别写、不合并（如"短端变贵、长端变便宜"）。
- 空环也出行：`C4 不可读（—）｜依据：无源｜边界：该环无证据`。
- 事件段（如启用）：首行 `与 C1 指针一致：未来 30 天政策与发布日程 N 项（calendar_version=K）`，随后日历表；分支只在用户要求时展开。
- 图形（可选）：默认只出**六环覆盖条**（多标的加并排小格）；**折线只在用户要求看走势时出，且一页最多 1 条**；每张图必须绑一条证据行（`references/render.md`）。
- 元信息：as-of、stale 清单、缺失清单、替代说明、证据强度、`horizon`。
- 固定尾句：`以上为客观事实与对比数据；价格结构判断与决策请自行完成。`

## 状态词白名单（摘要；判定细则见 `reading-rules.md`）

C1 偏松 / 偏紧 / 不变；C2 扩 / 缩 / 不变（附注 结构偏活 / 偏死）；C3 变贵 / 变便宜 / 不变；C4 加杠杆 / 去杠杆 / 不变（现金池 增 / 减 / 不变）；C5 增 / 减 / 不变；C6 参与度 升/降、广度 强/弱、结构 聚/散；板块层专用 份额 升/降、偏贵 / 偏便宜、相对 强/弱（须声明 universe）；**任何环缺数据 = 不可读**。

## 失败态（固定回应）

| 情形 | 回应 |
|---|---|
| 某环全部无源 | 保留环名标"不可读"，列"缺什么"；不用近似量顶替 |
| 频率不匹配（日/月混排） | 不平铺；各自标数据期，页首只放最慢环的 as-of |
| 请求歧义 | 先问一句，不默认 |
| 指标未注册 | 先补注册，不临时造 id |
| stale 超 3 倍 | 该环写"不可读"，不进状态词、不参与背离 |
| 比价锚不符 | 不出该比价并说明哪一锚；不给"勉强可比" |
| 事件源不可抓 | 该源 `not_crawlable`，转人工；不用媒体日期补位 |
| 事件无官方链接 | 不入日历，只列"未确认线索" |
| 事件前值不可得 | `branch_ordering_applicable=false`，写"排序不适用：前值不可得" |

## 禁止

买卖建议、仓位、评分、概率、方向预测；价格结构（笔/线段/中枢/背驰/买卖点）；因果连词（因此/所以/导致/意味着）；对手方叙事（接盘/出货/资金从 A 流向 B/外资撤离）；无边界形容（活跃/宽松/充裕/资金整体）；价格序列形状的图。完整清单见 `references/reading-rules.md` 第 5 节。

## 本期覆盖

**已覆盖**：市场层六环状态、板块层六环状态（含 R1–R3）、比价（七锚 + 证据行）、事件面（日历三态 + 分支枚举，`include_events=true`）、空环与 stale 标注、自检。
**未覆盖**：事件日历的自动抓取（需外部源）；本期支持人工录入日期。
