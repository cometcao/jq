# -*- coding: utf-8 -*-
"""
miniQMT 每日调仓策略（实盘优化版 + 时间等待）
- 保持原有逻辑：按名单调仓 + 再平衡（双向20%偏离）
- 优化：实时数据订阅、动态订单等待、网络重试、单例保护
- 新增：带 scheduled_time 的动作将等待到指定时间再执行
"""

import json
import time
import logging
import os
import sys
import atexit
import datetime  # 新增，用于时间处理
import random
from abc import ABC, abstractmethod

try:
    from xtquant.xttrader import XtQuantTrader
    from xtquant.xttype import StockAccount
    from xtquant import xtdata, xtconstant
except ImportError:
    print("错误: 请先安装 xtquant 库")
    exit(1)

# ==================== 工具类：行情数据（强制实时）====================
class MarketUtils:
    _cache = {}

    @classmethod
    def _ensure_connection(cls, retry=3):
        """尝试重新建立 xtdata 连接"""
        for i in range(retry):
            try:
                # 任意调用一下，触发内部重连
                xtdata.get_market_data_ex(['000001.SZ'], period='1d', count=1)
                logging.info("xtdata 连接已恢复")
                return True
            except Exception as e:
                logging.warning(f"尝试重连 xtdata ({i+1}/{retry}): {e}")
                time.sleep(2)
        return False

    @classmethod
    def get_limit_price(cls, code, limit_type='high_limit', retries=3):
        cache_key = f"{code}_{limit_type}_{time.strftime('%Y%m%d')}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        for attempt in range(retries):
            try:
                detail = xtdata.get_instrument_detail(code)
                if detail is None:
                    logging.warning(f"get_instrument_detail 返回 None: {code}")
                    if attempt < retries - 1:
                        time.sleep(1)
                        continue
                    return 0.0
                if limit_type == 'high_limit':
                    price = detail.get('UpStopPrice', 0.0)
                else:
                    price = detail.get('DownStopPrice', 0.0)
                if price > 0:
                    cls._cache[cache_key] = price
                    return price
                else:
                    return 0.0
            except Exception as e:
                err_msg = str(e)
                if "无法连接xtquant服务" in err_msg:
                    logging.error(f"xtdata 连接断开，尝试重连 ({attempt+1}/{retries})")
                    if cls._ensure_connection():
                        continue
                    else:
                        logging.error(f"重连失败，放弃获取 {code} {limit_type}")
                        return 0.0
                else:
                    logging.error(f"获取{limit_type}异常 {code}: {e}")
                    if attempt < retries - 1:
                        time.sleep(2)
                        continue
                    return 0.0
        return 0.0

    @classmethod
    def is_limit_status(cls, code, limit_type='high_limit', tolerance=0.001):
        # 类似地加入重试
        limit_price = cls.get_limit_price(code, limit_type)
        if limit_price <= 0:
            return False
        # 获取当前价（可以复用 get_limit_price 逻辑，但这里简单处理）
        for attempt in range(3):
            try:
                data = xtdata.get_market_data_ex([code], period='1d', count=1)
                if code in data and data[code] is not None and not data[code].empty:
                    current = data[code]['close'].iloc[-1]
                    return abs(current - limit_price) < tolerance
                else:
                    return False
            except Exception as e:
                if "无法连接xtquant服务" in str(e) and attempt < 2:
                    cls._ensure_connection()
                    time.sleep(1)
                    continue
                else:
                    logging.error(f"判断涨跌停异常 {code}: {e}")
                    return False
        return False

# ==================== 单例运行保护 ====================
def check_single_instance():
    """防止任务计划重复执行"""
    lock_file = 'strategy.lock'
    if os.path.exists(lock_file):
        try:
            with open(lock_file, 'r') as f:
                pid = int(f.read().strip())
            if time.time() - os.path.getmtime(lock_file) < 3600:
                logging.warning("检测到另一实例可能正在运行，退出")
                sys.exit(0)
        except:
            pass
    with open(lock_file, 'w') as f:
        f.write(str(os.getpid()))
    atexit.register(lambda: os.remove(lock_file) if os.path.exists(lock_file) else None)

# ==================== Action 框架 ====================
class Action(ABC):
    def __init__(self, name, scheduled_time=None):
        self.name = name
        self.scheduled_time = scheduled_time  # 格式 "HH:MM"，如 "09:35"
    @abstractmethod
    def run(self, context): pass

class SimpleAction(Action):
    def __init__(self, name, func, scheduled_time=None):
        super().__init__(name, scheduled_time)
        self.func = func
    def run(self, context): self.func(context)

class CompositeAction(Action):
    def __init__(self, name, scheduled_time=None):
        super().__init__(name, scheduled_time)
        self.children = []
    def add(self, child): self.children.append(child); return self

class SequenceAction(CompositeAction):
    """按顺序执行所有子动作，并支持按预定时间触发"""
    def run(self, context):
        logging.info(f">>> 开始组合: {self.name}, context id: {id(context)}")
        for child in self.children:
            # 处理子动作的预定时间
            if child.scheduled_time:
                try:
                    target_hour, target_minute = map(int, child.scheduled_time.split(':'))
                    now = datetime.datetime.now()
                    target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
                    if now < target_time:
                        wait_seconds = (target_time - now).total_seconds()
                        logging.info(f"等待到预定时间 {child.scheduled_time} 执行 {child.name}，需等待 {wait_seconds:.0f} 秒")
                        time.sleep(wait_seconds)
                    else:
                        logging.info(f"预定时间 {child.scheduled_time} 已过，立即执行 {child.name}")
                except Exception as e:
                    logging.error(f"解析时间 {child.scheduled_time} 失败: {e}")
            
            # 执行子动作
            tag = f" [{child.scheduled_time}]" if child.scheduled_time else ""
            logging.info(f"--- 执行子动作: {child.name}{tag} ...")
            try:
                child.run(context)
            except Exception as e:
                logging.error(f"!!! 子动作 {child.name} 失败: {e}")
                raise
        logging.info(f"<<< 组合 {self.name} 执行完毕")

# ==================== 重试装饰器 ====================
class RetryAction(Action):
    def __init__(self, action, max_retries=3, delay=2, scheduled_time=None):
        super().__init__(f"{action.name}(重试)", scheduled_time)
        self.action = action
        self.max_retries = max_retries
        self.delay = delay

    def run(self, context):
        for attempt in range(self.max_retries):
            try:
                return self.action.run(context)
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                logging.warning(f"{self.action.name} 失败(尝试{attempt+1}): {e}")
                time.sleep(self.delay * (attempt+1))

# ==================== 动态订单等待 ====================
def wait_for_order_completion(trader, account, initial_positions, timeout=60):
    """等待持仓变化，返回新持仓字典，超时返回None"""
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(1)
        new_positions = {p.stock_code: p for p in trader.query_stock_positions(account)}
        if len(new_positions) != len(initial_positions):
            return new_positions
    return None

# ==================== 具体动作定义 ====================
def load_config(context):
    config_file = context.get('config_file', 'qmt_config.json')
    with open(config_file, encoding='utf-8') as f:
        config = json.load(f)
    log_file = config.get("log_file", "strategy.log")
    os.makedirs(os.path.dirname(log_file) or '.', exist_ok=True)
    logger = logging.getLogger()
    if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(fh)
    context['config'] = config
    logging.info("配置加载成功")

def read_stock_lists(context):
    cfg = context['config']
    with open(cfg["stock_list_file"], encoding='utf-8') as f:
        data = json.load(f)
    all_codes = [item.replace('XSHE', 'SZ').replace('XSHG', 'SH') for item in data]
    context['candidate_pool'] = all_codes[:cfg["candidate_pool_size"]]
    context['buy_pool'] = all_codes[:cfg["max_holdings"]]
    logging.info(f"候选池: {len(context['candidate_pool'])}只, 买入池: {len(context['buy_pool'])}只")

def init_trader(context):
    cfg = context['config']
    path = cfg["miniqmt_path"]  # 必须是 userdata_mini 目录
    # 随机生成 session_id
    session_id = random.randint(10000, 99999)

    # 可选：清理残留锁文件（谨慎使用，确保没有其他进程在使用）
    # lock_file = os.path.join(path, "xtquant.lock")
    # if os.path.exists(lock_file):
    #     os.remove(lock_file)
    #     logging.info("已清除残留锁文件")

    for attempt in range(3):
        try:
            trader = XtQuantTrader(path, session_id)
            trader.set_relaxed_response_order_enabled(True)  # 关键优化
            trader.start()
            time.sleep(3)
            if trader.connect() != 0:
                raise Exception(f"连接失败，错误码: {trader.connect()}")
            context['trader'] = trader
            context['account'] = StockAccount(cfg["account_id"])
            logging.info("交易客户端就绪")
            return
        except Exception as e:
            logging.error(f"初始化尝试 {attempt+1}/3 失败: {e}")
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))  # 等待时间递增

def get_account_status(context):
    trader = context['trader']
    account = context['account']
    asset = trader.query_stock_asset(account)
    if asset is None:
        raise Exception("查询资产失败")
    # 获取所有持仓，并过滤掉 volume <= 0 的记录
    raw_positions = trader.query_stock_positions(account)
    positions = {}
    for p in raw_positions:
        if p.volume > 0:   # 只保留有实际股数的持仓
            positions[p.stock_code] = p
        else:
            logging.debug(f"忽略零股持仓: {p.stock_code} volume={p.volume}")
    
    context.update({
        'total_asset': asset.total_asset,
        'cash': asset.cash,
        'positions': positions
    })
    logging.info(f"总资产: {asset.total_asset:.2f}, 现金: {asset.cash:.2f}, 有效持仓: {len(positions)}只")

def sell_out_of_pool(context):
    cfg = context['config']
    trader = context['trader']
    account = context['account']
    positions = context['positions']
    candidate = context['candidate_pool']
    
    orders_placed = False
    for code, pos in positions.items():
        if code not in candidate:
            if not MarketUtils.is_limit_status(code, 'high_limit'):
                # 直接调用，不再传入 price
                oid = place_sell_order(trader, account, code, pos.volume, "sell_out_pool")
                if oid > 0:
                    orders_placed = True
    if orders_placed:
        new_positions = wait_for_order_completion(trader, account, positions, timeout=10)
        if new_positions is not None:
            context['positions'] = new_positions
        else:
            logging.warning("Sell order wait timeout, continue")
    get_account_status(context)

def rebalance(context):
    cfg = context['config']
    trader = context['trader']
    account = context['account']
    positions = context['positions']
    total_asset = context['total_asset']
    
    reserve = total_asset * cfg["cash_reserve_ratio"]
    cash_for_stocks = total_asset - reserve
    target_per_stock = cash_for_stocks / cfg["max_holdings"]
    
    # Sell over-weighted (保持不变)
    sell_orders = False
    for code, pos in positions.items():
        if pos.market_value > target_per_stock and not MarketUtils.is_limit_status(code, 'high_limit'):
            value_sell = pos.market_value - target_per_stock
            price = pos.market_value / pos.volume
            vol_sell = int(value_sell // (price * 100)) * 100
            if vol_sell > 0:
                oid = place_sell_order(trader, account, code, vol_sell, "rebalance_sell")
                if oid > 0:
                    sell_orders = True
    
    if sell_orders:
        new_positions = wait_for_order_completion(trader, account, positions, timeout=10)
        if new_positions:
            context['positions'] = new_positions
        else:
            logging.warning("Rebalance sell wait timeout")
    
    get_account_status(context)
    
    # Buy under-weighted (使用 calculate_buy_price_and_volume)
    total_asset = context['total_asset']
    positions = context['positions']
    reserve = total_asset * cfg["cash_reserve_ratio"]
    cash_for_stocks = total_asset - reserve
    target_per_stock = cash_for_stocks / cfg["max_holdings"]
    
    buy_orders = False
    for code, pos in positions.items():
        if pos.market_value < target_per_stock and not MarketUtils.is_limit_status(code, 'low_limit'):
            value_buy = target_per_stock - pos.market_value
            # 使用 calculate_buy_price_and_volume 来计算买入价格和股数
            # 注意：这里的 target_amount 是 value_buy（需要买入的金额）
            buy_price, vol_buy = calculate_buy_price_and_volume(trader, account, code, value_buy, cfg)
            if vol_buy > 0 and buy_price is not None:
                oid = place_buy_order(trader, account, code, vol_buy, buy_price, "rebalance_buy")
                if oid > 0:
                    logging.info(f"Rebalance buy {code} {vol_buy} shares @ {buy_price:.2f} order_id:{oid}")
                    buy_orders = True
            else:
                logging.info(f"Skipping rebalance buy for {code} due to price/volume calculation failure")
    
    if buy_orders:
        wait_for_order_completion(trader, account, positions, timeout=10)
    
    get_account_status(context)

def check_rebalance_and_execute(context):
    cfg = context['config']
    positions = context['positions']
    total_asset = context['total_asset']
    cash = context['cash']
    
    current_holdings = len(positions)
    slots = cfg["max_holdings"] - current_holdings
    if slots <= 0:
        # 无空位时，没有买入需求，也就不触发基于剩余资金的再平衡
        return
    
    reserve = total_asset * cfg["cash_reserve_ratio"]
    cash_for_buy = cash - reserve
    if cash_for_buy <= 0:
        logging.warning("可用买入资金不足，无需再平衡")
        return
    
    avg_alloc = cash_for_buy / slots  # 计划买入的平均资金
    target_per_stock = total_asset / cfg["max_holdings"]  # 目标平均市值（总资产/总仓位）
    
    deviation = abs(avg_alloc - target_per_stock) / target_per_stock
    if deviation > cfg["rebalance_threshold"]:
        logging.info(f"触发再平衡: 计划平均资金 {avg_alloc:.2f}, 目标平均市值 {target_per_stock:.2f}, 偏离 {deviation:.1%}")
        rebalance(context)

def buy_to_fill(context):
    cfg = context['config']
    trader = context['trader']
    account = context['account']
    positions = context['positions']
    buy_pool = context['buy_pool']
    total_asset = context['total_asset']
    cash = context['cash']
    
    current_codes = set(positions.keys())
    slots = cfg["max_holdings"] - len(current_codes)
    if slots <= 0:
        return
    
    reserve = total_asset * cfg["cash_reserve_ratio"]
    buy_cash = cash - reserve
    if buy_cash <= 0:
        logging.warning("Insufficient cash to buy")
        return
    
    candidates = [c for c in buy_pool if c not in current_codes][:slots]
    if not candidates:
        return
    
    per_stock = buy_cash / len(candidates)
    
    for code in candidates:
        buy_price, vol = calculate_buy_price_and_volume(trader, account, code, per_stock, cfg)
        if vol > 0 and buy_price is not None:
            oid = place_buy_order(trader, account, code, vol, buy_price, "buy_new")
            if oid > 0:
                logging.info(f"Buy order placed for {code}: {vol} shares @ {buy_price:.2f} order_id:{oid}")
            else:
                logging.error(f"Failed to place buy order for {code}")
        else:
            logging.info(f"Skipping {code} due to price/volume calculation failure")
            

def close_trader(context):
    if 'trader' in context:
        context['trader'].stop()
        logging.info("交易客户端关闭")

# ==================== 构建策略 ====================
InitSequence = SequenceAction("初始化")
InitSequence.add(SimpleAction("加载配置", load_config))

TradeSequence = SequenceAction("交易流程")
TradeSequence.add(SimpleAction("读取股票列表", read_stock_lists, "09:20")) \
             .add(RetryAction(SimpleAction("初始化交易客户端", init_trader), scheduled_time="09:35")) \
             .add(SimpleAction("获取账户状态", get_account_status)) \
             .add(SimpleAction("卖出清单外股票", sell_out_of_pool)) \
             .add(SimpleAction("检查再平衡", check_rebalance_and_execute)) \
             .add(SimpleAction("买入新股", buy_to_fill)) \
             .add(SimpleAction("关闭客户端", close_trader))

RootStrategy = SequenceAction("每日调仓策略")
RootStrategy.add(InitSequence).add(TradeSequence)



# ==================== 封装的下单函数 ====================
def calculate_buy_price_and_volume(trader, account, code, target_amount, cfg):
    """
    根据盘口价格和涨停价，计算符合“价格笼子”的买入价格和股数
    返回: (buy_price, buy_volume) 或 (None, 0) 表示无法买入
    """
    # 1. 获取涨停价（作为价格上限）
    high_limit = MarketUtils.get_limit_price(code, 'high_limit')
    if high_limit <= 0:
        logging.warning(f"Cannot get high limit price for {code}, skip")
        return None, 0

    # 2. 获取当前盘口价格（用于计算价格笼子上限）
    try:
        tick = xtdata.get_full_tick([code])
        if code not in tick or tick[code] is None:
            logging.warning(f"Cannot get tick data for {code}")
            return None, 0
        
        # 获取卖一价
        ask_price = tick[code].get('askPrice', [0])[0]
        if ask_price <= 0:
            ask_price = tick[code].get('lastPrice', 0)
        
        if ask_price <= 0:
            logging.warning(f"Cannot get valid price for {code}, ask_price={ask_price}")
            return None, 0
        
        # 3. 计算价格笼子上限：min(卖一价*102%, 卖一价+0.1)
        cage_limit = max(ask_price * 1.02, ask_price + 0.1)
        # 最终买入价格取“笼子上限”和“涨停价”的较小值
        buy_price = min(cage_limit, high_limit)
        
        # 4. 计算可买股数（预留1%资金缓冲）
        safety_factor = 0.99
        max_amount = target_amount * safety_factor
        volume = int(max_amount // (buy_price * 100)) * 100
        
        if volume <= 0:
            logging.info(f"Insufficient funds to buy one lot of {code}")
            return None, 0
        
        # 5. 资金校验：确保总金额不超可用现金
        asset = trader.query_stock_asset(account)
        if asset is None:
            logging.error(f"Query asset failed for {code}")
            return None, 0
        
        available_cash = asset.p_enable_balance
        required_cash = volume * buy_price * 1.001  # 含0.1%手续费预估
        
        if required_cash > available_cash:
            logging.warning(f"Cash insufficient for {code}: required {required_cash:.2f} > available {available_cash:.2f}")
            # 重新计算股数
            volume = int((available_cash * safety_factor) // (buy_price * 100)) * 100
            if volume <= 0:
                return None, 0
        
        return buy_price, volume
        
    except Exception as e:
        logging.error(f"Failed to calculate price for {code}: {e}")
        return None, 0

def place_sell_order(trader, account, code, volume, remark=""):
    """卖出委托（对手方最优价格）"""
    if volume <= 0:
        return None
    oid = trader.order_stock(
        account, code, xtconstant.STOCK_SELL, volume,
        xtconstant.MARKET_PEER_PRICE_FIRST, 0, remark
    )
    if oid > 0:
        logging.info(f"Sell {code} {volume} shares @ market peer price, order_id:{oid}")
    else:
        logging.error(f"Sell order failed {code} error_code:{oid}")
    return oid

def place_buy_order(trader, account, code, volume, price=None, remark=""):
    """
    买入委托（使用 order_stock）
    - 如果 price 不为 None，则按指定价格限价买入（涨停价）
    - 如果 price 为 None，则按对手价快速成交
    """
    if volume <= 0:
        return None
    if price is not None:
        # 限价单
        price_type = xtconstant.FIX_PRICE
        order_price = price
    else:
        # 对手价（快速成交）
        price_type = xtconstant.MARKET_PEER_PRICE_FIRST
        order_price = 0

    oid = trader.order_stock(
        account, code, xtconstant.STOCK_BUY, volume,
        price_type, order_price, remark
    )
    if oid > 0:
        action = f"限价 {price:.2f}" if price is not None else "对手价"
        logging.info(f"Buy {code} {volume} shares @ {action} order_id:{oid}")
    else:
        logging.error(f"Buy order failed {code} error_code:{oid}")
    return oid

# ==================== 主函数 ====================
def is_weekday(date):
    """判断日期是否为周一至周五（0=周一，4=周五，5=周六，6=周日）"""
    return date.weekday() < 5

def run_strategy_once():
    """执行一次完整的策略（包括内部 scheduled_time 等待）"""
    context = {}
    try:
        RootStrategy.run(context)
    except Exception as e:
        logging.exception("策略执行失败")
    else:
        logging.info("策略执行成功")

def main_loop(run_now=False):
    check_single_instance()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[logging.StreamHandler()])
    logging.info("miniQMT 每日调仓策略 (常驻调度版) 启动")

    if run_now:
        logging.info("立即执行模式，执行一次策略后退出")
        run_strategy_once()
        return

    while True:
        now = datetime.datetime.now()
        # 计算下一个工作日 09:00（从当前时间开始找）
        next_run = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run += datetime.timedelta(days=1)
        while not is_weekday(next_run.date()):
            next_run += datetime.timedelta(days=1)

        wait_seconds = (next_run - now).total_seconds()
        logging.info(f"等待至 {next_run} (等待 {wait_seconds/3600:.1f} 小时)")
        try:
            time.sleep(wait_seconds)
        except KeyboardInterrupt:
            logging.info("程序终止")
            sys.exit(0)

        # 到达目标时间，执行策略
        logging.info("时间到，开始执行策略")
        run_strategy_once()
        # 执行完后自动进入下一次循环，重新计算下一个目标时间

if __name__ == "__main__":
    run_now = "--now" in sys.argv
    main_loop(run_now)