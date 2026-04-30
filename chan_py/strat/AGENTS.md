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

## Gitignored in this directory
Config jsons, `logs/`, `test/`, backup files, and `strategy_positions.json`.
