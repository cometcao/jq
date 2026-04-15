# -*- coding: utf-8 -*-
"""
miniQMT 每日调仓策略（多策略版）
- 支持多策略：同一账户按 capital_ratio 分配资金，仓位彼此隔离
- 通过 strategy_positions.json 跟踪各策略持仓归属
- 保留：Action 框架、scheduled_time 等待、单例保护、网络重试
- 用法: python qmt_trader_multiple_strategies.py [--now] [--config xxx.json]
"""

import json
import time
import logging
import os
import sys
import atexit
import datetime
import random
from abc import ABC, abstractmethod


# ==================== 自定义异常类 ====================
class MarketDataException(Exception):
    """市场数据获取异常"""
    pass

class OrderExecutionException(Exception):
    """订单执行异常"""
    pass


# ==================== 工具类：订单处理 ====================
class OrderUtils:
    """订单处理工具类，提取重复的订单处理逻辑"""
    
    @staticmethod
    def safe_place_order(trader, account, code, volume, is_buy=True, price=None, remark=""):
        """
        安全下单：订单失败时只记录日志，不抛出异常
        返回: order_id (成功) 或 None (失败)
        """
        try:
            if is_buy:
                return place_buy_order(trader, account, code, volume, price, remark)
            else:
                return place_sell_order(trader, account, code, volume, remark)
        except Exception as e:
            action = "买入" if is_buy else "卖出"
            logging.error(f"{action}订单执行异常 {code}: {e}")
            return None
    
    @staticmethod
    def batch_process_orders(trader, account, orders, context, timeout=15):
        """
        批量处理订单，收集失败信息
        orders: [(code, volume, is_buy, price, remark), ...]
        返回: (success_codes, failed_codes)
        """
        success_codes = []
        failed_codes = []
        
        for code, volume, is_buy, price, remark in orders:
            oid = OrderUtils.safe_place_order(trader, account, code, volume, is_buy, price, remark)
            if oid and oid > 0:
                success_codes.append(code)
            else:
                failed_codes.append(code)
        
        if success_codes:
            new_pos = wait_for_order_completion(trader, account, success_codes, 
                                              context['broker_positions'], timeout=timeout)
            if new_pos is not None:
                context['broker_positions'] = new_pos
            else:
                logging.warning(f"订单等待超时: {success_codes}")
            _update_tracker_after_trade(context, success_codes)
        
        return success_codes, failed_codes


# ==================== 工具类：数据验证 ====================
class DataValidationUtils:
    """市场数据验证工具类"""
    
    @staticmethod
    def validate_market_data(code, is_buy=True):
        """
        验证市场数据是否可用
        返回: (is_valid, error_message)
        """
        try:
            if is_buy:
                MarketUtils.get_limit_price(code, 'high_limit')
            else:
                MarketUtils.get_limit_price(code, 'low_limit')
            
            tick = xtdata.get_full_tick([code])
            if code not in tick or tick[code] is None:
                return False, f"无法获取{code}的实时行情数据"
            
            return True, None
        except MarketDataException as e:
            return False, str(e)
        except Exception as e:
            return False, f"验证{code}市场数据失败: {e}"
    
    @staticmethod
    def get_safe_trade_price(code, is_buy=True):
        """
        安全获取交易价格，带异常处理
        返回: (price, error_message)
        """
        try:
            price, _ = calculate_trade_price_and_volume(code, 0, 0, is_buy=is_buy)
            return price, None
        except MarketDataException as e:
            return None, str(e)
        except Exception as e:
            return None, f"获取{code}交易价格失败: {e}"


# ==================== 日志格式化工具 ====================
def log_section(title, level="INFO"):
    """输出带分割线的章节标题"""
    separator = "=" * 60
    if level.upper() == "INFO":
        logging.info(f"\n{separator}")
        logging.info(f"{title}")
        logging.info(f"{separator}")
    elif level.upper() == "WARNING":
        logging.warning(f"\n{separator}")
        logging.warning(f"{title}")
        logging.warning(f"{separator}")
    elif level.upper() == "ERROR":
        logging.error(f"\n{separator}")
        logging.error(f"{title}")
        logging.error(f"{separator}")

def log_subsection(title):
    """输出子章节标题"""
    separator = "-" * 40
    logging.info(f"\n{separator}")
    logging.info(f"{title}")
    logging.info(f"{separator}")

def log_important(msg):
    """输出重要信息"""
    logging.info(f"🔥 {msg}")

def log_warning_highlight(msg):
    """输出警告信息（突出显示）"""
    logging.warning(f"⚠️  {msg}")

def log_error_highlight(msg):
    """输出错误信息（突出显示）"""
    logging.error(f"❌ {msg}")

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
        for i in range(retry):
            try:
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
                    raise MarketDataException(f"无法获取{code}的涨跌停价详情")
                price = detail.get('UpStopPrice' if limit_type == 'high_limit' else 'DownStopPrice', 0.0)
                if price > 0:
                    cls._cache[cache_key] = price
                    return price
                raise MarketDataException(f"{code}的{limit_type}价格无效: {price}")
            except MarketDataException:
                raise
            except Exception as e:
                if "无法连接xtquant服务" in str(e):
                    logging.error(f"xtdata 连接断开，尝试重连 ({attempt+1}/{retries})")
                    if cls._ensure_connection():
                        continue
                    raise MarketDataException(f"xtdata连接失败，无法获取{code}的{limit_type}价格")
                else:
                    logging.error(f"获取{limit_type}异常 {code}: {e}")
                    if attempt < retries - 1:
                        time.sleep(2)
                        continue
                    raise MarketDataException(f"获取{code}的{limit_type}价格失败: {e}")
        raise MarketDataException(f"获取{code}的{limit_type}价格失败，重试{retries}次后仍失败")

    @classmethod
    def is_limit_status(cls, code, limit_type='high_limit', tolerance=0.001):
        try:
            limit_price = cls.get_limit_price(code, limit_type)
            for attempt in range(3):
                try:
                    data = xtdata.get_market_data_ex([code], period='1d', count=1)
                    if code in data and data[code] is not None and not data[code].empty:
                        current = data[code]['close'].iloc[-1]
                        return abs(current - limit_price) < tolerance
                    raise MarketDataException(f"无法获取{code}的收盘价数据")
                except MarketDataException:
                    raise
                except Exception as e:
                    if "无法连接xtquant服务" in str(e) and attempt < 2:
                        cls._ensure_connection()
                        time.sleep(1)
                        continue
                    raise MarketDataException(f"判断{code}涨跌停状态失败: {e}")
            raise MarketDataException(f"判断{code}涨跌停状态失败，重试3次后仍失败")
        except MarketDataException:
            raise
        except Exception as e:
            raise MarketDataException(f"判断{code}涨跌停状态失败: {e}")

    @staticmethod
    def round_to_tick(price, tick=0.01):
        """将价格调整到最小变动单位的整数倍"""
        return round(price / tick) * tick


def calculate_cash_allocation(strat, total_asset, cash):
    """
    计算现金分配：储备金和可用购买现金
    返回: (reserve, available_cash)
    """
    reserve = total_asset * strat["cash_reserve_ratio"]
    available_cash = cash - reserve
    return reserve, max(available_cash, 0)


# ==================== 策略持仓跟踪 ====================
class StrategyPositionTracker:
    """
    跟踪各策略的持仓归属，持久化到 JSON 文件。
    因为 QMT API 没有策略标签，需要外部文件记录"哪只股票属于哪个策略"。
    同一只股票可被多个策略持有（各自独立的 volume）。
    """

    def __init__(self, tracking_file):
        self.tracking_file = tracking_file
        self.data = self._load()

    def _load(self):
        if not os.path.exists(self.tracking_file):
            return {}
        try:
            with open(self.tracking_file, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            data = {}
            for k, v in raw.items():
                if k == 'last_updated':
                    continue
                if isinstance(v, dict):
                    data[k] = {code: int(vol) for code, vol in v.items() if int(vol) > 0}
            return data
        except (json.JSONDecodeError, ValueError) as e:
            logging.error(f"持仓跟踪文件损坏，重新初始化: {e}")
            return {}

    def save(self):
        output = {"last_updated": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}
        output.update(self.data)
        tmp_file = self.tracking_file + '.tmp'
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=4, ensure_ascii=False)
        os.replace(tmp_file, self.tracking_file)

    def get_positions(self, strategy_name):
        """返回 {stock_code: volume}"""
        return dict(self.data.get(strategy_name, {}))

    def update_position(self, strategy_name, code, volume):
        """更新持仓，volume <= 0 时删除"""
        if strategy_name not in self.data:
            self.data[strategy_name] = {}
        if volume <= 0:
            self.data[strategy_name].pop(code, None)
        else:
            self.data[strategy_name][code] = int(volume)

    def get_tracked_volume(self, code):
        """某只股票在所有策略中的总 tracked volume"""
        return sum(pos.get(code, 0) for pos in self.data.values())

    def get_strategies_holding(self, code):
        """返回持有某只股票的策略名列表"""
        return [name for name, positions in self.data.items() if positions.get(code, 0) > 0]

    def sync_with_broker(self, broker_positions, strategy_names, strategy_configs=None):
        """
        与 broker 实际持仓对账。
        broker_positions: {stock_code: position_object} (volume > 0)
        strategy_configs: 策略配置列表，用于按资金比例分配孤儿持仓（可选）
        """
        # 确保所有策略在 data 中
        for name in strategy_names:
            if name not in self.data:
                self.data[name] = {}

        # 1. tracked 有但 broker 无 → 移除
        for strat_name in strategy_names:
            to_remove = [code for code in self.data.get(strat_name, {}) if code not in broker_positions]
            for code in to_remove:
                vol = self.data[strat_name].pop(code)
                logging.warning(f"对账: {strat_name} 的 {code}({vol}股) 在broker中不存在，移除")

        # 2. broker 有但无策略跟踪（孤儿）→ 按策略资金比例分配或分配给第一个策略
        all_tracked = set()
        for pos in self.data.values():
            all_tracked.update(pos.keys())
        
        for code, pos in broker_positions.items():
            if code not in all_tracked:
                if strategy_configs:
                    # 按策略资金比例分配孤儿持仓
                    try:
                        # 暂时分配给资金比例最高的策略，避免复杂分配
                        max_ratio_strat = max(strategy_configs, key=lambda s: s['capital_ratio'])['name']
                        self.data[max_ratio_strat][code] = pos.volume
                        logging.warning(f"对账: {code}({pos.volume}股) 未被跟踪，分配给资金比例最高的策略 '{max_ratio_strat}'")
                    except Exception as e:
                        # fallback: 分配给第一个策略
                        self.data[strategy_names[0]][code] = pos.volume
                        logging.warning(f"对账: {code}({pos.volume}股) 分配异常 {e}，临时分配给 '{strategy_names[0]}'，请手动调整")
                else:
                    # fallback: 分配给第一个策略
                    self.data[strategy_names[0]][code] = pos.volume
                    logging.warning(f"对账: {code}({pos.volume}股) 未被跟踪，临时分配给 '{strategy_names[0]}'，请手动调整")

        # 3. tracked 总量 vs broker 实际不一致
        for code, pos in broker_positions.items():
            tracked_total = self.get_tracked_volume(code)
            if tracked_total == pos.volume:
                continue
            holders = self.get_strategies_holding(code)
            if len(holders) == 1:
                old = self.data[holders[0]][code]
                self.data[holders[0]][code] = pos.volume
                logging.info(f"对账: {code} '{holders[0]}' 修正 {old} -> {pos.volume}")
            elif len(holders) == 0:
                # 上面第2步应该已经处理，这里是 fallback
                self.data[strategy_names[0]][code] = pos.volume
            else:
                logging.error(
                    f"对账: {code} 被 {holders} 持有, "
                    f"tracked={tracked_total} != broker={pos.volume}, 需手动修正"
                )


# ==================== 单例运行保护 ====================
def _is_process_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def check_single_instance():
    lock_file = 'multi_strategy.lock'
    if os.path.exists(lock_file):
        try:
            with open(lock_file, 'r') as f:
                pid = int(f.read().strip())
            if _is_process_alive(pid) and time.time() - os.path.getmtime(lock_file) < 3600:
                logging.warning(f"检测到另一实例正在运行 (PID={pid})，退出")
                sys.exit(0)
        except (ValueError, IOError) as e:
            logging.warning(f"锁文件读取异常: {e}")
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

class CompositeAction(Action):
    def __init__(self, name, scheduled_time=None):
        super().__init__(name, scheduled_time)
        self.children = []
    def add(self, child): self.children.append(child); return self

class SequenceAction(CompositeAction):
    def run(self, context):
        logging.info(f">>> 开始组合: {self.name}")
        for child in self.children:
            if child.scheduled_time:
                try:
                    target_hour, target_minute = map(int, child.scheduled_time.split(':'))
                    now = datetime.datetime.now()
                    target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
                    if now < target_time:
                        wait_seconds = (target_time - now).total_seconds()
                        logging.info(f"等待到 {child.scheduled_time} 执行 {child.name}，需等待 {wait_seconds:.0f} 秒")
                        time.sleep(wait_seconds)
                    else:
                        logging.info(f"预定时间 {child.scheduled_time} 已过，立即执行 {child.name}")
                except Exception as e:
                    logging.error(f"解析时间 {child.scheduled_time} 失败: {e}")
            tag = f" [{child.scheduled_time}]" if child.scheduled_time else ""
            logging.info(f"--- 执行: {child.name}{tag}")
            try:
                child.run(context)
            except Exception as e:
                logging.error(f"!!! {child.name} 失败: {e}")
                raise
        logging.info(f"<<< 组合 {self.name} 完毕")

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
                time.sleep(self.delay * (attempt + 1))


# ==================== 订单等待 ====================
def wait_for_order_completion(trader, account, affected_codes, initial_positions, timeout=30):
    """
    等待指定股票的持仓 volume 发生变化。
    affected_codes: 期望变化的股票代码集合
    initial_positions: 变化前全部持仓 {code: position_object}
    返回新持仓 dict，超时返回 None
    """
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(1)
        new_positions = {p.stock_code: p for p in trader.query_stock_positions(account) if p.volume > 0}
        for code in affected_codes:
            old_vol = initial_positions[code].volume if code in initial_positions else 0
            new_vol = new_positions[code].volume if code in new_positions else 0
            if old_vol != new_vol:
                return new_positions
    return None


# ==================== 配置加载 ====================
def load_config(context):
    config_file = context.get('config_file', 'qmt_multi_strategy_config.json')
    with open(config_file, encoding='utf-8') as f:
        config = json.load(f)

    log_file = config.get("log_file", "logs/multi_strategy.log")
    os.makedirs(os.path.dirname(log_file) or '.', exist_ok=True)
    logger = logging.getLogger()
    if not any(isinstance(h, logging.FileHandler) and h.baseFilename == os.path.abspath(log_file)
               for h in logger.handlers):
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(fh)

    context['config'] = config

    # 解析策略列表
    strategies = config['strategies']
    total_ratio = sum(s['capital_ratio'] for s in strategies)
    # 严格验证资金比例：必须在0.9999到1.0001之间
    if abs(total_ratio - 1.0) > 0.0001:
        raise ValueError(f"capital_ratio 之和 ({total_ratio:.4f}) 必须等于 1.0 (允许误差 ±0.0001)")
    
    # 为每个策略设置默认的 trading_times 并验证
    for s in strategies:
        if s['capital_ratio'] <= 0:
            raise ValueError(f"策略 '{s['name']}' 的 capital_ratio ({s['capital_ratio']}) 必须大于0")
        
        # 设置默认交易时间：09:35
        if 'trading_times' not in s:
            s['trading_times'] = ["09:35"]
        
        # 验证 trading_times 格式
        if not isinstance(s['trading_times'], list):
            raise ValueError(f"策略 '{s['name']}' 的 trading_times 必须是列表")
        
        # 验证时间格式
        for t in s['trading_times']:
            if not isinstance(t, str) or len(t) != 5 or t[2] != ':':
                raise ValueError(f"策略 '{s['name']}' 的交易时间格式错误: {t}，应为 HH:MM 格式")
            try:
                hour = int(t[:2])
                minute = int(t[3:])
                if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                    raise ValueError
            except ValueError:
                raise ValueError(f"策略 '{s['name']}' 的交易时间格式错误: {t}，应为有效的 HH:MM 格式")
    
    context['strategy_configs'] = strategies
    logging.info(f"多策略模式: {[s['name'] for s in strategies]}, capital_ratio合计={total_ratio:.4f}")
    for s in strategies:
        logging.info(f"  策略 '{s['name']}': 交易时间 {s['trading_times']}")

    # 初始化持仓跟踪
    tracking_file = config.get("position_tracking_file", "strategy_positions.json")
    context['position_tracker'] = StrategyPositionTracker(tracking_file)
    logging.info("配置加载成功")


def read_stock_lists(context):
    """读取策略的股票名单，支持文件存在性检查和过期检查
    
    规则：
    1. 如果文件不存在，返回空列表（策略清仓）
    2. 如果文件修改时间超过14天，返回空列表（策略清仓）
    3. 如果文件读取失败，返回空列表（策略清仓）
    4. 正常情况返回股票列表
    """
    strat = context['current_strategy']
    file_path = strat["stock_list_file"]
    
    # 检查文件是否存在
    if not os.path.exists(file_path):
        logging.warning(f"[{strat['name']}] 股票名单文件不存在: {file_path}")
        context['candidate_pool'] = []
        context['buy_pool'] = []
        return
    
    # 检查文件是否过期（超过14天）
    file_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
    days_old = (datetime.datetime.now() - file_mtime).days
    if days_old > 14:
        logging.warning(f"[{strat['name']}] 股票名单文件已过期: {file_path}，最后修改于 {file_mtime} ({days_old}天前)")
        context['candidate_pool'] = []
        context['buy_pool'] = []
        return
    
    try:
        with open(file_path, encoding='utf-8') as f:
            data = json.load(f)
        
        all_codes = [item.replace('XSHE', 'SZ').replace('XSHG', 'SH') for item in data]
        context['candidate_pool'] = all_codes[:strat["candidate_pool_size"]]
        context['buy_pool'] = all_codes[:strat["max_holdings"]]
        logging.info(f"[{strat['name']}] 候选池: {len(context['candidate_pool'])}只, 买入池: {len(context['buy_pool'])}只")
        
    except Exception as e:
        logging.error(f"[{strat['name']}] 读取股票名单文件失败: {e}")
        context['candidate_pool'] = []
        context['buy_pool'] = []


def init_trader(context):
    cfg = context['config']
    path = cfg["miniqmt_path"]
    session_id = random.randint(10000, 99999)
    for attempt in range(3):
        try:
            trader = XtQuantTrader(path, session_id)
            trader.set_relaxed_response_order_enabled(True)
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
            time.sleep(5 * (attempt + 1))


def close_trader(context):
    if 'trader' in context:
        try:
            context['trader'].stop()
            logging.info("交易客户端关闭")
        except Exception as e:
            logging.error(f"关闭交易客户端异常: {e}")


# ==================== 账户状态（策略作用域）====================
def get_account_status(context):
    """查询 broker 全部持仓/资产，按当前策略过滤"""
    trader = context['trader']
    account = context['account']
    strat = context['current_strategy']
    tracker = context['position_tracker']

    asset = trader.query_stock_asset(account)
    if asset is None:
        raise Exception("查询资产失败")

    # broker 全部持仓
    broker_positions = {p.stock_code: p for p in trader.query_stock_positions(account) if p.volume > 0}

    # 对账（每轮只做一次）
    if not context.get('_sync_done'):
        strategy_names = [s['name'] for s in context['strategy_configs']]
        tracker.sync_with_broker(broker_positions, strategy_names, context['strategy_configs'])
        context['_sync_done'] = True

    # 过滤当前策略持仓
    tracked = tracker.get_positions(strat['name'])
    strategy_positions = {}
    strategy_position_value = 0.0
    for code in tracked:
        if code in broker_positions:
            strategy_positions[code] = broker_positions[code]
            strategy_position_value += broker_positions[code].market_value

    # 虚拟资金 - 方案A（严格隔离）：每个策略使用自己的现金配额
    total_asset = asset.total_asset
    strategy_total = total_asset * strat['capital_ratio']
    strategy_cash_quota = asset.cash * strat['capital_ratio']
    strategy_cash_needed = strategy_total - strategy_position_value
    strategy_cash = max(min(strategy_cash_needed, strategy_cash_quota), 0)

    context.update({
        'broker_total_asset': total_asset,
        'broker_cash': asset.cash,
        'total_asset': strategy_total,
        'cash': strategy_cash,
        'positions': strategy_positions,
        'broker_positions': broker_positions,
    })
    logging.info(
        f"[{strat['name']}] 账户总资产: {total_asset:.2f}, "
        f"策略配额: {strategy_total:.2f}, 可用: {strategy_cash:.2f}, "
        f"持仓: {len(strategy_positions)}只"
    )


# ==================== tracker 更新辅助 ====================
def _update_tracker_after_trade(context, codes):
    """交易后根据 broker 实际持仓更新 tracker - 精确版本"""
    strat = context['current_strategy']
    tracker = context['position_tracker']
    broker_positions = context['broker_positions']

    for code in codes:
        broker_pos = broker_positions.get(code)
        if broker_pos is None or broker_pos.volume == 0:
            # 卖出或清仓
            tracker.update_position(strat['name'], code, 0)
        else:
            # 精确计算当前策略应占的份额
            current_vol = tracker.get_positions(strat['name']).get(code, 0)
            # 计算其他策略对该股票的总跟踪持仓
            other_vol = tracker.get_tracked_volume(code) - current_vol
            # 当前策略的新持仓 = broker总持仓 - 其他策略持仓
            my_new = max(broker_pos.volume - other_vol, 0)
            tracker.update_position(strat['name'], code, my_new)
            logging.debug(f"[{strat['name']}] 更新跟踪: {code} 当前={current_vol}, 其他={other_vol}, broker={broker_pos.volume}, 新={my_new}")


# ==================== 交易动作 ====================
def sell_out_of_pool(context):
    strat = context['current_strategy']
    trader = context['trader']
    account = context['account']
    positions = context['positions']
    candidate = context['candidate_pool']

    sell_codes = []
    for code, pos in positions.items():
        if code not in candidate:
            try:
                # 检查是否涨停，涨停时不能卖出
                if not MarketUtils.is_limit_status(code, 'high_limit'):
                    oid = place_sell_order(trader, account, code, pos.volume, f"sell_out_{strat['name']}")
                    if oid and oid > 0:
                        sell_codes.append(code)
            except MarketDataException as e:
                logging.error(f"[{strat['name']}] 获取{code}市场数据失败，跳过卖出: {e}")
                continue
            except Exception as e:
                logging.error(f"[{strat['name']}] 卖出{code}时发生异常: {e}")
                continue

    if sell_codes:
        new_pos = wait_for_order_completion(trader, account, sell_codes, context['broker_positions'], timeout=15)
        if new_pos is not None:
            context['broker_positions'] = new_pos
        else:
            logging.warning(f"[{strat['name']}] 卖出等待超时")
        _update_tracker_after_trade(context, sell_codes)

    get_account_status(context)


def _calculate_rebalance_targets(strat, total_asset):
    """计算再平衡的目标参数"""
    reserve = total_asset * strat["cash_reserve_ratio"]
    cash_for_stocks = total_asset - reserve
    target_per_stock = cash_for_stocks / strat["max_holdings"]
    return reserve, cash_for_stocks, target_per_stock


def rebalance(context):
    strat = context['current_strategy']
    trader = context['trader']
    account = context['account']
    positions = context['positions']
    total_asset = context['total_asset']

    # 计算再平衡目标
    reserve, cash_for_stocks, target_per_stock = _calculate_rebalance_targets(strat, total_asset)

    # --- 卖出超配 ---
    sell_codes = []
    for code, pos in positions.items():
        if pos.market_value > target_per_stock:
            try:
                # 检查是否涨停，涨停时不能卖出
                if not MarketUtils.is_limit_status(code, 'high_limit'):
                    value_sell = pos.market_value - target_per_stock
                    price = pos.market_value / pos.volume
                    vol_sell = int(value_sell // (price * 100)) * 100
                    if vol_sell > 0:
                        oid = place_sell_order(trader, account, code, vol_sell, f"rb_sell_{strat['name']}")
                        if oid and oid > 0:
                            sell_codes.append(code)
            except MarketDataException as e:
                logging.error(f"[{strat['name']}] 获取{code}市场数据失败，跳过卖出: {e}")
                continue
            except Exception as e:
                logging.error(f"[{strat['name']}] 卖出{code}时发生异常: {e}")
                continue

    if sell_codes:
        new_pos = wait_for_order_completion(trader, account, sell_codes, context['broker_positions'], timeout=15)
        if new_pos is not None:
            context['broker_positions'] = new_pos
        else:
            logging.warning(f"[{strat['name']}] 再平衡卖出超时")
        _update_tracker_after_trade(context, sell_codes)

    get_account_status(context)

    # --- 买入低配 ---
    # 重新获取更新后的账户状态
    total_asset = context['total_asset']
    positions = context['positions']
    available_cash = context['cash']
    
    # 重新计算目标（因为total_asset可能已变化）
    reserve, cash_for_stocks, target_per_stock = _calculate_rebalance_targets(strat, total_asset)

    buy_codes = []
    for code, pos in positions.items():
        if pos.market_value < target_per_stock:
            try:
                # 检查是否跌停，跌停时不能买入
                if not MarketUtils.is_limit_status(code, 'low_limit'):
                    value_buy = target_per_stock - pos.market_value
                    buy_price, vol_buy = calculate_trade_price_and_volume(code, value_buy, available_cash, is_buy=True)
                    if vol_buy > 0 and buy_price is not None:
                        oid = place_buy_order(trader, account, code, vol_buy, buy_price, f"rb_buy_{strat['name']}")
                        if oid and oid > 0:
                            buy_codes.append(code)
                            available_cash -= vol_buy * buy_price * 1.001
            except MarketDataException as e:
                logging.error(f"[{strat['name']}] 获取{code}市场数据失败，跳过买入: {e}")
                continue
            except Exception as e:
                logging.error(f"[{strat['name']}] 买入{code}时发生异常: {e}")
                continue

    if buy_codes:
        new_pos = wait_for_order_completion(trader, account, buy_codes, context['broker_positions'], timeout=15)
        if new_pos is not None:
            context['broker_positions'] = new_pos
        _update_tracker_after_trade(context, buy_codes)

    get_account_status(context)


def check_rebalance_and_execute(context):
    strat = context['current_strategy']
    positions = context['positions']
    total_asset = context['total_asset']
    cash = context['cash']

    slots = strat["max_holdings"] - len(positions)
    if slots <= 0:
        return

    # 使用辅助函数计算现金分配
    reserve, cash_for_buy = calculate_cash_allocation(strat, total_asset, cash)
    if cash_for_buy <= 0:
        return

    avg_alloc = cash_for_buy / slots
    # 修正：使用与 rebalance 函数相同的计算公式
    cash_for_stocks = total_asset - reserve
    target_per_stock = cash_for_stocks / strat["max_holdings"]
    deviation = abs(avg_alloc - target_per_stock) / target_per_stock if target_per_stock > 0 else 0

    if deviation > strat["rebalance_threshold"]:
        logging.info(f"[{strat['name']}] 触发再平衡: 偏离 {deviation:.1%}")
        rebalance(context)


def buy_to_fill(context):
    strat = context['current_strategy']
    trader = context['trader']
    account = context['account']
    positions = context['positions']
    buy_pool = context['buy_pool']
    total_asset = context['total_asset']
    cash = context['cash']

    current_codes = set(positions.keys())
    slots = strat["max_holdings"] - len(current_codes)
    if slots <= 0:
        return

    # 使用辅助函数计算现金分配
    reserve, buy_cash = calculate_cash_allocation(strat, total_asset, cash)
    if buy_cash <= 0:
        logging.warning(f"[{strat['name']}] 可用资金不足")
        return

    candidates = [c for c in buy_pool if c not in current_codes][:slots]
    if not candidates:
        return

    per_stock = buy_cash / len(candidates)
    available_cash = buy_cash

    buy_codes = []
    for code in candidates:
        try:
            buy_price, vol = calculate_trade_price_and_volume(code, per_stock, available_cash, is_buy=True)
            if vol > 0 and buy_price is not None:
                oid = place_buy_order(trader, account, code, vol, buy_price, f"buy_{strat['name']}")
                if oid and oid > 0:
                    logging.info(f"[{strat['name']}] Buy {code}: {vol}股 @ {buy_price:.2f}")
                    buy_codes.append(code)
                    available_cash -= vol * buy_price * 1.001
            else:
                logging.info(f"[{strat['name']}] Skipping {code}")
        except MarketDataException as e:
            logging.error(f"[{strat['name']}] 获取{code}市场数据失败，跳过买入: {e}")
            continue
        except Exception as e:
            logging.error(f"[{strat['name']}] 买入{code}时发生异常: {e}")
            continue

    if buy_codes:
        new_pos = wait_for_order_completion(trader, account, buy_codes, context['broker_positions'], timeout=15)
        if new_pos is not None:
            context['broker_positions'] = new_pos
        _update_tracker_after_trade(context, buy_codes)

    get_account_status(context)


# ==================== 下单函数 ====================
def calculate_trade_price_and_volume(code, target_amount, available_cash, is_buy=True):
    """
    统一的交易价格计算函数（买入和卖出）
    is_buy: True 表示买入，False 表示卖出
    """
    if is_buy:
        # 买入逻辑
        try:
            high_limit = MarketUtils.get_limit_price(code, 'high_limit')
            tick = xtdata.get_full_tick([code])
            if code not in tick or tick[code] is None:
                raise MarketDataException(f"无法获取{code}的实时行情数据")
            ask_price = tick[code].get('askPrice', [0])[0]
            if ask_price <= 0:
                # 卖一价为0，说明股票涨停了，直接用涨停价买入
                logging.info(f"股票 {code} 卖一价为0（涨停状态），使用涨停价 {high_limit:.2f} 买入")
                buy_price = high_limit
            else:
                cage_limit = max(ask_price * 1.02, ask_price + 0.1)
                buy_price = min(cage_limit, high_limit)
            
            # 调整价格到最小变动价位
            buy_price = MarketUtils.round_to_tick(buy_price)

            safety_factor = 0.99
            max_amount = min(target_amount, available_cash) * safety_factor
            volume = int(max_amount // (buy_price * 100)) * 100
            if volume <= 0:
                return None, 0
            return buy_price, volume
        except MarketDataException:
            raise
        except Exception as e:
            raise MarketDataException(f"计算{code}买入价格失败: {e}")
    else:
        # 卖出逻辑
        try:
            low_limit = MarketUtils.get_limit_price(code, 'low_limit')
            tick = xtdata.get_full_tick([code])
            if code not in tick or tick[code] is None:
                raise MarketDataException(f"无法获取{code}的实时行情数据")
            bid_price = tick[code].get('bidPrice', [0])[0]
            if bid_price <= 0:
                # 买一价为0，说明跌停了，直接用跌停价
                logging.info(f"股票 {code} 买一价为0（跌停状态），使用跌停价 {low_limit:.2f} 限价卖出")
                sell_price = low_limit
            else:
                # 计算价格笼子下限：min(买一价*0.98, 买一价-0.1)
                cage_lower_limit = min(bid_price * 0.98, bid_price - 0.1)
                # 卖出价格取价格笼子下限和跌停价的较大值（卖出时价格越高越好）
                sell_price = max(cage_lower_limit, low_limit)
                # 调整价格到最小变动价位
                sell_price = MarketUtils.round_to_tick(sell_price)
                logging.info(f"股票 {code} 买一价 {bid_price:.2f}, 价格笼子下限 {cage_lower_limit:.2f}, 跌停价 {low_limit:.2f}, 最终卖出价 {sell_price:.2f}")
            
            # 对于卖出，返回价格（卖出不需要计算股数，股数由调用方提供）
            return sell_price, 0
        except MarketDataException:
            raise
        except Exception as e:
            raise MarketDataException(f"计算{code}卖出价格失败: {e}")




def place_sell_order(trader, account, code, volume, remark=""):
    """卖出委托（使用统一的交易价格计算函数）"""
    if volume <= 0:
        return None
    
    try:
        # 使用统一的交易价格计算函数获取卖出价格
        # 注意：对于卖出，target_amount 参数不需要，传入 0
        # available_cash 参数也不需要，传入 0
        sell_price = calculate_trade_price_and_volume(code, 0, 0, is_buy=False)
        
        if sell_price is None:
            logging.warning(f"无法计算股票 {code} 的卖出价格，回退到对手价下单")
            # 回退到对手价下单
            oid = trader.order_stock(
                account, code, xtconstant.STOCK_SELL, volume,
                xtconstant.MARKET_PEER_PRICE_FIRST, 0, remark
            )
            if oid and oid > 0:
                logging.info(f"Sell {code} {volume}股 @ 对手价, order_id:{oid}")
                return oid
            else:
                logging.error(f"Sell failed {code} err:{oid}")
                return None
        
        # 使用限价单卖出
        oid = trader.order_stock(
            account, code, xtconstant.STOCK_SELL, volume,
            xtconstant.FIX_PRICE, sell_price, remark
        )
        if oid and oid > 0:
            logging.info(f"Sell {code} {volume}股 @ 价格 {sell_price:.2f}, order_id:{oid}")
            return oid
        else:
            logging.error(f"Sell failed {code} err:{oid}")
            return None
    except Exception as e:
        logging.error(f"卖出订单执行异常 {code}: {e}")
        return None


def place_buy_order(trader, account, code, volume, price=None, remark=""):
    if volume <= 0:
        return None
    try:
        if price is not None:
            price_type = xtconstant.FIX_PRICE
            order_price = price
        else:
            price_type = xtconstant.MARKET_PEER_PRICE_FIRST
            order_price = 0
        oid = trader.order_stock(
            account, code, xtconstant.STOCK_BUY, volume,
            price_type, order_price, remark
        )
        if oid and oid > 0:
            action = f"限价{price:.2f}" if price else "对手价"
            logging.info(f"Buy {code} {volume}股 @ {action} order_id:{oid}")
            return oid
        else:
            logging.error(f"Buy failed {code} err:{oid}")
            return None
    except Exception as e:
        logging.error(f"买入订单执行异常 {code}: {e}")
        return None


# ==================== scheduled_time 等待动作 ====================
# 注意：09:20的等待已移除，因为股票名单文件在每个交易时间点都会重新读取
WaitForTradeTime = SequenceAction("等待交易时间")
WaitForTradeTime.add(RetryAction(SimpleAction("初始化交易客户端", init_trader), scheduled_time="09:35"))


# ==================== 主流程 ====================
def is_weekday(date):
    return date.weekday() < 5


def run_strategy_once(config_file=None, current_time_str=None):
    """执行一次完整的多策略调仓
    config_file: 配置文件路径
    current_time_str: 当前时间字符串 (HH:MM)，如果为None则使用系统当前时间
    """
    context = {}
    if config_file:
        context['config_file'] = config_file
    try:
        log_section(f"策略执行开始")
        logging.info(f"执行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        load_config(context)
        
        # 获取当前时间
        if current_time_str is None:
            current_time_str = datetime.datetime.now().strftime("%H:%M")
        
        # 过滤出需要在当前时间执行的策略
        strategies_to_run = []
        for strat_cfg in context['strategy_configs']:
            if current_time_str in strat_cfg['trading_times']:
                strategies_to_run.append(strat_cfg)
        
        if not strategies_to_run:
            logging.info(f"当前时间 {current_time_str} 没有需要执行的策略")
            log_section(f"策略执行结束 - 无策略需要执行")
            return
        
        log_subsection(f"策略筛选结果")
        logging.info(f"当前时间: {current_time_str}")
        logging.info(f"需要执行的策略: {[s['name'] for s in strategies_to_run]}")
        logging.info(f"策略数量: {len(strategies_to_run)}")
        
        # 对于所有交易时间，直接初始化交易客户端
        # 但需要确保在交易时间内
        now = datetime.datetime.now()
        hour, minute = map(int, current_time_str.split(':'))
        target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        if now < target_time:
            wait_seconds = (target_time - now).total_seconds()
            logging.info(f"等待到 {current_time_str}，需等待 {wait_seconds:.0f} 秒")
            time.sleep(wait_seconds)
        
        WaitForTradeTime.run(context)

        for strat_cfg in strategies_to_run:
            context['current_strategy'] = strat_cfg
            context['_sync_done'] = False
            log_section(f"策略执行: {strat_cfg['name']} (资金比例={strat_cfg['capital_ratio']})")
            logging.info(f"交易时间: {current_time_str}")
            logging.info(f"开始时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            read_stock_lists(context)
            get_account_status(context)
            sell_out_of_pool(context)
            check_rebalance_and_execute(context)
            buy_to_fill(context)
            context['position_tracker'].save()

            logging.info(f"结束时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            log_section(f"策略完成: {strat_cfg['name']}")

        log_section(f"所有策略执行完成")
        logging.info(f"执行时间: {current_time_str}")
        logging.info(f"完成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logging.info(f"执行策略数量: {len(strategies_to_run)}")
        logging.info(f"执行策略列表: {[s['name'] for s in strategies_to_run]}")
    except Exception:
        logging.exception("策略执行失败")
    finally:
        close_trader(context)
        if 'position_tracker' in context:
            try:
                context['position_tracker'].save()
            except Exception:
                pass


def main_loop(run_now=False, config_file=None):
    check_single_instance()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[logging.StreamHandler()])
    logging.info("miniQMT 多策略调仓 启动")

    if run_now:
        logging.info("立即执行模式")
        run_strategy_once(config_file)
        return

    # 加载配置以获取所有策略的时间表
    context = {}
    if config_file:
        context['config_file'] = config_file
    try:
        load_config(context)
    except Exception as e:
        logging.error(f"加载配置失败: {e}")
        return
    
    # 收集所有策略的所有交易时间点
    all_trading_times = set()
    for strat_cfg in context['strategy_configs']:
        for t in strat_cfg['trading_times']:
            all_trading_times.add(t)
    
    # 转换为排序的时间列表
    sorted_times = sorted(all_trading_times)
    logging.info(f"所有策略的交易时间点: {sorted_times}")
    
    while True:
        now = datetime.datetime.now()
        current_time_str = now.strftime("%H:%M")
        
        # 如果是交易日，检查是否需要执行
        if is_weekday(now.date()):
            # 检查当前时间是否在交易时间点中
            if current_time_str in all_trading_times:
                logging.info(f"交易日 {now.date()}，当前时间 {current_time_str} 是交易时间点，开始执行")
                run_strategy_once(config_file, current_time_str)
            else:
                # 计算到下一个交易时间点的等待时间
                next_time = None
                for t in sorted_times:
                    hour, minute = map(int, t.split(':'))
                    target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if target_time > now:
                        next_time = target_time
                        break
                
                if next_time is None:
                    # 今天的所有交易时间点都已过，等待到明天的第一个时间点
                    tomorrow = now + datetime.timedelta(days=1)
                    # 找到明天的第一个交易日
                    while not is_weekday(tomorrow.date()):
                        tomorrow += datetime.timedelta(days=1)
                    
                    first_time = sorted_times[0]
                    hour, minute = map(int, first_time.split(':'))
                    next_time = tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                wait_seconds = (next_time - now).total_seconds()
                if wait_seconds > 60:  # 只显示较长的等待
                    log_section(f"等待阶段 - 交易日")
                    logging.info(f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
                    logging.info(f"等待至: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    logging.info(f"等待时长: {wait_seconds/3600:.1f} 小时 ({wait_seconds/60:.0f} 分钟)")
                    logging.info(f"等待开始: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    # 单次等待，无需分块
                    time.sleep(wait_seconds)
                    
                    logging.info(f"等待结束: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    log_section(f"等待结束 - 继续执行")
        else:
            # 非交易日，等待到下一个交易日的第一个时间点
            next_day = now + datetime.timedelta(days=1)
            while not is_weekday(next_day.date()):
                next_day += datetime.timedelta(days=1)
            
            first_time = sorted_times[0]
            hour, minute = map(int, first_time.split(':'))
            next_time = next_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            wait_seconds = (next_time - now).total_seconds()
            log_section(f"等待阶段 - 非交易日")
            logging.info(f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            logging.info(f"等待至: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
            logging.info(f"等待时长: {wait_seconds/3600:.1f} 小时 ({wait_seconds/60:.0f} 分钟)")
            logging.info(f"等待开始: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 单次等待，无需分块
            time.sleep(wait_seconds)
            
            logging.info(f"等待结束: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            log_section(f"等待结束 - 继续执行")


if __name__ == "__main__":
    run_now = "--now" in sys.argv
    cfg_file = None
    for i, arg in enumerate(sys.argv):
        if arg == "--config" and i + 1 < len(sys.argv):
            cfg_file = sys.argv[i + 1]
    main_loop(run_now, cfg_file)
