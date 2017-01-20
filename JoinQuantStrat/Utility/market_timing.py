# -*- encoding: utf8 -*-
'''
Created on 31 Oct 2016

@author: MetalInvest
'''

from kuanke.user_space_api import *
from utility_func import *

def market_safe(context):
    market_price = attribute_history(g.stock_domain, g.number_of_days_wave_backwards, '1d', ('close'), skip_paused=True, df=False)
    market_macd_raw, _, market_hist = MACD(market_price['close'])
    #return market_macd_raw[-1] > 0 or (market_macd_raw[-1] < 0 and market_hist[-1] > market_hist[-2] and market_hist[-2] > market_hist[3])
    if market_hist[-1] < 0:
        log.info("negative market macd!! we need to close all positions")
        g.sell_list = [stock for stock in context.portfolio.positions]
    return market_hist[-1] > 0

def two_eight_turn_v3(context, major, sub):
    price_major = attribute_history(major, 21, '1d', ('close'), df=False)
    price_sub = attribute_history(sub, 21, '1d', ('close'), df=False)
    major_delta = (price_major['close'][-1] - price_major['close'][0]) / price_major['close'][0]
    sub_delta = (price_sub['close'][-1] - price_sub['close'][0]) / price_sub['close'][0]

    log.info("growth for 80%% weighted with change rate %.2f%%" % (major_delta*100))
    log.info("growth for 20%% weighted with change rate %.2f%%" % (sub_delta*100))
    if major_delta < 0 and sub_delta < 0:
        log.info("negative growth for all!")
        return -1
    elif major_delta > sub_delta:
        return 8
    else:
        return 2
    
def two_eight_turn_inverse(context, major, sub):
    price_major = attribute_history(major, 21, '1d', ('close'), df=False)
    price_sub = attribute_history(sub, 21, '1d', ('close'), df=False)
    major_delta = (price_major['close'][-1] - price_major['close'][0]) / price_major['close'][0]
    sub_delta = (price_sub['close'][-1] - price_sub['close'][0]) / price_sub['close'][0]
    
    log.info("growth for 80%% weighted with change rate %.2f%%" % (major_delta*100))
    log.info("growth for 20%% weighted with change rate %.2f%%" % (sub_delta*100))
    if major_delta > 0 and sub_delta > 0:
        if major_delta < sub_delta:
            return 8
        else:
            return 2
    elif major_delta < 0:
        return 8    
    elif sub_delta < 0:
        return 2
    else:
        return -1
    
def two_eight_turn_v4(context, major, sub):
    major_period = findPeriod_v2(major)
    sub_period = findPeriod_v2(sub)
    price_major = attribute_history(major, major_period, '1d', ('close'), df=False)
    price_sub = attribute_history(sub, sub_period, '1d', ('close'), df=False)
    major_delta = (price_major['close'][-1] - price_major['close'][0]) / price_major['close'][0]
    sub_delta = (price_sub['close'][-1] - price_sub['close'][0]) / price_sub['close'][0]
    
    log.info("growth for 80%% weighted with change rate %.2f%%" % (major_delta*100))
    log.info("growth for 20%% weighted with change rate %.2f%%" % (sub_delta*100))
    if major_delta < 0 and sub_delta < 0:
        log.info("negative growth for all!")
        return -1
    elif major_delta > sub_delta:
        return 8
    else:
        return 2
    
def two_eight_turn_macd(context, major, sub):
    major_df = attribute_history(major, 55, '1d', ('close'), skip_paused=True, df=False)
    sub_df = attribute_history(sub, 55, '1d', ('close'), skip_paused=True, df=False) 
    major_macd_raw, _, major_hist = MACD(major_df['close'])
    sub_macd_raw, _, sub_hist = MACD(sub_df['close'])
    if major_hist[-1] < major_hist[-2] and sub_hist[-1] < sub_hist[-2]:
        return -1
    elif major_hist[-1] < major_hist[-2]:
        return 2
    elif sub_hist[-1] < sub_hist[-2]:
        return 8
    else:
        major_growth = (major_hist[-1] - major_hist[-2]) / abs(major_hist[-2])
        sub_growth = (sub_hist[-1] - sub_hist[-2]) / abs(sub_hist[-2])
        if major_growth > sub_growth:
            return 8
        else:
            return 2

def two_eight_turn_macd_v2(context, major, sub):
    major_df = attribute_history(major, 55, '1d', ('close'), skip_paused=True, df=False)
    sub_df = attribute_history(sub, 55, '1d', ('close'), skip_paused=True, df=False) 
    major_macd_raw, _, major_hist = MACD(major_df['close'])
    sub_macd_raw, _, sub_hist = MACD(sub_df['close'])
    if major_hist[-1] < 0 and sub_hist[-1] < 0:
        return -1
    elif sub_hist[-1] < 0:
        return 8
    elif major_hist[-1] < 0:
        return 2
    else:
        major_growth = (major_hist[-1] - major_hist[-2]) / abs(major_hist[-2])
        sub_growth = (sub_hist[-1] - sub_hist[-2]) / abs(sub_hist[-2])
        if major_growth > sub_growth:
            return 8
        else:
            return 2

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