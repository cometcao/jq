# 取数层（akshare）

> 版本 V2.24.0。定位：**C 类源**的免费取数层，服务于 `dist/market-state`。
> 规则依据：`docs/01_框架核心.md` 第十节（D03 分级、D04 缺失、第十节 2 的 stale 阈值）。

## 一句话

`scripts/fetch.py` 用 akshare 抓 19 个指标，多源轮换 + 限速 + 缓存 + 新鲜度闸门 + 失败降级，产出符合 `schemas/fact.schema.json` 的事实记录。

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

## 三道保护

1. **限速**：同源最小间隔 1.2 秒（`MIN_INTERVAL`）。
2. **缓存**：按频率设 TTL（日 6h / 周 24h / 月 72h / 季 168h），命中即不再请求。
3. **新鲜度闸门**：解析出的 `data_period` 距今超过 `LAG_DAYS`（日 10 天 / 月 60 天）判"疑似截断"，隔 8 秒重试、再失败就降级到下一源——**宁可失败，不落旧数**。

## stale 与不可读（沿用第十节 2）

落盘前按 `as-of − data_period` 与更新频率比较：

- **> 2 倍** → 记录标 `missing_type="stale"`（保留数值）；
- **> 3 倍** → **不落盘**，打印"不可读（超 3 倍时效）"，让该环自然成为空环。

实例：`MKT_TSF_YOY`（社融）免费源最新只到 2026-04，距 2026-11 约 7.8 倍 → 当前被正确拒绝。

## 已注册的 19 个指标

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
| MKT_DIV_YIELD | C3 | 中证指数 | 沪深300 股息率 |
| MKT_MARGIN_BAL | C4 | 交易所汇总 | 融资余额（全市场） |
| SECTOR_AMT | C6（板块） | 同花顺 | 板块成交额，用于派生 C2 份额 |
| IDX_DAILY | C6 | 腾讯 → 新浪 → 东财 | 仅数据层，不呈现 |
| INST_LHB_NET | C5 机构 | 东财 | 龙虎榜机构净买额（区间汇总） |
| INST_BLOCK_AMT | C5 机构 | 东财 | 大宗成交额（区间汇总） |
| INST_BLOCK_PREM | C5 机构 | 东财 | **源表结构不稳定**，部分窗口缺折溢率列 → 失败即跳过 |
| MKT_BREADTH | C6 广度 | 乐咕 | 上涨家数占比 |
| SECTOR_AMT_CONC | C6 结构 | 同花顺 | Top5 板块成交额占比（阈值 50%，N=90） |

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
