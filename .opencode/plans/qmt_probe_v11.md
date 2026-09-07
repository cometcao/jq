# 探针 v11 实施计划（2026-09-01，盘中框架下单链路验证）

## 背景与判定

- v10 盘中实测（09:31:03）：实盘 bar 门控✅、环境正常✅（`do_back_test=False`）、行情/账户/回调✅、**下单全 0 且委托面板完全无记录** ❌
- 手动委托面板下单（600697 卖 / 600000 买）**正常成交 + 回调推送** → 交易通道/服务器/账户层无问题
- 问题锁定在「策略框架 → 订单中心」段；新变量：策略一直跑在 `[trade]start simulation mode`，面板存在**模拟/实盘切换** → v11 切实盘模式
- 用户确认：虚拟盘交易权限不质疑（搁置券商侧排查）

## 修改文件

`C:\Users\comet\git\jq\chan_py\strat\qmt_stdqmt_probe.py`（v10 → v11），修改点：

1. **头注释**：v11 使用说明（绑 600051.SH 真实股票、面板切实盘模式、勿清日志、判定标准=客户端 ORDER 记录而非返回值）
2. **常量**：删除 `BUY_AMOUNT`；`SELL_DONE`/`BUY_DONE` → `PROBE11_DONE = [False]`
3. **删除 `_find_position`**（probe11 不再卖全仓）
4. **新增 `_order_rows()`**：`get_trade_detail_data(ACCOUNT_ID,'STOCK','ORDER')` 安全封装
5. **`probe3` → `probe11`**：顺序多变体（任一变体出现客户端 ORDER 记录即停）：
   - v1 `passorder(23,1101,acc,'000001.SZ',11,ask,100,'p11',2,'v1')` — qt2 指定价
   - v2 `passorder(23,1101,acc,'000001.SZ',5,0,100,'p11',1,'v2')` — prType5 最新价 qt1
   - v3 `passorder(23,1102,acc,'000001.SZ',6,0,2000,'p11',0,'v3')` — prType6 买1档 qt0
   - v4 `order_value('000001.SZ',2000,'LATEST',ctx,acc)` — 金额变体
   - v5 `order_shares('000001.SZ',100,'FIX',ask,ctx,acc)` — 原变体对照
   - v6 `passorder(24,1101,acc,'600051.SH',11,bid,100,'p11',2,'v6')` — 卖 100 股
   - 每个变体后 `_check()` 查 ORDER count，>0 即打印成功并停止后续变体
6. **init 新增 ORDER/DEAL 快照 dump**：验证 API 能看到手动单 1380/1451（若能看到 → ORDER 查询链路正常，v10 的 0 是真未创建）
7. **handlebar**：`SELL_DONE[0] and BUY_DONE[0]` → `PROBE11_DONE[0]`
8. 保留：`is_last_bar()` 门控、延迟 1 bar、`do_back_test`/`in_pythonworker` 诊断、三个回调、`_dump_trade_status`

## 验证

- `python -m py_compile qmt_stdqmt_probe.py`
- 语法通过即交付用户盘中运行

## 用户运行指引（随 v11 交付）

1. 策略面板新建策略选此文件，**绑定 600051.SH**（真实股票，非指数）
2. 账户 8880475040 虚拟盘，1 分钟周期
3. **模式切到实盘（非模拟）**
4. **不要清客户端日志**（引擎侧 `[PYTHON PASSORDER]` / `Send Trading Record` 证据）
5. 盘中启动，等 ~40 秒回放 → `[live]` → 下一根 bar probe11 自动执行
6. 贴回：`[live]` 行 + probe11 全部输出 + `[status]` 行 + 委托面板状态
7. 跑完我读引擎日志定位：引擎是否 `Send Trading Record`、订单中心是否落账

## 判定（v11 后）

| 结果 | 结论 |
|---|---|
| 任一变体 ORDER 记录出现/委托面板可见 | 链路打通 → 按 §13.6 改造 executor |
| 仍全 0 + 引擎日志有 Send Trading Record | 引擎→订单中心段被吞 → 实盘模式无效则回券商/注册问题（OrderStrategys） |
| 引擎日志无 passorder 行 | Python→引擎段异常 → 查 API 签名/环境 |
