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
import copy
import numpy as np
from collections import OrderedDict
from functools import partial
from scipy.signal import argrelextrema
import pandas as pd
from jqdata import *

# global constants
macd_func = partial(talib.MACD, fastperiod=12,slowperiod=26,signalperiod=9)

#enable_profile()

def set_variables():
    g.total_num_of_pos = 4   
    g.number_of_days = 30
    g.number_of_days_MA_backwards = 60
    g.number_of_days_backwards = 133
    g.number_of_N_Zval = 100
    g.reversal_index = 0.1
    g.t = 0                # 记录回测运行的天数
    g.if_trade = False     # 当天是否交易
    g.tc = 1   # trigger action per # of days
    g.m = 0
    g.mbc = 60 # trigger buy action per X min / day
    g.msc = 60 # trigger sell action per X min / day
    g.buy_period_check = '1d'
    g.sell_period_check = '60m'
    g.sell_list = [] # if we have stocks failed to sell, we need to record it and try to sell the next day
    g.to_buy = []

def set_params():
    g.upper_ratio_range = 1.03
    g.lower_ratio_range = 0.98
    g.macd_divergence_ratio = {}
    g.stop_loss = 0.93
    g.stop_gain = 0.95
    g.stock_domain = '399400.XSHE'
    g.benchmark = '000300.XSHG'

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
    if g.t%g.tc==0 and two_eight_turn(context):
        #每g.tc天，交易一次
        g.if_trade=True 
        # 设置手续费与手续费
        set_slip_fee(context) 
        # 设置可行股票池：获得当前开盘     全部上市A股
        g.feasible_stocks = set_feasible_stocks(get_index_stocks(g.stock_domain),g.number_of_days,context)

        g.to_buy = check_to_buy(context)
    g.t+=1

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
        g.stop_gain = 0.97
    else:
        g.stock_domain = zz500
        g.stop_loss = 0.93
        g.stop_gain = 0.93
    log.info("use %s as domain with past growth rate (hs300: %.2f, zz500: %.2f)" % (g.stock_domain, hs300_delta, zz500_delta))
    return not (hs300_delta < 0 and zz500_delta < 0)

def handle_data(context,data):
    """
    Called every period preset.
    """
    #if g.if_trade:
    hour = context.current_dt.hour
    minute = context.current_dt.minute
    if hour == 10 and minute == 42 and g.to_buy:
        rebalance([], g.to_buy, context)
        g.to_buy = []
        
    if g.sell_list:
        for stock in g.sell_list:
            log.info("short %s from sell_list" % stock)
            order_target_value(stock, 0)
        g.sell_list = []
    
    # if g.m%g.mbc==0: # try to check to buy 
    #     to_buy = check_to_buy(context)
    #     rebalance([], to_buy, context)
    
    if g.m%g.msc==0: # try to check to sell 
        to_sell = check_to_sell(context, data)
        rebalance(to_sell, [], context)
    g.m+=1
    
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
            log.info("short %s - %s" % (security, get_security_info(security).display_name))
            order_target_value(security, 0)
    for security in to_buy:
        if context.portfolio.cash > context.portfolio.portfolio_value/g.total_num_of_pos and security not in context.portfolio.positions and not inOpenOrder(security):
            log.info("long %s - %s" % (security, get_security_info(security).display_name))
            order_target_value(security, context.portfolio.portfolio_value/g.total_num_of_pos)   


def check_to_sell(context, data):
    to_sell = []
    for stock in context.portfolio.positions:
        pos = context.portfolio.positions[stock]
        df = attribute_history(stock, g.number_of_days_backwards, g.sell_period_check, ('high', 'low', 'open', 'close', 'volume'), df=False)
        if (macd_top_divergence(df, context, data)) or (pos.price / pos.avg_cost < g.stop_loss) or (df['close'][-1]/df['close'][-2]<g.stop_loss) or (pos.price / max(df['close'][-8:]) < g.stop_gain):
            #log.info("add %s in sell list" % stock)
            to_sell.append(stock)
    return to_sell

def check_to_buy(context):
    #filtered = filterByTrend(context)
    filtered = g.feasible_stocks
    from_anal = filterByAnal(filtered, context)
    #print from_anal
    # order by marekt cap, small to big
    from_anal.sort()
    log.info("Candidate stocks for today: %s" % from_anal)
    only_buy_security_list = [x[1] for x in from_anal[:g.total_num_of_pos]]
    return only_buy_security_list

def filterByAnal(filtered, context):
    chosen = []
    for stock in filtered:
        #print "check %s" % stock
        df = attribute_history(stock, g.number_of_days_backwards, g.buy_period_check, ('high', 'low', 'open', 'close', 'volume'), df=False)
        if (not np.isnan(df['high'][-1])) and (not np.isnan(df['low'][-1])) and (not np.isnan(df['close'][-1])):
            bottomReversal, ratio = macd_bottom_divergence(df, context)
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
        valuation.code.in_(stocks)
    ), date=queryDate)
    
    stockinfo = []
    for j in xrange(0, len(queryDf['market_cap'])):
        stockinfo.append( (queryDf['market_cap'][j], queryDf['code'][j]) )
    return stockinfo

def macd_bottom_divergence(df, context):
    macd_raw, signal, hist = macd_func(df['low'])
    return checkAtBottomDoubleCross(macd_raw, hist, df['low'])
    

def macd_top_divergence(df, context, data):
    macd_raw, signal, hist = macd_func(df['high'])
    return checkAtTopDoubleCross(macd_raw, hist, df['high'])    

def filterByTrend(context):
    """
    多头，强势股票
    input: g.feasible_stocks
    output: g.feasible_stocks
    """
    filtered = []
    for stock in g.feasible_stocks:
        sinfo = get_security_info(stock)
        df = attribute_history(stock, g.number_of_days_MA_backwards, '1d', ('high', 'close'), df=False)        
        # if df.isnull().values.any():
        #     continue
        if np.isnan(df['close'][-1]):
            continue
        #ema5 = talib.EMA(df['close'], timeperiod=5)
        sma5 = talib.SMA(df['close'], timeperiod=5)
        #sma21 = talib.SMA(df['close'].values, timeperiod=21)
        #sma34 = talib.SMA(df['close'], timeperiod=34)
        #ema55 = talib.EMA(df['close'], timeperiod=55)
        # sma89 = talib.SMA(df['close'].values, timeperiod=89)
        if df['high'][-1] < sma5[-1] :
            filtered.append(stock)
    return filtered



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
        
        # log.info("recentArea_est: %.2f" % recentArea_est)
        # log.info("previousArea_sum: %.2f" % previousArea_sum)
        # log.info("max recent price: %.2f" % max(prices[indexOfDeathCross[-1]:]) )
        # log.info("max previous price: %.2f" % max(prices[indexOfDeathCross[-2]:indexOfGoldCross[-1]]) )
        if recentArea_est < previousArea_sum and (max(prices[indexOfDeathCross[-1]:]) > max(prices[indexOfDeathCross[-2]:indexOfGoldCross[-1]]) ) :
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
        
        # this is only an estimation
        bottom_len = indexOfDeathCross[-1] - indexOfDeathCross[-2]
        # log.info("recentArea_est : %.2f, with min price: %.2f" % (recentArea_est, min(prices[indexOfDeathCross[-2]:indexOfGoldCross[-1]])))
        # log.info("previousArea_sum : %.2f, with min price: %.2f" % (previousArea_sum, min(prices[indexOfDeathCross[-1]:])) )
        # log.info("bottom_len: %d" % bottom_len)
        
        # standardize the price and macd_raw to Z value
        # return the diff of price zvalue and macd z value
        prices_z = zscore(prices)
        #macd_raw_z = zscore(np.nan_to_num(macd_raw))
        
        if recentArea_est < previousArea_sum and (min(prices_z[indexOfDeathCross[-2]:indexOfGoldCross[-1]]) / min(prices_z[indexOfDeathCross[-1]:]) > g.lower_ratio_range) :
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
    #得到当前未完成订单
    orders = get_open_orders()
    #循环，撤销订单
    for _order in orders.values():
        g.sell_list.append(_order.security)
        cancel_order(_order)
####################################################################################################