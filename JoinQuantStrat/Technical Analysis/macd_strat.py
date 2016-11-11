"""
This is a long only strategy
filter
1. eight two stock index swaps between 000300.XSHG and 399006.XSHE
2. Use MACD divergence for buy and sell signal
3. select stocks with smaller market cap

trade
buy: macd bottom reversal 
sell: macd top reverse or stop loss

"""
import talib
import numpy as np
from functools import partial
import pandas as pd
from jqdata import *
from blacklist import *
from scipy.signal import argrelextrema
from api import *
from webtrader import WebTrader
import tradestat
import config

# global constants
macd_func = partial(talib.MACD, fastperiod=12,slowperiod=26,signalperiod=9)
#macd_func = partial(talib.MACDEXT, fastperiod=12,slowperiod=26,signalperiod=9)

#enable_profile()

def loading():
    ''' 登陆 '''
    user = use(config.trade_acc['use_xq'])
    user.prepare(config.trade_acc['json2_xq'])
    return user
    
def check(user):
    ''' 获取信息并输出 '''
    log.info('获取今日委托单:')
    log.info('今日委托单:', json.dumps(user.entrust,ensure_ascii=False))
    log.info('-'*30)
    log.info('获取资金状况:')
    log.info('资金状况:', json.dumps(user.balance,ensure_ascii=False) )
    log.info('enable_balance(可用金额):',  json.dumps(user.balance[0]['enable_balance'],ensure_ascii=False))
    log.info('-'*30)
    log.info('持仓:')
    log.info('获取持仓:', json.dumps(user.position,ensure_ascii=False))

def realAction(stock, value_pct):
    if False and 'macd_real_action' in config.real_action and config.real_action['macd_real_action']:
        try:
            user = loading()
            check(user)
            log.info("stock [%s] is requested to be adjusted to weight %d pct" %(stock, value_pct))
            user.adjust_weight(stock[:6], int(value_pct))
        except:
            log.info("stock [%s] requested adjustment failed")

########################################################################################################

def displayVar():
    log.info("################################################")
    log.info("g.stock_domain: %s" % g.stock_domain)
    log.info("g.stock_filter: %s" % g.stock_filter)
    log.info("g.allow_stop_loss: %s" % g.allow_stop_loss)
    log.info("g.dynamic_stop_loss: %s" % g.dynamic_stop_loss)
    log.info("g.total_num_of_pos: %d" % g.total_num_of_pos)
    log.info("g.number_of_days: %d" % g.number_of_days)
    log.info("g.number_of_days_wave_backwards: %d" % g.number_of_days_wave_backwards)
    log.info("g.number_of_days_backwards: %d" % g.number_of_days_backwards)
    log.info("g.number_of_N_Zval: %d" % g.number_of_N_Zval)
    log.info("g.buy_period_check_super: %s" % g.buy_period_check_super)
    log.info("g.buy_period_check: %s" % g.buy_period_check)
    log.info("g.sell_period_check: %s" % g.sell_period_check)
    log.info("g.stop_loss: %f" % g.stop_loss)
    log.info("g.tailing_stop_loss: %f" % g.tailing_stop_loss)
    log.info("################################################")    
    
# def after_code_changed(context):
#     g.stock_domain = '000002.XSHG'
#     g.stock_filter = True
#     g.dynamic_stop_loss = True
#     g.allow_stop_loss = True
#     g.total_num_of_pos = 5
#     g.trading_hour = 10
#     g.trading_minute = 42
#     g.botUseZvalue = True
#     g.topUseZvalue = True

def set_variables():
    g.user = None
    g.total_num_of_pos = 5
    g.number_of_days = 30
    g.number_of_days_wave_backwards = 60
    g.number_of_days_backwards = 133
    g.number_of_N_Zval = 100
    g.reversal_index = 0.1
    g.t = 0                # 记录回测运行的天数
    g.if_trade = False     # 当天是否交易
    g.tc = 1   # trigger action per # of days
    g.m = 0
    g.mbc = 180 # trigger buy action per X min / day
    g.msc = 60 # trigger sell action per X min / day
    g.buy_period_check_super = '5d' # '5d'
    g.buy_period_check = '1d' # '1d'
    g.sell_period_check = '60m' # '60m'
    g.sell_list = [] # if we have stocks failed to sell, we need to record it and try to sell the next day
    g.to_buy = []
    g.pct_change = {}
    g.period = {}
    g.max_price = {} # this is set when position open, and cleared when position closed
    g.stock_filter = True
    g.dynamic_stop_loss = True
    g.allow_stop_loss = True
    g.botUseZvalue = True
    g.topUseZvalue = True

    
def reset_var():
    g.pct_change = {}
    g.period = {}
    g.if_trade = False

def set_params():
    g.upper_ratio_range = 1.03
    g.lower_ratio_range = 0.98
    g.macd_divergence_ratio = {}
    g.stop_loss = 0.93
    g.tailing_stop_loss = 0.95
    g.stock_domain = '000002.XSHG' #399400.XSHE 000002.XSHG
    g.benchmark = '000300.XSHG'
    g.trading_hour = 10
    g.trading_minute = 42
        # 加载统计模块
    g.trade_stat = tradestat.trade_stat()

def set_backtest():
    set_benchmark(g.benchmark) # 更改bench回测基准（银行股指数从2009年9月开始）
    set_option('use_real_price',True) # 用真实价格交易
    log.set_level('order','error')    # 设置报错等级

# 根据不同的时间段设置滑点与手续费
def set_slip_fee(context):
    # 将滑点设置为0
    set_slippage(FixedSlippage(0)) 
    # 根据不同的时间段设置手续费
    dt=context.current_dt
    
    if dt>datetime.datetime(2013,1, 1):
        set_commission(PerTrade(buy_cost=0.0003, sell_cost=0.0013, min_cost=5)) 
        
    elif dt>datetime.datetime(2011,1, 1):
        set_commission(PerTrade(buy_cost=0.001, sell_cost=0.002, min_cost=5))
            
    elif dt>datetime.datetime(2009,1, 1):
        set_commission(PerTrade(buy_cost=0.002, sell_cost=0.003, min_cost=5))
                
    else:
        set_commission(PerTrade(buy_cost=0.003, sell_cost=0.004, min_cost=5))

# 设置可行股票池：
# 过滤掉当日停牌的股票,且筛选出前days天未停牌股票
# 输入：stock_list为list类型,样本天数days为int类型，context（见API）
# 输出：list
def set_feasible_stocks(stock_list,days,context):
    # 得到是否停牌信息的dataframe，停牌的1，未停牌得0
    suspened_info_df = get_price(list(stock_list), start_date=context.current_dt, end_date=context.current_dt, frequency='daily', fields='paused')['paused'].T
    feasible_stocks=[]
    unsuspened_stocks = stock_list
    if not suspened_info_df.empty:
        # 过滤停牌股票 返回dataframe
        unsuspened_index = suspened_info_df.iloc[:,0]<1
        # 得到当日未停牌股票的代码list:
        unsuspened_stocks = suspened_info_df[unsuspened_index].index
        # 进一步，筛选出前days天未曾停牌的股票list:
    current_data=get_current_data()
    for stock in unsuspened_stocks:
        if sum(attribute_history(stock, days, unit='1d',fields=('paused'),skip_paused=False))[0]==0:
            feasible_stocks.append(stock)
    return feasible_stocks


def initialize(context):
    """
    Called once at the start of the algorithm.
    """   
    set_params() 
    
    set_variables() 
    
    set_backtest()

def before_trading_start(context):
    """
    Called every day before market open.
    """
    displayVar()
    
    if g.t%g.tc==0: #and two_eight_turn(context)  and market_safe(context)
        #每g.tc天，交易一次
        g.if_trade=True 
        # 设置手续费与手续费
        set_slip_fee(context) 
        # 设置可行股票池：获得当前开盘     全部上市A股
        g.feasible_stocks = get_index_stocks(g.stock_domain)
        # pddf = get_all_securities(date = context.current_dt.date())
        # g.feasible_stocks = pddf.index.values
        filterStockList(context)
        #g.feasible_stocks = set_feasible_stocks(get_index_stocks(g.stock_domain),g.number_of_days,context)

        g.to_buy = check_to_buy(context)
    g.t+=1

def market_safe(context):
    market_price = attribute_history(g.stock_domain, g.number_of_days_wave_backwards, '1d', ('close'), skip_paused=True, df=False)
    market_macd_raw, _, market_hist = macd_func(market_price['close'])
    return market_macd_raw[-1] > 0 or (market_macd_raw[-1] < 0 and market_hist[-1] > market_hist[-2] and market_hist[-2] > market_hist[3])

def two_eight_turn(context):
    '''
    if both price rise were negative, sell off
    '''
    dt=context.current_dt
    
    hs300 = '000300.XSHG'
    #hs300 = '399405.XSHE'
    #zz500 = '000905.XSHG'
    zz500 = '399006.XSHE'
    #zz500 = '000906.XSHG'
    if dt<datetime.datetime(2010,6, 1):    
        zz500 = '000905.XSHG'
    price_hs300 = attribute_history(hs300, 21, '1d', ('close'), df=False)
    price_zz500 = attribute_history(zz500, 21, '1d', ('close'), df=False)
    hs300_delta = (price_hs300['close'][-1] - price_hs300['close'][0]) / price_hs300['close'][0]
    zz500_delta = (price_zz500['close'][-1] - price_zz500['close'][0]) / price_zz500['close'][0]
    if hs300_delta > zz500_delta:
        g.stock_domain = hs300
        g.stop_loss = 0.97
        g.tailing_stop_loss = 0.97
    else:
        g.stock_domain = zz500
        g.stop_loss = 0.93
        g.tailing_stop_loss = 0.93
    log.info("use %s as domain with past growth rate (hs300: %.2f, zz500: %.2f)" % (get_security_info(g.stock_domain).display_name, hs300_delta, zz500_delta))
    
    if hs300_delta < 0 and zz500_delta < 0:
        log.info("NEGATIVE growth rate! we need to close all positions")
        g.sell_list = [stock for stock in context.portfolio.positions]
    
    return not (hs300_delta < 0 and zz500_delta < 0)
    
def two_eight_turn_v2(context):
    dt=context.current_dt
    
    major = '000300.XSHG'
    sub = '399006.XSHE'
    if dt<datetime.datetime(2010,6, 1):    
        sub = '000905.XSHG'    
        
    major_df = attribute_history(major, g.number_of_days_wave_backwards, '1d', ('close'), skip_paused=True, df=False)
    sub_df = attribute_history(sub, g.number_of_days_wave_backwards, '1d', ('close'), skip_paused=True, df=False)

    major_macd_raw, _, major_hist = macd_func(major_df['close'])
    sub_macd_raw, _, sub_hist = macd_func(sub_df['close'])
    
    if major_hist[-1] < 0 and sub_hist[-1] < 0:
        log.info("NEGATIVE growth rate! we need to close all positions")
        g.sell_list = [stock for stock in context.portfolio.positions]
        return False
    elif major_hist[-1] > 0 and sub_hist[-1] < 0:
        g.stock_domain = major
    elif sub_hist[-1] > 0 and major_hist[-1] < 0:
        g.stock_domain = sub
    else:
        if major_hist[-1] > sub_hist[-1] :
            g.stock_domain = major
        else:
            g.stock_domain = sub
    if g.stock_domain == major:
        g.stop_loss = 0.97
        g.tailing_stop_loss = 0.97
    else:
        g.stop_loss = 0.93
        g.tailing_stop_loss = 0.93     
    log.info("use %s as domain with past macd values (major: %.2f, sub: %.2f)" % (get_security_info(g.stock_domain).display_name, major_hist[-1], sub_hist[-1]))
    return True

def handle_data(context,data):
    """
    Called every period preset.
    """
    if g.sell_list:
        for stock in g.sell_list:
            if stock in context.portfolio.positions:
                #log.info("short %s from sell_list" % stock)
                #order_target_value(stock, 0)
                close_position(context.portfolio.positions[stock])
        g.sell_list = []
    
    if g.m%g.msc==0: # try to check to sell 
        to_sell = check_to_sell(context, data)
        rebalance(to_sell, [], context)
    g.m+=1    
    
    if g.if_trade:
        hour = context.current_dt.hour
        minute = context.current_dt.minute
        if hour == g.trading_hour and minute == g.trading_minute and g.to_buy:
            rebalance([], g.to_buy, context)
            g.to_buy = []
    
        # if g.m%g.mbc==0: # try to check to buy 
        #     to_buy = check_to_buy(context)
        #     rebalance([], to_buy, context)
    
    # to_buy = check_to_buy(context)
    # to_sell = check_to_sell(context, data)
    # rebalance(to_sell, to_buy, context)

def inOpenOrder(security):
    orders = get_open_orders()
    for _order in orders.values():
        if _order.security == security:
            return True
    return False

def rebalance(to_sell, to_buy, context):
    for security in to_sell:
        if security in context.portfolio.positions and not inOpenOrder(security):
            #log.info("short %s - %s" % (security, get_security_info(security).display_name))
            #order_target_value(security, 0)
            close_position(context.portfolio.positions[security])
    for security in to_buy:
        if context.portfolio.cash > context.portfolio.portfolio_value/g.total_num_of_pos and security not in context.portfolio.positions and not inOpenOrder(security):
            #log.info("long %s - %s" % (security, get_security_info(security).display_name))
            #order_target_value_new(security, context.portfolio.portfolio_value/g.total_num_of_pos)   
            open_position(security, context.portfolio.portfolio_value/g.total_num_of_pos)
            realAction(security, 100/g.total_num_of_pos)


def check_to_sell(context, data):
    to_sell = []
    for stock in context.portfolio.positions:
        pos = context.portfolio.positions[stock]
        if pos.sellable_amount > 0:
            df = attribute_history(stock, g.number_of_days_backwards, g.sell_period_check, ('high', 'low', 'open', 'close', 'volume'), df=False)
            
            sl = g.stop_loss
            sg = g.tailing_stop_loss

            if g.allow_stop_loss and g.dynamic_stop_loss:
                recent_period = findPeriod(stock)
                threthold = get_stop_loss_threshold(stock, recent_period)
                if threthold:
                    sl = 1 - threthold
                    sg = sl
                    #sg = 1 - (threthold / (pos.price / pos.avg_cost))
    
            if (macd_top_divergence(df, context, data)): 
                log.info("add %s in sell list due to top divergence" % stock)
                to_sell.append(stock)
            elif g.allow_stop_loss and ((pos.price / pos.avg_cost < sl) or (df['close'][-1]/df['close'][-2]<sl)):
                # # extra check
                # df = attribute_history(stock, g.number_of_days_backwards, g.buy_period_check, ('high', 'low', 'open', 'close', 'volume'), df=False)
                # df_s = attribute_history(stock, g.number_of_days_wave_backwards, g.buy_period_check_super, ('high','low', 'close'), df=False)
                # bottomReversal, ratio = macd_bottom_divergence(df, df_s, context)
                # if not bottomReversal:
                log.info("add %s in sell list due to stop loss" % stock)
                to_sell.append(stock)
            elif g.allow_stop_loss and (pos.price / g.max_price[stock] < sg):
                log.info("add %s in sell list due to tailing stop loss" % stock)
                to_sell.append(stock)
            #  record max price for the stock
            elif pos.price > g.max_price[stock]: # update the max price
                g.max_price[stock] = pos.price
    return to_sell

def check_to_buy(context):
    from_anal = filterByAnal(g.feasible_stocks, context)
    #print from_anal
    # order by marekt cap, small to big
    # from_anal.sort() # no need to sort, it's done by query
    log.info("Candidate stocks for today: %s" % from_anal)
    only_buy_security_list = [x[1] for x in from_anal[:g.total_num_of_pos]]
    return only_buy_security_list

def filterByAnal(filtered, context):
    chosen = []
    for stock in filtered:
        #print "check %s" % stock
        df = attribute_history(stock, g.number_of_days_backwards, g.buy_period_check, ('high', 'low', 'open', 'close', 'volume'), df=False)
        df_s = attribute_history(stock, g.number_of_days_wave_backwards, g.buy_period_check_super, ('high','low', 'close'), df=False)
        if (not np.isnan(df['high'][-1])) and (not np.isnan(df['low'][-1])) and (not np.isnan(df['close'][-1])):
            bottomReversal, ratio = macd_bottom_divergence(df, df_s, context)
            if bottomReversal:
                chosen.append(stock)
    mcap_stock = []
    if chosen:
        mcap_stock = getMcapInfo(chosen, context)
    return mcap_stock
    
def getMcapInfo(stocks, context):
    # get yesterdays market cap
    queryDate = context.current_dt.date()-timedelta(days=1)
    queryDf = get_fundamentals(query(
        valuation.market_cap, valuation.code
    ).filter(
        valuation.code.in_(stocks),
        indicator.eps > 0
    ).order_by(
        valuation.market_cap.asc()
    )
    )
    
    stockinfo = []
    for j in xrange(0, len(queryDf['market_cap'])):
        stockinfo.append( (queryDf['market_cap'][j], queryDf['code'][j]) )
    return stockinfo

def macd_bottom_divergence(df, df_s, context):
    macd_raw, _, hist = macd_func(df['close'])
    macd_raw_s, _, hist_s = macd_func(df_s['close'])
    checkResult, ratio = checkAtBottomDoubleCross(macd_raw, hist, df['low']) 
    if np.isnan(hist_s[-1]) or np.isnan(hist_s[-2]):
        return False, 0
    else:
        return checkResult and hist_s[-1] > hist_s[-2] and hist_s[-2] > hist_s[-3], ratio
    #return checkAtBottomDoubleCross(macd_raw, hist, df['low']) 
    #return checkResult and ((macd_raw_s[-1] > 0 and hist_s[-1] > hist_s[-2]) or (macd_raw_s[-1] < 0 and hist_s[-1] > hist_s[-2] and hist_s[-2] > hist_s[-3])) , ratio

def macd_top_divergence(df, context, data):
    macd_raw, signal, hist = macd_func(df['close'])
    return checkAtTopDoubleCross(macd_raw, hist, df['high']) 

def filterStockList(context):
    g.feasible_stocks = filter_blacklist_stock(context, g.feasible_stocks)
    g.feasible_stocks = filter_paused_stock(g.feasible_stocks)
    if g.stock_filter:
        g.feasible_stocks = filter_st_stock(g.feasible_stocks)
        g.feasible_stocks = filter_limitup_stock(context, g.feasible_stocks)
        g.feasible_stocks = filter_limitdown_stock(context, g.feasible_stocks)    

######################################################## copied filter ###############################################################

def filter_paused_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list if not current_data[stock].paused]

def filter_st_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list 
        if not current_data[stock].is_st 
        and 'ST' not in current_data[stock].name 
        and '*' not in current_data[stock].name 
        and '退' not in current_data[stock].name]

def filter_blacklist_stock(context, stock_list):
    blacklist = get_blacklist()
    return [stock for stock in stock_list if stock not in blacklist]

# 过滤涨停的股票
def filter_limitup_stock(context, stock_list):
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    
    # 已存在于持仓的股票即使涨停也不过滤，避免此股票再次可买，但因被过滤而导致选择别的股票
    return [stock for stock in stock_list if stock in context.portfolio.positions.keys() 
        or last_prices[stock][-1] < current_data[stock].high_limit]

# 过滤跌停的股票
def filter_limitdown_stock(context, stock_list):
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    return [stock for stock in stock_list if stock in context.portfolio.positions.keys() 
        or last_prices[stock][-1] > current_data[stock].low_limit]

######################################################## copied filter ###############################################################

def isDeathCross(i,j, macd):
    # if macd sign change, we detect an immediate cross
    # sign changed from -val to +val and 
    if i == 0:
        return False
    if j<0 and macd[i-1] >0:
        return True
    return False

def isGoldCross(i,j, macd):
    # if macd sign change, we detect an immediate cross
    # sign changed from -val to +val and 
    if i == 0:
        return False
    if j>0 and macd[i-1] <0:
        return True
    return False

def checkAtTopDoubleCross(macd_raw, macd_hist, prices):
    # hist height less than 0.5 should be considered a crossing candidate
    # return True if we are close at MACD top reverse
    indexOfGoldCross = [i for i, j in enumerate(macd_hist) if isGoldCross(i,j,macd_hist)]   
    indexOfDeathCross = [i for i, j in enumerate(macd_hist) if isDeathCross(i,j,macd_hist)] 
    #print indexOfCross
    if (not indexOfGoldCross) or (not indexOfDeathCross) or (len(indexOfDeathCross)<2) or (len(indexOfGoldCross)<2) or \
    abs(indexOfGoldCross[-1]-indexOfDeathCross[-1]) <= 2 or \
    abs(indexOfGoldCross[-1]-indexOfDeathCross[-2]) <= 2 or \
    abs(indexOfGoldCross[-2]-indexOfDeathCross[-1]) <= 2 or \
    abs(indexOfGoldCross[-2]-indexOfDeathCross[-2]) <= 2:
        return False
    
    if macd_raw[-1] > 0 and macd_hist[-1] > 0 and macd_hist[-1] < macd_hist[-2]: 
        latest_hist_area = macd_hist[indexOfGoldCross[-1]:]
        max_val_Index = latest_hist_area.tolist().index(max(latest_hist_area))
        recentArea_est = abs(sum(latest_hist_area[:max_val_Index])) * 2
        
        previousArea = macd_hist[indexOfGoldCross[-2]:indexOfDeathCross[-1]]
        previousArea_sum = abs(sum(previousArea))
        
        # recentlength_est = (max_val_Index - indexOfGoldCross[-1]) * 2
        # previouslength = indexOfDeathCross[-1] - indexOfGoldCross[-2]
        
        # if recentlength_est == 0 or previouslength == 0:
        #     return False
        
        if g.topUseZvalue:
            prices_z = zscore(prices)
        else:
            prices_z = prices
        # log.info("recentArea_est: %.2f" % recentArea_est)
        # log.info("previousArea_sum: %.2f" % previousArea_sum)
        # log.info("max recent price: %.2f" % max(prices[indexOfDeathCross[-1]:]) )
        # log.info("max previous price: %.2f" % max(prices[indexOfDeathCross[-2]:indexOfGoldCross[-1]]) )
        if recentArea_est < previousArea_sum and (max(prices_z[indexOfGoldCross[-1]:]) / max(prices_z[indexOfGoldCross[-2]:indexOfDeathCross[-1]]) > g.lower_ratio_range) :
            return True
    return False

def checkAtBottomDoubleCross(macd_raw, macd_hist, prices):
    # find cross index for gold and death
    # calculate approximated areas between death and gold cross for bottom reversal
    # adjacent reducing negative hist bar areas(appx) indicated double bottom reversal signal
    
    indexOfGoldCross = [i for i, j in enumerate(macd_hist) if isGoldCross(i,j,macd_hist)]   
    indexOfDeathCross = [i for i, j in enumerate(macd_hist) if isDeathCross(i,j,macd_hist)] 
    
    if (not indexOfGoldCross) or (not indexOfDeathCross) or (len(indexOfDeathCross)<2) or (len(indexOfGoldCross)<2) or \
    abs(indexOfGoldCross[-1]-indexOfDeathCross[-1]) <= 2 or \
    abs(indexOfGoldCross[-1]-indexOfDeathCross[-2]) <= 2 or \
    abs(indexOfGoldCross[-2]-indexOfDeathCross[-1]) <= 2 or \
    abs(indexOfGoldCross[-2]-indexOfDeathCross[-2]) <= 2:
        # no cross found
        # also make sure gold cross isn't too close to death cross as we don't want that situation
        return False,0

    # check for standard double bottom macd divergence pattern
    # green bar is reducing
    if macd_raw[-1] < 0 and macd_hist[-1] < 0 and macd_hist[-1] > macd_hist[-2]: 
        # calculate current negative bar area 
        latest_hist_area = macd_hist[indexOfDeathCross[-1]:]
        min_val_Index = latest_hist_area.tolist().index(min(latest_hist_area))
        recentArea_est = abs(sum(latest_hist_area[:min_val_Index])) * 2
        
        previousArea = macd_hist[indexOfDeathCross[-2]:indexOfGoldCross[-1]]
        previousArea_sum = abs(sum(previousArea))
        
        # recentlength_est = (min_val_Index - indexOfDeathCross[-1]) * 2
        # previouslength = indexOfGoldCross[-1] - indexOfDeathCross[-2]
        
        # if recentlength_est == 0 or previouslength == 0:
        #     return False,0    

        # this is only an estimation
        # bottom_len = indexOfDeathCross[-1] - indexOfDeathCross[-2]
        # log.info("recentArea_est : %.2f, with min price: %.2f" % (recentArea_est, min(prices[indexOfDeathCross[-2]:indexOfGoldCross[-1]])))
        # log.info("previousArea_sum : %.2f, with min price: %.2f" % (previousArea_sum, min(prices[indexOfDeathCross[-1]:])) )
        # log.info("bottom_len: %d" % bottom_len)
        
        # standardize the price and macd_raw to Z value
        # return the diff of price zvalue and macd z value
        if g.botUseZvalue:
            prices_z = zscore(prices)
        else:
            prices_z = prices
        #macd_raw_z = zscore(np.nan_to_num(macd_raw))
        
        if recentArea_est < previousArea_sum and (min(prices_z[indexOfDeathCross[-2]:indexOfGoldCross[-1]]) / min(prices_z[indexOfDeathCross[-1]:]) > g.lower_ratio_range ) :
            #price_change_rate = (min(prices_z[indexOfDeathCross[-2]:indexOfGoldCross[-1]]) - min(prices_z[indexOfDeathCross[-1]:])) / bottom_len
            #macd_change_rate = (min(macd_raw_z[indexOfDeathCross[-2]:indexOfGoldCross[-1]]) - min(macd_raw_z[indexOfDeathCross[-1]:])) / bottom_len
            # log.info("price_change_rate: %.2f" % price_change_rate)
            # log.info("macd_change_rate: %.2f" % macd_change_rate)
            return True, 0
    return False, 0

def zscore(series):
    return (series - series.mean()) / np.std(series)

#每个交易日结束运行
def after_trading_end(context):
    g.trade_stat.report(context)
    #得到当前未完成订单
    orders = get_open_orders()
    #循环，撤销订单
    for _order in orders.values():
        if not _order.is_buy: # we need to sell again tomorrow if failed to sell today
            g.sell_list.append(_order.security)
        cancel_order(_order)
    reset_var()

        
def findPeriod(stock):
    if stock not in g.period:
        df = attribute_history(stock, g.number_of_days_wave_backwards, '1d', ('high', 'low'), skip_paused=True)
        topIndex = argrelextrema(df['high'].values, np.greater_equal,order=1)[0]
        bottomIndex = argrelextrema(df['low'].values, np.less_equal,order=1)[0]
        delta = None
        if topIndex[-1] > bottomIndex[-1]:
            delta = df['low'].index[bottomIndex[-1]] - df['high'].index[topIndex[-2]]
        else:
            delta = df['high'].index[bottomIndex[-1]] - df['low'].index[topIndex[-2]]
        g.period[stock] = delta.days
    return g.period[stock]
####################################################################################################

def open_position(security, amount):
    order = order_target_value_new(security, amount) # 可能会因停牌失败
    if order != None and order.status == OrderStatus.held:
        g.max_price[security] = order.price
        

def close_position(position):
    security = position.security
    realAction(security, 0)
    order = order_target_value_new(security, 0) # 可能会因停牌失败
    if order != None:
        if order.filled > 0:
            # 只要有成交，无论全部成交还是部分成交，则统计盈亏
            g.trade_stat.watch(security, order.filled, position.avg_cost, position.price)
        if order.status == OrderStatus.held and order.filled == order.amount:
            # clear the max price record
            del g.max_price[security]
            # 只要有成交，无论全部成交还是部分成交，则统计盈亏
            # g.trade_stat.watch(security, order.filled, position.avg_cost, position.price)
    
# 自定义下单
# 根据Joinquant文档，当前报单函数都是阻塞执行，报单函数（如order_target_value）返回即表示报单完成
# 报单成功返回报单（不代表一定会成交），否则返回None
def order_target_value_new(security, value):
    if value == 0:
        log.info("short %s - %s" % (security, get_security_info(security).display_name))
    else:
        log.info("long %s - %s with amount RMB %f" % (security, get_security_info(security).display_name, value))
        
    # 如果股票停牌，创建报单会失败，order_target_value 返回None
    # 如果股票涨跌停，创建报单会成功，order_target_value 返回Order，但是报单会取消
    # 部成部撤的报单，聚宽状态是已撤，此时成交量>0，可通过成交量判断是否有成交
    return order_target_value(security, value)


# 计算个股回撤止损阈值
# 即个股在持仓n天内能承受的最大跌幅
# 算法：(个股250天内最大的n日跌幅 + 个股250天内平均的n日跌幅)/2
# 返回正值
def get_stop_loss_threshold(security, n = 3):
    pct_change = get_pct_change(security, 250, n)
    #log.debug("pct of security [%s]: %s", pct)
    maxd = pct_change.min()
    #maxd = pct[pct<0].min()
    avgd = pct_change.mean()
    #avgd = pct[pct<0].mean()
    # maxd和avgd可能为正，表示这段时间内一直在增长，比如新股
    bstd = (maxd + avgd) / 2

    # 数据不足时，计算的bstd为nan
    if not isnan(bstd):
        if bstd != 0:
            return abs(bstd)
        else:
            # bstd = 0，则 maxd <= 0
            if maxd < 0:
                # 此时取最大跌幅
                return abs(maxd)
    return 0.099 # 默认配置回测止损阈值最大跌幅为-9.9%，阈值高貌似回撤降低
    
# 计算个股止盈阈值
# 算法：个股250天内最大的n日涨幅
# 返回正值
def get_stop_profit_threshold(security, n = 3):
    pct_change = get_pct_change(security, 250, n)
    maxr = pct_change.max()
    
    # 数据不足时，计算的maxr为nan
    # 理论上maxr可能为负
    if (not isnan(maxr)) and maxr != 0:
        return abs(maxr)
    return 0.20 # 默认配置止盈阈值最大涨幅为20%
    
# 获取个股前n天的m日增幅值序列
# 增加缓存避免当日多次获取数据
def get_pct_change(security, n, m):
    pct_change = None
    if security in g.pct_change.keys():
        pct_change = g.pct_change[security]
    else:
        h = attribute_history(security, n, unit='1d', fields=('close'), skip_paused=True, df=True)
        pct_change = h['close'].pct_change(m) # 3日的百分比变比（即3日涨跌幅）
        g.pct_change[security] = pct_change
    return pct_change