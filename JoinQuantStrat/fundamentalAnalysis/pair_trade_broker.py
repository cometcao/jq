import talib
import numpy as np
import pandas as pd
'''
================================================================================
����ز�ǰ
================================================================================
'''
# ��ʼ���������趨Ҫ�����Ĺ�Ʊ����׼�ȵ�
#����ز�ǰҪ��������
def initialize(context):
    set_params()                             # ���ò��Գ���
    set_variables()                          # �����м����
    set_backtest()                           # ���ûز�����
    set_benchmark('601398.XSHG')

#1 
#���ò��Բ���
def set_params():
    g.stocks=['601398.XSHG', '601939.XSHG']  # �������й�Ʊ ���У�����
    g.flag_stat = False                      # Ĭ�ϲ�����ͳ��
    g.a = 0.7356
    g.b = 0
    g.c = 1.0261
    g.d = 0
    g.fzbz = 1                     # ��ֵ��׼
    '''
    ����Ԥ���Ƿ�=�����Ƿ�*a+b
    ����Ԥ��=����*c+d
    '''
    

#2
#�����м����
def set_variables():
    return None
#3
#���ûز�����
def set_backtest():
    set_option('use_real_price',True)        # ����ʵ�۸���
    log.set_level('order','debug')           # ���ñ���ȼ�

    
'''
================================================================================
ÿ�쿪��ǰ
================================================================================
'''
#ÿ�쿪��ǰҪ��������
def before_trading_start(context):
    set_slip_fee(context)                 # ������������������
    # ���ÿ��й�Ʊ��
    g.feasible_stocks = set_feasible_stocks(g.stocks,context)# �õ����й�Ʊ�������̼�, ÿ��ֻ��Ҫȡһ��, ���Է��� before_trading_start ��
    g.last_df = history(1,'1d','close', security_list=g.stocks)
    #log.debug(g.last_df)
    g.fz = 0                              # ÿ������
    

    
# ����ͣ�ƹ�Ʊ
def filter_paused_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list if not current_data[stock].paused]

# ͣ�Ʒ���True��    
def is_paused(stock):
    current_data = get_current_data()
    return current_data[stock].paused
    
# ����ST�������������б�ǩ�Ĺ�Ʊ
def filter_st_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list 
        if not current_data[stock].is_st 
        and 'ST' not in current_data[stock].name 
        and '*' not in current_data[stock].name 
        and '��' not in current_data[stock].name]
        
#4
# ���ÿ��й�Ʊ�أ����˵�����ͣ�ƵĹ�Ʊ
# ���룺initial_stocksΪlist����,��ʾ��ʼ��Ʊ�أ� context����API��
# �����unsuspened_stocksΪlist���ͣ���ʾ����δͣ�ƵĹ�Ʊ�أ��������й�Ʊ��
def set_feasible_stocks(initial_stocks,context):
    # �жϳ�ʼ��Ʊ�صĹ�Ʊ�Ƿ�ͣ�ƣ�����list
    pick_stock = filter_paused_stock(initial_stocks)
    # ȥ��ST
    pick_stock = filter_st_stock(pick_stock)
    return pick_stock

    
#5
# ���ݲ�ͬ��ʱ������û�����������
# ���룺context����API��
# �����none
def set_slip_fee(context):
    # ����������Ϊ0
    set_slippage(FixedSlippage(0)) 
    # ���ݲ�ͬ��ʱ�������������
    set_commission(PerTrade(buy_cost=0.00025, sell_cost=0.00125, min_cost=5)) 

'''
================================================================================
����ǰѡ��
================================================================================
'''
    
# �����Ʊ�أ�����g.df_pick
def stocks_to_buy(context, data):
    list_can_buy = []
    
    
        
'''
================================================================================
ÿ���ӽ���ʱ
================================================================================
'''
# �ز�ʱ��������
def handle_data(context,data):
    # ����   g.stocks[0]
    # ����   g.stocks[1]
    '''
    ���кͽ��е��Ƿ�
    ����Ԥ���Ƿ�=�����Ƿ�*a+b
    ����Ԥ��=����*c+d
    ����ʵ��-����Ԥ��=���0
    ����ʵ��-����Ԥ��=���1
    ���0-���1=��ֵ
    ��ֵ����
    ��ֵ���������Ǿ����빤��0��������1��Ҫ���гֲֵĻ���
    �����������뽨����������
    ����ҵ��������ҵ����ǰ�����һ������һ
    '''
    # �õ���ǰ�ʽ����
    cash = context.portfolio.cash
    price0 = data[g.stocks[0]].close
    price1 = data[g.stocks[1]].close
    last_close0 = g.last_df[g.stocks[0]][0]
    last_close1 = g.last_df[g.stocks[1]][0]
    zf0 = (price0-last_close0)/last_close0*100
    zf1 = (price1-last_close1)/last_close1*100
    yczf0 = zf1*g.a+g.b
    yczf1 = zf0*g.c+g.d
    wc0 = zf0 - yczf0
    wc1 = zf1 - yczf1
    g.fz_before = g.fz
    g.fz = wc0 - wc1
    if g.fz_before > 0 and g.fz < -1*g.fzbz:
        # �������ת
        orders = get_open_orders()
        for _order in orders.values():
            log.info(_order.order_id)
    elif g.fz_before < 0 and g.fz > g.fzbz:
        orders = get_open_orders()
        for _order in orders.values():
            log.info(_order.order_id)
    if g.fz < -1*g.fzbz:                          # ����ֵ��׼��
        #return g.stocks[0]
        if context.portfolio.positions[g.stocks[1]].sellable_amount > 0:
            order_target(g.stocks[1], 0, LimitOrderStyle(price1+0.01))
        order_value(g.stocks[0], cash, LimitOrderStyle(price0-0.01))
        '''
        if g.fz < g.fz_before and g.fz_before < g.fzbz: #���͹� ����׷����
            orders = get_open_orders()
            for _order in orders.values():
                cancel_order(_order)
            if context.portfolio.positions[g.stocks[1]].sellable_amount > 0:
        '''
    elif g.fz > g.fzbz:
        #return g.stocks[1]
        if context.portfolio.positions[g.stocks[0]].sellable_amount > 0:
            order_target(g.stocks[0], 0)
        order_value(g.stocks[1], cash, LimitOrderStyle(price1-0.01))
    
    
'''
================================================================================
ÿ�콻�׺�
================================================================================
'''
#ÿ�������ս�������
def after_trading_end(context):
    #�õ���ǰδ��ɶ���
    orders = get_open_orders()
    for _order in orders.values():
        log.info(_order.order_id)  