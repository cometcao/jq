# AGENTS.md — chan_py/strat

## Architecture & Entrypoints
- **Primary prod entry**: `qmt_trader_multiple_strategies.py` — multi-strategy scheduler.
- **Single-strategy variant**: `qmt_trader.py`.
- `qmt_trader_big.py` uses JoinQuant API convention (`initialize`, `run_daily`) with hardcoded `C:\Users\Administrator\Desktop\...` paths — not portable.
- `chan_II_strat.py` is a 缠论 strategy; imports `chan_II_signal` from sibling `analysis/` package, requires `scipy`.
- `ai_fundamental_filter.py` — AI compliance filter using 智谱 GLM-4-Flash.

## Running
```bash
# Multi-strategy (normal scheduled mode)
python qmt_trader_multiple_strategies.py

# Multi-strategy (execute immediately, skip schedule)
python qmt_trader_multiple_strategies.py --now

# Multi-strategy (custom config)
python qmt_trader_multiple_strategies.py --config custom_config.json

# Single-strategy
python qmt_trader.py [--now]
```
In scheduled mode, strategies fire at `trading_times` defined per strategy (default `["09:35"]`).

## Config & Stock List Quirks
- Stock list files (`stock_list_file`) use **XSHE / XSHG** market suffixes; auto-converted to **SZ / SH** internally.
- Stock list files **missing or older than 14 days** → treated as empty → **triggers full position liquidation**.
- Multi-strategy config: all strategies' `capital_ratio` must sum to **1.0** (tolerance ±0.0001).
- Position tracking per strategy lives in `strategy_positions.json`.
- **Never commit** config jsons — they contain account IDs and QMT paths.

## AI Fundamental Filter
- After loading a stock list, `qmt_trader_multiple_strategies.py` automatically runs `ai_fundamental_filter.filter_stocks()` on it.
- The filter strips non-compliant stocks while preserving original order.
- If `ZHIPU_API_KEY` env var is missing, the import is caught and filtering is silently skipped (no-op).
- **12-rule system** (国九条 framework, ordered by trigger frequency):
  1. ① 面值退市（＜1元连续20日）
  2. ② 监管处罚/立案（原Rule6，关联信号）
  3. ③ 净利润负+营收低
  4. ④ ST/*ST（结果指标）
  5. ⑤ 内控审计否定/无法表示
  6. ⑥ 重大诉讼（≥10%净资产）
  7. ⑦ 会计差错更正
  8. ⑧ 资金占用/违规担保（新增）
  9. ⑨ 分红不达标
  10. ⑩ 净资产为负
  11. ⑪ 重大财务造假
  12. ⑫ 市值退市（新增，＜5亿）

### Architecture: 4-Layer Deterministic Pipeline (2026-05-13)

每条股票按顺序经过四层流水线，任一层命中即剔除，不进入后续层。

```
Layer 1: 标题关键词扫描 (纯代码，0 API调用)
  ② 监管处罚/立案     → _local_rule2_scan() [配置关键词→severity→tiered lookback]
  ⑤ 内控审计否定/无法表示 → "否定意见"/"无法表示意见" 关键词匹配
  ⑦ 会计差错更正       → "会计差错更正" 关键词匹配
  ⑪ 财务造假          → "财务造假" 关键词匹配
  数据源: collect_external_info() 的 RISK_FLAGS flagged_lines + 全量公告标题
  命中 → 直接剔除，跳过后续所有层

Layer 2: 金融数据核验 (baostock, 确定性的)
  ① 面值退市    → 日K线收盘价连续<1元20日
  ③ 净利润负+营收低 → query_profit_data: netProfit<0 AND MBRevenue<阈值(主板3亿/科创创业板1亿)
  ④ ST/*ST     → 日K线 isST 字段
  ⑫ 市值退市    → close×totalShare<5亿连续20日(仅主板适用)
  数据源: baostock (query_history_k_data_plus, query_profit_data)
  命中 → 直接剔除，跳过后续层

Layer 3: LLM 兜底判断 (enable_search=False, 输入完全确定)
  输入 = 金融数据核验摘要 + 公告标题全文
  覆盖: 规则⑥(重大诉讼)、⑧(资金占用/违规担保)、⑨(分红不达标)、⑩(净资产为负)
  同输入→同输出(temperature=0)，无联网搜索波动
  模型: qwen3-max (fallback: qwen3-plus/turbo → glm-4.7-flash)

Layer 4: 外部搜索查漏补缺 (已实现)
  Layer 3 判合规(通过) + 标题含高信号关键词 → Bing 搜索查漏杀
  搜索结果固定格式化后二次调 LLM (仍 enable_search=False)
  Layer 3 判不合规(剔除)时不触发，不浪费搜索资源
  同输入→同输出，确保可复现

### Layer 4 Details

- 实现: `_deterministic_search()` → requests 调 Bing，取前 5 条标题+摘要，排除股价/行情类噪声（`-股价 -行情 -走势`）
- 触发条件: `_should_trigger_layer4()` → Layer 3 判合规(通过) + 标题含高信号关键词
- 高信号关键词: `涉案金额`、`应诉通知书`、`重大诉讼`、`诉讼进展`、`仲裁进展`、`关联方资金占用`、`违规担保`
- 注意: `"关联方资金占用"` 而非 `"资金占用"` — 后者会匹配例行审计报告标题（如"非经营性资金占用及其他关联资金往来情况的专项审计说明"）造成大量误触发
- 搜索结果固定格式化后二次调 LLM (enable_search=False)，同输入同输出
- 仅 Layer 3 判合规(通过)但标题有高信号时触发，不增加已剔除股票的搜索开销

### 2026-05-13 Fixes (4-layer rebuild + post-test polish)

| Fix | Problem | Solution |
|-----|---------|----------|
| 移除 LLM 联网搜索 | `enable_search=True` 导致结果不确定 | qwen/zhipu 均改为 `enable_search=False` |
| 扩展 Layer 1 标题扫描 | 仅规则②有本地扫描，⑤⑦⑪全靠模型（会幻觉） | `_local_scan_extended()` 覆盖 ②⑤⑦⑪ |
| Layer 2 金融核验 | 规则①③④⑫全靠模型 | baostock 确定性查询日K线+年报利润表 |
| 泛化证据交叉校验 | 非规则②的幻觉无防御 | `_apply_tiered_filter` Step 1 对所有规则做关键词证据校验 |
| Layer 4 方向修正 | FAIL→搜索翻案 | 改为 PASS+高信号→搜索查漏补缺 |
| L4 关键词修正 | `"资金占用"` 匹配例行审计报告 | 改为 `"关联方资金占用"` |
| 年份提取修正 | `_extract_year_from_reason` 取 max 可能得未来年份 | 过滤 `> current_year` |
| Bing 噪声排除 | 返回东方财富/雪球/同花顺股价页 | 加 `-股价 -行情 -走势` + title 过滤 |

## Dependencies
- `xtquant` — proprietary miniQMT SDK (not on PyPI).
- `scipy`, `requests`, `baostock`.
- `ai_fundamental_filter.py` needs `ZHIPU_API_KEY` and `DASHSCOPE_API_KEY` env vars.

## Testing
No formal test framework. Tests are standalone scripts in `test/` that mock `xtquant` via `sys.modules` and use bare `assert`.
```bash
python test/test_stock_list_validation.py
python test/test_09_20_removal.py
python test/test_wait_logic.py
python test/verify_integration.py
python test/simple_test.py
```

## Fill Buying Rule
- `buy_to_fill()` allocates per-stock budget as `buy_cash / max_holdings`, **not** `buy_cash / len(candidates)`.
- When candidates < max_holdings, each stock still gets only 1/N of buying cash; excess cash stays uninvested.

## Gitignored in this directory
Config jsons, `logs/`, `test/`, backup files, and `strategy_positions.json`.
