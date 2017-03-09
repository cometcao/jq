"""
This is a long only strategy
filter
1. Use MACD divergence for buy and sell signal
2. select stocks with smaller market cap

long check procedure:
1. super level macd increase for two period (week)
2. current level macd divergence (day)
3. sub level macd gold cross (60m)

short check procedure:
1. current level death cross(90m)
2. sub level macd divergence(30m) 
3. stop loss

trade
buy: macd bottom reversal 
sell: macd top reverse or stop loss

"""
import talib
import numpy as np

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
from market_timing import *
from seek_cash_flow import * 
from chip_migration import *
from scipy.signal import argrelextrema

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
    log.info("g.buy_period_check_sub: %s" % g.buy_period_check_sub)
    log.info("g.sell_period_check: %s" % g.sell_period_check)
    log.info("g.sell_period_check_sub: %s" % g.sell_period_check_sub)
    log.info("g.stop_loss: %f" % g.stop_loss)
    log.info("g.tailing_stop_loss: %f" % g.tailing_stop_loss)
    log.info("################################################")    
    
# def after_code_changed(context):
#     g.stock_domain = '000002.XSHG'
#     g.stock_filter = True
#     g.dynamic_stop_loss = False
#     g.allow_stop_loss = True
#     g.allow_tailing_stop_loss = False
#     g.macd_death_cross_sl = True
#     g.total_num_of_pos = 5
#     g.trading_hour = 14
#     g.trading_minute = 45
#     g.botUseZvalue = False
#     g.topUseZvalue = False
#     g.buy_period_check_super = '5d' # '5d'
#     g.buy_period_check = '1d' # '1d'
#     g.buy_period_check_sub = '30m'
#     g.sell_period_check = '90m' 
#     g.sell_period_check_sub = '60m'

class level_indicator:
    levels = ['5m', '15m', '60m', '1d', '5d']
    def __init__(self, current_level):
        self.level = current_level
        self.current_level_idx = level_indicator.levels.index(current_level)
    def higher_level(self):
        return level_indicator.levels[self.current_level_idx + 1]
    def lower_level(self):
        return level_indicator.levels[self.current_level_idx - 1]
    def higher_level(self,level):
        idx = level_indicator.levels.index(level)
        return level_indicator.levels[idx+1]
    def lower_level(self,level):
        idx = level_indicator.levels.index(level)
        return level_indicator.levels[idx-1]
        
def set_variables():
    g.user = None
    g.total_num_of_pos = 3
    g.number_of_days = 30
    g.number_of_days_wave_backwards = 60
    g.number_of_days_backwards = 233
    g.number_of_N_Zval = 100
    g.reversal_index = 0.1
    g.t = 0                # 记录回测运行的天数
    g.if_trade = False     # 当天是否交易
    g.tc = 1   # trigger action per # of days
    g.m = 0
    g.mbc = 90 # trigger buy action per X min / day
    g.msc = 45 # trigger sell action per X min / day
    g.buy_period_check_super = '1d' # '5d'
    g.buy_period_check = '60m' # '1d'
    g.buy_period_check_sub = '15m' # 30m
    g.sell_period_check = '1d' # '90m' 240m
    g.sell_period_check_sub = '60m' # '60m' 1d
    g.sell_list = [] # if we have stocks failed to sell, we need to record it and try to sell the next day
    g.to_buy = []
    g.pct_change = {}
    g.period = {}
    g.max_price = {} # this is set when position open, and cleared when position closed
    g.stock_filter = True
    g.dynamic_stop_loss = False
    g.allow_stop_loss = False
    g.allow_tailing_stop_loss = False
    g.macd_death_cross_sl = True
    g.max_holding = False
    g.botUseZvalue = False
    g.topUseZvalue = False
    g.is_day_curve_protect = True
    g.level = level_indicator("60m")
    g.long_record = {}
    g.port_value = []

    
def reset_var():
    g.pct_change = {}
    g.period = {}
    g.if_trade = False

def set_params():
    g.upper_ratio_range = 1.05
    g.lower_ratio_range = 1
    g.macd_divergence_ratio = {}
    g.stop_loss = 0.95
    g.tailing_stop_loss = 0.95
    g.stock_domain = '000002.XSHG' #399400.XSHE 000002.XSHG
    g.benchmark = '000300.XSHG'
    g.trading_hour = 14
    g.trading_minute = 46
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
    
    # schedule functions
    run_daily(first_thing_to_do, '09:36')
    
    run_daily(clear_to_sell_list, '09:41') # if anything left from previous day for sell, we need to clear it
    
    sell_gen = yield_times(step=g.msc)
    for ii in range(360/g.msc):
        run_daily(sell_action, sell_gen.next())
    
    # buy_gen = yield_times(step=60)
    # for i in range(6):
    #     run_daily(buy_action_intra, buy_gen.next()) #buy_action_intra buy_action_sub
    
    run_daily(buy_action, '%s:%s' % (g.trading_hour, g.trading_minute))
    
    # run_daily(real_action_email_final, time)
    

def yield_times(h=9, m=46, step=30):
    from datetime import date, datetime, time, timedelta
    start = datetime.combine(date.today(), time(h, m)) 
    end =  datetime.combine(date.today(), time(h+5, m)) 
    yield start.strftime("%H:%M")
    while start <= end:
        start += timedelta(minutes=step)
        yield start.strftime("%H:%M")
    

def before_trading_start(context):
    """
    Called every day before market open.
    """
    displayVar()
    
def first_thing_to_do(context):
    
    # market_growth_check = two_eight_turn_v4(context, '000016.XSHG', '399333.XSHE')
    
    if g.t%g.tc==0: #and market_growth_check > 0:# and market_safe(context):# and two_eight_turn(context): #and two_eight_turn(context): #and market_safe(context): # #
        #每g.tc天，交易一次
        g.if_trade=True 
        # 设置手续费与手续费
        set_slip_fee(context) 
        # 设置可行股票池：获得当前开盘 
        # shz50 = get_index_stocks('000016.XSHG')
        # shz180 = get_index_stocks('000010.XSHG')
        # shz380 = get_index_stocks('000009.XSHG')

        # szz100 = get_index_stocks('399001.XSHE')
        # szz300 = get_index_stocks('399007.XSHE')
        # zxr100 = get_index_stocks('399333.XSHE') # 中小R 100
        # cyb100 = get_index_stocks('399006.XSHE') # 创业板
   
        # if market_growth_check == 8:
        #     # g.feasible_stocks = list(set(shz50+shz180+szz100))
        #     g.feasible_stocks = shz50
        # else:
        #     # g.feasible_stocks = list(set(zxr100+cyb100))
        #     g.feasible_stocks = zxr100
        # g.feasible_stocks = shz50 + zxr100
        # g.feasible_stocks = list(set(shz50+shz180+shz380+szz100 + szz300 + zxr100+cyb100))
        # g.feasible_stocks = getAllStocks(context)
        
        g.feasible_stocks = [x[1] for x in getCirMcapInfo(context, num_limit=1000, cir_cap_limit=300, max_pe=200)]
        
        filterStockList(context)
        #g.feasible_stocks = set_feasible_stocks(g.feasible_stocks,g.number_of_days,context)
        
        pick_stock(context)
    # if market_growth_check < 0:
    #     g.sell_list += context.portfolio.positions.keys()
    g.t+=1

def pick_stock(context):
    new_candidate = check_to_buy(context)
    for n in new_candidate:
        new_stock = n[1]
        already_in_list = False
        for o in g.to_buy:
            if o[1] == new_stock:
                g.to_buy.append(n)
                g.to_buy.remove(o)
                already_in_list = True
                break
        if not already_in_list:
            g.to_buy.append(n)
    g.to_buy.sort()
    # g.to_buy = sorted(set(g.to_buy + new_candidate))
    log.info("Candidate stocks for long: %s" % [x[1] for x in g.to_buy])

def sell_action(context):
    to_sell = check_to_sell(context)
    rebalance(to_sell, [], context)
    
def buy_action(context): # used for fixed time long stock
    if g.if_trade and g.to_buy:
        # long_candidate = [x[1] for x in g.to_buy if x[2] == context.current_dt.date() or (x[2] != context.current_dt.date() and macd_bottom_divergence(context, x[1]))]
        long_candidate = [x[1] for x in g.to_buy]
        available_slots = g.total_num_of_pos - len(context.portfolio.positions)
        rebalance([], long_candidate[:available_slots], context)
        g.to_buy = [x for x in g.to_buy if x[1] not in long_candidate[:available_slots]]

def buy_action_sub(context): # used for intra-day level long stock
    if g.if_trade and g.to_buy:
        long_candidate = []
        for stock_item in g.to_buy:
            stock = stock_item[1]
            candidate_date = stock_item[2]
            df_sub = attribute_history(stock, g.number_of_days_backwards, g.buy_period_check_sub, ('close'), df=False)
            macd_raw_sub, _, macd_sub = MACD(df_sub['close'])
            df_current = attribute_history(stock, g.number_of_days_wave_backwards, g.buy_period_check, ('close'), df=True)
            df_current.loc[:,'macd_raw'], _, _ = MACD(df_current['close'].values)
            if macd_sub[-1] > macd_sub[-2] and macd_raw_sub[-1] < 0:
                if candidate_date < context.current_dt.date():
                    if df_current.macd_raw[-1] > df_current.loc[pd.Timestamp(candidate_date), 'macd_raw']:
                        long_candidate.append(stock)
                        g.to_buy.remove(stock_item)
                else:
                    long_candidate.append(stock)
                    g.to_buy.remove(stock_item)
        rebalance([], long_candidate, context)

def buy_action_intra(context):
    if g.if_trade:
        pick_stock(context)
    if g.to_buy:
        long_candidate = []
        for stock_item in g.to_buy:
            stock = stock_item[1]
            # df_sub = attribute_history(stock, g.number_of_days_backwards, g.buy_period_check_sub, ('close'), df=False)
            # macd_raw_sub, _, macd_sub = MACD(df_sub['close'])
            # if macd_sub[-1] > macd_sub[-2] and macd_raw_sub[-1] < 0:
            long_candidate.append(stock) # PREVIOUS_CHANGE
            # g.to_buy.remove(stock_item)
        rebalance([], long_candidate, context)
        g.to_buy = []
                
        
  
def remove_outdated_candidate(context):
    for stock_item in g.to_buy:
        stock = stock_item[1]
        candidate_date = stock_item[2]
        period = findPeriod_v2(stock)
        delta = context.current_dt.date() - candidate_date 
        if delta.days >= period and stock_item in g.to_buy:
            g.to_buy.remove(stock_item)

def clear_to_sell_list(context):
    if g.sell_list:
        for stock in g.sell_list:
            if stock in context.portfolio.positions:
                #log.info("short %s from sell_list" % stock)
                #order_target_value(stock, 0)
                close_position(context.portfolio.positions[stock])
                realAction(context.portfolio.positions[stock], 0, context)
        g.sell_list = []

def generate_portion(num):
    total_portion = num * (num+1) / 2
    start = num
    while num != 0:
        yield float(num) / float(total_portion)
        num -= 1

def rebalance(to_sell, to_buy, context):
    for security in to_sell:
        if security in context.portfolio.positions and not inOpenOrder(security):
            close_position(context.portfolio.positions[security])
            realAction(context.portfolio.positions[security], 0, context)
            if security in g.long_record:
                del g.long_record[security]

    position_count = len(context.portfolio.positions)
    if g.total_num_of_pos > position_count:
        buy_num = g.total_num_of_pos - position_count
        portion_gen = generate_portion(buy_num)
        available_cash = context.portfolio.cash
        for security in to_buy:
            if context.portfolio.positions[security].total_amount == 0:
                buy_portion = portion_gen.next()
                value = available_cash * buy_portion
                open_position(security, value)
                realAction(security, value/context.portfolio.total_value, context)
                max_holding_period = findPeriod_v2(security)
                g.long_record[security] = (context.current_dt.date(), max_holding_period)
                if len(context.portfolio.positions) == g.total_num_of_pos :
                    break    

def check_to_sell(context):
    if g.is_day_curve_protect:
        if len(g.port_value) >= 20:
            if context.portfolio.total_value < g.port_value[-20]*0.99:
                log.info("==> 启动资金曲线保护, 20日前资产: %f, 当前资产: %f" %(g.port_value[-20], context.portfolio.total_value))
                clear_position(context)
    to_sell = []
    for stock in context.portfolio.positions:
        pos = context.portfolio.positions[stock]
        current_data = get_current_data()
        if pos.sellable_amount > 0 and not current_data[stock].paused:
            current_level = g.sell_period_check
            lower_level = g.sell_period_check_sub
            if pos.price / pos.avg_cost > 1.1:
                current_level = g.level.lower_level(current_level)
                lower_level = g.level.lower_level(lower_level)
            df = attribute_history(stock, g.number_of_days_backwards, current_level, ('high', 'low', 'open', 'close', 'volume'), df=True)
            df.loc[:,'macd_raw'], _, df.loc[:,'macd'] = MACD(df['close'].values) 
            df_sub = attribute_history(stock, g.number_of_days_backwards, lower_level, ('high', 'low', 'open', 'close', 'volume'), df=True)
            
            sl = g.stop_loss
            sg = g.tailing_stop_loss

            if g.allow_stop_loss and g.dynamic_stop_loss:
                recent_period = findPeriod_v2(stock)
                threthold = get_stop_loss_threshold(stock, recent_period)
                if threthold:
                    sl = 1 - threthold
                    sg = sl
                    #sg = 1 - (threthold / (pos.price / pos.avg_cost))
    
            if (macd_top_divergence(df_sub, context)): 
                log.info("add %s in sell list due to top divergence" % stock)
                to_sell.append(stock)
            elif g.allow_stop_loss and (pos.price / pos.avg_cost < sl): #(df['close'][-1]/df['close'][-2]<sl)
                log.info("add %s in sell list due to stop loss" % stock)
                to_sell.append(stock)
            elif g.macd_death_cross_sl and df.macd[-1] < 0 : #< df.macd[-2] and df.macd_raw[-1] > 0 # PREVIOUS_CHANGE
                log.info("add %s in sell list due to death cross stop loss" % stock)
                to_sell.append(stock)
            elif g.allow_tailing_stop_loss and (pos.price / g.max_price[stock] < sg):
                log.info("add %s in sell list due to tailing stop loss" % stock)
                to_sell.append(stock)
            else:
                #record max price for the stock
                if df['close'][-1] > g.max_price[stock]: # update the max price
                    g.max_price[stock] = df['close'][-1]               
                long_date, max_period = g.long_record[stock]
                trade_days = get_trade_days(end_date=context.current_dt.date(), count=max_period)
                if g.max_holding and long_date <= trade_days[0] and pos.price / pos.avg_cost < g.upper_ratio_range:
                    log.info("add %s in sell list due to max holding limit" % stock)
                    to_sell.append(stock)
    return to_sell

def check_to_buy(context):
    from_anal = g.feasible_stocks
    from_anal = filterByMA(from_anal, context)
    from_anal = filterByMACD(from_anal, context)
    afterMACD = filterByAnal(from_anal, context)
    # order by marekt cap, small to big
    # from_anal.sort() # no need to sort, it's done by query
    # mcap_stock = []
    # if from_anal:
        #mcap_stock = getPeInfo(from_anal, context)
        # mcap_stock = getMcapInfo(from_anal, context)
    # df = cow_stock_value(from_anal)
    stock_list = []
    if afterMACD:
        stock_list = chip_concentration(context, afterMACD[:50])
    else:
        # market_df = attribute_history('000300.XSHG', 300, g.buy_period_check_super, ('close'), df=False)
        # market_sma60 = talib.SMA(market_df['close'], timeperiod=60)
        # if market_sma60[-1] / market_sma60[-20] > 1.05: # only during bull market        
        market_df = attribute_history('000300.XSHG', 55, '5d', ('close'), df=False)
        market_df['macd_raw'], _, market_df['macd'] = MACD(market_df['close'])
        if market_df['macd'][-1] > 0:
            stock_list = chip_concentration(context, from_anal[:50])
    # mcap_stock = [(1/item['score'], idx, context.current_dt.date()) for idx, item in df.iterrows()]
    mcap_stock = [(1/score, stock, context.current_dt.date()) for stock, score in stock_list]
    return mcap_stock

def filterByMA(stock_list, context):
    filtered_list = []
    market_df = attribute_history('000300.XSHG', 300, g.buy_period_check_super, ('close'), df=False)
    market_sma250 = talib.SMA(market_df['close'], timeperiod=250)
    market_growth_rate = market_sma250[-1] / market_sma250[-20]
    for stock in stock_list:
        df = attribute_history(stock, 300, g.buy_period_check_super, ('close'), df=False)
        if not np.isnan(df['close'][-1]):
            sma250 = talib.SMA(df['close'], timeperiod=250)
            if not np.isnan(sma250[-1]) and \
                (sma250[-1] / sma250[-20] > market_growth_rate or sma250[-1] / sma250[-20] > 1):
                # (df['close'][-1] > sma250[-1] and df['close'][-2] < sma250[-2] or \
                # df['close'][-1] > df['close'][-2] > sma250[-2] and df['close'][-3] < sma250[-3]):
                filtered_list.append(stock)
    return filtered_list

def filterByAnal(filtered, context):
    market_df = attribute_history('000300.XSHG', 300, g.buy_period_check_super, ('close'), df=False)
    market_sma20 = talib.SMA(market_df['close'], timeperiod=20)
    market_sma60 = talib.SMA(market_df['close'], timeperiod=60)
    chosen = []
    for stock in filtered:
        if market_sma20[-1] < market_sma60[-1]: # bear
            # print "check %s" % stock
            if macd_bottom_divergence(context, stock):
                chosen.append(stock)
        else:
            chosen.append(stock)
    return chosen

def filterByMACD(filtered, context):
    chosen = []
    for stock in filtered:
        df_s = attribute_history(stock, g.number_of_days_wave_backwards, g.buy_period_check_super, ('close'), df=False)
        macd_raw_s, _, hist_s = MACD(df_s['close'])
        if (not np.isnan(hist_s[-1])) and (not np.isnan(hist_s[-2])) and macd_raw_s[-1] > macd_raw_s[-2] > macd_raw_s[-3] and macd_raw_s[-1] < 0:
            chosen.append(stock)
    return chosen
        
def macd_bottom_divergence(context, stock):
    df = attribute_history(stock, g.number_of_days_backwards, g.buy_period_check, ('high', 'low', 'open', 'close', 'volume'), df=True)
    if (np.isnan(df['high'][-1])) or (np.isnan(df['low'][-1])) or (np.isnan(df['close'][-1])):
        return False
    
    df.loc[:,'macd_raw'], _, df.loc[:,'macd'] = MACD(df['close'].values)
    # df.loc[:,'OBV'] = talib.OBV(df['close'].values,double(df['volume'].values))
    df.loc[:,'vol_ma'] = talib.SMA(df['volume'].values, 5)
    df = df.dropna()

    #checkResult = checkAtBottomDoubleCross_chan(df)
    checkResult = checkAtBottomDoubleCross_v2(df)
    return checkResult 


def checkAtBottomDoubleCross_chan(df):
    # shortcut
    if not (df.shape[0] > 2 and df['macd'][-1] < 0 and df['macd'][-1] > df['macd'][-2]):
        return False
    
    # gold
    mask = df['macd'] > 0
    mask = mask[mask==True][mask.shift(1) == False]
    
    # death
    mask2 = df['macd'] < 0
    mask2 = mask2[mask2==True][mask2.shift(1)==False]
    
    try:
        gkey1 = mask.keys()[-1]
        dkey2 = mask2.keys()[-2]
        dkey1 = mask2.keys()[-1]
        recent_low = previous_low = 0.0
        if g.botUseZvalue:
            low_mean = df.loc[dkey2:,'low'].mean(axis=0)
            low_std = df.loc[dkey2:,'low'].std(axis=0)
            df.loc[dkey2:, 'low_z'] = (df.loc[dkey2:,'low'] - low_mean) / low_std
            
            recent_low = df.loc[dkey1:,'low_z'].min(axis=0)
            previous_low = df.loc[dkey2:gkey1, 'low_z'].min(axis=0)
        else:
            recent_low = df.loc[dkey1:,'low'].min(axis=0)
            previous_low = df.loc[dkey2:gkey1, 'low'].min(axis=0)
            
        recent_min_idx = df.loc[dkey1:,'low'].idxmin()
        loc = df.index.get_loc(recent_min_idx)
        recent_min_idx_nx = df.index[loc+1]
        recent_area_est = abs(df.loc[dkey1:recent_min_idx_nx, 'macd'].sum(axis=0)) * 2
        # recent_red_area = df.loc[gkey1:dkey1, 'macd'].sum(axis=0)
        
        previous_area = abs(df.loc[dkey2:gkey1, 'macd'].sum(axis=0))
        previous_close = df['close'][-1]
        
        result =  df.macd[-2] < df.macd[-1] < 0 and \
                0 > df.macd_raw[-1] and \
                recent_area_est < previous_area and \
                previous_low >= recent_low and \
                df.loc[dkey2,'vol_ma'] > df.vol_ma[-1]
                # abs (recent_low / previous_low) > g.lower_ratio_range
                # recent_area_est < recent_red_area and \
                # > df.macd_raw[recent_min_idx]
                #previous_low >= recent_low and \
                #previous_close / df.loc[recent_min_idx, 'close'] < g.upper_ratio_range
                # abs (recent_low / previous_low) > g.lower_ratio_range
                
        return result
    except IndexError:
        return False
        
def checkAtTopDoubleCross_chan(df):
    if not (df['macd'][-1] > 0 and df['macd'][-1] < df['macd'][-2]):
        return False
    
    # gold
    mask = df['macd'] > 0
    mask = mask[mask==True][mask.shift(1) == False]
    
    # death
    mask2 = df['macd'] < 0
    mask2 = mask2[mask2==True][mask2.shift(1)==False]
    
    try:
        gkey1 = mask.keys()[-1]
        gkey2 = mask.keys()[-2]
        dkey1 = mask2.keys()[-1]
        recent_high = previous_high = 0.0
        if g.topUseZvalue:
            high_mean = df.loc[gkey2:,'high'].mean(axis=0)
            high_std = df.loc[gkey2:,'high'].std(axis=0)
            df.loc[gkey2:, 'high_z'] = (df.loc[gkey2:,'high'] - high_mean) / high_std       
            
            recent_high = df.loc[gkey1:,'high_z'].min(axis=0)
            previous_high = df.loc[gkey2:dkey1, 'high_z'].min(axis=0)
        else:
            recent_high = df.loc[gkey1:,'high'].max(axis=0)
            previous_high = df.loc[gkey2:dkey1, 'high'].max(axis=0)
        
        recent_high_idx = df.loc[gkey1:,'high'].idxmax()
        loc = df.index.get_loc(recent_high_idx)
        recent_high_idx_nx = df.index[loc+1]
        recent_area_est = df.loc[gkey1:recent_high_idx_nx, 'macd'].sum(axis=0) * 2
        previous_area = df.loc[gkey2:dkey1, 'macd'].sum(axis=0)
        return df.macd[-2] > df.macd[-1] > 0 and \
                df.macd_raw[recent_high_idx] > df.macd_raw[-1] > 0 and \
                recent_area_est < previous_area and \
                recent_high >= previous_high
                # abs(recent_high / previous_high) > g.lower_ratio_range
    except IndexError:
        return False

def checkAtBottomDoubleCross_v2(df):
    # bottom divergence gold
    mask = df['macd'] > 0
    mask = mask[mask==True][mask.shift(1) == False]#[mask.shift(2)==False]
    
    mask2 = df['macd'] < 0
    mask2 = mask2[mask2==True][mask2.shift(1)==False]#[mask2.shift(2)==False]#[mask2.shift(-1)==True]
    try:
        dkey2 = mask2.keys()[-2]
        dkey1 = mask2.keys()[-1]
        
        gkey2 = mask.keys()[-2]
        gkey1 = mask.keys()[-1]
        
        result = df.loc[dkey2:gkey2, 'close'].min(axis=0) > df.loc[dkey1:gkey1, 'close'].min(axis=0) and \
               df.macd_raw[gkey2] < df.macd_raw[gkey1] < 0 and \
               df.loc[dkey2:gkey2, 'macd_raw'].min(axis=0) < df.loc[dkey1:gkey1, 'macd_raw'].min(axis=0) and \
               df.macd[-2] < 0 < df.macd[-1] and \
               df.loc[dkey2,'vol_ma'] > df.vol_ma[-1]
        return result
    except IndexError:
        return False

def macd_top_divergence(df, context):
    df.loc[:,'macd_raw'], _, df.loc[:,'macd'] = MACD(df['close'].values)
    return checkAtTopDoubleCross_chan(df) 

def filterStockList(context):
    g.feasible_stocks = filter_blacklist_stock(context, g.feasible_stocks)
    g.feasible_stocks = filter_paused_stock(g.feasible_stocks)
    if g.stock_filter:
        g.feasible_stocks = filter_st_stock(g.feasible_stocks)
        g.feasible_stocks = filter_limitup_stock(context, g.feasible_stocks)
        g.feasible_stocks = filter_limitdown_stock(context, g.feasible_stocks)    

def zscore(series):
    return (series - series.mean()) / np.std(series)

#每个交易日结束运行
def after_trading_end(context):
    #得到当前未完成订单
    orders = get_open_orders()
    #循环，撤销订单
    for _order in orders.values():
        if not _order.is_buy: # we need to sell again tomorrow if failed to sell today
            g.sell_list.append(_order.security)
        cancel_order(_order)
    reset_var()
    # remove_outdated_candidate(context)
    g.port_value.append(context.portfolio.total_value)
    g.to_buy = []
    g.trade_stat.report(context)

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
    
# 清空卖出所有持仓
def clear_position(context):
    if context.portfolio.positions:
        log.info("==> 清仓，卖出所有股票")
        for stock in context.portfolio.positions.keys():
            position = context.portfolio.positions[stock]
            close_position(position)