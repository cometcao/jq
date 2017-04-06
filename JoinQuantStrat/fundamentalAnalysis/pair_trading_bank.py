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
bank_stocks=['601398.XSHG', '601288.XSHG','601939.XSHG','601988.XSHG']  # �������й�Ʊ ���У�����
   
# ��ʼ������
def initialize(context):
    # ��ʼ���˲���
    # ����Ҫ�����Ĺ�Ʊ��Ϊ�գ�ÿ����Ҫ��ͣ�仯��Ʊ��
    set_universe([])
    g.riskbench = '000300.XSHG'
    set_commission(PerTrade(buy_cost=0.0002, sell_cost=0.00122, min_cost=5)) 
    set_slippage(FixedSlippage(0)) 
    set_option('use_real_price', True)
    # ���û�׼�Ա�Ϊ����300ָ��
    
    g.inter = 0.005
    
# ÿ�콻��ǰ����
def before_trading_start(context):
    g.df_last = history(1, unit='1d', field='close', security_list=bank_stocks, df=False, skip_paused=True, fq='pre')
  
# ÿ����λʱ��(�������ز�,��ÿ�����һ��,���������,��ÿ���ӵ���һ��)����һ��
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
            
# ÿ�콻�׺����
def after_trading_end(context):
    if bank_stocks[0] in context.portfolio.positions and context.portfolio.positions[bank_stocks[0]].total_amount > 0:
        record(code0=context.portfolio.positions[bank_stocks[0]].total_amount)
    if bank_stocks[1] in context.portfolio.positions and context.portfolio.positions[bank_stocks[1]].total_amount > 0:
        record(code1=context.portfolio.positions[bank_stocks[1]].total_amount)
    if bank_stocks[2] in context.portfolio.positions and context.portfolio.positions[bank_stocks[2]].total_amount > 0:
        record(code2=context.portfolio.positions[bank_stocks[2]].total_amount)
    if bank_stocks[3] in context.portfolio.positions and context.portfolio.positions[bank_stocks[3]].total_amount > 0:
        record(code3=context.portfolio.positions[bank_stocks[3]].total_amount)    