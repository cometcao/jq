# PTrade 迁移说明（2026-10-15）

> 背景：券商通知约一周后限制大 QMT 的**文件读写 + 网络连接**；便捷交易/文件单、批量埋单在本机
> 客户端的开关都是 0（`config\modules.lua`），组合交易只剩人工点击。因此执行侧迁到 **PTrade**：
> 策略跑在券商云端，**研究目录可在回测/交易中读写**，且客户端支持**定时上传**本地文件到研究目录。
> 详细调查过程见 [../tools/QMT_CHANNEL_FALLBACK_OPTIONS.md](../tools/QMT_CHANNEL_FALLBACK_OPTIONS.md)。

---

## 1. 架构

```
本机（有网；选股 + AI 完全不变）
  邮件 → 名单 → AI 国九条过滤
      └─ ptrade/ptrade_target.py（每个策略一份文件，文件里带它的下单时间与执行参数）
           ├─ 归档：ptrade/archive/rebalance_<策略>_<日期>_<时分>.json （本地对账用，不上传）
           └─ 上传：ptrade/upload_file/target_<策略>.json            （每策略一个固定名）
                    │  PTrade 客户端「定时上传」源目录 = ptrade\upload_file\
                    ▼
券商云端 PTrade
  研究目录(get_research_path())/upload_file/target_<策略>.json ← 客户端按同名文件夹镜像过去
  交易策略 ptrade_rebalance_executor.py（单文件、Py3.5.2、无 os/sys）
     initialize: 读每个 TARGET_FILES 文件的 trading_times → 逐个 run_daily 注册
     到点：读该策略名单 → tracker 份额切片 → 等权目标 → 差额 → order()
     写回：研究目录根 ptrade_orders_<策略>_<日期>.json（审计，含 notes/errors/age）
                       ptrade_state_<策略>.json（幂等标记）
                       ptrade_state_positions.json（tracker：每策略持有哪些代码/多少股）
```

**为什么这样切**：PTrade 交易沙箱**禁止外网**（`requests` 不可用），所以邮件/AI 永远留在本机；
而它**允许交易策略读写研究目录** + **客户端定时上传**，这两半都是平台正式功能，正好补上 QMT 断掉的"名单入口"。
每策略一个固定名文件 → 服务器端只有当天最新那份，不需要在云端清理历史文件；**时间与参数都写进文件**，
所以本机 config 是唯一来源，云端不再有第二份需要手工同步的常量。

**与 QMT 的分工差异**：调仓计划逻辑集中在单个 `_plan()` 里，替代 QMT 的三段式
（`sell_out_of_pool` + `check_rebalance_and_execute`/`rebalance` + `buy_to_fill` + 价格/资金辅助函数）。
仓位归属（tracker / `capital_ratio` 切片 / `_my_share`）**按原样移植**回来了（多策略需要一个账户内的份额划分）。

> **边界（2026-10-16 定，重要）**：PTrade 侧**只做仓位调整，不承担任何策略逻辑**。
> 名单是输入、顺序=排名，策略只按 `candidate_pool_size` / `max_holdings` 切片并等权执行；
> **不选股、不过滤、不排名、不自行发明卖出规则**。
> "谁该不该在名单里"（含 ST、国九条 12 条规则、估值）全部在本机 `ptrade_target.py` +
> `shared/ai_fundamental_filter.py` 决定。策略里仅有的非机械规则是三条**安全闸门**：
> ST 拒绝买入（并按 5% 幅度计算涨跌停）、涨停不买/停牌跳过/用可卖量、只认当天名单。

### 1.1 本机两个 target 脚本的关系（**不能同时跑**）

| 文件 | 用途 | 输出 |
|---|---|---|
| `stdqmt/qmt_stdqmt_target.py` | QMT 时代的原版（QMT 已停运，保留备查） | 只写 `stdqmt/qmt_exchange/rebalance_*.json`；配置 `stdqmt` 时代的 `qmt_stdqmt_config.json`（仓库根） |
| **`ptrade/ptrade_target.py`** | **现在用这个**：同一套邮件+AI 流程，**项目自包含**，每策略一个文件 | `ptrade/archive/rebalance_<策略>_*.json` + `ptrade/upload_file/target_<策略>.json` |

- **两者绝不能同时跑**：邮件检查会把邮件标记为已删除，两个进程会互相抢邮件。
  ⚠️ 现在两个脚本的 **lock 文件名不同**（`ptrade_target.lock` / `stdqmt_target.lock`），
  所以互斥**不再自动生效**，只能靠你只启动一个。
- `ptrade_target.py` 顶部加了 `sys.path` 引导，能自动找到 `shared/` 里的
  `check_email_for_signal.py` 与 `ai_fundamental_filter.py`（**原版没有这一步**：分目录后
  `python stdqmt/qmt_stdqmt_target.py` 会静默失败 —— 邮件检查变空操作、AI 过滤变直通，
  因为那两个 import 被 `try/except ImportError` 兜成了假函数）。
- **ptrade 项目自包含**：`ptrade_config.json`、`upload/`、`archive/`、`logs/`、`ptrade_target.lock`
  全部在 `ptrade/` 内，配置里的相对路径以 `ptrade/` 为基准（不是启动目录）→ 整个文件夹拷走即可用。

---

## 2. 文件契约

### 外部 → 云端：**每个策略一个文件**（2026-10-16 多策略改造后）

本机 `ptrade_target.py` 往 `ptrade/upload_file/` 写：

```
target_<策略名>.json      ← 每个策略一个（固定名、每天覆盖），文件名里的策略名必须与云端 TARGET_FILES 对上
archive/...              ← 本机归档（不上传），供对账
```

客户端「定时上传」源目录 = `ptrade\upload_file\` → 服务器研究目录下出现**同名文件夹** `upload_file\`
→ 策略读 `<研究目录>/upload_file/target_<策略>.json`（**找不到时退回研究目录根**，防客户端把文件夹拍平）。

```json
{
  "strategy":      "low_valuation",
  "generated_at":  "2026-10-17T09:20:11",
  "trading_times": ["09:35"],        // ← 云端从这里注册 run_daily（下单时间）
  "capital_ratio": 1.0,              // ← 仓位归属：占账户的比例
  "max_holdings":        8,
  "candidate_pool_size": 13,
  "cash_reserve_ratio":  0.0125,
  "rebalance_threshold": 0.20,
  "stocks": ["605189.XSHG", "301167.XSHE", "..."],
  "liquidate": false                 // 可选：显式清仓
}
```
- `stocks`：**全量过滤后的名单，顺序=排名**（策略按 `candidate_pool_size` / `max_holdings` 切片）；
  **代码方言只有一种：`XSHG`/`XSHE`**（2026-10-19 统一）。邮件源数据、本文件、云端内部键（tracker/审计）、
  以及每个平台 API 调用（`get_snapshot`/`get_stock_info`/`get_stock_status`/`order_market`）全部是
  `600000.XSHG` / `000001.XSHE`。QMT 时代的 `.SS`/`.SH`/`.SZ` 拼写已废弃；`_split_code` 仅在
  **读旧数据**（历史 tracker / 旧 target 文件）时容忍并迁移，`_tracker_load` 按新键合并以防同一持仓被算两次。
  证据：参考实盘策略的 `get_stock_info('603822.XSHG', field="stock_name")`
- 执行字段（`trading_times`/`capital_ratio`/四个参数）**缺省回落到策略内置的 `DEFAULT_*`**，所以旧格式文件也能跑
- `generated_at`：**必须是当天**（非当天 → 云端拒绝交易并记 ERROR；>7 天 → 清该策略仓位，见 §4.2）

### 多策略（云端）

| 项 | 做法 |
|---|---|
| 策略清单 | 策略里内置 `TARGET_FILES = ["target_low_valuation.json", ...]`。**沙箱没有目录列举**，所以"有哪些策略"只能内置；**加策略 = 本机 config 加一条 + 云端加一行 + 重启策略** |
| 下单时间 | 每读一个文件就按它的 `trading_times` 注册 `run_daily`（读不到文件时用 `DEFAULT_ORDER_TIMES`）；**改时间要重启策略**（`run_daily` 只能在 `initialize` 注册） |
| 同一时刻多策略 | 每个 (文件, 时刻) 一个回调；回调用策略名区分，互不干扰 |
| 仓位归属 | 一个账户 N 个策略 → 用研究目录里的 tracker（`ptrade_state_positions.json`）+ `capital_ratio` 切片：`策略总资产=账户总资产×ratio`、`策略现金=min(策略总额−策略持仓市值, 账户可用现金×ratio)`、共享代码按 `_my_share()`（券商持仓 − 其它策略份额）算。逻辑移植自 QMT executor（`_tracker_sync` 对账规则：未跟踪的给 ratio 最大的策略；单一持有者按券商数校正；多持有者不一致 → ERROR 要人工处理） |
| 成交确认 | PTrade 异步、账户 6 秒同步 → tracker 按**下单量**估算更新，次日 `_tracker_sync` 自动与券商量对账（单一持有者会被自动校正） |
- `stocks: []` 或 `liquidate: true` → **清仓**（与旧管线语义一致）
- 代码方言只有一种：`XSHG` / `XSHE`（云端内部与平台 API 相同，见 §1 与 AGENTS.md）

> ⚠️ **只交易"当天"的名单（2026-10-19 定，回到"只认当天"）**：目标文件按 `generated_at` 判年龄 →
> - `0 天`（今天生成）：正常交易；
> - `1 ~ MAX_TARGET_AGE_DAYS(7) 天`：**不交易**，日志记
>   `ERROR target is NOT from today (generated ..., N day(s) old) -> REFUSING to trade this round`，
>   仓位原样不动（状态 `not-today`）；
> - `> 7 天`：**清该策略份额**并记 WARN（本机进程已经很久没出过名单了）。
>
> 也就是说**上传晚到/漏传 = 当天不交易**，而不是"悄悄用昨天那份"。代价是要盯日志里的
> `target status=`：出现 `not-today` 就说明本机没出当天的文件（见 §3.0 的时序）。

> ⚠️ **与旧 QMT 语义的一处刻意差异**：QMT 版里"文件缺失 → 清仓"是外部进程写空列表实现的；
> 这里**文件读不到/无法判定日期默认不动仓**（`MISSING_FILE_ACTION="skip"`，记 ERROR），因为最常见的原因是上传没到。
> 想恢复旧语义就把它改成 `"liquidate"`。

### 云端 → 审计（写在研究目录**根下**，扁平，无子目录）

| 文件 | 内容 |
|---|---|
| `ptrade_orders_<策略>_<YYYYMMDD>.json` | 当日计划（sells/buys/notes/**errors**）+ 该策略份额的总额/现金 + `estimated_sell_proceeds` + order_id + `target_age_days` + 幂等 `tag` |
| `ptrade_state_<策略>.json` | 已执行过的 `(日期@时刻)` 标记（跨重启幂等，保留最近 40 条）+ 上次结果 |
| `ptrade_state_positions.json` | **tracker**：每个策略持有哪些代码、多少股（多策略份额归属，见 §2 多策略表） |

> 为什么是扁平文件而不是 `ptrade_state/` 子目录：**PTrade 沙箱禁用 `os`**，没有 `os.makedirs`
> → 无法创建子目录，只能直接写在研究目录根下（见 §4.2）。

---

## 3. 部署步骤

### 3.0 ⏰ 时序必须先对齐（否则当天不交易）

名单是**本机进程写出来的**，PTrade 只是读；所以三件事必须按顺序发生：

```
本机 ptrade_target.py              09:50 邮件检查 → AI 过滤 → 写 ptrade/upload_file/target_<策略>.json
                                          （AI 预算上限 600s，所以落地时间 09:50 ~ 10:00）
        ↓  PTrade 客户端「定时上传」必须晚于上面的落地时间（源目录 = ptrade\upload_file\）
研究目录/upload_file/target_<策略>.json   ↓
        ↓  PTrade 策略 run_daily(该文件里的 trading_times) 必须晚于上传完成
云端下单
```

**当前配置下的真实数字**（`ptrade/ptrade_config.json`：`trading_times: ["10:00"]`、`email_check_offset_minutes: 10`）：

| 环节 | 时间 | 来源 |
|---|---|---|
| 邮件检查 | **09:50** | `trading_times − offset` |
| 写名单文件 | **09:50 ~ 10:00** | 邮件 + AI（预算 600s） |
| 定时上传 | **要晚于上一行** | 客户端配置（**待你确认时刻**） |
| PTrade 下单 | **要晚于上传** | 目标文件里的 `trading_times`（本机 config 是唯一来源；读不到文件时用 `DEFAULT_ORDER_TIMES`） |

- 你要的是"**盘前 sync + 开盘调仓**"：本机 `trading_times` 定 **09:20**（→ 邮件 09:10、文件 09:10~09:20）、
  客户端 **09:25** 上传、策略 `trading_times` = **09:35**（你目前在用的时刻）。这样本机是"出文件的截止时刻"，
  云端是"下单时刻"，中间隔着上传，**不能取同一个值**。
- **实况核对**：本机 `ptrade/logs/ptrade_target.log` 每天有 `upload ...` / `archive ...` 两行，按它加"上传延迟"来定下单时刻。
- 时序错了不会乱下单：云端**只交易当天文件**，非当天 → `not-today` → **不交易 + ERROR**（仓位不动）；
  连续 >7 天没有新名单才清仓。所以日志里 `target status=` 必须是 `ok`、`age_days=0`。

### 3.1 步骤

1. **本机**：PTrade 客户端 →「定时上传」：**源目录 = `...\strat\ptrade\upload_file\`**（里面是 `target_<策略>.json`，每个策略一个）+ 上传到研究目录 + **上传时刻**（见 §3.0）；确认上传次数上限（向券商确认）。
2. **本机**：跑 [ptrade_target.py](ptrade_target.py) 常驻（**替代** `qmt_stdqmt_target.py`，绝不同时跑）：
   `python ptrade_target.py`（在 `ptrade/` 目录里跑，或写在计划任务里）—— 它读同目录的 `ptrade_config.json`；
   `email_reader_config.json` 在本目录/启动目录/仓库根任一处都能找到；
   ⚠️ `ai_filter_config.json` 由 `shared/ai_fundamental_filter.py` **按启动目录**加载 → 要么从仓库根启动，要么把这两个 json 也拷进 `ptrade/` 并从 `ptrade/` 启动。
   `shared/` 里的两个模块它能自己找到（顶部有 `sys.path` 引导）。
3. **本机 → 云端**：把 [ptrade_rebalance_executor.py](ptrade_rebalance_executor.py) 上传/粘贴到 PTrade 策略编辑器，单文件即可（PTrade 不支持 import 自有包）；
   **确认 `TARGET_FILES` 列出了每个策略的文件名**（加策略/改下单时间后要重启策略）。
4. **直接实盘**（`DRY_RUN` 默认 False）。到点后看日志：`selfcheck`（平台 API 实况，含每个文件的 times/exists）+ `slice: total=.. cash=.. positions=..` + **`rebalance gate: ... -> ON/OFF`**
   （重点确认**满仓时是 OFF**）+ 计划明细（SELL/BUY）+ 每单 `@ price -> order id`。
   想先排练一天就把 `DRY_RUN` 改回 `True`（只记日志与审计，不下单）。
5. **核对**：`ptrade_orders_<策略>_<日期>.json`（含份额总额/现金、`estimated_sell_proceeds`、`notes`、`errors`、`target_age_days`）与当日成交/持仓对一下。
6. **失败兜底**：策略没跑或跑错时人工调仓（QMT 已停运，没有客户端兜底按钮了）。
7. 上线前**不需要**再管 `qmt_rebalance_executor.py`（QMT 已停运，不会消费名单）。

---

## 4. 配置项（策略文件顶部常量）

| 常量 | 默认 | 说明 |
|---|---|---|
| **`TARGET_FILES`** | `["target_low_valuation.json"]` | **策略清单**（沙箱无目录列举，只能内置）。**加策略 = 本机 config 加一条 + 这里加一行 + 重启策略** |
| `DEFAULT_ORDER_TIMES` | `["09:35"]` | 文件还没上传时的兜底下单时间；文件到位后按文件里的 `trading_times` 注册 |
| `DEFAULT_PARAMS` | `capital_ratio 1.0 / max_holdings 8 / candidate_pool_size 13 / cash_reserve_ratio 0.0125 / rebalance_threshold 0.20` | **兜底参数**；正常每个策略用自己文件里的值（`max_holdings`=等权槽位与目标市值分母；`candidate_pool_size`=池内容忍度，池外一律清掉；`rebalance_threshold`=**组合级防 churn 门限**，详见 §4.1） |
| `TARGET_DIRS` | `["upload_file", ""]` | 目标文件候选目录：先 `<研究目录>/upload_file/`，再研究目录根（防客户端拍平文件夹） |
| `TRACKER_FILE` | `ptrade_state_positions.json` | 多策略仓位归属（写在研究目录根） |
| `MAX_TARGET_AGE_DAYS` | **7** | 只交易**当天**文件；1~7 天 → `not-today` **不交易 + ERROR**；>7 天 → **清该策略份额**。见 §4.2 |
| `DRY_RUN` | **False** | False = 直接实盘；True = 排练（只记日志与审计，不下单） |
| `MISSING_FILE_ACTION` | `skip` | 目标文件**读不到/无法判定日期**时：`skip` 不交易 或 `liquidate` 清该策略份额 |
| `PRICE_MODE` | `cage` | `cage`=对手价 ±2%/0.1 且不越涨跌停；`latest`=不带限价（平台用最新价） |
| `SELL_PROTECT_AT_LIMIT_DOWN` | **True** | 卖出保护价 = `max(最新价×0.98, 跌停价)`（尽全力卖，见 §4.1.1） |
| `BUY_PROTECT_AT_LIMIT_UP` | False | True = 买入保护价直接给涨停价（参考策略的激进买法，仍受 2% 约束） |
| `MARKET_TYPE_MAIN_SH` / `_STAR` / `_SZ` / `_OTHER` | 1 / **0** / 0 / 4 | `order_market` 的 `market_type`（按板块）；科创板不通就把 `_STAR` 改 1，见 §4.1.1.1 |
| `MAX_ORDERS_PER_RUN` | 40 | 单策略计划超过就整轮放弃（防坏文件清仓） |
| `ONLY_ONCE_PER_TIME` | True | 同一 `(策略, 日期@时刻)` 只执行一次，跨重启有效 |

### 4.0 `ptrade_config.json` 的键位（**本机 `ptrade_target.py` 读的**，云端策略不读它）

**真正有读者的键**：

| 键 | 用途 |
|---|---|
| `strategies[]` | 策略清单：`name` / `stock_list_file`(兜底) / `capital_ratio` / `max_holdings` / `candidate_pool_size` / `cash_reserve_ratio` / `rebalance_threshold` / `trading_times` / `email_check_offset_minutes` —— 前六个会**原样写进 target 文件**供云端使用 |
| `stock_list_dir` + `stock_list_files` | 名单来源：生效路径 = `stock_list_dir/<stock_list_files[策略]>`，且必须与 email 配置的 `save_directory` 一致（否则启动即拒绝） |
| `log_file` | 本机日志（相对 `ptrade/` 解析） |
| `exchange_path` | 本机归档目录（默认 `archive`） |
| `ptrade_upload_path` | 客户端「定时上传」源目录（默认 `upload_file`） |
| `ptrade_upload_name_tpl` | 上传文件命名模板（默认 `target_%s.json`） |

**QMT 时代的遗留键，ptrade 代码里零引用，部署时可以直接删**：

| 遗留键 | 当年给谁用 | 现在 |
|---|---|---|
| **`account_id`** | QMT executor 的 `get_trade_detail_data(account_id, 'STOCK', ...)` | ❌ 无用：云端 `order()` 由平台绑定账户，资产/持仓走 `context.portfolio` |
| `position_tracking_file` | QMT executor 的 tracker 文件 | ❌ 无用：仓位归属改用研究目录里的 `ptrade_state_positions.json`（云端自己写） |
| `max_holdings` / `candidate_pool_size` / `cash_reserve_ratio` / `rebalance_threshold`（若同时留了旧副本） | QMT executor 从 config 读 | ⚠️ 现在**必须留**：它们是本机写进 target 文件的执行参数来源（`strategies[]` 里那四个，不是顶层） |
| `run_now` | 无（脚本只认 `--now` 命令行参数） | ❌ 无用，可删 |
| `ptrade_upload_filename`（单数旧名） | 早期单策略版 | ❌ 已作废：启动时会打 WARN，改用 `ptrade_upload_name_tpl` |
| `executor_log_file` | QMT executor 的日志 | ❌ 创建这份配置时就没抄进来 |

### 4.1 调仓语义（2026-10-15 与 QMT 执行器逐项对齐）

**核心：均仓门限是"组合级"，不是"逐票级"** —— 这是**防 churn** 的设计，**勿改成按单只票的偏离来判断**：

```
slots = max_holdings − 该策略持仓数
if slots <= 0:           -> 满仓：不做任何池内均仓（某只狂涨/狂跌都不触发）
if cash_for_buy <= 0:    -> 没多余现金：同样不做
平均市值 = (策略份额总资产 − 储备) / max_holdings     # 储备 = 份额总资产 × cash_reserve_ratio
deviation = | (策略份额现金 − 储备) / slots − 平均市值 | / 平均市值
if deviation > rebalance_threshold(20%):  -> 触发：把每只【已持仓】的池内票拉回目标市值
                                            （超配的削、低配的补，没有逐票死区）
```
> 上式里的四个参数（`max_holdings` / `cash_reserve_ratio` / `rebalance_threshold` / `capital_ratio`）
> 以及"份额总资产/份额现金"都来自**该策略自己的 target 文件**（`_strategy_view`），不是账户整体 —— 多策略下每个
> 策略只在自己那一份里做等权与均仓。
每轮都会打印这一行，便于事后核对（含 OFF 的原因）：
`rebalance gate: slots=5 cash_for_buy=323500.00 avg=64700.00 target=64187.50 deviation=0.8% -> OFF`

**触发场景**（你原始设计的意图）：平仓/池外清仓放出资金、或涨跌改变了总资产 → 让 `现金/空槽数` 与
`平均市值` 拉开 20% 以上 → 才整体归位一次。**满仓时无论个股怎么走都不交易**。

| 环节 | QMT 执行器 | PTrade 版 | 状态 |
|---|---|---|---|
| 池内均仓门限 | 组合级（上式） | 同 | ✅ 已对齐 |
| 空槽买入预算 | `per_stock = (现金−储备) / 空槽数` | 同 | ✅ |
| 手续费系数 | `min(目标, 可用) × 0.99`，逐笔 `×1.001` 递减 | 同 | ✅ |
| 买入"保护价" | `min( min(ask×1.02, ask+0.1), 涨停价 )`（不追高） | 簇子价再夹 `最新价×1.02` | ✅ |
| **卖出"保护价"** | `max( max(bid×0.98, bid−0.1), 跌停价 )` | **`max(最新价×0.98, 跌停价)` = 2% 内最狠**（见 §4.1.1） | ⚠️ 有意更狠 |
| 卖价锚 | `bid1`（不是最新价） | 估算回款用 `bid1` 推；下单保护价用 2% 下限 | ✅ |
| 价格基准取不到 | **买**：跳过该单；**卖**：退化为"不带限价"挂单 | **买卖都跳过 + ERROR**（不再发无保护市价单，见 §4.1.1） | ⚠️ 刻意更严 |
| 涨停时买入 | 不检查（ask=0 时会挂涨停价） | **跳过**（更保守） | ⚠️ 有意不对齐 |
| **ST 股** | 无特别处理（5% 幅度由涨跌停价体现） | **一律不买**：`get_stock_status(code,'ST')` 或行情名含 ST 即判定 → **记 ERROR** 并跳过该票（进日志 + 审计 `errors[]`），本轮其它委托照常 | ⚠️ 有意加严 |
| 停牌 | 完全没有检查 | `get_stock_status('HALT')` → 跳过 | ⚠️ 有意不对齐 |
| T+1 可卖量 | 用全量份额，可能超卖被拒 | 用 `enable_amount` 可卖量 | ⚠️ 有意不对齐 |
| 阶段推进 | 卖池外 → 查账户 → 门限 → 均仓 → 填空槽，**每阶段重查账户**并等成交（30s 轮询） | **一次规划**，卖出回款按估算计入预算（按将要挂出的卖价 ×0.995，因为平台不允许等成交） | ⚙️ 平台差异（PTrade 异步、无法等成交） |
| 账户口径 | 策略切片：`总资产×capital_ratio`；`现金=min(策略总额−策略持仓市值，券商可用现金×capital_ratio)`；持仓=tracker 归属 | 直接用账户值 | ⚙️ 单策略（capital_ratio=1.0）下等价；多策略需补切片 |
| 状态 | `strategy_positions.json` tracker 落盘 | 无 tracker，写 `ptrade_state/orders_*.json` 审计 | ⚙️ 设计使然 |

> 对齐范围：✅ 七项按 QMT 语义实现；⚠️ 四项是 PTrade 侧**刻意更严**（涨停不买、ST 一律不买、停牌跳过、
> 用可卖量），对齐后会去挂涨停价买单/买入 ST/卖停牌股/下超卖量，不做；⚙️ 三项是平台差异，复刻没有意义。

#### 4.1.1 委托价：市价单的"保护价"怎么给（价格笼子 + 2% 规则 + 尽全力卖出）

**两个概念别混**：
| 概念 | 含义 | 谁约束它 |
|---|---|---|
| **限价单的委托价** | 真正挂出去的价格 | 交易所**价格笼子** |
| **市价单的 `limit_price`** | 只是**保护上限/下限**，成交价由盘口决定 | 交易所的市价申报规则 + 券商"偏离现价 ≤2%"风控 |

交易所**连续竞价"价格笼子"**（沪深主板/创业板/科创板，限价申报）：

| 方向 | 允许区间 | 基准价（按顺序取） |
|---|---|---|
| 买入申报价 | ≤ **max**(基准×102%, 基准+0.1 元) | ① 即时最低卖价 ask → ② 最新成交价 → ③ 前收盘价 |
| 卖出申报价 | ≥ **min**(基准×98%, 基准−0.1 元) | ① 即时最高买价 bid → ② 最新成交价 → ③ 前收盘价 |

> 旧 PTrade 策略 `low_valuation_regression_chan_filter_1d_strategy_full_gj.py` 把
> `up_px`/`down_px`（涨停/跌停价）直接当 `limit_price`。作为**限价**是越界的；
> 作为**市价单保护价**则要看券商风控——本券商对量化订单还额外要求**不偏离现价 2%**。

**本策略的实现**（`order_market(..., limit_price=保护价)`，保护价按下列规则算）：

```
卖出保护价 = max( 最新价 × 0.98 , 跌停价 )        ← 2% 内能报的最低价 = 尽全力卖
买入保护价 = min( min(ask×1.02, ask+0.1), 最新价×1.02 )   ← 不追高，且在 2% 内
```

- **卖出"尽全力"**：保护价压到 2% 规则允许的下限（`最新价×0.98`），若个股已接近跌停则用**跌停价**
  （`max` 取高者，永不越界）。这样市价单能一路扫到 2% 以内的所有买盘，把仓位尽快清掉，
  回款进预算后买入才有空间。
- **买入不追高**：沿用 QMT 的簇子（对手价 +0.1 / +2% 取保守者），并再夹 `最新价×1.02`。
  想改成参考策略那种"直接给涨停价"的激进买法，把 `BUY_PROTECT_AT_LIMIT_UP = True` 即可
  （仍受 2% 上限约束）。
- **基准回退**：卖出保护价在拿不到最新价时退回簇子价（`bid×0.98` / `bid−0.1`），再不行才跳过。
- **三个价都取不到 → 跳过该单并记 ERROR**（不发无保护市价单）。
- **`market_type` 按市场不同**（与参考文件完全一致，已用测试比对）：
  `688xxx → MARKET_TYPE_STAR(0)`、`60xxxx → MARKET_TYPE_MAIN_SH(1)`、`00xxxx/300xxx → MARKET_TYPE_SZ(0)`、
  其它 `→ MARKET_TYPE_OTHER(4)`。四个值都是文件顶部的常量，改一行即可，不用动逻辑。
- **下单失败自动降级为"±2% 变价限价单"**：`order_market(...)` 若
  ① 不可用 / 抛异常 / 返回空 / 平台把该单判为废单（`get_order(id).status == '9'`），
  就**立刻用同一个保护价改发限价单**（`order(..., limit_price=protect)`）——
  保护价本身就是在 `[跌停价, 涨停价]` 内、且不偏离最新价 2% 的价，所以变价单同样合法。
  日志会明确写：
  `WARN order_market(688xxx, 100, market_type=0) was rejected -> retrying as a limit order at protect=12.24 (+-2% repriced, inside limit-up/down)`。
  两步都失败才记 `ERROR ... REJECTED`（审计里 `"rejected": true`）。

#### 4.1.1.1 科创板（688）下单模式怎么确认

1. **启动时**看 selfcheck 两行：
   - `has_order_market = True/False`（有没有 `order_market` 这个 API）
   - `order_mode = order_market + limit_order_retry (market_type: SH60=1 STAR688=0 SZ=0 other=4)`
2. **首次真实 688 委托时**看日志：
   - `INFO bought 688xxx ... -> order <id>` → 当前 `MARKET_TYPE_STAR` 可用；
   - `WARN order_market(688xxx ...) was rejected -> retrying as a limit order ...`
     → 该 `market_type` 不适用于科创板，把 `MARKET_TYPE_STAR` **从 0 改成 1**、重启策略再试
     （无论哪种，那一笔**都已经按 ±2% 变价限价单发出去了**，不会丢单）。
3. 想在上线前就验证，可把 `DRY_RUN = True` 跑一天：日志会打印计划（不会真下单），
   但**无法验证 market_type 是否被接受**——那个只能靠一笔真实委托，所以第 2 步才是最终确认。

> 已知局限：`order_market` 是异步的，卖出成交价/成交量当场拿不到；买入预算是按
> "卖价 ×0.995"估算的。若某笔卖单没成交/被拒，买单可能因资金不足被拒（会记 ERROR）——
> 按你的要求，这属于可接受行为（卖单必须尽力先执行）。

#### 4.1.2 其他安全闸门（不在 QMT 语义内，实盘前加）

- `DRY_RUN` 默认 **False**（直接实盘；改成 `True` 可做一次只记不下单的排练）
- **账户读数保护**：`总资产 <= 0`（接口形状不对/读到空）→ 记 ERROR 并**整轮拒绝交易**，而不是拿 `现金/空槽数` 盲买
- **名单去重**：目标名单里的重复代码只保留第一次出现（否则会被下两次单），并记 WARN + 审计里的 `dupes`
- **ST 一律不买 + 报错**：ST 出现在名单里 = 上游（12 条规则过滤）出问题 → 该票记
  **ERROR**（`ST name <code> must be bought (new slot/top-up) - upstream target list is broken; REFUSING and skipping it`）
  并跳过，绝不买入；本轮其它委托照常执行，错误同时写进审计 `errors[]`
- **ST 涨跌幅**按 5% 计算（否则 5% 限制的票在 +5% 时会被认为"没到涨停"仍去买入/卖出）

### 4.2 PTrade 沙箱硬限制（2026-10-16 实测 + 平台确认）

**平台确认可用的模块**：`pandas`、`numpy`、`enum`、`math`、`time`、**`simplejson`**、`datetime`
**被禁**：`os`、`sys`（连带 `traceback`/`tempfile`/`shutil`/`glob`/`pathlib` 这类会 import 它们的）

| 限制 | 后果 / 对策 |
|---|---|
| **禁 `os`、`sys`** | 策略只 import `datetime` + `simplejson`（**JSON 走 simplejson**，并用 `__import__("json")` 兜底，源码里不出现 `import json` 语句）；文件访问全走内建 `open()`；路径用字符串拼 `"/"`（Windows/POSIX 的 open 都认） |
| 没有 `os.makedirs` | 状态/审计文件**扁平写在研究目录根下**：`ptrade_state_<策略>.json`、`ptrade_orders_<策略>_<日期>.json` |
| 没有 `os.listdir` | **只能读固定文件名** `target_low_valuation.json` → 本机 `ptrade_target.py` 必须写这个固定名（它已经这么做了）；带时间戳的 `rebalance_*.json` **无法被发现** |
| 没有 `os.replace/os.rename` | 写文件不能原子替换 → 改为「写完再读回校验」，失败记 ERROR；幂等判断额外用当日审计文件兜底 |
| 没有 `traceback` | 异常只记 `类型 + 消息`（丢栈） |

**不需要探针**：`open()` 与上面的模块清单均已确认。仓库里那个
[ptrade_capability_probe.py](ptrade_capability_probe.py) 只是留作以后再出沙箱问题时的诊断工具，不用跑。

---

## 5. 需要跟国金确认（按重要性）

1. **「定时上传」是否开放、次数上限**（决定名单能否自动进云端）
2. 交易策略里 `get_research_path()` 读写是否被允许
3. **实盘交易**环境是否有 `run_daily(context, func, time)` 与 `order()`（回测肯定有）
4. 研究环境能否联网（若可以，邮件+AI 理论上也能搬到云端）
5. Python 版本确认（社区文档写 **3.5.2**；本策略已避开 f-string/walrus，可直接跑）

---

## 6. 已知风险

| 风险 | 说明 / 缓解 |
|---|---|
| **客户端崩溃**（历史问题） | 之前因"需客户端常驻做定时上传"而崩溃即停摆。缓解：Windows 计划任务守护进程（检测进程不存在则重启），或确认券商是否支持服务端定时拉取 |
| Python 3.5.2 | 不能 `import` 自有包、不能 f-string、单线程、有执行时长/内存上限；本策略已适配 |
| 账户数据 6 秒同步 | 下单后不要立刻重算；本策略一轮只算一次、当日同刻不重跑 |
| **持仓变 ST、源头没卖** | 若源头把 ST 从名单剔除（规则④本该如此）→ 它落到 `candidate_pool_size` 之外 → **现有第 1 步"池外清仓"自动卖掉**，无需新逻辑。若源头坏了、ST 还在名单前 13 名内，则策略**不会**自行平仓（只拒绝加仓并报 ERROR）——按"PTrade 不加策略逻辑"的边界，这是**刻意接受的残留风险**，由源头或人工处理 |
| **上传晚到/漏传** | **当天不交易**：非当天文件 → `not-today` + ERROR，仓位原样不动（不会再"悄悄用昨天那份"）；连续 >7 天没有新名单才**清该策略份额** |
| **tracker 漂移**（多策略） | 成交是异步的 → tracker 按**下单量**估算；次日 `_tracker_sync` 与券商量对账：单一持有者自动校正，**多持有者且总数不一致 → 记 ERROR 要人工处理**。日志里搜 `reconcile:` 可看全部对账动作 |
| **加了策略忘了改代码** | 云端只服务 `TARGET_FILES` 里列出的文件 → 新增策略必须**加一行 + 重启**，否则那个策略的文件永远不会被读（`selfcheck` 会打印 `target_files`，一眼可查） |
| **改了时间没重启** | `run_daily` 只在 `initialize` 注册 → 改 `trading_times` 后要**重启策略**才生效（否则沿用上次注册的时刻，日志 `run_daily registered at ...` 可核对） |
| 代码后缀 `SS`/`SH` | 各实例可能不同；`initialize` 的 selfcheck 会自动探测并打印 `sh_suffix` |
| 交易环境禁网 | 邮件/AI 永远在本机；不要把联网逻辑搬进策略 |
| 无子账户 | PTrade 不支持账户隔离 → 单策略形态（与"回到单策略"的决定一致） |
| `order()` 行情依赖 | 不带限价时若行情取不到会下单失败；`cage` 模式自带限价，失败也会记 ERROR |

---

## 7. 本地自测（上传云端之前先跑）

**① 文件名契约（本机产出 ↔ 云端读取）**

```powershell
python ptrade_target_selftest.py
```
不联网、不发邮件、不下单，只验证最容易静默出错的那一环：`ptrade_target.py` 写出的
`upload_file/target_<策略>.json` 能否被 `ptrade_rebalance_executor.py` 正确读走。
断言：`shared/` 两个模块**能被搜到且不是假函数**（`check_email_for_signal` / `ai_fundamental_filter`）、
上传目录里**只有这个策略的一份文件**、归档文件同时生成、**没有 `.tmp` 残留**、云端状态 `ok` 且代码一致、
**文件名按策略生成、`trading_times` 与执行参数确实随文件到达**、云端在 `<研究目录>/upload_file/` 下找到它、
**昨天的文件被判 `not-today`（当天专用）**。夹具：`ptrade/_selftest/target/`。

**② 云端策略逻辑**

```powershell
python ptrade_executor_selftest.py
```
用假 PTrade API 跑完整策略，**共 21 组断言**：

- 初始化/自检（`sh_suffix` 探测、**按文件里的 `trading_times` 注册 `run_daily`**、`DRY_RUN` 默认必须是 False）
- 等权数学、组合级门限（`test_full_book_never_rebalances` / `test_gate_fires_on_cash_imbalance`）
- **多策略份额**（`test_two_strategies_share_a_position`：共享代码各拿自己那份、清仓只卖自己那份、未跟踪代码给 ratio 最大者）
- 当天专用（`test_previous_day_target_is_rejected` 非当天拒绝 + ERROR / `test_too_old_target_liquidates` >7 天清该策略份额）
- 价格笼子（买不越涨停、卖不低于跌停、卖价锚 bid1 —— `test_cage_respects_limits`）
- 限价缺失 → 买单跳过（`test_buy_skipped_without_limit_up`）
- ST：**一律不买**（`test_st_is_never_bought`）+ 5% 涨跌幅（`test_st_uses_five_percent_band`）
- 名单重复代码去重、不产生重复委托（`test_duplicate_pool_codes_deduped`）
- 涨跌停/停牌过滤、整手取整、现金预算不超支
- dry-run 不下单但写审计、真实下单先卖后买、同刻幂等
- 名单缺失/过期/**非当天**（`test_not_today_target_is_skipped`）/空列表清仓、资金不足
- **只认固定文件名**（`test_only_fixed_name_is_read`：带时间戳的文件读不到，因为沙箱没有目录列举，见 §4.2）

夹具落在 `ptrade/_selftest/executor/`（gitignored），可直接查看 `ptrade_state/orders_*.json`。

**历史上自测抓出的三个真实 bug（都已修，且有断言锁死）**：

1. 池内"无持仓"的股票被步骤 2、3 各下一次单（**重复委托**）→ 空槽只由步骤 3 在 `max_holdings` 内填。
2. 移植时把"组合级防 churn 门限"错写成"**逐票**偏离门限"（个股涨 20% 就被削回目标 → 不停均仓）
   → 改回组合级（见 §4.1），并加 `test_full_book_never_rebalances` 防止回归。
3. 目标名单里的**重复代码会被下两次单** → 加载时去重（保留首次出现）并记 WARN + 审计 `dupes`。

---

## 8. 待办

- [x] ~~外部进程改代码~~ → 现在用 [ptrade_target.py](ptrade_target.py)（同流程 + **每策略一个上传文件** + **项目自包含**，见 §1.1）；它**同时**在 `ptrade/archive/` 留归档供对账。
- [ ] 本机把 `ptrade_target.py` 设为常驻（替换 `qmt_stdqmt_target.py`），并把「定时上传」源目录指到 `...\strat\ptrade\upload_file\`
- [x] ~~停用 `qmt_rebalance_executor.py`~~ → **QMT 已彻底停运（2026-10-16 收尾）**，当天最后一次调仓已完成；`.json.done` 争抢问题不复存在。
- [x] ~~下单时间放 config / 云端硬编码两处~~ → **时间与执行参数已并入每个策略的 target 文件**（云端读文件注册与取值，常量只作兜底），config 成为唯一来源
- [x] ~~多策略支持~~ → 已实现：`TARGET_FILES` 驱动 + `trading_times` 每策略自带 + tracker/`capital_ratio` 份额归属（见 §2 多策略表）
- [ ] ⏰ 定下单时刻：本机 config 的 `trading_times` 要**早于**客户端上传、上传**早于**云端下单（见 §3.0）；本机值≠云端值（中间隔着上传）
- [ ] 确认 §5 的 5 件事（多一条：客户端「定时上传」是否支持**按文件夹同步**到研究目录下的同名子目录）
- [ ] 用 `ptrade_orders_<策略>_*.json` 的审计结果与成交对账（含 tracker 的 `reconcile:` 日志）
- [x] ~~QMT 组合交易人工兜底~~ → QMT 已停运；失败按"人工调仓"处理（§3.1）
