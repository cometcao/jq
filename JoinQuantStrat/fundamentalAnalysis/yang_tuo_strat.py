# ���ս���ϵͳ (���ڶ�������)
# ����2008��10��1�յ�2016��10��26��

from jqdata import *

'''
================================================================================
����ز�ǰ
================================================================================
'''

#����ز�ǰҪ��������
def initialize(context):
    set_params()      #1 ���ò߲���
    set_variables()   #2 �����м����
    set_backtest()    #3 ���ûز�����

#1 ���ò��Բ���
def set_params():
    # ÿ���޳�������������͵�change_No֧��Ʊ
    g.change_No = 2
    g.N = 60             # ���������ʻز����䣨������
    g.tc = 60            # ���õ�������
    g.num_stocks = 20    # ���óֲֹ�Ʊ��Ŀ
    # �����Ʊ�أ���ҵ��ָ���ɷֹ�
    g.index='000300.XSHG'
    
#2 �����м����
def set_variables():
    g.t = 0                    # ��¼�ز����е�����
    g.if_trade = False         # �����Ƿ���
    g.feasible_stocks = []     # ��ǰ�ɽ��׹�Ʊ��

#3 ���ûز�����
def set_backtest():
    set_benchmark('000300.XSHG')              # ����Ϊ��׼
    set_option('use_real_price', True)        # ����ʵ�۸���
    log.set_level('order', 'error')           # ���ñ���ȼ�

'''
================================================================================
ÿ�쿪��ǰ
================================================================================
'''
#ÿ�쿪��ǰҪ��������
def before_trading_start(context):
    if g.t%g.tc==0:
        #ÿg.tc�죬����һ����
        g.if_trade=True 
        #4 ���ÿ��й�Ʊ�أ���õ�ǰ���̵Ĺ�Ʊ�ز��޳���ǰ���߼��������ڼ�ͣ�ƵĹ�Ʊ
        g.feasible_stocks = set_feasible_stocks(get_index_stocks(g.index),g.N,context)
        #5 ������������������
        set_slip_fee(context) 
    g.t+=1


#4    
# ���ÿ��й�Ʊ��
# ���˵�����ͣ�ƵĹ�Ʊ,��ɸѡ��ǰdays��δͣ�ƹ�Ʊ
# ���룺stock_listΪlist����,��������daysΪint���ͣ�context����API��
# �����list=g.feasible_stocks
def set_feasible_stocks(stock_list,days,context):
    # �õ��Ƿ�ͣ����Ϣ��dataframe��ͣ�Ƶ�1��δͣ�Ƶ�0
    suspened_info_df = get_price(list(stock_list), 
                       start_date=context.current_dt, 
                       end_date=context.current_dt, 
                       frequency='daily', 
                       fields='paused'
    )['paused'].T
    # ����ͣ�ƹ�Ʊ ����dataframe
    unsuspened_index = suspened_info_df.iloc[:,0]<1
    # �õ�����δͣ�ƹ�Ʊ�Ĵ���list:
    unsuspened_stocks = suspened_info_df[unsuspened_index].index
    # ��һ����ɸѡ��ǰdays��δ��ͣ�ƵĹ�Ʊlist:
    feasible_stocks = []
    current_data = get_current_data()
    for stock in unsuspened_stocks:
        if sum(attribute_history(stock, days, unit = '1d',fields = ('paused'), skip_paused = False))[0] == 0:
            feasible_stocks.append(stock)
    return feasible_stocks
    
#5 ���ݲ�ͬ��ʱ������û�����������
def set_slip_fee(context):
    # ����������Ϊ0
    set_slippage(FixedSlippage(0)) 
    # ���ݲ�ͬ��ʱ�������������
    dt=context.current_dt
    
    if dt>datetime.datetime(2013,1, 1):
        set_commission(PerTrade(buy_cost=0.0003, sell_cost=0.0013, min_cost=5)) 
        
    elif dt>datetime.datetime(2011,1, 1):
        set_commission(PerTrade(buy_cost=0.001, sell_cost=0.002, min_cost=5))
            
    elif dt>datetime.datetime(2009,1, 1):
        set_commission(PerTrade(buy_cost=0.002, sell_cost=0.003, min_cost=5))
                
    else:
        set_commission(PerTrade(buy_cost=0.003, sell_cost=0.004, min_cost=5))

'''
================================================================================
ÿ�콻��ʱ
================================================================================
'''
def handle_data(context,data):
    # ���Ϊ������
    if g.if_trade == True: 
        #6 ������������źţ�����context�������Ʊ�б�list
        (sell,buy)=get_signals(context) 
        #7 ���µ�����λ������context,ʹ���źŽ��sell��buy
        rebalance(context, buy, sell)
    g.if_trade = False

#6
# �������Ե������źţ��õ�Ӧ�������Ĺ�Ʊ�б�
# ���룺context����API��
# �����Ӧ�����Ĺ�Ʊ�б�list����
def get_signals(context):
    # ����������Ϊ�����ʼ������һ�� ����datetime.date����
    enddate = context.previous_date
    # ������������ǰ��g.N(���Ǹ��������õ������ʼ������ڵ�һ�� ����datetime.date����
    startdate = shift_trading_day(enddate,-g.N)
    # �õ��ز������ʵĹ�Ʊ�б��������С����е����أ����б�������ʵ�ʿɽ��׹�Ʊ��һ�����죩����list
    stocks = g.feasible_stocks
    # �������ʽ������� ����list
    sorted_list = stock_ret(stocks,startdate,enddate,asc = True)
    # ��ȡ��ߵ�g.num_stocks�����ܽ��й���Ĺ�Ʊ
    should_buy = sorted_list[0:g.change_No]
    # ��ǰ�ֲֹ�Ʊ
    holding = list(context.portfolio.positions.keys())  
    # �����ǰ�ղ�
    if len(list(context.portfolio.positions.keys()))==0:
        # ������������g.num_stocks֧��Ʊ����
        should_buy = sorted_list[0:g.num_stocks]
        # ����Ϊ��
        should_sell = []
    else:
        # ����������Ʊlist����ǰΪ��
        should_sell = stock_ret(holding, startdate, enddate, asc = True)[0:g.change_No]
    # ���һ֧�ֲֹ�Ʊ���治�ø���
    for both in should_sell[:]:
        # ͬʱ�����п��й�Ʊ�����������͸���
        if both in should_buy[:]:
            # �Ȳ�����
            list(should_buy).remove(both)
            # Ҳ������
            list(should_sell).remove(both)
    # ��������list��Ԫ��
    return should_sell,should_buy

#7
# �������Ե������źţ��õ�Ӧ����Ĺ�Ʊ�б�
# ���������źŽ���������������
# ���룺context����API��
def rebalance(context, buy, sell):
    # ����������list�еĹ�Ʊ
    for stock_to_sell in list(sell)[:]: 
        order_target_value(stock_to_sell, 0)
    # �ѵ�ǰ�ֲֹ�Ʊ����Ҫ�����Ʊ�����µ�buy���б���������ͷ������Ҫ���й�Ʊ
    for stock in buy[:]:
        if stock in list(context.portfolio.positions.keys()):
            buy.append(stock)
    # ����ÿ����Ʊ����ǰ����ֵ/g.num_stocks���
    for stock_to_buy in buy[:]:
        # ��order��������Ϊ˳�������Ϊ��ֹ���е��ֹ�Ʊ���ں��е��ֹ�Ʊռ��������һ�ε�����λ���������������Խ���������
        order_target_value(stock_to_buy, context.portfolio.cash/g.num_stocks)
        order_target_value(stock_to_buy, context.portfolio.cash/g.num_stocks)
            
#8
# ĳһ�յ�ǰshift������������ 
# ���룺dateΪdatetime.date����(��һ��date��������datetime)��shiftΪint����
# �����datetime.date����(��һ��date��������datetime)
def shift_trading_day(date,shift):
    # ��ȡ���еĽ����գ�����һ���������н����յ� list,Ԫ��ֵΪ datetime.date ����.
    tradingday = get_all_trade_days()
    # �õ�date֮��shift����һ�����б��е��б�� ����һ����
    shiftday_index = list(tradingday).index(date)+shift
    # �����кŷ��ظ������� Ϊdatetime.date����
    return tradingday[shiftday_index]

#9  
# �����ڼ������ʣ���ǰ��Ȩ���̼ۼ��㣩����Ʊ����
# ���룺stock_listΪlist���ͣ�startdate enddateΪdatetime.date����ascΪ��������
# �����list����
def stock_ret(stock_list,startdate,enddate,asc = False):
    # �õ��ز������ڹ�Ʊ���̼� ����dataframe
    log.info(startdate)
    df_close = get_price(list(stock_list),start_date = startdate, end_date = enddate, fields = 'close')['close'].T
    # ɾȥ��ֵ ����dataframe
    df_close = df_close.dropna(axis = 0)
    # ����ز����������� ����dataframe
    df_close['ret']=(df_close[enddate]-df_close[startdate])/df_close[startdate]
    #�������ʽ������У���ȡ��Ʊ���룬����list
    stocks = list(df_close.sort('ret', ascending = asc).index)
    # ���ع�Ʊ����list
    return stocks

'''
================================================================================
ÿ�����̺�
================================================================================
'''
# ÿ�����̺�Ҫ�������飨�������в���Ҫ��
def after_trading_end(context):
    return