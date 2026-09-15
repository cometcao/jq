# qmt_stdqmt_config.json 配置说明

## 概述

`qmt_stdqmt_config.json` 是标准 QMT 迁移方案的**唯一策略配置**，供两个独立进程共同消费：

| 进程 | 文件 | 职责 |
|------|------|------|
| 计划进程（外部） | `qmt_stdqmt_target.py` | 邮件读取 → 读股票列表 → AI 过滤 → 生成 `rebalance_*.json`（不碰交易） |
| 执行进程（QMT 内） | `qmt_rebalance_executor.py` | 定时触发 → 消费 rebalance 文件 → 下单交易 → 更新 tracker |

两个进程在各自启动时读取**同一份文件的不同字段**，通过 `exchange_path` 目录下的文件交接，无直接通信。因此改字段时须先确认它被谁消费、是否需要重启对应进程（见文末「修改检查清单」）。

> 本文件包含账户 ID 与本地路径，**不要提交到 git**（`AGENTS.md` 已将其列入 gitignore）。

---

## 顶层字段

```json
{
    "account_id": "8880475040",
    "log_file": "logs/stdqmt_plan.log",
    "executor_log_file": "logs/qmt_executor.log",
    "exchange_path": "qmt_exchange",
    "stock_list_dir": "C:\\Users\\Administrator\\Desktop\\upload",
    "stock_list_files": {"low_valuation": "low_valuation_stocks.json"},
    "position_tracking_file": "strategy_positions.json",
    "strategies": [ ... ],
    "run_now": false
}
```

| 字段 | 读取方 | 含义与约束 |
|------|--------|-----------|
| `account_id` | 仅 executor | QMT 交易账号。executor 启动时 `set_account` + `schedule_run` 均依赖它 |
| `log_file` | 仅 target | 计划进程日志（相对 `strat/` 解析，默认 `logs/stdqmt_plan.log`） |
| `executor_log_file` | 仅 executor | 执行进程日志（相对 `strat/` 解析） |
| `exchange_path` | 双方 | 文件交接目录，绝对/相对路径均可（相对路径以 `strat/` 为基准）。target 写入 `rebalance_*.json`，executor 读取并改名 `.done` |
| `stock_list_dir` | 仅 target | 股票列表所在目录。若配置了 `stock_list_files` 且邮件配置存在，启动时**强制校验**其与 `email_reader_config.json` 的 `save_directory` 一致，否则拒绝启动 |
| `stock_list_files` | 仅 target | `{策略名: 文件名}`。命中某策略时覆盖其 `stock_list_file` 为 `stock_list_dir/文件名`；也决定了上面那条目录校验是否生效（未映射则不校验） |
| `position_tracking_file` | 仅 executor | 各策略持仓跟踪 JSON（相对路径以 `strat/` 为基准，默认 `strategy_positions.json`） |
| `run_now` | 仅 executor | `true` = QMT 策略 init 时立即执行全流程（手动验证用）；**生产必须 `false`**（定时模式，纯 `schedule_run` 驱动） |
| `strategies` | 双方 | 策略数组，见下 |

---

## strategies 数组字段

```json
{
    "name": "low_valuation",
    "stock_list_file": "C:\\Users\\comet\\Desktop\\low_valuation_stocks.json",
    "capital_ratio": 1.0,
    "max_holdings": 8,
    "candidate_pool_size": 13,
    "cash_reserve_ratio": 0.0125,
    "rebalance_threshold": 0.20,
    "trading_times": ["10:00"],
    "email_check_offset_minutes": 10
}
```

| 字段 | 读取方 | 含义与约束 |
|------|--------|-----------|
| `name` | 双方 | 策略名。用于 rebalance 文件名前缀、tracker 键名、`stock_list_files` 映射键，须唯一 |
| `stock_list_file` | 仅 target | 列表文件路径。**若 `stock_list_files` 中有同名映射则被覆盖**（拼接为 `stock_list_dir/文件名`），此处的旧路径通常已过时 |
| `capital_ratio` | 双方 | 该策略资金占比（>0）。**所有策略之和必须 = 1.0**（容差 ±0.0001），否则两个进程都会拒绝加载 |
| `trading_times` | 双方 | 交易时段列表 `["HH:MM"]`（可多个）。**计划锚点与执行触发点是同一组时间**：target 据此反推生成时刻，executor 为每个 (策略, 时间) 注册一条每日 `schedule_run`。缺省 `["09:35"]` |
| `email_check_offset_minutes` | 仅 target | 邮件检查与文件生成提前量（分钟）。文件生成/邮件检查时刻 = `trading_time − offset`。邮件检查在该时刻**跨过后的首次唤醒**执行（每天一次，且仅在该时刻对应的 trading_time 尚未到达前）。**省略 = 默认 5；显式 0 = 禁用邮件检查**且生成时刻 = 交易时刻本身（`get("email_check_offset_minutes", 5)`，仅 `>0` 才执行邮件检查） |
| `max_holdings` | 仅 executor | 最大持仓数。决定目标仓位 `cash_for_stocks / max_holdings` 及买入池截断上限 |
| `candidate_pool_size` | 仅 executor | 候选池大小，从文件股票列表头部截取；池外持仓会被卖出（`sell_out_of_pool`） |
| `cash_reserve_ratio` | 仅 executor | 现金预留比例（总资产 × 该比例 = 预留），用于计算可用资金 |
| `rebalance_threshold` | 仅 executor | 再平衡触发阈值：当平均分配额与目标单票仓位的偏差超过该比例时触发 `rebalance`（0.20 = 偏差 20%） |

### 多个策略 / 多时段同时触发

- 多个策略配置了同一 `trading_time` → target 在同一个生成时刻为每个策略各生成一份文件（一轮邮件检查后连续处理）；executor 每个 (策略, 时间) 一条独立定时任务。
- 同一策略多个 `trading_times` → 每个时段生成一份文件，文件名时间戳不同，executor 取当日该策略**前缀最新且未处理**的一份。

---

## 时间规则与两进程配合（示例）

当前配置：`trading_times: ["10:00"]`，`email_check_offset_minutes: 10`：

```
09:50  计划进程（target，常驻，仅工作日）
       ├─ 邮件检查：check_email_for_signal 拉取目标主题最新未读邮件附件 → 落盘 stock_list_dir
       ├─ 读股票列表（缺失/超14天/读失败 → 空列表 = 清仓语义）
       ├─ AI 过滤：预算 = min(600s, 距 10:00 剩余时间)；单模型调用 20s 超时 + 降级链健康跳过
       │    到点 → 已处理股票按结论过滤，未处理股票透传（记 warning 日志）
       │    异常 → 跳过本轮，不生成文件（保守，不交易）
       └─ 写入 qmt_exchange/rebalance_low_valuation_<YYYYMMDD_HHMM>.json

10:00  执行进程（QMT 内，schedule_run 每日触发）
       └─ 找当日该策略最新 rebalance_*.json → 原子改名 .done → 解析 → 交易
          （无文件则记 "no file pending for today"，跳过本轮，不做追赶）
```

关键语义：
- **文件必须在交易时刻前就绪**是设计前提，因此 executor 侧无 recheck/重试/补单机制（丢失只影响本轮 diff，下轮自动修正）。
- 邮件检查失败不阻塞生成；**AI 到点不阻塞交易（2026-09-15 起部分过滤）**：已处理股票按结论过滤、未处理股票透传；仅线程卡死兜底（预算 + 30s）才回退整份未过滤。
- **AI 调用层硬化（2026-09-15）**：单模型调用 20s 超时（客户端级，禁用 SDK 自动重试）；降级链运行内连续失败 2 次的模型跳过，成功模型优先复用（粘性，Layer 4 复审复用 Layer 3 模型）。
- **唤醒/检查时刻抗漂移（2026-09-15 修复）**：target 用绝对时间睡眠（`_sleep_until`，每 ≤60s 重算剩余），email 检查 + AI 过滤耗时再长（超时上限 600s）也不会推迟次日的唤醒/检查/生成时刻；邮件检查按"跨过计划时刻即查、每天一次"触发，晚唤醒/晚启动当天仍会补查，且交易时段结束后不会消耗邮件。
- target 仅认 `is_weekday`（无节假日认知）；executor 依赖 QMT 日历。节假日 target 会尝试读邮件/生成文件但 executor 不触发。

---

## 关联配置文件

### email_reader_config.json（邮件信号源）

```json
{
    "imap_server": "imap.163.com",
    "email_user": "17317768857@163.com",
    "email_pass": "",
    "save_directory": "C:\\Users\\Administrator\\Desktop\\upload",
    "target_subject": ["TTC1"],
    "run_time": "09:15"
}
```

| 字段 | 说明 |
|------|------|
| `imap_server` / `email_user` / `email_pass` | IMAP 凭据 |
| `save_directory` | 附件落盘目录，**必须等于** `qmt_stdqmt_config.json` 的 `stock_list_dir`（target 启动时校验） |
| `target_subject` | 主题关键词数组，每个关键词取最新一封未读邮件，附件按原文件名落盘 |
| `run_time` | **仅 standalone 模式**（`python check_email_for_signal.py` 独立跑）生效；被 target 进程调用时忽略——检查时刻由 `email_check_offset_minutes` 自动推算 |

### ai_filter_config.json（AI 合规过滤）

被 `ai_fundamental_filter.py` 消费，文件缺失/为空时自动降级到智谱 GLM（需 `ZHIPU_API_KEY` + `DASHSCOPE_API_KEY` 环境变量）：

| 字段 | 说明 |
|------|------|
| `qwen_model_list` | 千问模型降级链（顺序 = 失败时依次降级；当前 7 个模型）。单次调用 20s 超时、禁用 SDK 自动重试；运行内连续失败 2 次的模型跳过，成功模型优先复用（粘性） |
| `sources` | 公告数据源 URL 模板：`cninfo`(巨潮) / `eastmoney`(东财) / `sse`(上交所) / `szse`(深交所)，含搜索起止日期 |
| `violation_tier_rules` | 规则②(监管处罚/立案)本地扫描的关键词分级：`high`(立案/处罚等, 回溯5年) / `medium`(通报批评/责令改正, 3年) / `low`(警示函/关注函, 2年) |

### 交接文件（exchange_path 目录）

- 命名：`rebalance_<策略名>_<YYYYMMDD_HHMM>.json`（例如 `rebalance_low_valuation_20260908_0950.json`）
- 内容：`{"strategy", "generated_at", "stocks": [...]}`，空 `stocks` 数组 = 清仓指令
- 消费后由 executor 原子改名为 `<同名>.done`；改名失败（文件已被处理）则跳过
- target 每日每 (策略, 时段) 仅生成一次（内存去重）；executor 只认当天日期前缀

---

## 运行方式

```bash
# 计划进程：常驻模式（工作日按日程唤醒）
python qmt_stdqmt_target.py

# 计划进程：立即为所有策略生成一次（跳过邮件检查，AI 预算放宽到 600s）
python qmt_stdqmt_target.py --now

# 指定配置文件
python qmt_stdqmt_target.py --config x.json
```

执行进程在 QMT 客户端内加载 `qmt_rebalance_executor.py`（真实交易模式，非模拟），由配置文件 `run_now` 决定是否立即执行。

---

## 修改检查清单

| 改什么 | 重启谁 | 备注 |
|--------|--------|------|
| `trading_times` / `account_id` | QMT 内重新加载策略 | executor 的 `schedule_run` 在 `init` 时注册 |
| `email_check_offset_minutes` / `stock_list_files` / `stock_list_dir` | 重启 target 进程 | 目录改动须同步改 email `save_directory`（启动校验会拒绝不一致） |
| `capital_ratio` | 两个进程都重启 | 和 ≠ 1.0 时双方均拒绝加载 |
| `max_holdings` / `candidate_pool_size` / `cash_reserve_ratio` / `rebalance_threshold` | QMT 内重新加载策略 | 仅 executor 消费 |
| `qwen_model_list` / `sources` / `violation_tier_rules` | 重启 target 进程 | AI 过滤在计划进程中以线程方式调用 |

⚠️ 配置含账户 ID 与本地路径，**禁止提交到 git**。
