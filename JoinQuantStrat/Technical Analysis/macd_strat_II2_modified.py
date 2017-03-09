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
from blacklist import *
from jqdata import *
# from scipy.signal import argrelextrema
from api import *
from webtrader import WebTrader
import tradestat
import config
from utility_func import *
from trading_module import *

# global constants
macd_func = partial(talib.MACD, fastperiod=12,slowperiod=26,signalperiod=9)
#macd_func_ext = partial(talib.MACDEXT, fastperiod=12,slowperiod=26,signalperiod=9)

def MACD(prices):
    raw, signal, macd = macd_func(prices)
    # macd = macd * 2
    return raw, signal, macd

#enable_profile()

def realAction(stock, value_pct, context):
    if 'macd_real_action' in config.real_action and config.real_action['macd_real_action'] and context.run_params.type == 'sim_trade':
        try:
            realAction_xq_2(stock[:6], value_pct)
        except:
            traceback.print_exc()
            log.info("We have an issue on xue qiu 2 actions!! for stock %s" % stock)
            send_message("Stock [%s] adjustment to %.2f failed for xue qiu 2" % (stock, value_pct), channel='weixin')        

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
#     g.allow_stop_loss = False
#     g.total_num_of_pos = 5
#     g.trading_hour = 9
#     g.trading_minute = 45
#     g.botUseZvalue = True
#     g.topUseZvalue = True
#     g.buy_period_check_super = '5d' # '5d'
#     g.buy_period_check = '1d' # '1d'
#     g.sell_period_check = '60m' # '60m'

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
    g.sell_period_check = '90m' # '60m'
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
    g.macd_slope = {}

    
def reset_var():
    g.pct_change = {}
    g.period = {}
    g.if_trade = False
    g.macd_slope = {}

def set_params():
    g.upper_ratio_range = 1.03
    g.lower_ratio_range = 0.98
    g.macd_divergence_ratio = {}
    g.stop_loss = 0.91
    g.tailing_stop_loss = 0.91
    g.stock_domain = '000002.XSHG' #399400.XSHE 000002.XSHG
    g.benchmark = '000300.XSHG'
    g.trading_hour = 9
    g.trading_minute = 45
        # 加载统计模块
    g.trade_stat = tradestat.trade_stat()

def set_backtest():
    set_benchmark(g.benchmark) # 更改bench回测基准（银行股指数从2009年9月开始）
    set_option('use_real_price',True) # 用真实价格交易
    log.set_level('order','error')    # 设置报错等级


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
    
    if g.t%g.tc==0 and market_safe(context):# and two_eight_turn(context): #and two_eight_turn(context): #and market_safe(context): # #
        #每g.tc天，交易一次
        g.if_trade=True 
        # 设置手续费与手续费
        set_slip_fee(context) 
        # 设置可行股票池：获得当前开盘     全部上市A股
        #g.feasible_stocks = get_index_stocks(g.stock_domain)
        pddf = get_all_securities(date = context.current_dt.date())
        g.feasible_stocks = pddf.index.values
        filterStockList(context)
        #g.feasible_stocks = set_feasible_stocks(get_index_stocks(g.stock_domain),g.number_of_days,context)

        g.to_buy = check_to_buy(context)
    g.t+=1

def market_safe(context):
    market_price = attribute_history(g.stock_domain, g.number_of_days_wave_backwards, '1d', ('close'), skip_paused=True, df=False)
    market_macd_raw, _, market_hist = MACD(market_price['close'])
    #return market_macd_raw[-1] > 0 or (market_macd_raw[-1] < 0 and market_hist[-1] > market_hist[-2] and market_hist[-2] > market_hist[3])
    if market_hist[-1] < 0:
        log.info("negative market macd!! we need to close all positions")
        g.sell_list = [stock for stock in context.portfolio.positions]
    return market_hist[-1] > 0

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
        # g.stop_loss = 0.97
        # g.tailing_stop_loss = 0.97
    else:
        g.stock_domain = zz500
        # g.stop_loss = 0.93
        # g.tailing_stop_loss = 0.93
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

    major_macd_raw, _, major_hist = MACD(major_df['close'])
    sub_macd_raw, _, sub_hist = MACD(sub_df['close'])
    
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
    # if g.stock_domain == major:
    #     g.stop_loss = 0.97
    #     g.tailing_stop_loss = 0.97
    # else:
    #     g.stop_loss = 0.93
    #     g.tailing_stop_loss = 0.93     
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
                realAction(context.portfolio.positions[stock], 0, context)
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

def rebalance(to_sell, to_buy, context):
    for security in to_sell:
        if security in context.portfolio.positions and not inOpenOrder(security):
            #log.info("short %s - %s" % (security, get_security_info(security).display_name))
            #order_target_value(security, 0)
            close_position(context.portfolio.positions[security])
            realAction(context.portfolio.positions[security], 0, context)
    for security in to_buy:
        if context.portfolio.cash > context.portfolio.portfolio_value/g.total_num_of_pos and security not in context.portfolio.positions and not inOpenOrder(security):
            #log.info("long %s - %s" % (security, get_security_info(security).display_name))
            #order_target_value_new(security, context.portfolio.portfolio_value/g.total_num_of_pos)   
            open_position(security, context.portfolio.portfolio_value/g.total_num_of_pos)
            realAction(security, 100/g.total_num_of_pos, context)


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
                log.info("add %s in sell list due to stop loss" % stock)
                to_sell.append(stock)
            elif g.allow_stop_loss and (pos.price / g.max_price[stock] < sg):
                log.info("add %s in sell list due to tailing stop loss" % stock)
                to_sell.append(stock)
            #record max price for the stock
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
        df = attribute_history(stock, g.number_of_days_backwards, g.buy_period_check, ('high', 'low', 'open', 'close', 'volume'), df=True)
        df_s = attribute_history(stock, g.number_of_days_wave_backwards, g.buy_period_check_super, ('high','low', 'close'), df=False)
        if (not np.isnan(df['high'][-1])) and (not np.isnan(df['low'][-1])) and (not np.isnan(df['close'][-1])):
            if macd_bottom_divergence(df, df_s, context, stock):
                chosen.append(stock)
    mcap_stock = []
    if chosen:
        mcap_stock = getPeInfo(chosen, context)
        #mcap_stock = getMcapInfo(chosen, context)
        #mcap_stock = sorted(g.macd_slope.items(), reverse=True)
    return mcap_stock

def macd_bottom_divergence(df, df_s, context, stock):
    df.loc[:,'macd_raw'], _, df.loc[:,'macd'] = MACD(df['close'].values)
    df = df.dropna()
    # return checkAtBottomDoubleCross_v2(df)
    return checkAtBottomDoubleCross_v2(df)
    #macd_raw, _, hist = MACD(df['close'])
    #macd_raw_s, _, hist_s = MACD(df_s['close'])
    
    # checkResult, slope = checkAtBottomGoldCross(macd_raw, hist, df['low']) 
    # g.macd_slope[slope] = stock
    # return checkResult
    
    #checkResult = checkAtBottomDoubleCross(macd_raw, hist, df['low']) 
    #if np.isnan(hist_s[-1]) or np.isnan(hist_s[-2]):
    #    return False
    #else:
    #    return checkResult and hist_s[-1] > hist_s[-2] and hist_s[-2] > hist_s[-3]

def checkAtBottomDoubleCross_v2(df):
    # bottom divergence
    mask = df['macd'] > 0
    mask = mask[mask==True][mask.shift(1) == False]
    
    mask2 = df['macd'] < 0
    mask2 = mask2[mask2==True][mask2.shift(1)==False]
    try:
        dkey2 = mask2.keys()[-2]
        dkey1 = mask2.keys()[-1]
        
        gkey2 = mask.keys()[-2]
        gkey1 = mask.keys()[-1]
        result = df.loc[dkey2:gkey2, 'low'].min(axis=0) > df.loc[dkey1:gkey1, 'low'].min(axis=0) and \
               df.macd_raw[gkey2] < df.macd_raw[gkey1] < 0 and \
               df.macd[-2] < 0 < df.macd[-1]
        return result
    except IndexError:
        return False

def macd_top_divergence(df, context, data):
    macd_raw, signal, hist = MACD(df['close'])
    return checkAtTopDoubleCross(macd_raw, hist, df['high']) 

def filterStockList(context):
    g.feasible_stocks = filter_blacklist_stock(context, g.feasible_stocks)
    g.feasible_stocks = filter_paused_stock(g.feasible_stocks)
    if g.stock_filter:
        g.feasible_stocks = filter_st_stock(g.feasible_stocks)
        g.feasible_stocks = filter_limitup_stock(context, g.feasible_stocks)
        g.feasible_stocks = filter_limitdown_stock(context, g.feasible_stocks)    


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
        recentlength_est = (max_val_Index - indexOfGoldCross[-1]) * 2
        
        previousArea = macd_hist[indexOfGoldCross[-2]:indexOfDeathCross[-1]]
        previousArea_sum = abs(sum(previousArea))
        previouslength = indexOfDeathCross[-1] - indexOfGoldCross[-2]
        
        if recentlength_est == 0 or previouslength == 0:
            return False
        
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

def checkAtBottomGoldCross(macd_raw, macd_hist, prices):
    # At relatively high level, gold cross is good enough
    indexOfGoldCross = [i for i, j in enumerate(macd_hist) if isGoldCross(i,j,macd_hist)]

    if indexOfGoldCross and indexOfGoldCross[-1] == len(macd_raw)-1 and macd_raw[-1] < 0:
        return True, zscore(np.nan_to_num(macd_hist))[-1]
    return False, 0
    

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
        return False

    # check for standard double bottom macd divergence pattern
    # green bar is reducing
    if macd_raw[-1] < 0 and macd_hist[-1] < 0 and macd_hist[-1] > macd_hist[-2]: 
        # calculate current negative bar area 
        latest_hist_area = macd_hist[indexOfDeathCross[-1]:]
        min_val_Index = latest_hist_area.tolist().index(min(latest_hist_area))
        recentArea_est = abs(sum(latest_hist_area[:min_val_Index])) * 2
        recentlength_est = (min_val_Index - indexOfDeathCross[-1]) * 2
        
        previousArea = macd_hist[indexOfDeathCross[-2]:indexOfGoldCross[-1]]
        previousArea_sum = abs(sum(previousArea))
        previouslength = indexOfGoldCross[-1] - indexOfDeathCross[-2]
        
        if recentlength_est == 0 or previouslength == 0:
            return False 

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
            return True
    return False

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



def open_position(security, amount):
    order = order_target_value_new(security, amount) # 可能会因停牌失败
    if order != None and order.status == OrderStatus.held:
        g.max_price[security] = order.price
        

def close_position(position):
    security = position.security
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
    