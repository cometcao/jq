# -*- encoding: utf8 -*-
'''
Created on 31 Oct 2016

@author: MetalInvest
'''
from kuanke.user_space_api import *
from jqdata import *
from scipy.signal import argrelextrema
from blacklist import *

def getMcapInfo(stocks, context):
    # get yesterdays market cap
    #queryDate = context.current_dt.date()-timedelta(days=1)
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

def getPeInfo(stocks, context):
    # get yesterdays market cap
    #queryDate = context.current_dt.date()-timedelta(days=1)
    queryDf = get_fundamentals(query(
        valuation.pe_ratio, valuation.code
    ).filter(
        valuation.code.in_(stocks),
        indicator.eps > 0
    ).order_by(
        valuation.pe_ratio.asc()
    )
    )

    stockinfo = []
    for j in xrange(0, len(queryDf['pe_ratio'])):
        stockinfo.append( (queryDf['pe_ratio'][j], queryDf['code'][j]) )
    return stockinfo

def findPeriod(stock):
    if stock not in g.period:
        df = attribute_history(stock, g.number_of_days_wave_backwards, '1d', ('high', 'low'), skip_paused=True)
        topIndex = argrelextrema(df['high'].values, np.greater_equal,order=1)[0]
        bottomIndex = argrelextrema(df['low'].values, np.less_equal,order=1)[0]
        delta = None
        if len(topIndex) < 2 or len(bottomIndex) < 2:
            return 20
        if topIndex[-1] > bottomIndex[-1]:
            delta = df['low'].index[bottomIndex[-1]] - df['high'].index[topIndex[-2]]
        else:
            delta = df['high'].index[bottomIndex[-1]] - df['low'].index[topIndex[-2]]
        g.period[stock] = delta.days
    return g.period[stock]


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

def inOpenOrder(security):
    orders = get_open_orders()
    for _order in orders.values():
        if _order.security == security:
            return True
    return False

##############

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
        and '��' not in current_data[stock].name]

def filter_blacklist_stock(context, stock_list):
    blacklist = get_blacklist()
    return [stock for stock in stock_list if stock not in blacklist]

# ������ͣ�Ĺ�Ʊ
def filter_limitup_stock(context, stock_list):
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    
    # �Ѵ����ڳֲֵĹ�Ʊ��ʹ��ͣҲ�����ˣ�����˹�Ʊ�ٴο��򣬵��򱻹��˶�����ѡ���Ĺ�Ʊ
    return [stock for stock in stock_list if stock in context.portfolio.positions.keys() 
        or last_prices[stock][-1] < current_data[stock].high_limit]

# ���˵�ͣ�Ĺ�Ʊ
def filter_limitdown_stock(context, stock_list):
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    return [stock for stock in stock_list if stock in context.portfolio.positions.keys() 
        or last_prices[stock][-1] > current_data[stock].low_limit]

# ������ɻس�ֹ����ֵ
# �������ڳֲ�n�����ܳ��ܵ�������
# �㷨��(����250��������n�յ��� + ����250����ƽ����n�յ���)/2
# ������ֵ
def get_stop_loss_threshold(security, n = 3):
    pct_change = get_pct_change(security, 250, n)
    #log.debug("pct of security [%s]: %s", pct)
    maxd = pct_change.min()
    #maxd = pct[pct<0].min()
    avgd = pct_change.mean()
    #avgd = pct[pct<0].mean()
    # maxd��avgd����Ϊ������ʾ���ʱ����һֱ�������������¹�
    bstd = (maxd + avgd) / 2

    # ���ݲ���ʱ�������bstdΪnan
    if not np.isnan(bstd):
        if bstd != 0:
            return abs(bstd)
        else:
            # bstd = 0���� maxd <= 0
            if maxd < 0:
                # ��ʱȡ������
                return abs(maxd)
    return 0.099 # Ĭ�����ûز�ֹ����ֵ������Ϊ-9.9%����ֵ��ò�ƻس�����
    
# �������ֹӯ��ֵ
# �㷨������250��������n���Ƿ�
# ������ֵ
def get_stop_profit_threshold(security, n = 3):
    pct_change = get_pct_change(security, 250, n)
    maxr = pct_change.max()
    
    # ���ݲ���ʱ�������maxrΪnan
    # ������maxr����Ϊ��
    if (not np.isnan(maxr)) and maxr != 0:
        return abs(maxr)
    return 0.20 # Ĭ������ֹӯ��ֵ����Ƿ�Ϊ20%
    
# ��ȡ����ǰn���m������ֵ����
# ���ӻ�����⵱�ն�λ�ȡ����
def get_pct_change(security, n, m):
    pct_change = None
    if security in g.pct_change.keys():
        pct_change = g.pct_change[security]
    else:
        h = attribute_history(security, n, unit='1d', fields=('close'), skip_paused=True, df=True)
        pct_change = h['close'].pct_change(m) # 3�յİٷֱȱ�ȣ���3���ǵ�����
        g.pct_change[security] = pct_change
    return pct_change

######################################################## copied filter ###############################################################



# ���ݲ�ͬ��ʱ������û�����������
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
        
        
def set_feasible_stocks(stock_list,days,context):
    # �õ��Ƿ�ͣ����Ϣ��dataframe��ͣ�Ƶ�1��δͣ�Ƶ�0
    suspened_info_df = get_price(list(stock_list), start_date=context.current_dt, end_date=context.current_dt, frequency='daily', fields='paused')['paused'].T
    feasible_stocks=[]
    unsuspened_stocks = stock_list
    if not suspened_info_df.empty:
        # ����ͣ�ƹ�Ʊ ����dataframe
        unsuspened_index = suspened_info_df.iloc[:,0]<1
        # �õ�����δͣ�ƹ�Ʊ�Ĵ���list:
        unsuspened_stocks = suspened_info_df[unsuspened_index].index
        # ��һ����ɸѡ��ǰdays��δ��ͣ�ƵĹ�Ʊlist:
    current_data=get_current_data()
    for stock in unsuspened_stocks:
        if sum(attribute_history(stock, days, unit='1d',fields=('paused'),skip_paused=False))[0]==0:
            feasible_stocks.append(stock)
    return feasible_stocks

# �Զ����µ�
# ����Joinquant�ĵ�����ǰ����������������ִ�У�������������order_target_value�����ؼ���ʾ�������
# �����ɹ����ر�����������һ����ɽ��������򷵻�None
def order_target_value_new(security, value):
    if value == 0:
        log.info("short %s - %s" % (security, get_security_info(security).display_name))
    else:
        log.info("long %s - %s with amount RMB %f" % (security, get_security_info(security).display_name, value))
        
    # �����Ʊͣ�ƣ�����������ʧ�ܣ�order_target_value ����None
    # �����Ʊ�ǵ�ͣ������������ɹ���order_target_value ����Order�����Ǳ�����ȡ��
    # ���ɲ����ı������ۿ�״̬���ѳ�����ʱ�ɽ���>0����ͨ���ɽ����ж��Ƿ��гɽ�
    return order_target_value(security, value)