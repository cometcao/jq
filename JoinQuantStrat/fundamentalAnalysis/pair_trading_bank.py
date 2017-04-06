import math
import pandas as pd
import numpy as np
import statsmodels.api as sm
import scipy.stats as scs
import scipy.optimize as sco
import talib as tl
from datetime import timedelta
#from Trader import *
#enable_profile()
bank_stocks=['601398.XSHG', '601288.XSHG','601939.XSHG','601988.XSHG']  # 设置银行股票 工行，建行
   
# 初始化参数
def initialize(context):
    # 初始化此策略
    # 设置要操作的股票池为空，每天需要不停变化股票池
    set_universe([])
    g.riskbench = '000300.XSHG'
    set_commission(PerTrade(buy_cost=0.0002, sell_cost=0.00122, min_cost=5)) 
    set_slippage(FixedSlippage(0)) 
    set_option('use_real_price', True)
    # 设置基准对比为沪深300指数
    
    g.inter = 0.005
    
# 每天交易前调用
def before_trading_start(context):
    g.df_last = history(1, unit='1d', field='close', security_list=bank_stocks, df=False, skip_paused=True, fq='pre')
  
# 每个单位时间(如果按天回测,则每天调用一次,如果按分钟,则每分钟调用一次)调用一次
def handle_data(context, data):
   
    raito = []
    
    for code in bank_stocks:
        raito.append( data[code].close / g.df_last[code][-1] )
        
    if not context.portfolio.positions.keys():
        if max(raito) - min(raito) > g.inter:
            min_index = raito.index(min(raito))
            order_value(bank_stocks[min_index], context.portfolio.total_value)
            g.is_stop = True
    else:
        code = context.portfolio.positions.keys()[0]
    
        index = bank_stocks.index(code)
        if raito[index] - min(raito) > g.inter:
            order_target(code, 0)
            min_index = raito.index(min(raito))
            order_value(bank_stocks[min_index], context.portfolio.total_value)
            g.is_stop = True
            
# 每天交易后调用
def after_trading_end(context):
    if bank_stocks[0] in context.portfolio.positions and context.portfolio.positions[bank_stocks[0]].total_amount > 0:
        record(code0=context.portfolio.positions[bank_stocks[0]].total_amount)
    if bank_stocks[1] in context.portfolio.positions and context.portfolio.positions[bank_stocks[1]].total_amount > 0:
        record(code1=context.portfolio.positions[bank_stocks[1]].total_amount)
    if bank_stocks[2] in context.portfolio.positions and context.portfolio.positions[bank_stocks[2]].total_amount > 0:
        record(code2=context.portfolio.positions[bank_stocks[2]].total_amount)
    if bank_stocks[3] in context.portfolio.positions and context.portfolio.positions[bank_stocks[3]].total_amount > 0:
        record(code3=context.portfolio.positions[bank_stocks[3]].total_amount)    