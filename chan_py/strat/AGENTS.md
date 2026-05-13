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
- Each stock requires an LLM API call with ~0.8s delay; expect meaningful latency for large lists.
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
- **Deleted**: 三年亏损超2亿（原Rule7，非现行规则）.
- **Rule ② two-pass system**: `_local_rule2_scan()` performs a pure-code scan on external-info flagged lines (keyword→severity→date→tiered lookback). Hitting any match immediately rejects the stock, skipping the API call. If the local scan finds nothing, the API serves as fallback. Rule ② is the only rule with this split path (all other rules rely on API for threshold verification).

### Rule ② Architecture (final, 2026-05-12)
#### Why it's complex
- **qwen3-max started producing generic "经核查，未发现触发..."** for Rule ② (~2026-05-12), while remaining reliable on Rules ①, ③-⑫.
- Root cause: external model behavior change (cloud API) — model adopted a "conservative clean" strategy for Rule ②, avoiding violation judgments.
- Attempted prompt/evidence/temperature fixes all failed. This is not fixable locally.

#### 2026-05-13 diagnostic: local vs remote inconsistency
- Compared `debug_search.log` (local) vs `debug_search_remote.log` (remote).
- **Data sources were identical** between environments — all fetchers returned the same announcements.
- Divergent results were entirely from LLM nondeterminism — same `external_info` input → different model outputs (e.g. 好想你 PASS locally, FAIL remotely on hallucinated Rule② violation).
- Root cause: `temperature=0.3` injected randomness. Fixed to `temperature=0`.
- Secondary bug: model returns `'②'` (U+2461 circled digit) but `_apply_tiered_filter` checked `"2"` (ASCII 50) → evidence cross-verification never executed. Fixed with `_RULE_CIRCLED` translation table + `_normalize_rules()`.
- `_call_with_fallback` now returns the model name (5th value) for debug traceability.

#### Final decision: keep two-pass + API fallback + tiered filter
| Component | Role | Keep? | Why |
|-----------|------|-------|-----|
| `_local_rule2_scan()` | 本地关键字+时效扫描 flagged_lines | ✅ Keep | pageSize=50 让更多标题进入 flagged_lines，覆盖充分 |
| API fallback (LLM) | 本地未命中时兜底 | ✅ Keep | 模型对 Rule ② 不可靠（已退化），实际靠 `_apply_tiered_filter` 纠偏 |
| `_apply_tiered_filter` | 模型证据校验+时效豁免+年份回退 | ✅ Keep | 模型对 Rule ② 不可靠，这些防护是必要补丁 |
| pageSize=50 | 数据源公告数量 | ✅ Key fix | 茅台留置、东亚药业责令改正均由 pageSize=50 的 flagged_lines 捕获 |
| Rules ①, ③-⑫ via LLM | 模型主判 | ✅ No change | 事实型查询，模型从未退化 |

**Pre-search (attempted & removed 2026-05-12)**: Qwen refused to search for negative keywords even in a no-judgment prompt; Zhipu hit rate limits; cninfo keyword fulltext search proved unreliable. Dropped in favor of pageSize=50.

#### Rule ① stays with LLM — not subject to local bypass
Rule ① (面值退市) is a simple factual query ("股价＜1元?"), not a semantic judgment. The model handles this fine. Local computation would require xtdata/baostock price data, adding dependency to an otherwise standalone text-analysis module. Same reasoning applies to Rule ⑫ (市值退市).

#### Tiered time-window filtering (config: `ai_filter_config.json`)
Applies to Rule ② violations:
| Severity | Lookback | Triggered by |
|----------|----------|-------------|
| high | 5 years | 立案调查, 立案, 行政处罚, 公开谴责, 留置, 纪律审查, 监察调查 |
| medium | 3 years | 通报批评, 责令改正, 责令整改 |
| low | 2 years | 监管警示函, 警示函, 出具警示函, 监管关注函, 关注函, 监管警示 |

Violations older than their tier's lookback are exempted.

### Data Source Status (2026-05-12)

| Source | Status | Root Cause | Fix |
|--------|--------|-----------|-----|
| 巨潮资讯网 (cninfo) | ✅ Fixed | Referer 污染：全局 `Referer: sse.com.cn` 导致 cninfo 判定为跨站请求，返回 HTTP 200 + 空 body | 拆分为 `HEADERS` (无 Referer) + `SSE_HEADERS` (仅 SSE 用)；URL 升级为 https |
| 东方财富 (eastmoney) | ✅ Fixed | HTML SPA (`<div id="app">`)，CSS 无效 | JSON API: `np-anotice-stock.eastmoney.com/api/security/ann`，数据在 `data.list` |
| 上交所 (sse) | ✅ Fixed | 缺 `Referer` + 参数名错误 (`security_Code` 被忽略) + JSONP 格式 | `Referer: https://www.sse.com.cn/` + `productId={code}` + strip JSONP + 读 `data.result` |
| 深交所 (szse) | ❌ Blocked | WAF/CDN，所有 API 403/500 | 已由 eastmoney `ann_type=SZA` 覆盖 |

**Coverage**: 沪市 cninfo+eastmoney+sse 三重，深市 cninfo+eastmoney 双重。

**Diagnostic script**: `test/test_data_sources.py` — calls `_fetch_from_url(debug=True)` for all 4 sources (gitignored).

**Debug logging strategy** (2026-05-12):
- Console (debug=True): one-liner summary per source — `[name] OK: N 条` or `[name] EMPTY`
- `debug_search.log`: full diagnostics (HTTP status, Content-Type, JSON errors, response body, raw data)
- `_fetch_from_url` uses internal `_diag()` helper: if `log_file` is provided → write to log; if only `debug=True` → print; otherwise silent
- `collect_external_info` prints its own console summaries (not through `_diag`), keeping the `_fetch_from_url` layer silent when called from the production path

### AI Filter TODOs / Known Risks
- [x] ~~`_call_qwen` exception branch returned 3 values, callers unpacked 4 → crash~~ (fixed)
- [x] ~~Year fallback defaulted to `current_year`, making old violations seem recent~~ (now defaults to `current_year - 10` with warning)
- [x] ~~`_classify_violation` checked nonexistent `vd.type` field → always fell back to `"medium"`~~ (now uses `vd.description`)
- [x] ~~`vd.rule` comparison assumed string, model may return int~~ (now casts with `str()`)
- [x] ~~Anomalous-rules check required *all* 10 rules exactly to trigger → too strict~~ (now triggers at >=5 rules)
- [x] ~~Empty `external_info` silently passed to model, increasing hallucination risk~~ (now prints warning)
- [x] ~~Prompt lacked exemption for 控股股东高管 (e.g. 浙农股份 汪路平)~~ (added to Rule ② exemption + 【关键判断原则】)
- [x] ~~`_apply_tiered_filter` returned True after exempting Rule②, ignoring other violated rules (e.g. Rule1+Rule② → stock passed)~~ (now checks `remaining` is empty before returning qualified)
- [x] ~~`collect_external_info` never received market suffix (normalized code stripped it) → always queried both SSE+SZSE for every stock~~ (now passes `raw_code` with original suffix)
- [x] ~~`_classify_violation` defaults to `"medium"` when no keyword matches — for unknown severity, `"high"` would be more conservative (5yr vs 3yr lookback).~~ (fixed, default is now `"high"`)
- [x] ~~Config `violation_tier_rules.high.types` lacks standalone `"立案"` keyword (only has `"立案调查"`). `RISK_FLAGS` includes it but `_classify_violation` won't match.~~ (fixed, added `"立案"` to config)
- [x] ~~Model still may hallucinate violations.~~ Added Rule ② local-evidence cross-verification: if `external_info` (fixed sources) contains no `RISK_FLAGS` keywords, the model's Rule ② claim is rejected as unverifiable. ~~(2026-05-13: This cross-verification was bypassed — model returns `'②'` (Unicode circled) but code checked `"2"` (ASCII), causing `_apply_tiered_filter` to exit early at line 598. Fixed: `_RULE_CIRCLED` + `_normalize_rules()` normalizes `①②③…` → `123…` at filter entry.)~~
- [x] ~~**Model nondeterminism** — `temperature=0.3` caused different judgment results for identical inputs across local/remote~~ (fixed 2026-05-13: `temperature=0` in both `_call_qwen` and `_call_zhipu`)
- [x] ~~**Model name not logged** — `_call_with_fallback` didn't report which model was used~~ (fixed 2026-05-13: returns 5th value `model_used`, logged to `debug_search.log`)
- [x] ~~**Add comprehensive debug logging to `_fetch_from_url`**~~ (done 2026-05-12)
- [x] ~~**Run `test/test_data_sources.py`** to get actual HTTP responses from eastmoney/sse/szse~~ (done 2026-05-12)
- [x] ~~**Fix 东方财富 data source** — update CSS selectors based on actual HTML~~ (fixed: replaced with JSON API)
- [x] ~~**Fix 上交所 data source** — add Referer header + update parsing~~ (fixed: Referer + JSONP + pageHelp.data)
- [x] ~~**Fix 深交所 data source** — find actual API endpoint~~ (blocked by WAF, covered by eastmoney)
- [ ] **Improve `maintain_sources` health check** — `_check_url` should validate response body contains expected content (not just HTTP 200)
- [x] ~~**Re-test `_local_rule2_scan` on 贵州茅台/东亚药业** after data sources are fixed~~ (verified: both caught by local scan at pageSize=50)

## Dependencies
- `xtquant` — proprietary miniQMT SDK (not on PyPI).
- `scipy`, `requests`.
- `ai_fundamental_filter.py` needs `ZHIPU_API_KEY` env var.

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
