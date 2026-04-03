# coding=utf-8
import json

# ==================== Configuration File Paths ====================
CONFIG_FILE = r'C:\Users\Administrator\Desktop\qmt_trader\qmt_config_test.json'
STOCK_LIST_FILE = r'C:\Users\Administrator\Desktop\qmt_trader\target_stocks.json'

# ==================== Global Variables ====================
g_target_pool = []   # candidate pool (first candidate_pool_size stocks)
g_buy_pool = []      # buy pool (first max_holdings stocks)
g_config = {}        # configuration parameters

# ==================== Initialization ====================
def initialize(context):
    load_config()
    run_daily(read_stock_lists, time='09:20')
    run_daily(trade, time='09:35')
    log.info("Strategy initialized, waiting for scheduled triggers")

def load_config():
    global g_config
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            g_config = json.load(f)
        log.info(f"Configuration loaded: {g_config}")
    except Exception as e:
        log.error(f"Failed to load configuration: {e}")
        raise

def read_stock_lists(context):
    """Read stock list from JSON array and update global pools"""
    global g_target_pool, g_buy_pool
    try:
        with open(STOCK_LIST_FILE, 'r', encoding='utf-8') as f:
            all_codes = json.load(f)
        if not isinstance(all_codes, list):
            raise ValueError("Stock list file must be a JSON array")
        all_codes = [item.replace('XSHE', 'SZ').replace('XSHG', 'SH') for item in all_codes]
        g_target_pool = all_codes[:g_config["candidate_pool_size"]]
        g_buy_pool = all_codes[:g_config["max_holdings"]]
        log.info(f"Stock list: candidate pool {len(g_target_pool)} stocks, buy pool {len(g_buy_pool)} stocks")
    except Exception as e:
        log.error(f"Failed to read stock list: {e}")

# ==================== Core Trading Logic ====================
def trade(context):
    log.info("========== Start rebalancing ==========")

    # Access portfolio via context.portfolio (standard QMT API)
    portfolio = context.portfolio
    total_asset = portfolio.portfolio_value
    cash = portfolio.available_cash
    positions = {code: pos for code, pos in portfolio.positions.items() if pos.volume > 0}
    current_codes = set(positions.keys())

    # 1. Sell stocks not in candidate pool
    for code, pos in positions.items():
        if code not in g_target_pool:
            low_limit = get_limit_price(code, 'low_limit')
            if low_limit and low_limit > 0:
                order_id = order(code, -pos.volume, low_limit)   # negative volume for sell
                if order_id:
                    log.info(f"Sell {code} {pos.volume} shares @ {low_limit:.2f} order_id:{order_id}")
                else:
                    log.warning(f"Failed to place sell order for {code}")
            else:
                log.warning(f"Cannot get low limit price for {code}, skip sell")

    time.sleep(3)

    # Update account status
    portfolio = context.portfolio
    total_asset = portfolio.portfolio_value
    cash = portfolio.available_cash
    positions = {code: pos for code, pos in portfolio.positions.items() if pos.volume > 0}
    current_codes = set(positions.keys())

    # 2. Check rebalance condition
    slots = g_config["max_holdings"] - len(current_codes)
    if slots > 0:
        reserve = total_asset * g_config["cash_reserve_ratio"]
        buy_cash = cash - reserve
        if buy_cash > 0:
            avg_alloc = buy_cash / slots
            target_per_stock = total_asset / g_config["max_holdings"]
            if abs(avg_alloc - target_per_stock) > target_per_stock * g_config["rebalance_threshold"]:
                log.info(f"Rebalance triggered: avg_alloc={avg_alloc:.2f}, target_per_stock={target_per_stock:.2f}")
                full_rebalance(context)
                # Refresh status after rebalance
                portfolio = context.portfolio
                total_asset = portfolio.portfolio_value
                cash = portfolio.available_cash
                positions = {code: pos for code, pos in portfolio.positions.items() if pos.volume > 0}
                current_codes = set(positions.keys())

    # 3. Buy new stocks to fill up to max_holdings
    slots = g_config["max_holdings"] - len(current_codes)
    if slots > 0:
        reserve = total_asset * g_config["cash_reserve_ratio"]
        buy_cash = cash - reserve
        if buy_cash <= 0:
            log.warning("Insufficient cash to buy new stocks")
        else:
            candidates = [c for c in g_buy_pool if c not in current_codes]
            stocks_to_buy = candidates[:slots]
            if not stocks_to_buy:
                log.info("No stocks available to buy")
            else:
                per_stock = buy_cash / len(stocks_to_buy)
                for code in stocks_to_buy:
                    high_limit = get_limit_price(code, 'high_limit')
                    if high_limit and high_limit > 0:
                        vol = int(per_stock // (high_limit * 100)) * 100
                        if vol > 0:
                            order_id = order(code, vol, high_limit)
                            if order_id:
                                log.info(f"Buy {code} {vol} shares @ {high_limit:.2f} order_id:{order_id}")
                            else:
                                log.warning(f"Failed to place buy order for {code}")
                        else:
                            log.info(f"Insufficient funds to buy one lot of {code}")
                    else:
                        log.warning(f"Cannot get high limit price for {code}, skip buy")

    log.info("========== Rebalancing completed ==========")

def full_rebalance(context):
    """Full portfolio rebalancing: adjust each stock's market value to target (excluding reserve cash)"""
    portfolio = context.portfolio
    total_asset = portfolio.portfolio_value
    positions = {code: pos for code, pos in portfolio.positions.items() if pos.volume > 0}

    reserve = total_asset * g_config["cash_reserve_ratio"]
    cash_for_stocks = total_asset - reserve
    target_per_stock = cash_for_stocks / g_config["max_holdings"]

    # Sell over-weighted stocks (if not limit up)
    for code, pos in positions.items():
        if pos.market_value > target_per_stock and not is_limit_status(code, 'high_limit'):
            value_sell = pos.market_value - target_per_stock
            price = pos.market_value / pos.volume
            vol_sell = int(value_sell // (price * 100)) * 100
            if vol_sell > 0:
                low_limit = get_limit_price(code, 'low_limit')
                if low_limit and low_limit > 0:
                    order_id = order(code, -vol_sell, low_limit)
                    if order_id:
                        log.info(f"Rebalance sell {code} {vol_sell} shares @ {low_limit:.2f} order_id:{order_id}")
                    else:
                        log.warning(f"Failed to place rebalance sell for {code}")

    time.sleep(3)

    # Update status
    portfolio = context.portfolio
    total_asset = portfolio.portfolio_value
    positions = {code: pos for code, pos in portfolio.positions.items() if pos.volume > 0}
    reserve = total_asset * g_config["cash_reserve_ratio"]
    cash_for_stocks = total_asset - reserve
    target_per_stock = cash_for_stocks / g_config["max_holdings"]

    # Buy under-weighted stocks (if not limit down)
    for code, pos in positions.items():
        if pos.market_value < target_per_stock and not is_limit_status(code, 'low_limit'):
            value_buy = target_per_stock - pos.market_value
            price = pos.market_value / pos.volume if pos.volume > 0 else get_limit_price(code, 'high_limit')
            vol_buy = int(value_buy // (price * 100)) * 100
            if vol_buy > 0:
                high_limit = get_limit_price(code, 'high_limit')
                if high_limit and high_limit > 0:
                    order_id = order(code, vol_buy, high_limit)
                    if order_id:
                        log.info(f"Rebalance buy {code} {vol_buy} shares @ {high_limit:.2f} order_id:{order_id}")
                    else:
                        log.warning(f"Failed to place rebalance buy for {code}")

    time.sleep(3)

# ==================== Helper Functions ====================
def get_limit_price(code, limit_type='high_limit'):
    """Get limit up/down price using QMT market data"""
    try:
        data = get_market_data([code], period='1d', field=[limit_type])
        if data is not None and not data.empty:
            price = data[limit_type].iloc[-1]
            if price is not None and price > 0:
                return price
    except Exception as e:
        log.error(f"Failed to get {limit_type} for {code}: {e}")
    return None

def is_limit_status(code, limit_type='high_limit', tolerance=0.001):
    """Check if stock is at limit up/down"""
    limit_price = get_limit_price(code, limit_type)
    if not limit_price:
        return False
    try:
        data = get_market_data([code], period='1d', field=['close'])
        if data is not None and not data.empty:
            current = data['close'].iloc[-1]
            return abs(current - limit_price) < tolerance
    except:
        pass
    return False