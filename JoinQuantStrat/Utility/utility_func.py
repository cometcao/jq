# -*- encoding: utf8 -*-
'''
Created on 31 Oct 2016

@author: MetalInvest
'''
from kuanke.user_space_api import *
from jqdata import *
from scipy.signal import argrelextrema
from blacklist import *
import talib
from functools import partial

# global constants
macd_func = partial(talib.MACD, fastperiod=12,slowperiod=26,signalperiod=9)
#macd_func_ext = partial(talib.MACDEXT, fastperiod=12,slowperiod=26,signalperiod=9)

def MACD(prices):
    raw, signal, macd = macd_func(prices)
    # macd = macd * 2
    return raw, signal, macd

def getAllStocks(context):
#     pddf = get_all_securities(date = context.current_dt.date())
#     return pddf.index.values
    return get_index_stocks("000001.XSHG") + get_index_stocks("399106.XSHE")
    
# #庄股值计算    
# def cow_stock_value(stock,stock_time) :
#     q = query(valuation).filter(valuation.code == stock)
#     try:
#         pb = get_fundamentals(q, stock_time)['pb_ratio'][0]
#         cap = get_fundamentals(q, stock_time)['circulating_market_cap'][0]
#     except:
#         return 0
#     if cap>100: return 0
#     num_fall=fall_money_day_3line(stock,120,20,60,160,stock_time)
#     num_cross=money_5_cross_60(stock,120,5,160,stock_time)
#     
#     return (num_fall*num_cross)/(pb*(cap**0.5))
# 
# #计算脉冲（1.0版本）                 
# def  money_5_cross_60(stock , n,n1=5,n2=60,stock_time=datetime.datetime.now()):
#     if  not (n2 >n1 ) : 
#         log.info("fall_money_day 参数错误")
#         return 0 
#     #stock_m=attribute_history(stock, n+n2+1, '1d', ['money'], True)
#     stock_m=get_price(stock,count=n+n2+1,end_date=stock_time,frequency='daily', \
#                       fields=['money'], skip_paused=True)
#     #print(len(stock_m)) 
#     i=0
#     count=0
#     while i<n:
#         money_MA60=stock_m['money'][i+1:n2+i].mean()
#         money_MA60_before=stock_m['money'][i:n2-1+i].mean()
#         money_MA5=stock_m['money'][i+1+n2-n1:n2+i].mean()
#         money_MA5_before=stock_m['money'][i+n2-n1:n2-1+i].mean()
#         if (money_MA60_before-money_MA5_before)*(money_MA60-money_MA5)<0: 
#             count=count+1
#         i=i+1    
#     return count
# 
#     
# #3条移动平均线计算缩量 
# def fall_money_day_3line(stock,n,n1=20,n2=60,n3=120,stock_time=datetime.datetime.now()):
#     if  not ( n3>n2 and n2 >n1 ) : 
#         log.info("fall_money_day 参数错误")
#         return 0 
#     #stock_m=attribute_history(stock, n+n3, '1d', ['money'], True)
#     stock_m=get_price(stock,count=n+n3,end_date=stock_time,frequency='daily', \
#                       fields=['money'], skip_paused=True)
#     #print(len(stock_m)) 
#     i=0
#     count=0
#     while i<n:
#         money_MA200=stock_m['money'][i:n3-1+i].mean()
#         money_MA60=stock_m['money'][i+n3-n2:n3-1+i].mean()
#         money_MA20=stock_m['money'][i+n3-n1:n3-1+i].mean()
#         if money_MA20<=money_MA60 and money_MA60<=money_MA200:
#             count=count+1
#         i=i+1
#     return count

def getCirMcapThrethold(threthold = 0.95):
    queryDf = get_fundamentals(query(
        valuation.circulating_market_cap, valuation.code
        ).order_by(
            valuation.circulating_market_cap.asc()
        ))
    total_num = queryDf.shape[0]
    threthold_index = int(total_num * threthold)
    return queryDf['circulating_market_cap'][threthold_index]

def getPSThrethold(threthold = 0.5):
    return getFundamentalThrethold('valuation.ps_ratio')

def getFundamentalThrethold(factor, threthold = 0.95):
    eval_factor = eval(factor)
    queryDf = get_fundamentals(query(
        eval_factor, valuation.code
        ).order_by(
            eval_factor.asc()
        ))
    total_num = queryDf.shape[0]
    threthold_index = int(total_num * threthold)
    return queryDf[factor.split('.')[1]][threthold_index]    

def getCirMcapInfo(context, num_limit=100, cir_cap_limit = 100, max_pe=200):
    queryDf = get_fundamentals(query(
        valuation.circulating_market_cap, valuation.code
    ).filter(
        indicator.eps > 0,
        valuation.pe_ratio < max_pe,
        valuation.circulating_market_cap <= cir_cap_limit
    ).order_by(
        valuation.market_cap.asc()
    ).limit(num_limit)
    )

    stockinfo = zip(queryDf['circulating_market_cap'].values, queryDf['code'].values)
    return stockinfo

def getFullMcapInfo(context, num_limit=100, mcap_limit=10000, max_pe=250):
    queryDf = get_fundamentals(query(
        valuation.market_cap, valuation.code
    ).filter(
        indicator.eps > 0,
        valuation.pe_ratio < max_pe,
        valuation.market_cap <= mcap_limit
    ).order_by(
        valuation.market_cap.asc()
    ).limit(num_limit)
    )

    stockinfo = zip(queryDf['market_cap'].values, queryDf['code'].values)
    return stockinfo

def getMcapInfo(stocks, context, mcap_limit = 10000, max_pe=200):
    # get yesterdays market cap
    #queryDate = context.current_dt.date()-timedelta(days=1)
    queryDf = get_fundamentals(query(
        valuation.market_cap, valuation.code
    ).filter(
        valuation.pe_ratio < max_pe,
        valuation.market_cap < mcap_limit,
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

def findPeriod_v2(stock):
    if stock not in g.period:
        df = attribute_history(stock, 233, g.buy_period_check, ('close'), skip_paused=True)
        df.loc[:,'macd_raw'], _, df.loc[:,'macd'] = MACD(df['close'].values)
        df = df.dropna()
        if df.shape[0] > 2:
            try:
                # gold
                mask = df['macd'] > 0
                mask = mask[mask==True][mask.shift(1) == False]
                # death
                mask2 = df['macd'] < 0
                mask2 = mask2[mask2==True][mask2.shift(1)==False]       
                     
                gkey1 = mask.keys()[-1]
                gkey2 = mask.keys()[-2]
                dkey1 = mask2.keys()[-1]
                dkey2 = mask2.keys()[-2]

                if gkey1 > dkey1:
                    dk = df.index.get_loc(dkey1)
                    gk = df.index.get_loc(gkey2)
                    g.period[stock] = dk - gk
                else:
                    gk = df.index.get_loc(gkey1)
                    dk = df.index.get_loc(dkey2)
                    g.period[stock] = gk - dk
            except IndexError:
                g.period[stock] = 20
        else:
            g.period[stock] = 20    
    return g.period[stock]

def findPeriod(stock):
    if stock not in g.period: # g.period resets every day
        df = attribute_history(stock, g.number_of_days_wave_backwards, '1d', ('high', 'low'), skip_paused=True)
        topIndex = argrelextrema(df['high'].values, np.greater_equal,order=2)[0]
        bottomIndex = argrelextrema(df['low'].values, np.less_equal,order=2)[0]
        delta = None
        if len(topIndex) < 2 or len(bottomIndex) < 2:
            return 20
        if topIndex[-1] > bottomIndex[-1]:
            delta = df['low'].index[bottomIndex[-1]] - df['high'].index[topIndex[-2]]
        else:
            delta = df['high'].index[topIndex[-1]] - df['low'].index[bottomIndex[-2]]
        if delta.days == 0:
            g.period[stock] = 20
        else:
            g.period[stock] = abs(delta.days)
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

def getlatest_df(stock, count, context, fields, df_flag = True):
    df = attribute_history(stock, count, '1d', fields, df=df_flag)
    latest_stock_data = attribute_history(stock, 1, '230m', fields, skip_paused=True, df=df_flag)
    if df_flag:
        latest_stock_data = latest_stock_data.reset_index(drop=False)
        latest_stock_data.ix[0, 'index'] = pd.DatetimeIndex([context.current_dt.date()])[0]
        latest_stock_data = latest_stock_data.set_index('index')
        df = df.reset_index().drop_duplicates(subset='index').set_index('index')
        df = df.append(latest_stock_data, verify_integrity=True) # True
    else:
        final_fields = []
        if isinstance(fields, basestring):
            final_fields.append(fields)
        else:
            final_fields = list(fields)
        [np.append(df[field], latest_stock_data[field][-1]) for field in final_fields]
    return df


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

def isFirstTradingDayOfWeek(context):
    trading_days = get_trade_days(end_date=context.current_dt.date(), count=2)
    today = trading_days[-1]
    last_trading_day = trading_days[-2]
    return (today.isocalendar()[1] != last_trading_day.isocalendar()[1])