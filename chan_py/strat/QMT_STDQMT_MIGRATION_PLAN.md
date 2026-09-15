# miniQMT → 标准 QMT 迁移计划（简化版）

> 背景：国金 miniQMT 服务即将停止，现有系统 `qmt_trader_multiple_strategies.py` 依赖外部直连 miniQMT 的 `XtQuantTrader` 通道，必须迁移到标准 QMT 客户端。
> 现状：QMT 2.0.8.300（国金），账号已开通 API 交易权限（miniQMT 已运行一年）。

## 0. 开工指引（新会话必读）

1. **本文件**：全部决策、文件协议、实施顺序以此文件为准，不参考任何历史对话。
2. **旧系统代码** `qmt_trader_multiple_strategies.py`：只读参考（拷贝函数的来源），**绝不修改**；其备份文件同理。
3. **`AGENTS.md`**：仓库运行上下文（依赖、测试方式、已知限制）。
4. **配置文件**：新系统**单配置自包含** `qmt_stdqmt_config.json`（`strategies` / `position_tracking_file` 已从旧配置拷贝并入，2026-09-01 用户决策：新旧系统零文件共享；旧 `qmt_multi_strategy_config.json` 不再被新系统读取）。
5. 按第 8 节实施顺序逐步执行，每步完成标准见第 11 节。
6. 实施中遇到与本文档冲突的判断，先停下问用户，不要自行决策。

### 0.1 会话恢复速览（2026-09-01 深夜更新 —— 历史存档，已被 §0.2 取代）

- **当前阶段**：executor 已改造为**纯定时驱动**（drType:3 定案），run_now 全流程验证通过；**明早 09:35 盘中验收 = 最后一步**（exec_on_time 定时触发 → 真实成交）
- **恢复第一步（明早 09:35 前）**：确认面板条目运行最新版 executor（21:57 部署：定时驱动版、`run_now=false`），`qmt_exchange/rebalance_low_valuation_20260902_0925.json` **已生成**（22 股，隔日文件已就绪，executor 只处理当日）
- **09:35 观察 FormulaOutput**：`exec_on_time` 触发 → `processing ... (22 stocks)` → 卖出/买入提交 → 30s 成交轮询 → tracker 更新；**若 09:35 无触发** → 兜底：删条目重建 → drType:0 → handlebar 事件驱动（§14.4-6）
- **关键结论（今日全套）**：
  - 探针 ✅ 全部通过：模式（模拟/实盘）+ API（passorder qt2）+ 买卖链路 + 回调（§13.4/§13.7）
  - executor 三处代码级坑：① init 缺 `set_account`；② `__file__` NameError → 硬编码 `SCRIPT_DIR`；③ 定时回调用 `exec_on_time`/`exec_recheck`（非魔法名）
  - **drType:3 定案（不纠结）**：21:41 引擎日志实证 drType:3 下完整 tradeModule 下单链路（含 `send order to tradeModule`）；run_now 全流程验证通过（21:41，7 笔卖出 passorder 提交 + ORDER 记录 + tracker 落盘）；21:57 晚间无 recheck tick → run_time 定时器大概率**只在交易时段调度**（8/31 盘中探针同款 60nSecond 同样从未见触发输出）→ 明早 09:35 为决定性验收
  - 外部进程闭环：config 一致性 ✅（stock_list_dir == email save_directory）、AI env key ✅、名单 22 只 ✅；**本机无 `Administrator\upload`**（名单映射指向空路径 → `--now` 会生成空文件=清仓）；email_pass 为空（非阻塞）；target 的 exchange_path/lock 为 CWD 相对路径（生产启动目录需与 executor 一致或硬化绝对化）—— **email/AI 配置路径为用户自理项**
  - 新系统单配置自包含 `qmt_stdqmt_config.json`（strategies 已并入，account_id=8880475040 测试号）
- **详见**：§13 探针实测记录（事实库）、§13.7 决定性结论、§14 当前行动状态

### 0.2 会话恢复速览（2026-09-03 收盘后更新 —— 历史存档，已被 §0.3 取代）

**当前阶段一句话**：executor 已改为 **schedule_run 纯每日定时版**（代码完成 + 本地冒烟 ✅），**唯一剩余动作 = 用户手动盘中验证** schedule_run 回调在 drType:3 下能否派发；能 → 定时验收通过；不能 → 转 §14.4-9 兜底（handlebar/drType:0）。

**恢复第一步（下一个交易日盘中，用户手动）**：
1. 部署最新 `qmt_rebalance_executor.py`（仓库文件；面板加载即加密更新 `D:\gjzq\qmt_test_gj\python\` 副本，路径 `SCRIPT_DIR`/`NEW_CONFIG_PATH` 常量已指向仓库）
2. 配置 `qmt_stdqmt_config.json`：`run_now=false`；把 `trading_times` 从当前 `["13:10"]` 改回生产时刻（如 `["09:35"]`）——注意锚点取"下一未来时刻"：盘中重启时若当天该时刻已过，任务落次日，属正常（错过当日靠 run_now 手动）
3. 重启策略（实盘模式）→ 观察注册日志 `daily task registered <t> [low_valuation] first=... seq=N`
4. 到 trading_time 观察：`exec_on_time` 触发 → `processing ... (N stocks)` → 卖出/买入提交 → 30s 轮询成交 → tracker 落盘 → **定时验收通过**（若无当日 rebalance 文件会记 `no file pending for today`，可先用 `qmt_stdqmt_target.py --now` 或手写当日文件制造真实交易，注意 --now 因本机无 `Administrator\upload` 会生成空文件=清仓，手写文件更安全）
5. 到点仍无触发（无 `exec_on_time` 日志）→ schedule_run 在 drType:3 不派发 → 执行 §14.4-9 兜底（恢复 handlebar 事件驱动 + 查条目 drType 分类；TEST_PROB 恒 drType:0 而 executor 恒 3，机制未解）

**已完成事实（本次会话）**：
- ✅ run_now 盘中真实成交验收（09-03 13:00:05-07，虚拟盘 8880475040）：`.done` 消费 22 股文件 → 7 笔池外卖出 + 5 笔 buy pool 买入提交 → 部分成交（虚拟盘模拟撮合）→ tracker 13:00:07 落盘。全链路（消费→卖出→买入→30s 轮询→tracker）在真实订单中心验证通过。**run_now = 手动执行入口（过渡运营手段），生产定时模式 run_now=false**
- ✅ **run_time 死因定案（§13.7-13/14）**：`run_time` 的 startTime 要求完整时间戳（fun.xml：示例 `"2019-10-14 13:20:00"`）；executor 传 `"09:35"` 纯时刻 → PyTimer 注册成功但永不可达 → 跨 3 日（09-01 夜/09-02 全天存活/09-03 13:10 锚点存活）**从不派发**。md §13.1"注册成功"仅指不报错，从未验证触发
- ✅ **schedule_run 采用（纯每日定时，用户决策）**：`ContextInfo.schedule_run(func, time_point, repeat_times, interval, name)`（`_PyContextInfo.py:1000`）—— time_point 为 `datetime`（str 需 `'%Y%m%d%H%M%S'`）；**已过时间点立即触发 → 交易锚点严禁过去时刻**；`repeat_times=-1` 永久 + `interval=timedelta`；返回唯一 seq；`cancel_schedule_run` 配套。executor 每策略×每 trading_time 一个每日任务；**轮询/重试/启动补查全部移除**（email/AI 先于 executor 完成、文件必就绪——"规定的时间做规定的事情"）
- ✅ executor 代码改造 + py_compile + 本地冒烟（假 ctx 断言：仅 1 个每日任务、锚点未来、`exec_recheck` 等旧机制无残留）
- ℹ️ 部署链：QMT 实际运行安装目录的加密副本（= 仓库明文的 base64 形态），与仓库不同步；改动以仓库为准，部署/测试由用户自理

**当前环境状态**：
- 配置：`account_id=8880475040`（测试虚拟盘）、`trading_times=["13:10"]`（待改回生产）、`run_now=false`
- `strategy_positions.json`：8 只持仓（13:00 轮后快照，含部分成交余量：001218 42500/300645 16200 未清、300981 60400/301167 23600/600697 42600 未补满）；下次启动 reconcile 自动纠偏
- `qmt_exchange/`：`rebalance_low_valuation_20260903_1308.json`（22 股含 000001，**未消费**，隔日即失效可清）；旧 `.done` 可清
- 生产切换（§14.4-10）：account_id 改生产号、SCRIPT_DIR/路径确认、target 路径绝对化硬化、连续 2 交易日验证

**详见**：§5（现行设计 spec）、§10（决策记录）、§12（进度）、§13.7（事实结论 1-14）、§14.4-6~9（盘中行动记录）

### 0.3 会话恢复速览（2026-09-07 盘中更新 —— 历史存档，已被 §0.4 取代）

**当前阶段一句话**：**定时验收通过** —— 2026-09-07 10:00:00.002 `schedule_run` 在 drType:3 下准时派发 `exec_on_time`，全流程真实成交 + tracker 落盘（§14.4-8 关闭）；**唯一剩余动作 = 生产切换**（§14.4-10）。

**恢复第一步（生产切换，用户手动）**：
1. 生产部署（§14.4-10）：account_id 改生产号；`trading_times` 从测试 `["10:00"]` 改回生产时刻；确认 `SCRIPT_DIR`/`NEW_CONFIG_PATH` 常量、`qmt_exchange/` 等路径（仓库内，无需动）；target 侧 `exchange_path`/lock 绝对化硬化（CWD 相对风险）
2. 外部进程 `qmt_stdqmt_target.py` 常驻自测（`--now` 注意本机无 `Administrator\upload` → 空文件=清仓）
3. 面板部署最新 `qmt_rebalance_executor.py`（**纯 ASCII**，见下规则）→ 切实盘模式重启 → 连续 2 交易日观察：文件消费 `.done`、定时触发、成交、tracker 对账无"需手动修正"

**已完成事实（本次会话 2026-09-07）**：
- ✅ **schedule_run 定时派发实证通过（10:00，§14.4-8 关闭）**：09:57:26 面板重启（部署 § ASCII 修复版）→ `daily task registered 10:00 [low_valuation] first=2026-09-07 10:00:00 seq=646` → **10:00:00.002 准时派发** `processing rebalance_low_valuation_20260907_0925.json.done (22 stocks)` → 卖出 300981 提交（余 16500 部分成交）+ 买入 000001 93100sh 全成交 / 600444 余 18600（虚拟盘撮合正常）→ tracker 10:00:02 落盘（8 只）；无编码错误/无超时/无异常。**drType:3 + schedule_run 定时驱动设计（2026-09-03 定案）最终验收通过，兜底路线（§14.4-9）无需启用**
- ✅ **executor 源文件编码 bug 定案并修复（09:21-09:35）**：症状 `SyntaxError: (unicode error) 'utf-8' codec can't decode byte 0xa1 in position 2471: invalid start byte (<string>, line 60)`。根因：面板将策略源码转存为 **GBK(ANSI/CP936)**，引擎按文件头 `# -*- coding: utf-8 -*-` cookie 以 utf-8 解码；仓库文件含 3 处 `§`(U+00A7) → GBK 编码为 `0xA1 0xEC` → 首个 0xA1 处解码失败（对 GBK 转存副本做 `compile()` 可逐字节复现同款报错，含 position 2471/line 60）。修复：3 处 `§` 全部替换为 ASCII（`sec13.7`/`sec14.4` 写法）→ 文件纯 ASCII → GBK/UTF-8 字节恒等，任何编码管线均安全。**部署规则：QMT 面板源码必须保持纯 ASCII（§13.4"全英文化"教训复现，勿再引入 §/中文/全角字符）**

**当前环境状态**：
- 配置：`account_id=8880475040`（测试虚拟盘）、`trading_times=["10:00"]`（测试改期，生产切换时改回）、`run_now=false`
- `strategy_positions.json`：8 只持仓（10:00 轮快照，含部分成交余量 300981 16500 / 600444 18600 未清，下次启动 reconcile 自动纠偏）
- `qmt_exchange/`：`rebalance_low_valuation_20260907_0925.json.done`（22 股，10:00 已消费）；旧 `.done`/`.json` 可清理

**详见**：§5（现行设计 spec）、§10（决策记录）、§12（进度）、§13.7（事实结论 1-14）、§14.4-8（本次验收记录）、§14.4-10（生产切换待办）

### 0.4 会话恢复速览（2026-09-15 更新 —— 当前权威版，新会话从这里开始）

**当前阶段一句话**：生产运行中；target `main_loop` 定时漂移 bug 已修复（§4.1）—— email 检查/生成时刻因"旧 `now` 睡眠"逐日漂移（09:10 → 09:20，跨周末日志显示 `waiting 4320 minutes`），改为绝对时间睡眠 + 跨过计划时刻即查。

**本次修复（2026-09-15，仅 target + AI 过滤模块；executor 不动）**：
- `qmt_stdqmt_target.py`：新增 `_sleep_until(target)`（按绝对时间分片睡眠，每 ≤60s 重算剩余）；email 检查 + AI 过滤等长任务后重取 `now` 再算 `_next_wake`；email 触发改为"跨过计划时刻即查、每天一次、且 trading_time 未到"（`email_check_deadline` 守卫）
- `ai_fundamental_filter.py` + `qmt_stdqmt_target.py`（§4.2）：单次模型调用 20s 超时 + 禁用 SDK 重试；降级链运行内连续失败 2 次跳过 + 成功模型粘性复用（Layer 4 复用 Layer 3 模型）；AI 到点改**部分过滤**（已处理按结论、未处理透传），仅线程卡死兜底才回退整份未过滤
- 未改动 `qmt_trader_multiple_strategies.py`（旧系统，§0 规定只读）；旧系统已停用
- 验证：`py_compile` ✅ + helper 冒烟（漂移修复）✅ + AI mock 测试（熔断/粘性/部分过滤/target 三态）✅

**生产观察点（下一个交易日）**：`[email] checking at 09:10` 应每天准时出现；`generating list ... (generation time 09:10)` 紧随其后（AI 超时则 ~09:20 完成，但次日仍 09:10 唤醒）；`waiting until` 时长不应再逐日 +10 分钟；AI 日志应显示单模型耗时（如 `[qwen3.7-max] 3.2s`），若到点则出现 `[部分过滤]`/`deadline hit` 而非整份未过滤。

**详见**：§4.1（漂移根因与修复）、§4.2（AI 提速与部分过滤）、§12（进度）

## 1. 核心原则

- **现有系统零修改**：`qmt_trader_multiple_strategies.py` 及其备份文件一行不改。
- **外部进程只做外面的事**：email 检查 + 名单读取 + AI 过滤，产出"当下该持有什么"（target 名单），不接触账户数据、不做金额计算。
- **其余全部由 QMT 系统完成**：账户查询、资金分配、目标金额、diff、下单、仓位记录全部在 QMT 客户端内置框架策略中完成（仓位控制代码改写后整体搬入）。
- **单通道 FrameworkAdapter**（QMT 内置策略框架）：不做双通道实装；**不设手动 Excel 兜底——框架通道被券商关闭即系统弃用**（用户决策）。
- 独立工具模块直接 import：`check_email_for_signal`、`ai_fundamental_filter`；交易系统函数拷贝进新文件（不 import 旧系统）。

## 2. 总体架构

```
┌─ 外部进程 qmt_stdqmt_target.py（零 API 依赖，自包含拷贝）──────────────┐
│ email检查 → 读名单(直接读email落地文件)+AI过滤 → 写 rebalance_*.json   │
│ （全量过滤名单；空=清仓；切片/金额决策归executor；单例锁）             │
└───────────────────────────────┬───────────────────────────────────────┘
                        rebalance_*.json（唯一必需文件）
┌───────────────────────────────┴───────────────────────────────────────┐
│ QMT 内置框架策略 qmt_rebalance_executor.py                            │
│ 定时触发 → 读rebalance文件+配置 → 查账户 → 资金分配/储备/阈值/算目标 →  │
│ diff → 涨跌停判断 → passorder(qt2) → 更新 strategy_positions.json       │
└───────────────────────────────────────────────────────────────────────┘
```

## 3. 文件协议（`qmt_exchange/` 共享目录）

| 文件 | 方向 | 内容 |
|---|---|---|
| `rebalance_<策略名>_<YYYYMMDD_HHMM>.json` | 外部→QMT | 策略名 + 股票代码列表（空数组 = 清仓） |

- 命名带时间戳，规避一天多次执行（09:35 / 14:35）的覆盖问题；executor 每策略取最新未处理文件，仅当日生成生效（隔日忽略）。
- **处理标记**：executor 接手文件即原子重命名为 `.done`（`os.replace`）——同时充当消费标记与防重入锁（重命名失败 = 已被处理/并发处理中，跳过）。下单成败不影响标记：失败部分记日志，靠下一场次（14:35 新文件）或次日 diff 重算补单，与旧系统"失败仅日志、下个时间点重算"一致；账户真实状态由 tracker 对账可见。
- 14 天过期/名单缺失 → 外部进程写空列表 → executor 全量卖出（语义与旧系统一致）。
- `account_status` / `execution_result` 等中间文件**不需要**（账户数据 QMT 内原生可查，归属由 tracker 维护）。
- **原子写**：外部进程写文件先写 `.tmp` 再 `os.replace`（同旧 tracker.save 逻辑），防 executor 读到半截文件。

**文件格式示例**：
```json
{
    "strategy": "low_valuation",
    "generated_at": "2026-08-27T09:35:00",
    "stocks": ["600000.SH", "000001.SZ"]
}
```
（`stocks` 为全量过滤后的名单，不做切片、不含金额；空数组 = 清仓。切片与资金决策由 executor 按配置执行。）

## 4. 外部进程 `qmt_stdqmt_target.py`

**直接 import**：`check_email_for_signal.check_email_and_save_attachment`、`ai_fundamental_filter.filter_stocks`（均带 try/except 降级，同旧系统写法）。

**拷贝自旧系统**（逻辑原样，去掉金额/账户部分）：
- `read_stock_lists`：14 天过期清仓检查、XSHE/XSHG→SZ/SH 转换、AI 过滤（**不做候选池切片**——切片是卖出/买入决策，归 executor）
- log 工具（`log_section` 等）、`check_single_instance`（独立锁 `stdqmt_target.lock`）、`is_weekday`
- email 集成：`email_check_offset_minutes` 自动计算检查时间（**默认 5 分钟**，未配置也按 5 处理）、失败不阻塞
- `main_loop` 调度骨架：trading_times + email 时间合并唤醒

**新增**：
- `_write_rebalance_files()`：在 email 检查完成后**立即**读名单 + AI 过滤 + 生成/覆盖 `rebalance_<策略>_<YYYYMMDD_HHMM>.json`（无论是否收到新附件；文件在 trading_times 之前（默认 −5 分钟）就绪。全量过滤名单，原子写：tmp + `os.replace`）
- **名单直读 email 落地文件**：用新配置 `stock_list_dir`（= email 的 `save_directory`）+ `stock_list_files`（策略名→固定附件名）映射，加载时覆盖策略的 `stock_list_file`。email 附件落地即名单文件，无拷贝环节。14 天过期语义不变（mtime = 最近一次邮件落地时间）
- **AI 过滤时间预算**：**每策略独立**，上限 10 分钟且**最迟不晚于该策略 trading_time**（executor 触发时刻）→ 到点**部分过滤**（2026-09-15 改，见 §4.2）：已处理股票按结论过滤、未处理透传，记 warning 日志；仅线程卡死兜底（预算 + 30s）才回退未过滤名单
- **AI 过滤异常**（非超时失败）→ 不生成文件、跳过本轮 + error 日志（保守语义，与旧系统"异常→清仓"不同，见决策记录）
- **启动校验**：`stock_list_dir` 与 `email_reader_config.json` 的 `save_directory` 必须一致，不一致告警并拒绝生成（防静默读错目录）
- CLI：`--now`（立即生成，不做 email 检查，同旧系统语义）/ `--config`
- **部署**：与旧系统同款常驻进程 + 单例锁，正式切换时直接替换旧常驻进程

**不出现的内容**：xtquant、tracker、账户查询、任何金额计算。

### 4.1 定时漂移修复（2026-09-15）

**症状（生产运行）**：`trading_times: ["09:35"]` + `email_check_offset_minutes: 25` → 检查/生成时刻 09:10。9/11（周五）09:10 检查正常，09:20 出现 `AI filter timeout (budget 600s)`，随后日志 `waiting ... (4320 minutes later)`；9/14（周一）实际 09:20 才唤醒，此后每天 09:20 唤醒且邮件检查被静默跳过。

**根因**：`main_loop` 在循环开头取 `now`，随后先执行 email 检查 + `_generate_due`（AI 过滤上限 600s）；再以**旧 `now`** 调 `_next_wake` 并 `time.sleep(wait_seconds)` —— 睡眠实际从 09:20 才开始，却仍睡满"09:10 → 次日 09:10"的时长 → 实际唤醒 = 目标时刻 + 循环体耗时。周五 `_next_wake` 跳过周末取周一 09:10（= 4320 分钟），实际周一 09:20 醒。邮件检查为精确分钟匹配（`current_time_str in email_check_times`），漂到 09:20 后当天检查被跳过、只生成文件（用旧附件）；此后每天循环体固定 ~10 分钟 → 永久停在 09:20，直到 09:10 前重启进程。

**修复**（仅 target；executor 不动 —— `schedule_run` 由框架按绝对 `time_point` + `timedelta(days=1)` 调度，回调耗时不影响次日触发）：
- 新增 `_sleep_until(target)`：按绝对时间分片睡眠（每 ≤60s 重算剩余），唤醒精度不再受循环体耗时影响；长任务后重取 `now` 再算 `_next_wake`
- email 触发改为"跨过计划时刻即查、每天一次"：`g <= current` 且当日未查且该时刻映射的 trading_time 尚未到达（`email_check_deadline` 守卫）→ 晚唤醒/晚启动当天补查，交易时段结束后不消耗邮件
- `qmt_trader_multiple_strategies.py`（旧系统）存在同款旧 `now` 睡眠模式，但按 §0 开工指引"只读参考、绝不修改"未改动；旧系统已停用
- 验证：`py_compile` ✅ + helper 冒烟（周末跳过 / 同日唤醒 / `_sleep_until` 精度 1ms / 漂移后补查 / 交易后不补查）✅

### 4.2 AI 调用层提速 + 部分过滤（2026-09-15）

**症状**：AI 过滤经常跑满 600s 预算（日志 `AI filter timeout (budget 600s)`），根因是降级链在"某些模型失效/变慢"时每只股票都从链头重试，且单次调用没有超时（openai SDK 默认 600s + 重试 2 次，zai 默认重试 3 次）→ 一个卡住的模型即可吃光预算；到点后 target 丢弃全部 AI 进度、整份名单未过滤放行，同时 daemon 线程继续在后台烧调用。账号 `/models` 核对：7 个配置模型全部存在，属调用级失败/变慢而非模型名失效。

**修复（P0，`ai_fundamental_filter.py` + `qmt_stdqmt_target.py`）**：
- **20s 单次调用超时**：客户端级 `LLM_CALL_TIMEOUT = 20`，`OpenAI(..., timeout=20, max_retries=0)` / `ZhipuAiClient(..., timeout=20, max_retries=0)`（覆盖 qwen/智谱/URL 搜索全部调用）
- **运行内健康记忆 + 粘性**：`_call_with_fallback` 按 `model_hint → last_good → 链中未熔断` 顺序；连续失败 2 次 → 本次运行跳过（WARN）；成功即清零并记住；Layer 4 复审传 `model_hint=model_used`，不再从头扫链
- **协作式截止 + 部分过滤**：`filter_stocks(stock_list, delay, debug, deadline, stats)` 在每只股票开跑前与 Layer 4 前检查 deadline；到点返回 `已处理按结论过滤 + 未处理透传`（保持原顺序），并打印 `[部分过滤]` 摘要；`stats` 记录 processed/qualified/deadline_hit
- **target 侧**：`_ai_filter_with_budget` 传 deadline + stats，`join(budget + 30)` 仅作线程卡死兜底（仍回退未过滤）；deadline 命中记 warning（processed/qualified/passed-through 数量）
- 异常语义不变：AI 抛异常 → 本轮不生成文件；`maintain_sources` 修复 URL 前也检查 deadline
- 验证：`py_compile` ✅ + mock（粘性/model_hint / 连续 2 次熔断 / 截止后全透传 / 卡在第 1 只后部分过滤 / 无截止行为不变 / target 部分-兜底-异常三态）✅

## 5. executor `qmt_rebalance_executor.py`（QMT 内置框架策略）

**零第三方依赖**（仅标准库 + QMT 内置 xtquant）。

**定时触发机制**（交易时间完全 config 驱动；**纯每日定时设计**，2026-09-03 定案，替代 09-01 的 run_time 方案）：
- 解析新配置各策略 `trading_times`，每策略×每时刻注册**一个 schedule_run 每日任务**（`ContextInfo.schedule_run(func, 下一未来 HH:MM, repeat_times=-1, interval=timedelta(days=1), name="{策略}_{时刻}")`），到点精确触发、无轮询
- **禁止过去时间点**：schedule_run 对已过时间点会立即执行 → 交易锚点恒取"今天若未到则今天、否则明天"
- **无重试/无启动补查**（2026-09-03 用户决策）：executor 触发时 email+AI 早已完成、rebalance 文件必已就绪；缺文件 → 本轮跳过记日志（下一场次/次日 diff 补）；重启错过当日时刻 → 不补执行，手动入口 = `run_now=true` 重启（init 立即全流程）或下一场次
- 仅处理当日生成的文件，隔日忽略
- 无 handlebar 依赖（drType:3 下 bar 循环不跑）；21:41/13:00 实证 drType:3 下 init 发出的 passorder 直达 order center（完整 tradeModule 链路、真实成交）；schedule_run 回调在 drType:3 下是否派发待盘中实证（§14.4-8，测试由用户手动完成）

**处理流程**（每策略）：原子重命名 `.done` 接管文件（**重命名失败 = 已被处理，跳过**）→ 读文件校验（**解析失败 → 跳过该策略本轮 + 告警，不交易**）→ 查资产/持仓（`get_trade_detail_data`）→ 资金分配/储备/阈值/算目标 → diff → 涨跌停判断 → `passorder(...,quickTrade=2)` → 确认成交（30s 持仓轮询）→ 更新 tracker。下单失败只记日志，不重试本轮（下一场次/次日 diff 重算补单）。

**仓位控制（从旧系统拷贝改写）**：
- `get_account_status`：资产/持仓改经框架 API 查询
- `sell_out_of_pool` / `rebalance` / `check_rebalance_and_execute` / `buy_to_fill`：金额算法原样保留，下单调用改经框架 API
- **共持股票卖出修复**：`sell_out_of_pool` / `rebalance` 的卖出量 = `broker_pos.volume − 其他策略 tracked volume`（旧系统卖 broker 全量会误卖他策略份额，趁迁移修正；`_update_tracker_after_trade` 的精确份额计算保持不变）
- `calculate_cash_allocation` / `_calculate_rebalance_targets`：原样
- `calculate_trade_price_and_volume`：金额→整手数量换算、价格笼子限价（原样迁入）
- `wait_for_order_completion` 等价物：下单后轮询持仓变化确认成交（超时 30s 常量），**确认成交后才更新 tracker**
- 候选池/买入池切片（`candidate_pool_size` / `max_holdings`）：卖出/买入决策，由 executor 执行
- `MarketUtils` 涨跌停判断（xtdata）：原样迁入，接管原外部职责

**仓位记录（tracker 搬入 executor）**：
- `StrategyPositionTracker` + `sync_with_broker` + `_update_tracker_after_trade` 整体搬入
- 成交后更新并 save（同旧格式 `strategy_positions.json`，接续旧状态）
- **路径绝对化**：`exchange_path` / `position_tracking_file` / `executor_log_file` 全部基于 executor 脚本所在目录解析为绝对路径，避免 QMT 内置环境工作目录不同导致文件写丢
- 多策略共持一只股票、孤儿持仓分配等逻辑零改动（卖出量修复除外）

**下单要点**：涨停不卖/跌停不买、卖出用可卖数量、金额换算整手（预留手续费）、资金超限按比例缩减。

**其他**：
- 配置校验复用旧 `load_config` 逻辑（capital_ratio 合计=1.0±0.0001、trading_times 格式）
- `run_now` 开关（新配置键 `run_now`，测试用：init 立即执行全流程；drType:3 下订单直达 order center（晚间被拒/废单），验证流程/逻辑/接线而非真实成交；生产置 false）

## 6. 配置

**唯一配置文件 `qmt_stdqmt_config.json`**（新系统自包含，旧系统配置零依赖；`strategies` / `position_tracking_file` 已从旧配置拷贝并入，2026-09-01 用户决策）：

```json
{
    "account_id": "8880475040",
    "log_file": "logs/stdqmt_plan.log",
    "executor_log_file": "logs/qmt_executor.log",
    "exchange_path": "qmt_exchange",
    "stock_list_dir": "C:\\Users\\Administrator\\Desktop\\upload",
    "stock_list_files": {"low_valuation": "low_valuation_stocks.json"},
    "position_tracking_file": "strategy_positions.json",
    "strategies": [
        {
            "name": "low_valuation",
            "stock_list_file": "C:\\Users\\comet\\Desktop\\low_valuation_stocks.json",
            "capital_ratio": 1.0,
            "max_holdings": 8,
            "candidate_pool_size": 13,
            "cash_reserve_ratio": 0.0125,
            "rebalance_threshold": 0.20,
            "trading_times": ["09:35"],
            "email_check_offset_minutes": 10
        }
    ],
    "run_now": false
}
```

键名说明：
| 键 | 说明 |
|---|---|
| `account_id` | executor 下单/查账户账号（标准 QMT 客户端内有效账号；测试用 8880475040 虚拟盘） |
| `log_file` | 外部进程日志 |
| `executor_log_file` | executor 日志 |
| `exchange_path` | rebalance 文件交换目录（相对路径按 executor 脚本目录解析） |
| `stock_list_dir` | = `email_reader_config.json` 的 `save_directory`（email 附件落地目录） |
| `stock_list_files` | 策略名→固定附件名；外部进程据此覆盖策略 `stock_list_file` |
| `position_tracking_file` | tracker 持仓记录（相对路径按 executor 脚本目录解析） |
| `strategies` | 策略定义（自旧配置拷贝，`capital_ratio` 合计须=1.0±0.0001） |
| `run_now` | executor 测试开关：`true` = init 立即执行全流程（drType:3 下订单直达 order center，晚间被拒/废单，验证流程/接线**非真实成交**）；生产必须 `false`（定时驱动） |

executor 内置环境无法依赖相对路径，**配置文件绝对路径以常量写在 executor 脚本顶部**（部署时按实际安装位置确认一次）。

**`.gitignore`**：`qmt_stdqmt_config.json` 与 `qmt_exchange/` 不入库。

## 7. 探针（✅ 已完成通过，结论见 §13/§14）

> 2026-09-01 实测完成。探针文件 `qmt_stdqmt_probe.py`（v11.2）已在策略交易面板跑过多轮，全部结论与原始日志记录在 §13。

结论摘要：
1. **行情**：标准 QMT 内置策略环境 **xtdata 无行情服务** → 全走框架 API（`ContextInfo.get_instrument_detail` / `get_full_tick`）
2. **框架 API**：`ContextInfo` 无 accID（账户用 `set_account`）；交易/账户函数是**模块级全局函数**（`passorder` / `get_trade_detail_data`）；委托/成交回调可用
3. **下单机制**：订单只在**实盘 bar**（`is_last_bar()==True`）之后才可能执行；策略启动回放全部历史 K 线（~40 秒），回放期下单被 skip
4. **决定性发现**：**模拟模式（`[trade]start simulation mode`）下框架订单被静默丢弃**（引擎 `Send Trading Record` 后无 `send order to tradeModule`）；**面板切实盘模式（`[trade]start trading mode`）后买卖全链路打通**（实测成交）
5. **API 选择**：`passorder(...,quickTrade=2)` 买（opType 23）/卖（opType 24）均验证成交；`order_shares` 为死路径（quickTrade=0 实盘静默吞单）；`passorder` 恒返 0，判定看 ORDER 记录而非返回值
6. **handlebar 每 ~3s 触发**：所有下单逻辑必须 barpos/一次性标志门控（v11 重复下单 16 笔教训）

**探针通过 → 按 §13.6 改造 executor（✅ 已完成 + mock 验证），下一步 QMT 虚拟盘 run_now 全流程验证 → 盘中小额实测。**

## 8. 实施顺序

1. git 提交当前工作区（`ai_fundamental_filter.py` 改动 + 本计划文档 `QMT_STDQMT_MIGRATION_PLAN.md`）
2. 创建 `qmt_stdqmt_config.json`（gitignored）+ `.gitignore` 加两行 + 建 `qmt_exchange/` 目录
3. 写外部进程 `qmt_stdqmt_target.py`
4. mock 验证：`--now` 生成 rebalance 文件，对照旧系统同输入历史日志核对名单过滤（14天/转换/AI），并确认名单路径指向 email 落地文件
5. 跑探针（第 7 节）→ 通过后写 executor（单框架适配器）
6. QMT 小额/模拟账户验证（旧系统已停；**此时新配置 `account_id` 改为模拟/小额账户号**，步骤 7 再改回生产号）
7. 正式切换：旧系统停用（文件保留），executor 常驻运行

## 9. 风险与边界

| 风险 | 缓解 |
|---|---|
| 框架通道被券商关闭 | 系统弃用（用户决策，不设手动 Excel 兜底） |
| QMT 内置 Python 无法 import 第三方库 | executor 零第三方依赖；AI 过滤/baostock 留在外部进程 |
| QMT 未启动时外部进程仍生成文件 | 无妨：当日文件等到期或次日忽略；重启错过当日时刻可 `run_now=true` 手动执行（2026-09-03 起无自动补查） |
| 外部进程宕机 | 当日无文件 → executor 不交易（与旧系统单进程宕机行为一致） |
| 切换期双重交易 | 旧系统先停，executor 才接生产账户 |
| 节假日判断 | 与旧系统一致（仅工作日），维持已知限制 |

## 10. 决策记录

- [x] 执行方式：QMT 内置框架策略（单通道 FrameworkAdapter，不做双通道实装）
- [x] 外部进程不做账户查询、不做金额计算（只产目标名单）
- [x] 仓位记录：tracker 搬进 executor（`strategy_positions.json` 格式沿用）
- [x] 行情移交 QMT 执行侧（外部不再依赖 xtdata）
- [x] 无手动 Excel 兜底：框架通道关闭即系统弃用
- [x] 切换后旧系统停用（文件保留）
- [x] 交换目录放仓库内 `qmt_exchange/` + gitignore
- [x] 配置：新文件 `qmt_stdqmt_config.json`，命名遵循旧系统惯例
- [x] **配置单文件自包含（2026-09-01）**：新旧系统**零文件共享**；旧 `qmt_multi_strategy_config.json` 不再被新系统读取，`strategies` / `position_tracking_file` 数据拷贝并入新配置（email/AI 模块 import 共享不算文件共享）
- [x] executor 触发方式：精确按配置 trading_times 触发（零偏移），文件由外部进程提前生成，非轮询
- [x] `email_check_offset_minutes` 默认 5 分钟（未配置按 5 处理），文件在 trading_time 前就绪
- [x] AI 过滤超时（每策略独立：上限 10 分钟且最迟不晚于 trading_time）→ 忽略结果、用未过滤名单（error 日志）；AI 过滤异常 → 跳过本轮不生成文件（比旧系统"异常→清仓"保守）
- [x] 文件处理标记：接手即原子重命名 `.done`（兼防重入锁）；下单成败不影响标记，失败靠下一场次/次日 diff 补单
- [x] 名单直读 email 落地文件（`stock_list_dir`/`stock_list_files` 映射，无拷贝）
- [x] 共持股票卖出量修复：迁移中修正旧系统误卖他策略份额的 bug
- [x] 探针前移：写 executor 前先验证框架通道
- [x] **魔法函数名规避（2026-09-01）**：executor 定时回调不用 `on_trading_time`/`on_recheck`（避免面板 drType:3 定时驱动分类导致 K 线循环不跑），改名 `exec_on_time`/`exec_recheck`（§13.7-11）
- [x] **魔名文本扫描调查（2026-09-01 深夜，结论已超越）**：曾假设"解析器静态扫描源码文本命中魔名字面量（注释也算）→ drType:3"；清字面量 + 重存后（21:41 运行）仍 `m_drType:3`，条目配置（indexUserConfig.xml）显示 executor 条目带 `eStrategyType="4"` + 网格模板参数而创建选项无差异 → 分类机制未完全解开，但**已被 21:41 引擎日志实证超越：drType:3 下订单全链路（含 tradeModule 行）可用，drType 不再纠结（用户决策）**（§13.7-11）
- [x] **定时驱动设计定案（2026-09-01 深夜）**：drType:3 即系统正道 —— `run_time` 定时器为唯一触发源（exec_on_time 各交易时间触发 + exec_recheck 60s 重查/首触发启动 catch-up），handlebar/`_live_ready` 依赖全部删除；21:41 引擎日志实证 drType:3 下完整 tradeModule 下单链路（含 `send order to tradeModule` 行）；收盘后订单 `废单(57)/已报(50)` 为预期行为；21:57 晚间无 recheck tick + 8/31 盘中同款定时器同样无触发输出 → **定时器大概率只在交易时段调度**，明早 09:35 为决定性验收
- [x] **删除 dry_run、只留 run_now（2026-09-01）**：测试环境无需双保险；`run_now` = init 立即执行全流程（验证流程/逻辑/接线，非真实成交），生产置 false 走定时驱动；`dry_run` 参数从 FrameworkAdapter 与配置中移除（place_order 无条件走真实 passorder）
- [x] **外部进程闭环检查（2026-09-01 深夜）**：config 一致性 ✅（stock_list_dir == email save_directory）、AI env key ✅（ZHIPU/DASHSCOPE 已设）、`ai_fundamental_filter` 导入 ✅、名单 22 只 ✅（XSHE/XSHG 格式正确）；⚠️ 本机无 `C:\Users\Administrator\Desktop\upload`（名单映射指向空路径 → `--now` 生成空文件=清仓）；⚠️ email_pass 为空（email 检查失败但非阻塞）；⚠️ target 的 `exchange_path`/lock/log 为 CWD 相对路径（启动目录与 executor 不同 → 文件写丢、闭环静默断裂；生产建议绝对化）—— **email/AI 配置路径为用户自理项（用户决策，2026-09-01）**
- [x] **run_now 盘中真实成交验收通过（2026-09-03 13:00）**：面板实盘模式 + `run_now=true` init 全流程真实成交（虚拟盘 8880475040）—— 7 笔池外卖出 + 5 笔 buy pool 买入提交，部分成交（虚拟盘模拟撮合），tracker 13:00:07 落盘；30s 轮询确认无超时。**run_now/init 路径 = 手动执行入口，可作过渡运营手段**
- [x] **定时器死因定案（2026-09-03）**：`run_time` 在此客户端**从不触发**（非"只在交易时段调度"）：09-02 条目 09:02:58 启动全天存活无 destruct → 09:35 无触发；09-03 条目 13:05:46 启动存活跨 13:10:00 锚点（bar 每分钟正常计算）→ 无 PyTimer 派发；引擎日志 PyTimer 仅存 cancel/destruct（停止时），全天零 fire 行；`exec_recheck`（60nSecond）的 PyTimer 从未出现（每条目仅一个 PyTimer，疑单槽/被覆盖）。根因 = **startTime 需完整时间戳**（fun.xml 官方契约，见 §13.7-14）；md §13.7-11"定时器只在交易时段调度"假设被证伪
- [x] **schedule_run 采用（2026-09-03，纯每日定时定案）**：executor `_register_triggers` 以 `ContextInfo.schedule_run` 替换 run_time —— 每个 trading_time 一个每日任务（首次 = **下一个未来 HH:MM**，`repeat_times=-1`、`interval=timedelta(days=1)`，名称 `{策略}_{时刻}`，日志记录 seq）。**已过时间点会立即触发 → 交易锚点严禁传过去时间**（防误交易）。**轮询/重试/启动补查机制全部移除**（用户决策 2026-09-03：executor 触发时 email+AI 流程早已完成、rebalance 文件必已就绪，只需"规定的时间做规定的事情"；缺文件 = 本轮跳过记日志，下一场次/次日 diff 补；重启错过当日时刻 → 不补执行，手动入口 = `run_now=true` 或下一场次）。代码改动 + 测试由用户手动完成（2026-09-03，§14.4-8）
- [x] **executor 源码纯 ASCII 化修复（2026-09-07）**：QMT 面板把策略源码转存 GBK(ANSI/CP936)，引擎按 cookie 以 utf-8 解码 → 文件内 3 处 `§`(U+00A7，GBK=`0xA1 0xEC`) 触发 `can't decode byte 0xa1 in position 2471 (<string>, line 60)`（compile GBK 转存副本逐字节复现）。修复：`§` → `sec` 文本，文件纯 ASCII。**部署规则：QMT 面板源码保持纯 ASCII（§13.4 全英文化教训，勿再引入非 ASCII 字符）**
- [x] **schedule_run 定时派发实证通过（2026-09-07 10:00）**：drType:3 下定时回调正常派发（注册 seq=646 → 10:00:00.002 触发，误差 2ms），executor 定时驱动设计（2026-09-03 定案）最终验收通过（§14.4-8 / 关键待确认项 6 关闭），兜底路线（§14.4-9）未启用

## 11. 每步完成标准

| 步骤 | 完成标准 |
|---|---|
| 1. 提交工作区 | `git status` 干净（`ai_fundamental_filter.py` 与本计划文档已提交），备份文件未被改动 |
| 2. 配置 + gitignore | `qmt_stdqmt_config.json` 已创建（`account_id` 正确、`stock_list_files` 映射与 email 附件名一致）；`qmt_exchange/` 已建；`.gitignore` 含新配置与 `qmt_exchange/` 两行且 `git status` 不再显示 |
| 3. 外部进程 | `qmt_stdqmt_target.py` 可运行：`--now` 正常退出，无 xtquant/账户相关代码（grep 验证）；单例锁 `stdqmt_target.lock` 生效 |
| 4. mock 验证 | `--now` 产出的 `rebalance_*.json` 格式与第 3 节示例一致（含空列表清仓路径）；14天/转换/AI 三规则分别验证通过（同输入对照旧系统历史日志）；名单路径 = email 落地文件且 mtime 随邮件更新；目录一致性校验生效；AI 过滤超时→未过滤名单+error 日志、异常→跳过不生成 两条路径验证 |
| 5. 探针 + executor | 探针四项通过且结果记录在案；executor 语法/导入通过、`run_now` 开关 + mock 验证通过；定时触发、仓位控制（含共持卖出修复）、tracker 三部分齐全；零第三方 import |
| 6. QMT 验证 | 小额/模拟账户成交一单，`.done` 标记与 tracker 更新正确；旧系统确认已停 |
| 7. 正式切换 | 旧系统停用后 executor 切生产账户常驻；连续 2 个交易日正常：rebalance 文件被消费并标记 `.done`、成交记录、tracker 对账无"需手动修正"错误 |

## 12. 进度追踪

> 更新于 2026-09-07 盘中（历史，配合 §0.3）：run_now 真实成交验收通过（§14.4-7）；run_time 从不触发已定案（startTime 需完整时间戳）；executor 改造为 **schedule_run 纯每日定时版**（代码+冒烟✅）；**定时派发实证通过（2026-09-07 10:00:00.002，§14.4-8）—— 定时验收完成**；本次同时完成 executor 源文件编码 bug 修复（§ ASCII 化）。**剩余动作 = 生产切换（§14.4-10）**。
>
> 更新于 2026-09-15（**当前权威进度版，配合 §0.4 使用**）：target 定时漂移修复（§4.1）—— email 检查/生成时刻因旧 `now` 睡眠逐日漂移（09:10 → 09:20），`_sleep_until` 绝对时间睡眠 + 跨过计划时刻即查；AI 调用层提速 + 部分过滤（§4.2）—— 20s 单次超时、降级链熔断/粘性、到点部分过滤（已处理生效 + 未处理透传）；`py_compile` + helper 冒烟 + AI mock 测试 ✅。

| 步骤 | 状态 | 说明 |
|---|---|---|
| 1. 提交工作区 | 待办 | `ai_fundamental_filter.py` 有未提交改动；计划文档（§0.3/§10/§12/§14.4-8 更新）与 executor（§ ASCII 修复）/target/probe 尚未 git add |
| 2. 配置 + gitignore | ✅ | `qmt_stdqmt_config.json` 已建（**单配置自包含**：strategies/position_tracking_file 已并入，§6）；`.gitignore` 已加；`qmt_exchange/` 已建 |
| 3. 外部进程 | 进行中 | `qmt_stdqmt_target.py` 已生成 + 自包含化（只读新配置），`py_compile` 通过；闭环前置检查完成（§14.4-5）；**2026-09-15 生产运行中发现并修复定时漂移（§4.1）+ AI 调用层提速/部分过滤（§4.2），py_compile + helper 冒烟 + AI mock 测试 ✅**；用户自理 email/AI 配置路径 |
| 4. mock 验证 | 未开始 | 用户自测；注意本机无 `Administrator\upload`（`--now` 会生成空文件=清仓），需建目录拷贝名单或对齐路径 |
| 5. 探针 + executor | **探针✅ / run_time 定时驱动❌（从不触发，定案 §13.7-13）/ run_now 真实成交✅ / schedule_run 纯每日定时改造✅ / 定时派发实证✅（2026-09-07 10:00，§14.4-8）** | executor 已改为 schedule_run 纯每日定时（无轮询/重试/补查）+ py_compile/冒烟✅；09-07 完成 § ASCII 化编码修复 + **定时实证（10:00:00.002 准时触发 → 22 股文件消费 → 卖出/买入真实提交 → tracker 落盘）**（§0.3/§14.4-8） |
| 6. QMT 验证 | ✅ 定时验收通过（2026-09-07） | run_now 验收 ✅（13:00 真实成交，§14.4-7）；**定时验收 ✅（10:00 实证，§14.4-8）**；下一步 = 生产切换（§14.4-10：换生产账户、`trading_times` 改回、target 路径绝对化、连续 2 交易日验证）；旧系统确认已停 |
| 7. 正式切换 | 未开始 | 旧系统停用后 executor 切生产账户常驻；连续 2 个交易日正常 |

**已生成文件**：
| 文件 | 角色 | 待办 |
|---|---|---|
| `qmt_stdqmt_target.py` | 外部进程（零 API 依赖，单配置） | 自测 `--now`、常驻模式；建议 `exchange_path`/lock 绝对化硬化 |
| `qmt_stdqmt_probe.py` | 探针（QMT 框架策略）v11.2 | ✅ 已完成全部验证（§13.4/§13.7）；可作为对照组策略保留 |
| `qmt_rebalance_executor.py` | executor（QMT 框架策略，schedule_run 纯每日定时版） | ✅ 2026-09-03 改造完成（py_compile + 本地冒烟 ✅）；✅ 2026-09-07 § ASCII 化编码修复 + **定时实证通过（10:00，§14.4-8）**；生产切换时再确认常量路径 |
| `qmt_stdqmt_config.json` | 唯一配置（gitignored） | 当前 account_id=8880475040 测试号、run_now=false；生产部署时改回 + 确认 `stock_list_dir` |
| `qmt_exchange/rebalance_low_valuation_20260902_0925.json` | ~~明早验收测试文件~~（2026-09-02 未测，用户无空） | 隔日失效可清理 |
| `qmt_exchange/rebalance_low_valuation_20260903_1258.json(.done)` | 09-03 run_now 验收文件（22 股，13:00 已消费） | 已完成使命，可清理 |
| `qmt_exchange/rebalance_low_valuation_20260903_1308.json` | 09-03 定时验收文件（22 股，300981→000001 替换版） | **未被消费**（13:10 定时器未触发），schedule_run 改造后可复用/清理 |
| `qmt_exchange/rebalance_low_valuation_20260907_0925.json(.done)` | **09-07 定时验收文件（22 股，10:00 已消费）** | ✅ 已完成使命，可清理 |
| `test/qmt_stdqmt_config_test.json` | 本机 mock 用（gitignored，`test/` 下） | 自测用，可删 |

**关键待确认项（探针输出）**：
1. ~~`get_trading_detail_data` 字段名~~ ✅ 已确认：`m_strInstrumentID`/`m_nVolume`/`m_nCanUseVolume`/`m_dMarketValue`/`m_dBalance`/`m_dAvailable`；总资产=`m_dBalance`
2. ~~`order_shares` 参数顺序与价格类型~~ ✅ 已确认但**弃用**：`order_shares` 为死路径（quickTrade=0 实盘 bar 静默吞单）→ 一律 `passorder(...,quickTrade=2)`
3. ~~run_time 格式~~ ✅ 3 参形式可用（`run_time(func, intervalday, time)`）；executor 用 `("1nDay", t)` / `("60nSecond", 最早交易时间)`（原实现参数颠倒已修正）
4. ~~收盘后下单~~ ✅ 实测：drType:3 下直达 order center 但被拒（`废单(57)` 或滞留 `已报(50)`，安全）；盘中链路由探针 v11/v11.2 实证
5. ❌ **`m_drType:3` + run_time 定时驱动设计被证伪（2026-09-03，详见 §13.7-13）**：drType:3 下 init→passorder 确实直达 order center（21:41/13:00 实证），但 **run_time 定时器在此客户端从不派发**（startTime 纯时刻不可达），"定时器只在交易时段调度"假设错误；改造为 schedule_run 后需盘中实证回调派发
6. ✅ **schedule_run 回调在 drType:3 下能派发（2026-09-07 10:00 实证）**：注册 `seq=646` → **10:00:00.002 准时触发** `exec_on_time`，全流程成交 + tracker 落盘（§14.4-8）；兜底路线（§14.4-9 handlebar/drType:0）无需启用

## 13. 探针实测记录（2026-08-31）

> 来源：客户端内跑探针 + 安装目录源码/文档（`D:\gjzq\qmt_test_gj\python\_PyContextInfo.py`、`config\fun.xml`、官方示例）+ 客户端引擎日志（`D:\gjzq\qmt_test_gj\userdata\log\XtClient_Formula_20260831_20260831.log`）。

### 13.1 框架事实（已确认）

- `ContextInfo` **无 accID 属性**；账户用 `ContextInfo.set_account(account_id, account_type)` 设置（类型：FUTURE/STOCK/CREDIT/HUGANGTONG/SHENGANGTONG/STOCK_OPTION/SWAP）
- 交易/账户函数为**模块级全局函数**（引擎注入，无 ContextInfo 前缀）：
  - `order_shares(stockcode, shares[, style, price], ContextInfo[, accId])` — **末参是账号**（曾误传备注，引擎日志 `accountID:probe3_buy` 坐实）；股数正=买 / 负=卖；style：LATEST/FIX/COMPETE/MARKET/HANG/SALE1-5/BUY1-5
  - `order_value(stockcode, value[, style, price], ContextInfo[, accId])` — 按金额下单，股数自动取整百
  - `passorder(opType, orderType, accountid, orderCode, prType, price, volume[, strategyName, quickTrade, userOrderId], ContextInfo)` — 股票 opType 23=买 / 24=卖；orderType 1101=股数 / 1102=金额(元) / 1113=资产比例 / 1123=可用比例；prType 11=指定价 / 5=最新价 / 6=买1档；quickTrade 0=下一bar首tick触发 / 1=实盘bar立即 / 2=无条件立即
  - `get_trade_detail_data(accountID, strAccountType, strDatatype[, strategyName])` — strDatatype：POSITION/ORDER/DEAL/ACCOUNT/TASK；返回 PythonObj 列表，属性访问
- 主推回调（策略级函数定义即可被调用）：`order_callback` / `deal_callback` / `orderError_callback(ContextInfo, passOrderInfo, msg)` / `position_callback` / `account_callback`
- 行情（框架 API）：`get_instrument_detail`（含 UpStopPrice/DownStopPrice/PreClose）、`get_full_tick`（**返回 dict**：lastPrice/askPrice/bidPrice 5档列表/askVol/bidVol/lastClose）、`get_market_data_ex(fields, stock_code, period, ...)`（返回 {code: DataFrame}）；**xtdata 在标准 QMT 无行情服务，弃用**
- `run_time(funcname, intervalday, time, exchange='SH')`：3 参形式可用（`"60nSecond"` 周期与 `"09:35"` 整点均注册成功）；第 4 参是交易所（非结束日期）

### 13.2 账户/持仓字段（实测输出，已确认）

- 账户 `CAccountDetail`：`m_strAccountID` / `m_dBalance`（≈总资产，待核对）/ `m_dAvailable`（可用资金）/ `m_dStockValue`（持仓市值）/ `m_dAssetBalance` / `m_dFundValue` — **旧系统的 `m_dAssetValue` 键不存在**，总资产字段语义待改造时用真实账户数据核对
- 持仓 `CPositionDetail`：`m_strInstrumentID`（**无后缀**，如 '600051'）/ `m_nVolume` / `m_nCanUseVolume` / `m_dMarketValue` / `m_dOpenPrice` / `m_dFloatProfit` / `m_strExchangeID`
- 委托/成交对象：`m_strOrderSysID` / `m_nVolume` / `m_dPrice` / `m_nOrderStatus` / `m_strStatus`

### 13.3 回放机制（引擎日志实证，重要）

- 策略启动**回放全部历史 K 线**：1 分钟周期约 38073 根（~1ms/根，约 40 秒）；5 分钟约 7600 根
- 回放期 `is_last_bar()==False`：quickTrade=0 委托**被 skip**（引擎日志 `passorder cp, skip ... isLastBar:false` → 返回 0）；quickTrade=2 通过检查（`Send Trading Record, passorder quick`）但**不产生客户端委托**
- **订单只在实盘 bar（`is_last_bar()==True`）之后才可能执行** — 探针 v9/v10 已实现实盘 bar 门控（v10 再加延迟 1 bar 确保进入实时模式）

### 13.4 下单返回 0 的排查历程

| 探针版本 | 状态 | 结论 |
|---|---|---|
| v1-v5 | 报错 / 零返回 | 中文源文件编码问题 → 全英文化；run_time 周期不触发（模型研究模式） |
| v6 | order_shares 返回 0 | **备注误传账号位**（引擎日志 `accountID:probe3_buy`）→ 签名修正 |
| v7 | 全 0 | 模块级 API 确认存在；账户/持仓对象结构确认 |
| v8 | 全 0 | handlebar 每分钟触发；**回放期 skip 机制发现**（引擎日志） |
| v9 | 实盘 bar 仍 0 | 15:05 **收盘后**实盘 bar（barpos=38077）qt2 发送后无后续；ORDER 空 |
| v10 | 盘中仍 0（09:31） | **模拟模式下订单被静默丢弃**：引擎 `setQuickPassorderArguments`+`Send Trading Record` 后无 `send order to tradeModule`、无委托记录；同日手动面板单（600697/600000）正常成交 → 通道本身无问题，问题在模式 |
| v11 | ✅ 打通（10:28） | **面板切实盘模式后**（`[trade]start trading mode`）买 000001 100 股全链路成交（ORDER 2614 系列）；bug：PROBE11_DONE 未置位 → handlebar 每 ~3s 触发重下单 16 笔（全部成交，虚拟盘无碍） |
| v11.2 | ✅ 卖出验证（10:35-10:37） | vS1 `passorder(24,qt2,指定价)` ✅、vS2 `order_shares(-100,FIX)` ❌（**quickTrade=0 实盘 bar 静默吞单，死路径**）、vS3 `passorder(24,qt1,prType6)` ✅ |

### 13.5 已记录但未解释的现象（明日验证时对照，勿重复排查）

- `Subscribe Trading Record ... subID = 0`（8 次运行一致）— 是否正常待盘中确认
- `userdata\users\8880475040\Config.xml` 的 `<OrderStrategys/>` 为空
- 无「程序化交易」UI 开关（用户确认该版本不存在该开关）
- 虚拟盘**手动交易正常**（用户确认）→ 模拟通道本身可用，问题在「策略框架 → 订单服务」段
- 主日志 `XtClient_20260831.log` 于 12:59 后停更（升级后日志分散到 `*_20260831_20260831.log` 系列；引擎日志在 `userdata\log\`）

### 13.7 决定性结论（2026-09-01，探针通过）

1. **模拟模式 = 框架订单唯一死因**：模拟模式下引擎走到 `setQuickPassorderArguments` + `Send Trading Record` 即止（无 `[trade]passOrder: send order to tradeModule`）；切实盘模式后全链路打通（买卖均实测成交 + `python push order/deal`）。executor **必须切实盘模式运行**。
2. **`passorder` 永远返回 0**（成交也返回 0）→ 成功判定必须看 ORDER 记录/委托面板/回调，不能看返回值。
3. **`order_shares` 死路径**：quickTrade=0 在实盘 bar 被引擎静默丢弃（vS2 证据）→ 一律用 `passorder(opType,1101,accid,code,prType,价,量,strategyName,2,userOrderId,ctx)`。
4. **`handlebar` 每 ~3s 触发**（每次数据更新）→ 任何下单逻辑必须 barpos/一次性标志门控（v11 重复下单 16 笔教训）。
5. **持仓代码无后缀**（`600051`），需按 `m_strExchangeID` 补 `SH`/`SZ` 后缀对齐 tracker。
6. **总资产=`m_dBalance`、可用资金=`m_dAvailable`**（账户输出：balance≈available+市值）。
7. **run_time 第 4 参是交易所**，3 参形式（`run_time(func, intervalday, time)`）可用。
8. 绑定品种（指数/股票）不影响下单；策略启动回放 ~40 秒。**注意（2026-09-01 深夜修订）**：drType:0 下"init 期间不得下单"成立（回放期 qt2 不产生委托，探针 v9/v10 门控依据）；**drType:3 下不成立** —— 21:41 实证 init/run_now 发出的 passorder 直达 order center（`[PYTHON PASSORDER]` → `setQuickPassorderArguments` → `[trade]passOrder: send order to tradeModule` → ORDER 记录生成）。
9. **`set_account` 是强制前置条件（2026-09-01 实测）**：引擎仅在策略代码调用 `ContextInfo.set_account(accid,'STOCK')` 后才执行 `bindTradeCallBackFunc` → 进入 `[trade]start trading mode` → 建立数据订阅 → 回放 → 实盘 bar。executor 曾漏掉此行 → 引擎停留在 `loadArgvs` 后无任何后续（无回放/无 handlebar/无定时触发），面板无报错、log 正常输出，症状隐蔽。**任何新框架策略第一行必须 set_account**（mock 测试须模拟此契约）。
10. **QMT 引擎无 `__file__`**：策略源码按 `<string>` 执行 → `os.path.dirname(os.path.abspath(__file__))` 直接 NameError。executor 的 `SCRIPT_DIR` 硬编码为 `C:\Users\comet\git\jq\chan_py\strat`（部署时按安装位置改）。
11. **drType 分类调查（2026-09-01 深夜，最终结论：不纠结）**：executor 所有运行（含改名 `exec_on_time`/`exec_recheck`、清魔名字面量、删条目重建）恒为 **`m_drType:3`（定时驱动）**：引擎绑定账户后不派发 `continueRun`（无 handlebar、无 `[trade]start X mode` 行）。探针恒为 `m_drType:0`（11 次）。曾假设解析器静态扫描源码文本命中魔名字面量（注释也算）→ 清字面量后（21:41 部署）仍 3；条目配置 `indexUserConfig.xml` 显示 executor 条目带 `eStrategyType="4"` + 网格模板参数（基准价/网格间距/止盈止损），而创建选项与 TEST_PROB 无差异 → 分类机制未完全解开。**决定性转折（21:41 引擎日志）**：drType:3 下 `run_time` 定时器是唯一触发源，而 init 发出的 passorder **直达 order center**（完整 tradeModule 链路）→ 定时驱动设计完全可行，**drType 不再纠结（用户决策）**。仅剩待实证：定时器是否只在交易时段调度（21:57 晚间无 tick，8/31 盘中同款 60nSecond 亦无触发输出 → 大概率是），明早 09:35 决定性验收。
12. **`handlebar` 只在 drType 0 下触发**：drType 3 时引擎不派发 `continueRun`（数据照算、`send model result to formula manager` 后无 `PythonFormula::continueRun`）。
13. **`run_time` 定时器从不触发（2026-09-03 定案）**：证据链 —— ① 09-02 条目 09:02:58 启动、当日无 PyTimer destruct（全天存活）→ 09:35 无触发；② 09-03 条目 13:05:46 启动（`trigger registered 13:10`）、SH000300 1 分钟 bar 每分钟正常计算、存活跨 13:10:00 锚点 → 无 PyTimer 派发（13:10:00 引擎日志仅数据模型行）；③ 引擎日志 PyTimer 只出现在条目停止时（`PyTimer cancel task / destruct ... Func = exec_on_time`），全天零 fire 行；④ `exec_recheck`（60nSecond）的 PyTimer 从未出现（每条目仅见一个 PyTimer，疑单槽/第二次注册被覆盖）；⑤ 探针 v1-v5 时代"run_time 周期不触发"即弃用此机制，本客户端从未成功触发过。**根因见 14**。
14. **定时 API 官方契约（fun.xml 实锤，2026-09-03）**：① `run_time(funcName, period, startTime)` 的 startTime 要求**完整时间戳**（示例 `"2019-10-14 13:20:00"`）；"如果要定时器立刻启动，可以设置历史的时间"；period 格式 `'5nSecond'`/`'5nDay'`/`'500nMilliSecond'`。executor 曾传 `"09:35"` 纯时刻 → 任务启动时间不可达 → 永不触发。② 成熟替代 **`ContextInfo.schedule_run(func, time_point, repeat_times=0, interval=None, name='')`**（`_PyContextInfo.py:1000`，包装为 ms 时间戳调 C++）：time_point 为 `datetime` 或 `'%Y%m%d%H%M%S'` 字符串；**设置时已过 time_point 会立即执行 func**（交易锚点必须传下一个未来时刻）；`repeat_times=-1` 永久重复（直至 `cancel_schedule_run(seq|name)` 取消）；`interval=timedelta`；返回全局唯一 seq。③ `ContextInfo.cancel_schedule_run(key)` 按任务号或组名取消（`_PyContextInfo.py:1019`）。

### 13.6 executor 改造清单（✅ 2026-09-01 已完成，mock 验证通过）

1. ✅ **删全部 xtdata**：`get_limit_price` → `ctx.get_instrument_detail`（UpStopPrice/DownStopPrice）；`is_limit_status` → `ctx.get_full_tick` lastPrice 对比；tick → `ctx.get_full_tick`（dict，`row.get(field,[0])[0]` 兼容 5 档列表）；删 `_ensure_connection`
2. ✅ **FrameworkAdapter 改模块级 API**：`query_asset` → `get_trade_detail_data(accid,'STOCK','ACCOUNT')`（总资产=`m_dBalance`、现金=`m_dAvailable`）；`query_positions` → `...'POSITION'`（`m_strInstrumentID` 无后缀 → 按 `m_strExchangeID` 补全）；`place_order` → `passorder(23/24,1101,accid,code,prType11/5,价,量,name,2,uid,ctx)`（**不用 order_shares**）
3. ✅ **提交语义**：passorder 恒返 0 → `place_order` 返回"已提交=真"，成交确认靠 30s 持仓轮询 + tracker 对账（与旧系统一致）；超时后加 ORDER 状态诊断日志（只读不改行为）
4. ✅ **账户绑定**：`RebalanceEngine.__init__` 中 `ctx.set_account(account_id,'STOCK')`（2026-09-01 补上，此前缺失导致引擎不进入交易模式，见 §13.7-9）
5. ✅ **run_time 参数修正（2026-09-01 深夜）**：`ctx.run_time("exec_on_time", "1nDay", t)`（intervalday="1nDay"、time=t）与 `run_time("exec_recheck", "60nSecond", <最早交易时间>)`（原实现把时间传进 intervalday 位、日期传进 time 位，语义颠倒）
6. ✅ **定时驱动重构（2026-09-01 深夜，替代原 bar 门控）**：删除 handlebar/`on_live_bar`/`_live_ready`/双 bar 延迟机制（drType:3 下 bar 循环不跑，全部无用）；`exec_on_time` 去守卫直接按交易时间处理；`exec_recheck` 去守卫 + 首触发启动 catch-up + 前 3 次 tick 打日志（实证定时器）；`run_now` 保留（run_now 时置 `_startup_done` 防重复 catch-up）
7. ✅ **`__file__` 规避**：`SCRIPT_DIR` 硬编码（见 §13.7-10）
8. ✅ **单配置自包含**：只读 `qmt_stdqmt_config.json`（strategies/position_tracking_file 已并入；旧配置零依赖，见 §6）
9. ✅ **mock 全管线**：注入假 `passorder`/`get_trade_detail_data`/`set_account`，断言：set_account 绑定、触发器注册、.done 消费、池外卖出/池内保留补仓/buy_to_fill、tracker 落盘（temp 脚本 `C:\Users\comet\AppData\Local\Temp\opencode\test_executor_mock.py`，可重建）

## 14. 探针行动记录（2026-09-01 已完成 ✅）

### 14.1 盘中验证（✅ 全部完成）

1. ✅ 策略面板运行 `qmt_stdqmt_probe.py`（账户 8880475040 虚拟盘，1 分钟周期）
2. ✅ 回放静默 → `[live] barpos=38136 do_back_test=False` → 下一实盘 bar 自动下单
3. ✅ 实测记录：v11 买入（10:28，ORDER 2614 系列 16 笔成交）、v11.2 卖出（10:35-10:37，ORDER 2772/2852 成交；order_shares 静默丢弃）
4. ✅ 对照组（13:27）：TEST_PROB 新建条目正常（`[trade]start trading mode` + 卖出成交 4167）→ 排除面板/环境因素

### 14.2 判定（✅ 链路打通）

- **全链路打通**：`deal_callback` 成交 + 委托面板可见 + ORDER 查询可见
- **关键变量 = 面板交易模式**：模拟模式（`[trade]start simulation mode`）框架订单不落订单中心；实盘模式（`[trade]start trading mode`）全链路正常

### 14.3 失败分支（不适用，已通过）

### 14.4 executor 盘中验证（✅ 验收完成 — 2026-09-07：run_now 真实成交 ✅ / run_time 死因定案 ✅ / schedule_run 定时派发实证 ✅ / § ASCII 编码修复 ✅）

1. ✅ 按 §13.6 改造 `qmt_rebalance_executor.py` + mock 全管线验证
2. ✅ 盘中多次运行定位代码级死因：缺 set_account（§13.7-9）→ 修复出现 `bindTradeCallBackFunc`；`__file__` NameError（§13.7-10）→ 修复加载成功；drType:3 调查（§13.7-11）→ **定时驱动设计定案，drType 不再纠结**
3. ✅ **run_now 全流程验证（21:33/21:41）**：init 直接跑完整流程成功 —— `.done` 消费（22 股）、账户查询（总资产 871.7 万）、8 持仓 reconcile、7 笔池外卖出经真实 passorder 提交（引擎日志含完整 `[PYTHON PASSORDER]` → `setQuickPassorderArguments` → `send order to tradeModule` 链路 + ORDER 记录生成）；收盘后订单 `废单(57)/已报(50)` 为预期；tracker 落盘 ✓（21:41:59）；21:33 中断版（手动停止于 30s 轮询）行为正常
4. ✅ **定时器实证（21:57，结果：晚间不触发）**：部署定时驱动版（run_now=false）→ 启动后 4.5 分钟无 `recheck tick` 日志；8/31 盘中探针同款 60nSecond 定时器（13.7MB 输出日志）同样从未见触发输出 → **结论：run_time 定时器大概率只在交易时段调度**，晚间静默为正常机制，无需改锚点（两种解释生产等价：明早 09:35 起 exec_on_time + exec_recheck 均在盘中触发）
5. ✅ **外部进程闭环检查（深夜）**：config 一致性 ✅ / AI env key ✅ / 名单 22 只 ✅；本机无 `Administrator\upload`（`--now` 会生成空文件）、email_pass 空、target 路径 CWD 相对 —— **email/AI 配置路径为用户自理项（用户决策）**
6. ✅ **09:35 定时验收未发生（09-02/09-03）→ run_time 死因定案**：09-02 条目全天存活无触发（用户无空未观察，日志为证）；09-03 条目 13:05:46 启动存活跨 13:10:00 锚点无派发（§13.7-13）；结论 = **run_time startTime 需完整时间戳，纯时刻用法不可达**（§13.7-14）
7. ✅ **run_now 盘中真实成交验收（2026-09-03 13:00:05-13:00:07）**：面板实盘模式 + `run_now=true` 重启 → init 全流程：`.done` 消费 `rebalance_low_valuation_20260903_1258.json`（22 股）→ 账户 861 万/8 持仓 → 7 笔池外卖出提交（600000/600051/600512/000001/000544/001218/300645）→ 30s 轮询 ~1s 返回（positions 8→3）→ 5 笔买入提交（300981/605189/301167/600697/600739）→ 轮询返回 → tracker 13:00:07 落盘（8 只）。成交多为**部分成交**（虚拟盘模拟撮合 + T+1 当日买入 300981 不可卖预期），无超时无异常；残余偏差由下次启动 reconcile 自愈。**结论：全链路（消费→卖出→买入→轮询→tracker）在真实订单中心验证通过**
8. ✅ **schedule_run 定时派发实证通过（2026-09-07 10:00，验收完成）**：executor `_register_triggers` 改用 `schedule_run` 注册**纯每日定时任务**（每策略×每 trading_time：首次 = 下一未来 HH:MM，`-1` + `timedelta(days=1)`；**轮询/重试/启动补查全部移除** —— email/AI 先于 executor 完成、文件必就绪；缺文件本轮跳过，重启错过当日 → run_now 手动或下一场次）；`exec_on_time` 模块级函数为回调，`run_now`/`manual_execute` 为手动入口。**当日行动记录**：① 09:21 测试先因编码错误失败 —— `SyntaxError: (unicode error) 'utf-8' codec can't decode byte 0xa1 in position 2471: invalid start byte (<string>, line 60)`；根因 = 面板将源码转存 GBK(ANSI)（09:21:28 加密副本 D: 刷新实证），引擎按 utf-8 cookie 解码，文件内 3 处 `§`(U+00A7 → GBK `0xA1 0xEC`) 首个 0xA1 处爆错（`compile(GBK转存副本,'<string>','exec')` 逐字节复现同款报错文本）→ 修复：3 处 `§` 替换为 ASCII `sec` 写法，文件纯 ASCII（GBK/UTF-8 恒等，免疫面板编码管线）② 测试改期 10:00（`qmt_stdqmt_config.json` `trading_times=["10:00"]`）③ 09:57:26 面板切实盘模式重启 → `daily task registered 10:00 [low_valuation] first=2026-09-07 10:00:00 seq=646` ④ **10:00:00.002 准时派发**：`.done` 消费 22 股文件 → reconcile（001218/300645 移除、600697/300981/301167 修正）→ 卖出 300981 73300sh（部分成交余 16500）+ 买入 000001 93100sh 全成交、600444 76100sh 部分成交余 18600（虚拟盘撮合，正常）→ tracker 10:00:02 落盘（8 只）。无编码错误、无超时、无异常；残余偏差下场/次日 diff 自愈。**drType:3 + schedule_run 定时驱动设计最终验收通过；schedule_run 回调派发不确定性关闭（兜底路线 9 无需启用）**
9. ➖ **兜底路线（§14.4-8 实证通过后无需启用，备而不删）**：若 schedule_run 曾不派发 → 恢复 handlebar 事件驱动（drType:0）——需重新加回被 §13.6-6 删除的 handlebar + barpos/一次性门控（v11 16 连单教训），并调查条目 drType 分类机制（executor 恒 drType:3 / TEST_PROB 恒 drType:0，创建入口相同，机制未解）
10. ⏳ **生产切换（下一步，§0.3 恢复第一步）**：生产部署（面板条目、account_id 改回生产号、SCRIPT_DIR/路径确认、target 路径绝对化硬化）→ 切生产 → 连续 2 交易日验证
