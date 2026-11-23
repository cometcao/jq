# 数据层说明（落盘数据怎么读、怎么标注）

> 规则版本 V2.89.0。本文件回答：**这个 Skill 的数据从哪来、什么优先级、每行怎么标注**。
> 对应实现：`scripts/fetch.py`（抓数）、`scripts/state.py`（生成状态）、`scripts/verify_official.py`（官方核对）。

## 一、取数优先级（不得跳级）

| 顺序 | 来源 | 用法 | 元信息里怎么写 |
|---|---|---|---|
| 1 | **落盘事实** `data/facts/<数据期>/<指标>.json` | 首选；或直接 `python scripts/state.py --policy traceable` 一次生成 | 注明数据期与档位 |
| 2 | 实时端点（MCP） | 落盘里没有该指标时才用 | 注明「未落盘，实时端点」 |
| 3 | 不可读 | 两者都没有 | `不可读` + 缺什么 |

**落盘记录优先的原因**：它带 `source_tier`、`fallback_flag`、`data_period`，且经过 schema 校验与（部分）官方核对；实时端点取来的数没有这些溯源信息。

## 二、目录与含义

```
data/facts/<数据期>/<指标>.json     当前值（读这个判断状态）
data/revisions/<指标>/<数据期>.jsonl 修订链（查"改过没有"）
data/official/<指标>.jsonl          官方核对历史（决定 B / C）
data/cache/<指标>.json              工作缓存（按 TTL，不算事实）
data/provenance.json                每个指标的官方源与请求域名
data/c_reasons.json                 C 类可用理由（登记了才能用）
reports/<as-of>-state.md            已生成的输出
```

## 三、已接入的 19 个指标

| 环 | 指标 id | 界面名 | 档位 |
|---|---|---|---|
| C1 | POL_LPR | 当前 LPR | C |
| C2 | MKT_M2_YOY / MKT_M1_YOY | M2 / M1 同比 | C |
| C2 | FISC_DEP | 财政存款余额 | C |
| C2 | MKT_RMB_LOAN_YOY | 人民币贷款余额同比 | C |
| C3 | MKT_DR007 | DR007（FDR007 定盘） | **B** |
| C3 | MKT_CGB10Y | 中国 10Y 国债收益率 | C |
| C3 | FX_CNY_MID | USD/CNY 中间价 | **B** |
| C3 | MKT_DIV_YIELD | 股息率 | **B** |
| C4 | MKT_MARGIN_BAL | 两融余额 | C |
| C5 | RTL_MARGIN_INVESTORS | 两融个人投资者数 | C |
| C5 | INST_LHB_NET | 龙虎榜机构净买额 | C |
| C5 | INST_BLOCK_AMT | 大宗成交额 | C |
| C5 | INST_BLOCK_PREM | 大宗折溢价率 | C |
| C6 | IDX_DAILY | 宽基指数日线 | C |
| C6 | SECTOR_AMT | 板块成交额 | C |
| C6 | MKT_BREADTH | 上涨家数占比 | C |
| C6 | SECTOR_AMT_CONC | 板块成交额集中度（Top-5 口径） | C |

**不可读的三格**：C4 现金池（客户保证金无公开日度源）、C5 北向（官方已停日度）、C2 社融存量（源滞后，用贷款同比替代）。

## 四、三条标注规则

### 1. 档位标注

| 档位 | 能不能支撑状态词 | 行内要不要标 |
|---|---|---|
| A / B | 能 | 不标 |
| **C** | 能，**前提是 `data/c_reasons.json` 有登记**（当前 14 项全有） | **必须标** `〔C 类·<理由>…〕` |
| D | 派生量，不进状态词 | — |

若同一指标已有 A/B，则该指标不再用 C。

### 2. as-of 与「非最新」标注

- 页首 `as-of` = **最新交易日**（日频指标里最大的 `data_period`）；
- **日期只写一次**：与页首 as-of 相同的行**不写日期**；更早的行写 `（YYYY-MM-DD*）`，`*` 的含义在页首说明。
- 无日期列的快照类接口（龙虎榜、板块集中度）以指数日线的数据期作为"最近交易日"。

### 3. 修订可追溯

同一（指标, 数据期）重复写入时，`data/revisions/` 里保留全部版本（`revision_seq` 递增、`changed_from` 记录旧值）。
**被问"这个数改过吗"时**：读该 jsonl，回答"改过 N 次，从 X 改成 Y，时间 T"。

## 五、不要做

- 不要用实时端点覆盖落盘值后当作落盘事实（那会丢溯源）；
- 不要把 cache 当事实（它会过期）；
- 不要跨指标顶替（例如用成交额回答资金面）；
- 不要在 C 类行省略理由标注；
- 不要把 `不可读` 写成"暂无数据，预计…"之类的预测句。
