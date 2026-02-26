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
    """实盘行情工具（使用 get_instrument_detail 获取涨跌停价）"""
    _cache = {}
    
    @classmethod
    def get_limit_price(cls, code, limit_type='high_limit'):
        """
        获取指定股票的涨停价或跌停价
        :param code: 股票代码，格式如 '000001.SZ' 或 '600000.SH'
        :param limit_type: 'high_limit' 对应涨停价，'low_limit' 对应跌停价
        :return: 价格（浮点数），获取失败返回 0.0
        """
        cache_key = f"{code}_{limit_type}_{time.strftime('%Y%m%d')}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]
        
        try:
            # 获取合约详细信息
            detail = xtdata.get_instrument_detail(code)
            
            if detail is None:
                logging.warning(f"get_instrument_detail 返回 None: {code}")
                return 0.0
            
            # 根据类型返回对应价格
            if limit_type == 'high_limit':
                price = detail.get('UpStopPrice', 0.0)
            elif limit_type == 'low_limit':
                price = detail.get('DownStopPrice', 0.0)
            else:
                price = 0.0
            
            if price and price > 0:
                cls._cache[cache_key] = price
                return price
            else:
                logging.warning(f"{code} 的 {limit_type} 为 0 或不存在")
                return 0.0
                
        except Exception as e:
            logging.error(f"获取{limit_type}异常 {code}: {e}")
            return 0.0

    @classmethod
    def is_limit_status(cls, code, limit_type='high_limit', tolerance=0.001):
        """判断股票是否处于涨跌停状态"""
        limit_price = cls.get_limit_price(code, limit_type)
        if limit_price <= 0:
            return False
        
        try:
            # 获取当前收盘价（也可用最新价）
            data = xtdata.get_market_data_ex(
                [code],
                period='1d',
                count=1,
                dividend_type='front_ratio'
            )
            if code in data and data[code] is not None and not data[code].empty:
                current = data[code]['close'].iloc[-1]
                is_limit = abs(current - limit_price) < tolerance
                if is_limit:
                    logging.info(f"{code} 处于{limit_type}状态: 当前价 {current:.3f}, 限价 {limit_price:.3f}")
                return is_limit
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
                    # 改为同步下单 order_stock
                    oid = trader.order_stock(
                        account, code, xtconstant.STOCK_SELL, pos.volume,
                        xtconstant.FIX_PRICE, price, '卖出清单外'
                    )
                    if oid > 0:
                        logging.info(f"卖出 {code} {pos.volume}股 @ {price:.2f} 订单号:{oid}")
                        orders_placed = True
                    else:
                        logging.error(f"卖出下单失败 {code} 错误码:{oid}")
    
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
                    # 同步下单卖出
                    oid = trader.order_stock(
                        account, code, xtconstant.STOCK_SELL, vol_sell,
                        xtconstant.FIX_PRICE, limit_price, '再平衡卖出'
                    )
                    if oid > 0:
                        logging.info(f"再平衡卖出 {code} {vol_sell}股 订单号:{oid}")
                        sell_orders = True
                    else:
                        logging.error(f"再平衡卖出下单失败 {code} 错误码:{oid}")
    
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
                    # 同步下单买入
                    oid = trader.order_stock(
                        account, code, xtconstant.STOCK_BUY, vol_buy,
                        xtconstant.FIX_PRICE, limit_price, '再平衡补仓'
                    )
                    if oid > 0:
                        logging.info(f"再平衡补仓 {code} {vol_buy}股 订单号:{oid}")
                        buy_orders = True
                    else:
                        logging.error(f"再平衡补仓下单失败 {code} 错误码:{oid}")
    
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
    logging.info(f"当前持仓代码: {current_codes}, 剩余仓位: {slots}")

    if slots <= 0:
        logging.info("slots <= 0，无需买入")
        return

    reserve = total_asset * cfg["cash_reserve_ratio"]
    buy_cash = cash - reserve
    logging.info(f"保留现金: {reserve:.2f}, 可用买入资金: {buy_cash:.2f}")

    if buy_cash <= 0:
        logging.warning("可用买入资金不足，无法买入")
        return

    candidates = [c for c in buy_pool if c not in current_codes]
    logging.info(f"候选买入股票（未持仓）: {candidates}")

    stocks_to_buy = candidates[:slots]
    if not stocks_to_buy:
        logging.info("无可买入的股票")
        return

    per_stock = buy_cash / len(stocks_to_buy)
    for code in stocks_to_buy:
        price = MarketUtils.get_limit_price(code, 'high_limit')
        logging.info(f"股票 {code} 涨停价获取结果: {price}")
        if price <= 0:
            logging.warning(f"获取 {code} 涨停价失败，跳过")
            continue
        vol = int(per_stock // (price * 100)) * 100
        logging.info(f"计算可买股数: {vol}")
        if vol > 0:
            # 改用同步下单函数 order_stock
            oid = trader.order_stock(
                account, code, xtconstant.STOCK_BUY, vol,
                xtconstant.FIX_PRICE, price, '买入新股'
            )
            if oid > 0:
                logging.info(f"买入下单成功: {code} {vol}股 @ {price:.2f} 订单号:{oid}")
            else:
                logging.error(f"买入下单失败 {code} 错误码:{oid}")
        else:
            logging.info(f"{code} 资金不足以买一手")
            

def close_trader(context):
    if 'trader' in context:
        context['trader'].stop()
        logging.info("交易客户端关闭")

# ==================== 构建策略 ====================
InitSequence = SequenceAction("初始化")
InitSequence.add(SimpleAction("加载配置", load_config))

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
    check_single_instance()
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[logging.StreamHandler()])
    logging.info("="*50)
    logging.info("miniQMT 每日调仓策略 (实盘优化版 + 时间等待)")
    logging.info(f"启动时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    context = {}
    try:
        RootStrategy.run(context)
    except Exception as e:
        logging.exception("策略执行失败")
    else:
        logging.info("策略执行成功")
    logging.info("="*50)

if __name__ == "__main__":
    main()