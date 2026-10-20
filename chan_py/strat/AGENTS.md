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

## Email Signal Check
- `check_email_for_signal.py` is imported by `qmt_trader_multiple_strategies.py` (legacy, frozen) and `qmt_stdqmt_target.py` (std QMT pipeline), and called automatically at computed times.
- **Timing**: auto-computed as `trading_time - email_check_offset_minutes` per strategy. A strategy with `trading_times: ["09:35"]` and `email_check_offset_minutes: 10` triggers email check at `09:25`. In `qmt_stdqmt_target.py` the check fires once at/after that time (not an exact-minute match) and only while the mapped trading session is still ahead, so a late wake/restart still checks; wake sleeps are absolute-time based (`_sleep_until`) and immune to long email/AI durations.
- **Config**: `email_reader_config.json` (unchanged) provides IMAP credentials, `save_directory`, `target_subject`. Its `run_time` field is ignored (now auto-computed).
- **Strategy config**: add `"email_check_offset_minutes": <N>` to any strategy that needs email checks. Omit or set `0` to disable for that strategy.
- **Behavior**: fetches the latest unseen email per `target_subject`, saves attachments, marks them deleted. Retries up to 3 times if no unseen emails found. Failure never blocks strategy execution.
- If `email_reader_config.json` is missing or invalid, email check is silently disabled.
- Standalone mode still works: `python check_email_for_signal.py` runs with its own loop at `run_time`.

## AI Fundamental Filter
- After loading a stock list, `qmt_trader_multiple_strategies.py` automatically runs `ai_fundamental_filter.filter_stocks()` on it.
- The filter strips non-compliant stocks while preserving original order.
- If `ZHIPU_API_KEY` env var is missing, the import is caught and filtering is silently skipped (no-op).
- **Call-layer hardening (2026-09-15)**: client-level `LLM_CALL_TIMEOUT = 20s` with SDK retries disabled (`max_retries=0`); the qwen chain is sticky (last-good model first, Layer 4 reuses the Layer-3 model via `model_hint`) and keeps run-internal health state (2 consecutive failures → skipped for the rest of the run); `filter_stocks(deadline=..., stats=...)` stops at the deadline and returns partial results (processed verdicts + unprocessed pass-through) instead of falling back to a fully unfiltered list.
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
  模型: 降级链配置驱动 —— ai_filter_config.json 的 qwen_model_list（顺序=降级链，名单见配置）；名单为空 → 直接走智谱兜底（`zhipu_model` 配置，缺 key 报 KeyError）；单次调用超时 60s（`llm_call_timeout_seconds` 可调，deadline 前自动收敛到剩余时间）

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
- `buy_to_fill()` allocates per-stock budget as `buy_cash / slots` (where `slots = max_holdings - current_positions`).
- Since `candidates` is already capped at `slots`, each new stock gets the full target-weight allocation.
- When there are fewer candidates than slots (pool exhausted), excess cash stays uninvested.

## Gitignored in this directory
Config jsons, `logs/`, `test/`, backup files, and `strategy_positions.json`.

## 2026-05-14 Bug Fixes

| Fix | Location | Problem | Solution |
|-----|----------|---------|----------|
| `trader.connect()` double call | `init_trader:617` | Error message calls `connect()` again, showing wrong error code | Assign result first: `result = trader.connect()` |
| Tracker update on timeout | `sell_out_of_pool`, `rebalance`(sell), `rebalance`(buy), `buy_to_fill`, `batch_process_orders` | `_update_tracker_after_trade` called even when `wait_for_order_completion` times out → operates on stale `broker_positions` | Move call inside `if new_pos is not None:` block; timeout delegates to `get_account_status` sync |
| `buy_to_fill` per-stock allocation | `buy_to_fill:863` | `per_stock = buy_cash / max_holdings` → 1 slot fill gets only 1/8 of available cash | Changed to `buy_cash / slots` |
| Unused `reserve` variable | `buy_to_fill:861` | `calculate_cash_allocation` returns tuple; `reserve` never read | Changed to `_, buy_cash = ...` |
| Email module missing | `main_loop` | Email signal check not integrated into multi-strategy scheduler | Merged import + auto-computed check times + `all_wake_times` merge |

### Known Unresolved
- **No Chinese market holiday awareness**: `is_weekday` only checks Mon–Fri. On holidays the script logs connection errors at each trading time but does not trade (QMT refuses connection). No reliable free holiday data source found.

## 2026-09-15 Bug Fixes

| Fix | Location | Problem | Solution |
|-----|----------|---------|----------|
| Daily wake-time drift | `qmt_stdqmt_target.py` `main_loop` | `now` captured at loop top, then email check + AI filter (up to 600s) ran before `_next_wake(now, ...)` / `time.sleep(wait_seconds)` → sleep started ~10 min late but still lasted a full day → next wake = scheduled time + body duration (09:10 → 09:20 after AI timeout; Fri 09:10 → Mon 09:20, logged as `waiting 4320 minutes`) | Recompute `now` after the long work; `_sleep_until(target)` sleeps to the absolute target in ≤60s slices |
| Email check silently skipped | `qmt_stdqmt_target.py` `main_loop` | Exact-minute match (`current_time_str in email_check_times`) missed the check once the wake drifted, and the drift persisted → email never re-checked, files regenerated from the stale attachment | Trigger once per day when the scheduled time has been crossed (`g <= current`) and the mapped `trading_time` is still ahead (`email_check_deadline` guard); per-day dedup set |
| AI model chain latency | `ai_fundamental_filter.py` client init / `_call_with_fallback` | No per-call timeout (openai SDK default 600s + 2 retries; zai 3 retries) and every stock re-walked the full 7-model chain | Client-level `timeout=20, max_retries=0`; run-internal fail count + sticky last-good model + Layer 4 `model_hint` |
| AI deadline discarded progress | `ai_fundamental_filter.filter_stocks` / `qmt_stdqmt_target._ai_filter_with_budget` | 600s deadline → whole raw list used (0% filtered) while the daemon thread kept burning API calls in the background | Cooperative deadline (`deadline` + `stats`): processed verdicts kept, unprocessed passed through, thread exits; `join(budget+30)` only as hard fallback |

`qmt_trader_multiple_strategies.py` (legacy, frozen per migration plan §0) has the same stale-`now` sleep pattern; left unmodified (old system retired). Executor needs no change — `schedule_run` fires by absolute `time_point` + `timedelta(days=1)`, independent of callback duration.

## 2026-09-16 Bug Fixes

| Fix | Location | Problem | Solution |
|-----|----------|---------|----------|
| Per-call timeout too short | `ai_fundamental_filter.py:29` | 20s is too short for strong models / large prompts (measured: glm-4.5-flash needs 18s even on a tiny prompt, 64s on a medium one), causing widespread call failures | Default 60s via `llm_call_timeout_seconds` in `ai_filter_config.json` (invalid value falls back to 60); URL-maintenance calls keep per-request `timeout=20` |
| Deadline-aware fallback chain | `ai_fundamental_filter._call_with_fallback` | A call started 1s before the deadline could run 60s past it, exceeding the target's `join(budget+30)` margin → partial results discarded and full unfiltered list used | Pass `deadline` down: per-call timeout converges to `max(5, min(60, remaining))`, chain stops at the deadline and returns the pass-through marker |
| Zhipu fallback silently dead | `ai_fundamental_filter._call_zhipu` / `_call_with_fallback` | glm-5.2 requires balance (429 code 1113); the exception was swallowed into `(True, "默认合规")` while still reporting `model_used="glm-5.2"` → AI filter silently became a no-op | Fallback model switched to free `glm-4-flash` (2–5s, works without balance), name now config-driven via `zhipu_model` (missing key → KeyError at startup); exception now returns `None`; total failure returns `model_used="none"` + `stats['llm_failed']` counter — still fail-open (pass-through) but visible in logs |
| AI failure visibility | `qmt_stdqmt_target._ai_filter_with_budget` | All-LLM-failure runs had no warning | `llm_failed` added to the deadline warning; all-failed run logs ERROR "本轮等于未过滤" |
| Config load ordering | `ai_fundamental_filter.py:24` | Config was loaded after client init, so `llm_call_timeout_seconds` could not drive the client timeout | Strict config load moved before client init; missing config remains a hard startup error (system problem) |

## 2026-10-15 券商收紧大 QMT（禁策略读文件 + 禁策略 HTTP）

**背景**：券商通知约一周后限制大 QMT 的**文件读写**与**网络 HTTP 信号**。现行唯一的跨进程通道
（`qmt_exchange/rebalance_*.json`，由 QMT 内置策略 `open()`）会断，因此需要换通道。

**关键结论**：限制针对的是**策略沙箱**；QMT **客户端自身**的正式功能不在此列。官方手册
`config\help\systemfunction\迅投QMT极速策略交易系统说明文档.pdf`（472 页，中文以字形 ID 存储）实证了三条可用通道，
全部详见 **[QMT_CHANNEL_FALLBACK_OPTIONS.md](QMT_CHANNEL_FALLBACK_OPTIONS.md)**（含页码索引与参数速查表）：

| 优先级 | 通道 | 手册页 | 自动化 |
|---|---|---|---|
| ① 主 | **便捷交易（文件单）**：客户端每 N 毫秒扫文件夹读协议文件下单 | p.290-292, 323-327 | 全自动 |
| ① 主 | **批量预埋单（DBF 双向共享文件）**：下单 + `*_result.dbf` 回报 | p.327-333 | 全自动 |
| ② 兜底 | **组合交易 + 篮子自动导入 + 人工「一键调仓」**（客户端自己算轧差与买卖方向） | p.176-186, 364 | 半自动 ~15s/天 |
| ③ 备选 | QMT 内置策略 + **自定义板块**（`get_stock_list_in_sector`，策略零文件 IO） | — | 全自动 |
| — | **数据导出**（定时导出资产/持仓/委托/成交，DBF/TXT/CSV）＝ ① 的回报回路 | p.337-338 | — |

**新增工具（本次）**：
- `qmt_fileorder_bridge.py` — ① 主方案的外部执行引擎：读「数据导出」持仓/资金 → 腾讯/新浪行情 →
  等权目标 + 差额（沿用原 executor 资金算法）→ 生成便捷交易 `.txt` / 预埋单 `.dbf`；`--feedback` 读回报。
  **默认 dry-run**，需显式 `--execute`。自测夹具：`qmt_exchange/_selftest/`（`--config ... --inspect`）。
- `qmt_basket_bridge.py` — ② 兜底：名单 → 迅投默认格式等权篮子 CSV → 篮子自动导入目录；
  `--templates` 打印 `config\help\baskethelp\*.csv` 官方模板。
- `qmt_manual_extract.py` — 还原官方手册文本（`--toc` / `--search` / `--page` / `--dump`），中文为字形 ID 编码，pdftotext 类工具无效。
- `qmt_channel_probe.py` — 策略沙箱能力矩阵（面板内跑，不下单；`--safe` 零出站流量；`WATCH_SECTOR_NAME` 测板块热重载）。
- `qmt_sector_bridge.py` — ③ 备选：外部写 QMT 自定义板块（`datadir\Sector\<组>\<板块名>`，纯文本逗号分隔，无换行）。

**待办 / 未验证**：便捷交易实例数受**券商管理端授权**控制（须问客户经理）；预埋单 DBF 字段长度需首次实盘校准；
数据导出列名映射见 `qmt_fileorder_bridge.py` 顶部 `COL_*`（`--inspect` 打印实际列名）；便捷交易撤单协议分隔符未实测。

**重要规则（沿用）**：QMT 面板部署的策略源码必须**纯 ASCII**（面板存 GBK / 引擎按 UTF-8 解码）。

> **2026-10-16 目录迁移注记（本节正文未改动，仅追加）**
>
> 本节与 2026-05~09 的历史章节写于分目录之前，其中的裸文件名/旧路径与现在的位置对照如下，
> **语义与结论不变**：
>
> | 文中写法 | 现在的位置 |
> |---|---|
> | `qmt_stdqmt_target.py` / `qmt_rebalance_executor.py` / `qmt_stdqmt_probe.py` / `qmt_stdqmt_config.json` | `stdqmt/`（后两者中的配置仍在仓库根） |
> | `qmt_exchange/`（交换目录与 `_selftest/` 夹具） | `stdqmt/qmt_exchange/` |
> | `QMT_CHANNEL_FALLBACK_OPTIONS.md` / `qmt_fileorder_bridge.py` / `qmt_basket_bridge.py` / `qmt_manual_extract.py` / `qmt_channel_probe.py` / `qmt_sector_bridge.py` | `tools/` |
> | `qmt_trader*.py` / `qmt_test.py` / `qmt_multi_strategy_config*.json` / `qmt_config*.json` / `MULTI_TIME_SCHEDULE_README.md` | `legacy_miniqmt/`（已停用） |
> | `check_email_for_signal.py` / `ai_fundamental_filter.py` | `shared/` |
> | `chan_II_strat.py` | `chan/` |
> | `logs/` / `test/` / `strategy_positions.json` / `email_reader_config.json` | 仍在仓库根 |
>
> QMT 相关文档（本节、`stdqmt/*.md`、`tools/QMT_CHANNEL_FALLBACK_OPTIONS.md`）按**存档**保留、正文不再修改；
> 现行 PTrade 管线只看下一节与 [ptrade/PTRADE_MIGRATION_NOTES.md](ptrade/PTRADE_MIGRATION_NOTES.md)。

## 2026-10-15（续）执行侧迁往 PTrade → **2026-10-16 上线（多策略）**

**决策**：QMT 路线走不通（便捷交易/文件单、批量埋单在本机 `config\modules.lua` 中开关为 0；组合交易只剩人工点击），
且选股逻辑不可能进 QMT 沙箱 → **执行侧迁到 PTrade**，本机继续负责选股 + AI 过滤。
**QMT 执行侧已于 2026-10-16 彻底停运。** 完整说明见 **[ptrade/PTRADE_MIGRATION_NOTES.md](ptrade/PTRADE_MIGRATION_NOTES.md)**。

**通道原理**（均为平台正式功能，非绕过）：PTrade 交易沙箱**禁外网** → 邮件/AI 留本机；
**研究目录可在回测/交易中读写** + 客户端**定时上传**本地文件夹到研究目录 → 这就是名单入口。

**布局（项目自包含，整个 `ptrade/` 文件夹可拷走）**：
```
ptrade/ptrade_target.py        本机名单进程（替代 qmt_stdqmt_target.py；两者绝不能同时跑）
ptrade/ptrade_config.json      它自己的配置（单一来源：时间 + 参数 + 策略清单）
ptrade/upload_file/            客户端「定时上传」源目录 → target_<策略>.json（每策略一个）
ptrade/archive/                本机归档（不上传，供对账）
ptrade/logs/  ptrade_target.lock
ptrade/ptrade_rebalance_executor.py   云端策略（粘进 PTrade 编辑器的那一份）
```
- **时间与执行参数写在文件里**：本机把 `trading_times`/`capital_ratio`/`max_holdings`/`candidate_pool_size`/
  `cash_reserve_ratio`/`rebalance_threshold` 连同名单写进 `target_<策略>.json`；云端 `initialize` 按各文件的
  `trading_times` 注册 `run_daily`，到点按该策略的参数与 **`capital_ratio` 份额**交易 → **config 是唯一来源**，
  云端不再有第二份要手工同步的常量（改时间/参数不用重传策略，改变要重启策略一次）。
- **多策略**：一个账户 N 个策略靠 tracker（研究目录 `ptrade_state_positions.json`）+ `_my_share()` 份额归属
  （移植自 QMT executor）。云端只服务 `TARGET_FILES` 里列出的文件 → **加策略 = config 加一条 + `TARGET_FILES` 加一行 + 重启**。
- **PTrade 沙箱硬限制**：**禁 `os`/`sys`**（连带 `traceback`/`glob`/`pathlib` 等）；可用 `pandas/numpy/enum/math/
  time/simplejson/datetime`。因此策略内只有内建 `open()`、无目录列举（只能读固定文件名）、无 `mkdir`（状态/审计
  文件扁平写在研究目录根）、无原子 rename。详见 notes §4.2。
- **异步成交：槽位与买预算都按"卖出之后"算（2026-10-20 实盘修复）**：PTrade 下单即返回，成交/账户同步是异步的。
  `slots = max_holdings − (持仓 − 本轮卖出的票)`（否则满仓时永远 `slots=0` → **只卖不买**，这就是 10-20 的故障：卖了 2 只、一只没买）；
  `买预算 = 现金 + 本轮回款估算×0.995`；卖完后等 ≤15s（`SELL_CASH_WAIT_SECONDS`）让回款落账再发买单，
  日志 `cash while waiting for sell fills: ...`。卖单最终没成交 → 买单因资金不足被拒并记 ERROR（可接受）。
- **只交易"当天"的名单（2026-10-19）**：目标文件 `generated_at` 不是今天 → 云端 **不交易 + 记 ERROR**
  （`target is NOT from today ... REFUSING to trade this round`，仓位原样不动）；`> MAX_TARGET_AGE_DAYS(7) 天`
  才**清该策略份额**。上传晚到/漏传的后果是"当天不交易"，不会再悄悄用昨天那份。
- **委托价：市价单的"保护价"（2026-10-19 定稿）**：`order_market(limit_price=…)` 传的是**保护价**，不是委托价。
  **卖出必须尽全力** → 卖出保护价 = **`max(最新价×0.98, 跌停价)`**（2% 规则内能报的最低价，可扫到跌停）；
  买入不追高 → 簇子价 `min(min(ask×1.02, ask+0.1), 涨停价)` 再夹 `最新价×1.02`
  （想学参考策略的激进买法：`BUY_PROTECT_AT_LIMIT_UP = True`，仍受 2% 约束）。
  `market_type` 按市场：`688→MARKET_TYPE_STAR(0)`、`60x→1`、`00x/300x→0`、其它`→4`（与参考文件一致，已测试比对）。
  **市价单被拒会自动降级为"±2% 变价限价单"**：`order_market` 抛异常/返回空/平台判废单（`status=='9'`）时，
  立刻用同一个保护价改发 `order(..., limit_price=protect)`（保护价本身就在涨跌停内、且不偏离 2%），
  日志记 `WARN ... was rejected -> retrying as a limit order`。**科创板怎么确认**：启动看
  `has_order_market` 与 `order_mode`；首次 688 委托看是 `INFO bought ... -> order id` 还是那条 WARN，
  后者就把 `MARKET_TYPE_STAR` 0→1 重启（那一笔已按变价单发出，不会丢）。
  同时还必须满足交易所**价格笼子**（买 ≤ max(基准×102%, 基准+0.1)、卖 ≥ min(基准×98%, 基准−0.1)，
  基准=对手价→最新价→前收盘），两个界取更严者；都取不到 → **跳过该单并记 ERROR**。详见 notes §4.1.1 / §4.1.1.1。
- **平台 API 形态（同一份实盘文件证实）**：`get_stock_status(code,'HALT'|'ST')` 返回**字典**要
  `[code]` 取值（把字典当布尔 → 每只票都被判停牌，这是 2026-10-19 `nothing to do` 的真因）；
  `get_snapshot(code)[code]` 字段为 `last_px`/`up_px`/`down_px`；下单用
  `order_market(code, amount=±shares, market_type=…, limit_price=…)`；**`get_snapshot` 在
  `initialize` 阶段不可调用**（平台抛 `RuntimeError`，行情只能在真实运行时验证）。
- **代码方言只有一种：`XSHG` / `XSHE`（2026-10-19 统一）**：邮件源数据、target 文件、云端内部键（含
  tracker/审计）、以及每个平台 API 调用（`get_snapshot`/`get_stock_info`/`get_stock_status`/`order_market`）
  **全部**是 `600000.XSHG` / `000001.XSHE`。QMT 时代的 `.SS`/`.SH`/`.SZ` 拼写已彻底不用，
  `_split_code` 只在**读旧数据**（历史 tracker / 旧 target 文件）时容忍它们并迁移成 `XSHG`/`XSHE`
  （`_tracker_load` 会按新键合并，避免同一持仓被算两次）。
  证据：参考实盘策略 `get_stock_info('603822.XSHG', field="stock_name")`。
- **自测**：`ptrade_executor_selftest.py`（**30 组**：满仓卖出后同轮买入/等待成交识别/成交后回填 tracker/多策略份额/
  当天专用(非当天拒绝)/>7 天清仓/价格笼子/保护价(卖=max(最新价×0.98,跌停价))/下单降级为变价限价单/ST 两道/
  重复名单/方言统一/状态字典解码/order_market 优先/拒单记 ERROR）+ `ptrade_target_selftest.py`
  （本机产出 ↔ 云端读取的契约：源方言 `XSHG/XSHE` 全程不改写）。两侧都跑通了才算改完。

**待办**：向国金确认定时上传是否开放/次数上限、是否支持**按文件夹同步**到研究目录下的同名子目录、
`get_research_path()` 读写、实盘是否有 `run_daily`/`order`；确认本机 `trading_times`（出文件截止）严格早于
客户端上传、上传严格早于云端下单时刻。
