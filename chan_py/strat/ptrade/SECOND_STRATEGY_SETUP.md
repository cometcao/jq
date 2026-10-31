# 接入第二个策略（邮件信号）——本机两侧配置清单

> 这份是**你自己部署用**的操作清单，配合 [SIGNAL_API.md](SIGNAL_API.md)（发给朋友的契约）使用。
> 路径按你的实际部署填；代码侧只需要改 **1 行常量**（`TARGET_FILES`）+ 重启策略。

## 0. 数据流（现状，不需要改代码）

```
朋友的策略  --邮件(TTC2 + ttc2_stocks.json)-->  本机 ptrade_target.py
                                             │ ① 拉信并保存附件
                                             │ ② 读附件 -> 校验/归一(仅 XSHG/XSHE)
                                             │ ③ 12 条规则 AI 合规过滤
                                             │ ④ 生成 upload_file/target_<name>.json
                                             ▼
                                  客户端定时上传 -> PTrade 研究目录
                                             ▼
                              云端 ptrade_rebalance_executor.py 按该文件的时点/参数下单
```

## 0. 先只测管线（**不改 `ptrade_config.json`**，云端也不会碰）

只想验证"朋友的邮件 → 附件落地 → 生成 `target_ttc2.json` → 上传到服务器"这一段时，
**不需要**给策略登记 `capital_ratio`（也就不会触发老策略减仓），用一次性演练入口：

```powershell
cd <仓库>\ptrade
python ptrade_target.py --pipeline-test ttc2
# 附件已经在 save_directory 里、只想校验+生成文件：
python ptrade_target.py --pipeline-test ttc2 --list-file "C:\Users\...\Desktop\upload\ttc2_stocks.json"
```

它只做四件事：

1. 拉一次邮箱（主题含 `TTC2`）并保存附件 —— 与正式流程同一个函数；
2. 用**同一套校验**读附件（格式 / 方言 / 去重 / 条目合法性）；
3. 写 `upload_file/target_ttc2.json`，内容带 `"pipeline_test": true`，**不含**
   `capital_ratio / max_holdings / trading_times` 等实盘参数；
4. 按序号打印每只票，方便你和朋友核对顺序。

**为什么绝对安全**：不在 `ptrade_config.json` 里 → 本机不调度、不分配资金；
不在云端 `TARGET_FILES` 里 → `initialize` 不会给它注册 `run_daily`，永远不会下单。

期望日志：

```
========== pipeline test: ttc2 (nothing is registered, nothing will trade) ==========
[ttc2] list file expected at: ...\upload\ttc2_stocks.json
[ttc2] list loaded: 15 code(s), 0 dropped
[ttc2] OK: 15 usable code(s), order preserved
[ttc2]    1. 600519.XSHG
...
[ttc2] wrote ...\upload_file\target_ttc2.json (15 stocks, pipeline_test=true)
```

失败时明确告诉你卡在哪一步（退出码 2）：

| 输出 | 含义 | 处理 |
|---|---|---|
| `FAIL: no attachment at ...` | 邮件没到 / 主题不含 `TTC2` / 附件名不对 | 让朋友按 [SIGNAL_API.md](SIGNAL_API.md) 重发 |
| `FAIL: list unusable (stale_list)` | 附件不是今天写入的 | 重新拉信（该命令会先拉一次） |
| `N invalid entr(ies) dropped` | 全部条目非法 | 检查代码格式 |

**验证"已上传到 PTrade 服务器"**：等客户端定时上传跑一次（或手动点一次上传），然后在服务器确认

```
/home/fly/notebook/upload_file/target_ttc2.json
```
里面有 `"pipeline_test": true` 和今天的 `generated_at`；云端日志**不会**出现任何 ttc2 的下单记录。

> 演练文件会留在 `upload_file/` 一起上传，无副作用；正式登记该策略后，下一次 09:25 的生成会把它
> **覆盖**成带真实参数的版本。想要干净也可以手动删掉。

---

## 1. `shared/email_reader_config.json`（收信侧，两个策略共用）

只需要把朋友的主题关键字加进 `target_subject` 数组（**已支持数组，无需改代码**）：

```json
{
    "imap_server": "imap.163.com",
    "email_user": "17317768857@163.com",
    "email_pass": "***",
    "save_directory": "C:\\Users\\...\\Desktop\\upload",
    "target_subject": ["TTC1", "TTC2"],
    "run_time": "09:15"
}
```

- `TTC1` = 你现在的策略，`TTC2` = 朋友的策略（**约定给朋友的固定关键字，别改**）。
- 匹配是**子串**匹配：两个关键字不能互为子串；建议就用 `TTC2`。
- 每次拉信会把**所有**匹配主题的最新未读邮件的附件存进 `save_directory`（同一目录，靠**文件名**区分策略）。
- 附件名必须是 `ttc2_stocks.json`（朋友那边固定）。

## 2. `ptrade/ptrade_config.json`（调仓/生成侧）

两个策略各一条。**`capital_ratio` 之和必须 = 1.0**（进程启动会校验，不满足直接拒绝启动）；
**停用（`enabled: false`）的策略不计入这个合计**，可以写 0。

先试运行（推荐第一步）：把 ttc2 设成 `enabled: false` + `capital_ratio: 0`，
`low_valuation` 保持 `1.0` 不变 —— 这样管线每天照常出文件、上传，**服务器端完全无视**，老策略份额不受影响：

```json
        {
            "name": "ttc2",
            "enabled": false,
            "capital_ratio": 0,
            "max_holdings": 6,
            "candidate_pool_size": 13,
            "cash_reserve_ratio": 0.0125,
            "rebalance_threshold": 0.20,
            "trading_times": ["09:35", "10:00"],
            "email_check_offset_minutes": 10,
            "ai_filter": false
        }
```

正式启用时：`"enabled": true`、给个真实比例（例如 0.3），**同时把 `low_valuation` 从 1.0 降到 0.7**，
两个比例合计回到 1.0，然后**重启 PTrade 策略**。

完整示例（已启用、比例 0.7 / 0.3）：

```json
{
    "log_file": "logs/ptrade_target.log",
    "exchange_path": "archive",
    "ptrade_upload_path": "upload_file",
    "ptrade_upload_name_tpl": "target_%s.json",
    "stock_list_dir": "C:\\Users\\...\\Desktop\\upload",
    "stock_list_files": {
        "low_valuation": "low_valuation_stocks.json",
        "ttc2": "ttc2_stocks.json"
    },
    "strategies": [
        {
            "name": "low_valuation",
            "enabled": true,
            "capital_ratio": 0.7,
            "max_holdings": 8,
            "candidate_pool_size": 13,
            "cash_reserve_ratio": 0.0125,
            "rebalance_threshold": 0.20,
            "trading_times": ["09:35"],
            "email_check_offset_minutes": 10
        },
        {
            "name": "ttc2",
            "enabled": true,
            "capital_ratio": 0.3,
            "max_holdings": 6,
            "candidate_pool_size": 13,
            "cash_reserve_ratio": 0.0125,
            "rebalance_threshold": 0.20,
            "trading_times": ["09:35", "10:00"],
            "email_check_offset_minutes": 10,
            "ai_filter": false
        }
    ]
}
```

要点：

| 键 | 说明 |
|---|---|
| `stock_list_files` | 策略名 → 附件文件名；会用 `stock_list_dir` 拼成绝对路径覆盖 `stock_list_file` |
| `capital_ratio` | 账户份额；**启用中的策略合计必须 1.0**；每策略的下单额 = `账户总资产 × ratio`；停用策略可写 0 且不计入合计 |
| `trading_times` | **可以有多个**（= 一天多个调仓时点）；每个时点都是独立一轮，幂等标记是 `日期@时:分` |
| `email_check_offset_minutes` | 拉信时刻 = 每个 `trading_time` 往前推 N 分钟（09:35 − 10 → 09:25） |
| `max_holdings` | 该策略的持仓格数（朋友策略建议 6~8） |
| `candidate_pool_size` | 池内保留数；朋友的名单建议 ≥ 这个数（否则会空槽） |
| **`enabled`** | **`false` = 服务器端彻底无视这个策略**（不下单、不清仓、不看名单年龄）；`capital_ratio` 可写 **0**，且**不计入 1.0 的合计** → 加一个停用策略**不影响**在用策略的份额。不写 = `true` |
| **`ai_filter`** | **`false` = 跳过我们内置的 12 条规则 AI 合规过滤**，名单原样使用（朋友自己把关）；不写该键 = `true`（保持现有策略行为）。必须是 true/false 布尔值 |

## 3. 云端策略（唯一的一行代码改动）

`ptrade/ptrade_rebalance_executor.py` 顶部：

```python
TARGET_FILES = ["target_low_valuation.json", "target_ttc2.json"]
```

改完**重启 PTrade 策略**（`initialize` 里按每个文件的 `trading_times` 注册 `run_daily`）。
文件还不存在时不会报错：该文件对应的时点会用默认值注册，到点只记
`target status=missing -> skip`，不会下单。

**如果该文件里写着 `"enabled": false`**：
- `initialize` 直接**不注册** `run_daily`，日志 `DISABLED (enabled=false in the target file) -> no run_daily registered`；
- 即使被手动触发，`_run` 也会在**年龄/清仓判断之前**返回：
  `target says enabled=false -> this strategy is DISABLED, the server ignores it completely`。

所以"加进 `TARGET_FILES` + `enabled: false`"是**最安全的预演姿态**：服务器认得出这个策略，但一个动作都不做。

## 4. 上线前必须知道的三个影响

1. **`capital_ratio` 一改，老策略下一轮会立刻减仓。**
   例如 `low_valuation` 从 1.0 → 0.7：它的份额从 100% 降到 70%，多余的 30% 会被判定为超配 →
   **下一轮卖掉约 30% 的持仓**（正常行为，但你要有心理准备；第一次最好放在你盯盘的日子）。
   → 预演阶段用 `enabled: false` + `capital_ratio: 0`，老策略仍是 1.0，**完全不受影响**。
2. **两个策略共用一个账户，靠 tracker 归属份额。**
   首次运行时，账户里已有的持仓会被"未跟踪 → 归给 `capital_ratio` 最大的策略"；
   想干净起步，可以先把老策略的持仓按目标跑一轮再做比例调整，或接受一次对账噪音。
3. **朋友的名单过期不会"沿用"**：附件必须是**当天**写入的，否则当天不生成文件 → 云端看到非当天文件
   → 记 ERROR 并**不交易**（`LIST_MUST_BE_TODAY = True`）。这是刻意的，避免拿昨天的信号当今天用。

## 5. 上线检查清单

- [ ] `shared/email_reader_config.json` 的 `target_subject` 含 `TTC2`
- [ ] `save_directory` == `ptrade_config.json` 的 `stock_list_dir`（不一致进程会拒绝启动）
- [ ] 启用中的策略 `capital_ratio` 合计 1.0（**停用策略可写 0、不计入**）
- [ ] 朋友的附件名严格是 `ttc2_stocks.json`
- [ ] `python ptrade_target.py --email` 跑一次，确认日志出现两封邮件、两个附件都保存
- [ ] `python ptrade_target.py --now` 跑一次，确认 `upload_file/` 里出现
      `target_low_valuation.json` 与 `target_ttc2.json` 两个文件
- [ ] 云端 `TARGET_FILES` 已加 `target_ttc2.json` 并重启
- [ ] 次日检查云端日志：`run start ... strategy=ttc2 ...` + `slice: ... ratio=0.3`

## 6. 常见异常对照

| 日志 | 含义 / 处理 |
|---|---|
| `list file does not exist: ...ttc2_stocks.json` | 附件没收到或文件名不对（朋友改名了） |
| `list file was last written on ... (NOT today)` | 今天没收到新邮件（或附件没被覆盖）→ 当天不交易，符合预期 |
| `N invalid entr(ies) dropped from the list` | 朋友发了非法代码（如 `600739` 没后缀）→ 那几条被丢弃，其余照用 |
| `list has no usable code after validation` | 名单全废 → 当天不生成文件 |
| `capital_ratio sum ... must equal 1.0` | 两个策略比例没配平，进程拒绝启动 |
| 云端 `target is NOT from today` | 本机没生成今天的文件（邮件缺失/附件过期），仓位不动 |
