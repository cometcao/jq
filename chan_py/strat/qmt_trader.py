# -*- coding: utf-8 -*-
"""
miniQMT 每日调仓策略（实盘优化版 · 无报警）
- 保持原有逻辑：按名单调仓 + 再平衡（双向20%偏离）
- 优化：实时数据订阅、动态订单等待、网络重试、单例保护
"""

import json
import time
import logging
import os
import sys
import atexit
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
    """实盘行情工具（实时获取，带缓存）"""
    _cache = {}
    
    @classmethod
    def get_limit_price(cls, code, limit_type='high_limit'):
        """
        获取指定股票的涨停价或跌停价
        :param code: 股票代码，格式如 '000001.SZ' 或 '600000.SH'
        :param limit_type: 'high_limit' 或 'low_limit'
        :return: 价格（浮点数），获取失败返回 0.0
        """
        cache_key = f"{code}_{limit_type}_{time.strftime('%Y%m%d')}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]
        
        try:
            # 确保数据已下载（避免首次获取为空）
            xtdata.download_history_data(code, period='1d', start_time='', end_time='')
            
            # 获取最新日线数据（不传 subscribe 参数）
            data = xtdata.get_market_data_ex(
                [code],
                period='1d',
                count=1,
                dividend_type='front_ratio'
            )
            
            if code in data and data[code] is not None and not data[code].empty:
                price = data[code][limit_type].iloc[-1]
                cls._cache[cache_key] = price
                return price
        except Exception as e:
            logging.error(f"获取{limit_type}异常 {code}: {e}")
        return 0.0

    @classmethod
    def is_limit_status(cls, code, limit_type='high_limit', tolerance=0.001):
        """判断股票是否处于涨跌停状态"""
        price = cls.get_limit_price(code, limit_type)
        if price <= 0:
            return False
        try:
            # 获取当前收盘价（也可用最新价，但日线足够）
            data = xtdata.get_market_data_ex(
                [code],
                period='1d',
                count=1,
                dividend_type='front_ratio'
            )
            if code in data and data[code] is not None and not data[code].empty:
                current = data[code]['close'].iloc[-1]
                return abs(current - price) < tolerance
        except Exception as e:
            logging.error(f"判断涨跌停异常 {code}: {e}")
        return False

# ==================== 单例运行保护 ====================
def check_single_instance():
    """防止任务计划重复执行"""
    lock_file = 'strategy.lock'
    if os.path.exists(lock_file):
        try:
            with open(lock_file, 'r') as f:
                pid = int(f.read().strip())
            # 检查进程是否存在（Windows兼容简化：仅检查文件修改时间）
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
        self.scheduled_time = scheduled_time
    @abstractmethod
    def run(self, context): pass

class SimpleAction(Action):
    def __init__(self, name, func, scheduled_time=None):
        super().__init__(name, scheduled_time)
        self.func = func
    def run(self, context): self.func(context)

class SequenceAction(Action):
    def __init__(self, name, scheduled_time=None):
        super().__init__(name, scheduled_time)
        self.children = []
    def add(self, child): self.children.append(child); return self
    def run(self, context):
        logging.info(f">>> 开始 {self.name}")
        for child in self.children:
            tag = f" [{child.scheduled_time}]" if child.scheduled_time else ""
            logging.info(f"--- 执行 {child.name}{tag}")
            child.run(context)
        logging.info(f"<<< 结束 {self.name}")

# ==================== 重试装饰器 ====================
class RetryAction(Action):
    def __init__(self, action, max_retries=3, delay=2):
        self.action = action
        self.max_retries = max_retries
        self.delay = delay
        super().__init__(f"{action.name}(重试)")
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
def wait_for_order_completion(trader, account, initial_positions, timeout=10):
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
    config_file = context.get('config_file', 'qmt_config_test.json')
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
    """带重试的初始化"""
    cfg = context['config']
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            trader = XtQuantTrader(cfg["miniqmt_path"], 2)
            account = StockAccount(cfg["account_id"])
            trader.start()
            time.sleep(3)
            if trader.connect() != 0:
                raise Exception(f"连接失败，错误码: {trader.connect()}")
            context['trader'] = trader
            context['account'] = account
            logging.info("交易客户端就绪")
            return
        except Exception as e:
            logging.error(f"初始化尝试 {attempt+1}/{max_attempts} 失败: {e}")
            if attempt == max_attempts - 1:
                raise
            time.sleep(5 * (attempt+1))

def get_account_status(context):
    trader = context['trader']
    account = context['account']
    asset = trader.query_stock_asset(account)
    if asset is None:
        raise Exception("查询资产失败")
    positions = {p.stock_code: p for p in trader.query_stock_positions(account)}
    context.update({
        'total_asset': asset.total_asset,
        'cash': asset.cash,
        'positions': positions
    })
    logging.info(f"总资产: {asset.total_asset:.2f}, 现金: {asset.cash:.2f}, 持仓: {len(positions)}只")

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
                price = MarketUtils.get_limit_price(code, 'low_limit')
                if price > 0:
                    trader.order_stock_async(account, code, xtconstant.STOCK_SELL, pos.volume,
                                             xtconstant.FIX_PRICE, price, '卖出清单外')
                    logging.info(f"卖出 {code} {pos.volume}股 @ {price:.2f}")
                    orders_placed = True
    
    if orders_placed:
        new_positions = wait_for_order_completion(trader, account, positions, timeout=10)
        if new_positions is not None:
            context['positions'] = new_positions
        else:
            logging.warning("卖出订单等待超时，继续执行")
    
    get_account_status(context)  # 重新获取最新状态

def rebalance(context):
    cfg = context['config']
    trader = context['trader']
    account = context['account']
    positions = context['positions']
    total_asset = context['total_asset']
    
    reserve = total_asset * cfg["cash_reserve_ratio"]
    cash_for_stocks = total_asset - reserve
    target_per_stock = cash_for_stocks / cfg["max_holdings"]
    
    # 卖出超额的
    sell_orders = False
    for code, pos in positions.items():
        if pos.market_value > target_per_stock and not MarketUtils.is_limit_status(code, 'high_limit'):
            value_sell = pos.market_value - target_per_stock
            price = pos.market_value / pos.volume
            vol_sell = int(value_sell // (price * 100)) * 100
            if vol_sell > 0:
                limit_price = MarketUtils.get_limit_price(code, 'low_limit')
                if limit_price > 0:
                    trader.order_stock_async(account, code, xtconstant.STOCK_SELL, vol_sell,
                                             xtconstant.FIX_PRICE, limit_price, '再平衡卖出')
                    logging.info(f"再平衡卖出 {code} {vol_sell}股")
                    sell_orders = True
    
    if sell_orders:
        new_positions = wait_for_order_completion(trader, account, positions, timeout=10)
        if new_positions:
            context['positions'] = new_positions
        else:
            logging.warning("再平衡卖出等待超时")
    
    get_account_status(context)
    
    # 补仓不足的
    total_asset = context['total_asset']
    positions = context['positions']
    reserve = total_asset * cfg["cash_reserve_ratio"]
    cash_for_stocks = total_asset - reserve
    target_per_stock = cash_for_stocks / cfg["max_holdings"]
    
    buy_orders = False
    for code, pos in positions.items():
        if pos.market_value < target_per_stock and not MarketUtils.is_limit_status(code, 'low_limit'):
            value_buy = target_per_stock - pos.market_value
            price = pos.market_value / pos.volume if pos.volume > 0 else MarketUtils.get_limit_price(code, 'high_limit')
            vol_buy = int(value_buy // (price * 100)) * 100
            if vol_buy > 0:
                limit_price = MarketUtils.get_limit_price(code, 'high_limit')
                if limit_price > 0:
                    trader.order_stock_async(account, code, xtconstant.STOCK_BUY, vol_buy,
                                             xtconstant.FIX_PRICE, limit_price, '再平衡补仓')
                    logging.info(f"再平衡补仓 {code} {vol_buy}股")
                    buy_orders = True
    
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
        return
    
    reserve = total_asset * cfg["cash_reserve_ratio"]
    cash_for_buy = cash - reserve
    if cash_for_buy <= 0:
        return
    
    avg_alloc = cash_for_buy / slots
    
    if current_holdings > 0:
        avg_market = sum(p.market_value for p in positions.values()) / current_holdings
    else:
        avg_market = (total_asset * (1 - cfg["cash_reserve_ratio"])) / cfg["max_holdings"]
    
    if abs(avg_alloc - avg_market) > avg_market * cfg["rebalance_threshold"]:
        logging.info(f"触发再平衡: 平均分配资金 {avg_alloc:.2f}, 平均市值 {avg_market:.2f}, 偏离 {abs(avg_alloc-avg_market)/avg_market:.1%}")
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
        logging.warning("现金不足，无法买入")
        return
    
    candidates = [c for c in buy_pool if c not in current_codes][:slots]
    if not candidates:
        return
    
    per_stock = buy_cash / len(candidates)
    for code in candidates:
        price = MarketUtils.get_limit_price(code, 'high_limit')
        if price <= 0:
            continue
        vol = int(per_stock // (price * 100)) * 100
        if vol > 0:
            trader.order_stock_async(account, code, xtconstant.STOCK_BUY, vol,
                                     xtconstant.FIX_PRICE, price, '买入新股')
            logging.info(f"买入 {code} {vol}股 @ {price:.2f}")

def close_trader(context):
    if 'trader' in context:
        context['trader'].stop()
        logging.info("交易客户端关闭")

# ==================== 构建策略 ====================
InitSequence = SequenceAction("初始化")
InitSequence.add(SimpleAction("加载配置", load_config, "09:00"))

TradeSequence = SequenceAction("交易流程")
TradeSequence.add(SimpleAction("读取股票列表", read_stock_lists, "09:20")) \
             .add(RetryAction(SimpleAction("初始化交易客户端", init_trader, "09:35"))) \
             .add(SimpleAction("获取账户状态", get_account_status)) \
             .add(SimpleAction("卖出清单外股票", sell_out_of_pool)) \
             .add(SimpleAction("检查再平衡", check_rebalance_and_execute)) \
             .add(SimpleAction("买入新股", buy_to_fill)) \
             .add(SimpleAction("关闭客户端", close_trader))

RootStrategy = SequenceAction("每日调仓策略")
RootStrategy.add(InitSequence).add(TradeSequence)

# ==================== 主函数 ====================
def main():
    # 单例保护
    check_single_instance()
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[logging.StreamHandler()])
    logging.info("="*50)
    logging.info("miniQMT 每日调仓策略 (实盘优化版)")
    logging.info(f"启动时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    context = {}
    try:
        RootStrategy.run(context)
    except Exception as e:
        logging.exception("策略执行失败")
        # 可根据需要在此处添加其他报警方式（如日志监控）
    else:
        logging.info("策略执行成功")
    logging.info("="*50)

if __name__ == "__main__":
    main()