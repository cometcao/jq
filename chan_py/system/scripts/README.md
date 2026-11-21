# 取数层（akshare）

> 版本 V2.47.0。定位：**C 类源**的免费取数层，服务于 `dist/market-state`。
> 规则依据：`docs/01_框架核心.md` 第十节（D03 分级、D04 缺失、第十节 2 的 stale 阈值）。

## 一句话

`scripts/fetch.py` 用 akshare/官网抓 28 个指标（另 2 项人工录入），多源轮换 + 限速 + 缓存 + 新鲜度闸门 + 失败降级，产出符合 `schemas/fact.schema.json` 的事实记录。

```bash
python scripts/fetch.py                 # 抓全部
python scripts/fetch.py POL_LPR MKT_CGB10Y
python scripts/fetch.py --list          # 看已注册指标
python scripts/fetch.py --no-cache      # 强制重抓
```

产物：

```
data/cache/<id>.json          最近一次成功结果（含 fetched_at，用于 TTL）
data/facts/<所属期>/<id>.json 事实记录（可直接被校验器与 Skill 消费）
data/official/<id>.json       （可选）你放的官方对账结果 → 记录升 B 类
```

## 分级与对账（最重要的一条）

akshare 抓来的是 **C 类**（第三方加工）。按 D03：

- **C 类可以进事实层**，但**不能单独支撑状态词**——某环只有 C 类证据时，该环写"不可读"；
- **升 B 的路径**：把官方原文的对账结果放进 `data/official/<id>.json`：

```json
{ "value": "7.1", "unit": "%", "data_period": "2026-10-01",
  "source_url": "http://www.pbc.gov.cn/...（官方发布页）",
  "checked_at": "2026-11-21" }
```

写进去之后，`fetch.py` 下次运行会把该指标记录标成 `source_tier=B` 并带 `verified_by`。

## 多源轮换（实测结论）

| 源 | 实测表现 | 用法 |
|---|---|---|
| **东财（push2）** | 密集调用后 `Push2RateLimitError`：**约 5 分钟恢复，反复触发可能 40 分钟+** | 不作主力；仅作后备 |
| **新浪** | 正常很快；**短时间重复调用会返回截断数据**（实例：上证只到 2019-01-30，3423 行） | 靠新鲜度闸门兜住 |
| **腾讯** | 稳定但慢（全历史分页约 26 秒） | 指数日线主力 |
| **同花顺** | 稳定（板块一览 90 行、板块指数 118 期） | 板块层主力 |
| **中证指数** | 稳定（估值 20 期，滞后 1 天） | 股息率/PE |
| **央行 / 外汇交易中心 / 拆借中心** | 稳定 | 宏观与利率主力 |

## 官方抽样核对（verify_official.py）

```bash
python scripts/verify_official.py        # 核对并写入 data/official/（升 B）
python scripts/verify_official.py --dry  # 只看结果
```

绕开 akshare、直取官方接口，与缓存值逐项比对；一致才写 `data/official/<id>.json`，下次 `fetch.py` 运行时该指标升 B。

首次结果（2026-11-21）：

| 指标 | 缓存 | 官方 | 结论 |
|---|---|---|---|
| MKT_DR007 | 1.3700 | 1.3700 | ✅ 升 B |
| FX_CNY_MID | 6.7131 | 6.7131 | ✅ 升 B |
| MKT_DIV_YIELD | 2.53 | 3.04 | ❌ 保持 C |

股息率不一致的原因：**同一 URL 在 CDN 边缘返回了不同版本**——akshare 拿到的是 10-29 版，直取拿到的是 11-20 版。已列为待复核项。

## 升 B 的两道门槛

1. **直连官方域名**：取数函数实际请求的域名是官方的（`fetch.py` 自动探测写入 `data/provenance.json` 的 `hosts`；实测 14 项中只有 **DR007（chinamoney）、汇率（safe.gov.cn）、股息率（csindex）** 三项直连官方）；
2. **抽样核对**：把官方页面上的值与取到的值逐项比对，写入 `data/official/<id>.json`。

两条都满足才升 B。经东财/新浪/腾讯/同花顺中转的数据**过不了第 1 条**，因此保持 C。

## C 类可用白名单

`data/c_reasons.json` 登记"哪些 C 类指标可以支撑状态词、理由是什么"。规则：

- **C 类可用前提：该环没有 A/B 证据**（此时它是唯一数据）；若该环已有 A/B，C 不参与状态词；
- 使用时该行必须带 `〔C 类·<理由>…〕`；
- 理由优先取 `c_reasons.json`，未登记用默认理由"唯一可得来源，未对账"；
- 升 B 仍需人工对账（`data/official/<id>.json`）。

## 状态生成器（state.py）

```bash
python scripts/state.py                        # traceable：B 可用；C 需登记理由
python scripts/state.py --policy strict        # 仅 B 类（当前会全不可读）
python scripts/state.py --policy demo          # 连 C 类也放行（仅调试）
python scripts/state.py --write                # 写 reports/<as-of>-state.md
```

输出每一行形如：

```
C2 扩（2026-10-01）｜依据：M2 同比 7.10% > 0｜边界：不说明资金进入股市
C6 参与度降（2026-11-20）｜依据：板块成交额 1985.20 亿 对比上一期 2163.28 亿｜边界：不说明资金来源〔C 类聚合·可用理由：同花顺板块指数由交易所行情聚合…〕
```

**B 类不逐行标注**；**C 类只有登记了 `data/c_reasons.json` 理由的才放行，并逐行标注理由**；未登记的 C 一律不可读。

末尾附**数据溯源表**（指标 → 官方源 → 官方页面 URL → 档位），可直接点开核对；对账通过后把值与链接写进 `data/official/<id>.json`，档位升 B，标注随之消失。

## 存储与修订（D11，V2.47.0）

| 路径 | 内容 | 规则 |
|---|---|---|
| `data/facts/<期>/<id>.json` | 当前值 | 幂等覆盖，原子写（`.tmp` + `os.replace`） |
| `data/revisions/<id>/<期>.jsonl` | 修订链 | 只追加；`revision_seq` 0=初值，`changed/changed_from` 标出改动 |
| `data/official/<id>.jsonl` | 核对历史 | 只追加；`matched=true` 才升 B |
| `data/cache/<id>.json` | 工作缓存 | 按 TTL 过期，不算事实 |
| `reports/<as-of>-state.md` | 输出 | 保留 30 份 |

查某个数改过没有：

```bash
cat data/revisions/MKT_M2_YOY/2026-10-01.jsonl
```

## as-of 规则（V2.47.0）

- 整页 `as-of` 取**最新交易日**（日频指标里最大的数据期），不再被月频环拖回一个月前；
- **只标注不是最新数据的行**：数据期早于 as-of 的行尾追加 `〔非最新：YYYY-MM-DD〕`，其余行不标。
- 无日期列的快照类接口（龙虎榜、板块集中度）用指数日线的数据期作"最近交易日"，避免周末被标成当天。

## 板块估值映射（data/sector_index_map.json）

板块层 C3 需要"板块 PE"，来源是中证指数的行业/主题指数估值。板块名与指数代码的映射写在这个文件里：

```json
{ "map": { "半导体": "H30184" } }
```

**未映射的板块，C3 如实写"不可读"**（不会拿别的板块顶替）。加一个新板块：找到它在官网的指数代码，加一行即可。

## 比价记录（compare.py）

```bash
python scripts/compare.py --list                                  # 列出可比指标
python scripts/compare.py --left MKT_M2_YOY --right MKT_M1_YOY --op difference
python scripts/compare.py --left MKT_DR007 --right MKT_CGB10Y --op difference
python scripts/compare.py --left MKT_TURNOVER --op percent_change  # 时间自比
```

**七锚不通过就不产出记录**（规则：不给"勉强可比"）。实测拦下三类：

| 请求 | 拦在 | 提示 |
|---|---|---|
| 板块 ÷ 市场 | 层级锚 | 跨层不可比 |
| 价格 ÷ 价格 | 属性锚 | price 不得做比值（ADR-001） |
| 单一数据期做变化率 | 窗口锚 | 修订链只有 1 期，无法自比 |

通过后写入 `data/compares/<compare_id>.json`（符合 `compare.schema.json`），记录里带**七锚逐条说明**与 `operand_order`。

## 一键同步（sync.py）

```bash
python scripts/sync.py                  # 抓数 → 历史增量 → 事件 → 两层状态
python scripts/sync.py --no-events      # 跳过事件
python scripts/sync.py --days 14
```

**每次运行自动补最近缺少的数据**：`fetch.py`（快照，6h 缓存内不重复请求）→ `history.py`（**增量合并**，只补缺的期，不重写）→ `events.py` → `state.py` 两层。
某一步失败不阻断后续（落盘数据仍可用），末尾打印 `完成 N/M 步`。

**stale 按交易日计**（V2.47.0）：`fetch.py` 与 `check.py` 统一用"交易日差 ÷ 频率天数"，周末与节假日不再把 stale 惩罚放大（此前周一会把周五数据误判为 stale）。

## 历史序列（history.py）

```bash
python scripts/history.py --rings C1,C2,C3,C4,C5,C6
```

快照只存最新一期、修订链记的是"同一期重跑几次"，**都不是历史**。折线图需要真序列，所以单独回补到 `data/history/<id>.jsonl`：

| 环 | 代表序列 | 期数 |
|---|---|---|
| C1 | 1 年期 LPR（月频） | 24 |
| C2 | M2 同比（月频） | 24 |
| C3 | FDR007（日频） | 51 |
| C4 | 融资余额（日频） | 60 |
| C5 | 两融个人投资者（日频） | 60 |
| C6 | 沪指+深成指成交额合计（日频） | 60 |

C6 用的是**沪指+深成指成交额合计**（比全市场窄），实测与官方两市成交额 14222 亿吻合，但口径仍需声明。

## 事件日历（events.py）

```bash
python scripts/events.py --days 30           # 表格
python scripts/events.py --days 30 --json --write   # 写 data/events/calendar-<asof>.json
```

抓 **国家统计局「最新统计信息发布日程」**（官方表格，12 个月 × 发布内容），用"日/周几"反推年份后过滤未来 N 天。

- 覆盖：CPI、PPI、PMI、工业效益、国民经济运行、投资、消费、房地产等 **11 项/30 天**（实测 2026-11-20）；
- **不在本表**：央行 OMO/MLF、交易所公告、部委政策 → 标 `不可读`，不拿第三方日历补；
- 反推年份匹配不上就跳过，**不猜日期**。

## 多板块观察（sector.py）

注册表里的 `SECTOR_*` 只能代表**一个**板块，而"医药=6 个行业加总"这类是**动态口径**，所以多板块观察走独立脚本：

```bash
python scripts/sector.py            # 表格
python scripts/sector.py --json     # JSON
python scripts/sector.py --write    # 另存 data/sector_groups/<期>.json 并追加修订链
```

分组写在 `data/sector_config.json`（首次运行自动生成）：

```json
{ "groups": [
    { "name": "医药", "members": ["中药","医药商业","化学制药","医疗器械","医疗服务","生物制品"] },
    { "name": "电力", "members": ["电力"] },
    { "name": "基础化工", "members": ["化学原料","化学制品","化学纤维","橡胶制品","塑料制品","农化制品"] } ] }
```

口径固定三条：**同花顺行业分类**、**分组成员加总**、**涨跌幅按成交额加权**；成员名写错会打印 `⚠ 未找到`，不会静默跳过。

## 机器可读输出（--json）

```bash
python scripts/state.py --layer market --json --write   # 写 reports/state-market.json
python scripts/state.py --layer sector --json --write   # 写 reports/state-sector.json
```

供面板或其他程序消费，不必解析 Markdown：

```json
{ "layer": "market", "as_of": "2026-11-20", "generated_at": "...",
  "policy": "traceable", "b_indicators": ["MKT_DR007", "FX_CNY_MID", "MKT_DIV_YIELD"],
  "lines": [ { "ring": "C4", "state": "去杠杆", "period": null,
               "evidence": "融资余额 21927.30 亿 对比上一期 22082.48 亿",
               "boundary": "不说明是新资金", "tags": ["C 类·…"], "raw": "整行原文" } ] }
```

## 三道保护

1. **限速**：同源最小间隔 1.2 秒（`MIN_INTERVAL`）。
2. **缓存**：按频率设 TTL（日 6h / 周 24h / 月 72h / 季 168h），命中即不再请求。
3. **新鲜度闸门**：解析出的 `data_period` 距今超过 `LAG_DAYS`（日 10 天 / 月 60 天）判"疑似截断"，隔 8 秒重试、再失败就降级到下一源——**宁可失败，不落旧数**。

## stale 与不可读（沿用第十节 2）

落盘前按 `as-of − data_period` 与更新频率比较：

- **> 2 倍** → 记录标 `missing_type="stale"`（保留数值）；
- **> 3 倍** → **不落盘**，打印"不可读（超 3 倍时效）"，让该环自然成为空环。

实例：`MKT_TSF_YOY`（社融）免费源最新只到 2026-04，距 2026-11 约 7.8 倍 → 当前被正确拒绝。

## 已注册的指标（28 自动 + 2 人工）

| id | 环 | 源 | 备注 |
|---|---|---|---|
| POL_LPR | C1 | akshare/em | 1 年期 LPR |
| MKT_M2_YOY / MKT_M1_YOY | C2 | akshare/em → sina | 同级双源 |
| MKT_TSF_YOY | C2 | akshare | 只有增量且滞后，当前判不可读 |
| MKT_RMB_LOAN_YOY | C2 | 同花顺 | **社融的同属性替代（仅贷款口径）**，4.70% |
| RTL_MARGIN_INVESTORS | C5 | 交易所汇总 | **开户的窄口径替代（仅杠杆投资者）**，847.90 万户 |
| FISC_DEP | C2 | 央行资产负债表"政府存款" | V2.13.6 由 C1 改归 C2 |
| MKT_CGB10Y | C3 | akshare/em | 国债 10Y |
| MKT_DR007 | C3 | 拆借中心 | 用 FDR007（定盘）作代理 |
| FX_CNY_MID | C3 | 外汇交易中心 | 中间价 ÷100 |
| MKT_DIV_YIELD | C3 | 中证指数（直取 xls） | 沪深300 股息率 |
| MKT_MARGIN_BAL | C4 | 交易所汇总 | 融资余额（全市场） |
| MKT_MARGIN_COLLATERAL | C4 | 交易所汇总 | 两融担保物总价值（6.51 万亿，含证券） |
| MKT_MMF_SCALE | C4 现金池 | 东财（中基协口径） | 货币基金规模 **15.80 万亿**（保证金停发后的同属性代理） |
| EXT_CN_ETF_AUM | C5 外部 | **KraneShares 官网** | 海外中国 ETF 规模 **$4.38B**（KWEB+KBA+KURE，北向停发后的代理） |
| MKT_MARGIN_DEP | C4 现金池 | **人工** | 客户保证金（官方 2017 停发，一般留空） |
| MKT_NORTH_AMT | C5 外部 | **人工** | 北向盘后成交额（官方 2024-08 停披露，一般留空） |
| SECTOR_AMT | C6（板块） | 同花顺 | 板块成交额，用于派生 C2 份额 |
| IDX_DAILY | C6 | 腾讯 → 新浪 → 东财 | 仅数据层，不呈现 |
| INST_LHB_NET | C5 机构 | 东财 | 龙虎榜机构净买额（区间汇总） |
| INST_BLOCK_AMT | C5 机构 | 东财·市场统计 | 大宗成交额（当日，溢价占比附注） |
| INST_BLOCK_PREM | C5 机构 | 东财·每日统计 | 折溢价率均值（换源后已稳定） |
| MKT_BREADTH | C6 广度 | 乐咕 | 上涨家数占比 |
| MKT_TURNOVER | C6 参与度 | 同花顺 | 全市场成交额（板块加总 14311 亿） |
| SECTOR_AMT_CONC | C6 结构 | 同花顺 | Top5 板块成交额占比（阈值 50%，N=90） |
| SECTOR_SHARE | 板块 C2 份额 | 自算 | 板块成交额 ÷ 全市场（半导体 13.87%） |
| SECTOR_PCT | 板块 C6 结果 | 同花顺 | 板块指数涨跌幅（−6.85%） |
| SECTOR_BREADTH | 板块 C6 广度 | 同花顺 | 板块内上涨家数占比（3.7%） |
| SECTOR_VAL | 板块 C3 相对贵贱 | **中证指数官网** | 板块 PE ÷ 沪深300 PE = **6.33×**（半导体 H30184） |
| SECTOR_INST_FLOW | 板块 C5 主体 | 中证成分 + 龙虎榜 | 板块内机构净买 **−2.35 亿**（87 只成分中上榜若干） |

## 加一个指标

在 `SPECS` 里加一行即可：

```python
dict(id="XXX", channel="C3", subject="公共池", freq="日", value_kind="level", layer="市场",
     providers=[("akshare/em", ["函数名1", "函数名2"], 解析器)],
     proves="…", does_not_prove="…"),
```

要点：
- **别名列表**：akshare 改名（1.20 大改过一批）只需在列表里补一条；
- **解析器**返回 `(current_state, meta)`，`meta` 至少含 `data_period`；
- **value_kind / channel / subject 必须与 `docs/09` 注册表一致**，否则校验器会拦（它拦过我们 6 次）。

## 已知缺口（免费源拿不到）

| 缺口 | 现状 | 建议 |
|---|---|---|
| 社融**存量同比** | 只有增量且滞后；已用贷款余额同比作替代 | 官方月报人工对账 |
| 客户保证金 | 投保基金月度表（Excel/PDF） | 人工季度录入 |
| 新增开户数 | 已用两融个人投资者数作窄口径替代 | 中国结算月报人工对账 |
| 信用利差 | 需 AA 中票 − 国开自算 | 自算归比价层 |
| 北向 | 官方已停日度 | 不做 |

## 回归基线（2026-11-20 实测，改动后用它自检）

```
POL_LPR        3.00%
MKT_CGB10Y     1.5803%
MKT_DR007      1.37%
FX_CNY_MID     6.7131
MKT_DIV_YIELD  2.53%
MKT_M2_YOY     7.10%
MKT_M1_YOY     4.40%
FISC_DEP       73065 亿元
MKT_MARGIN_BAL 21927.30 亿元
SECTOR_AMT     1985.20 亿元
IDX_DAILY      3533.79
```
