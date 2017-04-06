# �����Ӳ���-APTģ�ͣ�Multi-factor�� 
# 2006-01-01 �� 2016-05-29, ��200000, ÿ��
import math
import datetime
import numpy as np
import pandas as pd
from jqdata import *
# �����Ԫ���Թ滮��Ҫ�Ĺ��߰�
import statsmodels.api as sm
from statsmodels import regression

'''
================================================================================
����ز�ǰ
================================================================================
'''
#����ز�ǰҪ��������
def initialize(context):
    set_params()      # 1���ò߲���
    set_variables()   # 2�����м����
    set_backtest()    # 3���ûز�����
    
#1
#���ò��Բ���
def set_params():
    g.tc = 63         # ���õ�������
    g.lag= 4          # �ù�ȥ�����ڵĲƱ��ع�
    g.N = 20          # ��Ҫǰ�����������
    g.num_stocks= 20  # Ĭ��ֵѡ������õ�20����Ʊ
    # �Լ�ѡȡ��һЩ����
    g.factors=['eps','adjusted_profit','inc_return','operation_profit_to_total_revenue',
               'net_profit_margin','gross_profit_margin','ga_expense_to_total_revenue',
               'goods_sale_and_service_to_revenue','inc_total_revenue_year_on_year']

#2
#�����м����
def set_variables():
    g.t = 0                # ��¼�ز����е�����
    g.if_trade = False     # �����Ƿ���
    a=get_all_trade_days() 
    g.ATD=['']*len(a)      # ��¼����ű��Ѿ����е�����
    for i in range(0,len(a)):
        g.ATD[i]=a[i].isoformat()

#3
#���ûز�����
def set_backtest():
    set_option('use_real_price',True) # ����ʵ�۸���
    log.set_level('order','error')    # ���ñ���ȼ�




'''
================================================================================
ÿ�쿪��ǰ
================================================================================
'''
#ÿ�쿪��ǰҪ��������
def before_trading_start(context):
    if g.t%g.tc==0:
        #ÿg.tc�죬����һ��
        g.if_trade=True 
        # ������������������
        set_slip_fee(context) 
        # ���ÿ��й�Ʊ�أ���õ�ǰ���̵Ļ���300��Ʊ�ز��޳���ǰ���߼��������ڼ�ͣ�ƵĹ�Ʊ
        g.feasible_stocks = set_feasible_stocks(get_index_stocks('000300.XSHG'),g.N,context)
    g.t+=1
    
#4 
# ���ÿ��й�Ʊ�أ�
# ���˵�����ͣ�ƵĹ�Ʊ,��ɸѡ��ǰdays��δͣ�ƹ�Ʊ
# ���룺stock_listΪlist����,��������daysΪint���ͣ�context����API��
# �����list
def set_feasible_stocks(stock_list,days,context):
    # �õ��Ƿ�ͣ����Ϣ��dataframe��ͣ�Ƶ�1��δͣ�Ƶ�0
    suspened_info_df = get_price(list(stock_list), start_date=context.current_dt, end_date=context.current_dt, frequency='daily', fields='paused')['paused'].T
    # ����ͣ�ƹ�Ʊ ����dataframe
    unsuspened_index = suspened_info_df.iloc[:,0]<1
    # �õ�����δͣ�ƹ�Ʊ�Ĵ���list:
    unsuspened_stocks = suspened_info_df[unsuspened_index].index
    # ��һ����ɸѡ��ǰdays��δ��ͣ�ƵĹ�Ʊlist:
    feasible_stocks=[]
    current_data=get_current_data()
    for stock in unsuspened_stocks:
        if sum(attribute_history(stock, days, unit='1d',fields=('paused'),skip_paused=False))[0]==0:
            feasible_stocks.append(stock)
    return feasible_stocks

#5
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




'''
================================================================================
ÿ�콻��ʱ
================================================================================
'''
def handle_data(context, data):
    if g.if_trade==True:
        
        # ���յ�ǰ���ʲ��������䵽ÿ����Ʊ������ʽ�
        g.everyStock=context.portfolio.portfolio_value/g.num_stocks
        # �������ԣ��õ�������Ĺ�Ʊ�б�
        toBuy = to_buy(context)
        #ִ����������
        order_sell(context,toBuy)
        #ִ���������
        order_buy(toBuy)
        
    g.if_trade = False

#6
# �������ԣ��õ�������Ĺ�Ʊ�б�
# ���룺context�����ۿ�API�ĵ���
# �����������Ĺ�Ʊ�б�-list����
def to_buy(context):
    # ��ý�������ڵ��ַ���
    todayStr=str(context.current_dt)[0:10]
    # ��õ�ǰ������
    current_factors=getOriginalFactors(g.factors,todayStr)
        
    factors_table=getDS(g.feasible_stocks,todayStr,g.lag)

    weights=linreg(factors_table[g.factors],factors_table[['return']])
        
    betas=weights[1:]
    # ������һ�ڵĻع����������һ����Ȼ���ã��Թ�Ʊ��һ�ڵ�������й���
    points=current_factors.dot(betas)+weights[0]
    points.sort(ascending=False)

    NoB=0
    for i in range(0,g.num_stocks):
        if points[i]>0:
            NoB+=1
            
    to_buy=array(points.index[0:NoB])
    return to_buy
    
#7
# ִ����������
# ���룺context,toBuy-list����
# �����none
def order_sell(context,toBuy):
    #������гֲֹ�Ʊ���ڹ�Ʊ�أ����
    list_position=context.portfolio.positions.keys()
    #�гֲ֣����ǲ���Ҫ���������
    for i in range(0,len(g.feasible_stocks)):
        if indexOf(g.feasible_stocks[i],toBuy)==-1 and indexOf(g.feasible_stocks[i],list_position)>-1:
            order_target_value(g.feasible_stocks[i], 0)
    return

#8
# ִ���������
# ���룺context,toBuy-list����
# �����none
def order_buy(toBuy):
    # �����Ʊ�ڴ��ֲ��б���������ķݶ�ֲ�
    for i in range(0,len(g.feasible_stocks)):
        if indexOf(g.feasible_stocks[i],toBuy)>-1:
            order_target_value(g.feasible_stocks[i], g.everyStock)

#9
# ����һ��Ԫ�������������λ�ã���������ڣ��򷵻�-1
# ���룺aΪlist����
# �����int����
def indexOf(e,a):
    for i in range(0,len(a)):
        if e<=a[i]:
            return i
    return -1

#10
# ȡ���ݵĺ���
# ���룺����-list���ͣ�����d-str���ͣ�XXXX-XX-XX��
# ���df-dataframe����
def getOriginalFactors(factors,d):
    # ���ڲ�ѯ���������ݵĲ�ѯ���
    q = query(valuation,balance,cash_flow,income,indicator).filter(valuation.code.in_(g.feasible_stocks))
    # ��ù�Ʊ�Ļ��������ݣ�
    df = get_fundamentals(q,d)
    code=array(df['code'])
    df = df[factors]
    df.index=code
    df = df.dropna()
    return df

#11
# �����������Э���������Իع��
# ���룺factors�����й�Ʊ����һ������ֵ-list��returns�ǹ�Ʊ��һ�ڵ�����
# �����class��
def linreg(factors,returns):
    # ����һ�г����У���ʾ�г���״̬�Լ���������û�п��ǵ�������
    X=sm.add_constant(factors)
    # ���ж�Ԫ���Իع�
    results = regression.linear_model.OLS(returns, X).fit()
    # ���ض�Ԫ���Իع�Ĳ���ֵ
    return results.params



#12
# �����Ч�Ļع���������ֵ�������ʡ�ȡǰlags�����ȵ������Լ���֮��һ��ʱ���������
# ���룺stocksΪlist���ͣ�dateStrΪstr���ͣ�lagsΪint
# �����DataFrame
def getDS(stocks,dateStr,lags):
    #����һ���յ�dataframe,�г���day���� pubDate
    cols=g.factors+['day','pubDate','return']
    code_list=[val+'_lag'+str(i) for val in stocks for i in range(lags)]
    len_rows=len(code_list)
    len_cols=len(cols)
    table=np.zeros((len_rows,len_cols)) #����0����
    table[:,:]=nan
    table_factors=pd.DataFrame(table,columns=cols,index=code_list)
    
    cols2=g.factors+['day','pubDate']
    for i in stocks:
        # ���ǰһ�������յ����ڣ���Ϊ��ǰ���������ǲ�֪����ǰ���̼۵ģ�
        D=getDay(dateStr,-1)
        # һ��ѭ������ÿһ�����񼾶Ƚ��л�ȡ����
        for j in range(0,lags):
            # ��ѯ�������ӵ����
            q = query(indicator,valuation).filter(indicator.code.in_([i]))
            f_temp=get_fundamentals(q,D)
            #���ж��Ƿ����У�������У��Ž���װ��
            row_name=i+'_lag'+str(j)
            if len(f_temp)>0:
                f_temp=f_temp[cols2]
                f_temp.index=[row_name]
                table_factors.ix[[row_name],cols2]=f_temp
                #�õ����ڲƱ�����¶������ǰ��һ������:
                LD=getDay(table_factors['pubDate'][row_name],-1)
                p1=getHistory(i,LD)
                p2=getHistory(i,D)
                # ����������ڸ��˶��ٸ�������
                getDayDifferent = indexOf(D,g.ATD)-indexOf(LD,g.ATD)
                r=math.log(p2/p1)/getDayDifferent
                table_factors.ix[[row_name],['return']]=r
            else:
                LD=D
            D=LD
    table_factors=table_factors.dropna() # �����к���nan�����(ÿ�д���һֻ��Ʊ)ɾ��
    return table_factors

#13
# �����ʷ��ĳ����Ʊĳһ������̼�
# ���룺stockΪstr���ͣ�dateStrΪstr����
# �����DataFrame
def getHistory(stock,dateStr):
    # ��ùɼ�����
    df = get_price(stock, start_date=dateStr, end_date=dateStr, frequency='daily', fields=['close'])
    # ������ݴ��ڣ���ô���ص������̼�
    if len(df)>0:
        return df['close'][0]
    # ������ݲ����ڣ�����NaN
    else:
        return float("nan")

# 14
# ���ڼ���֮���ĳ������֮ǰ����֮��dt�������յ�����
# ���룺precent-str���ͣ�dt-int����
# ���������-str
def getDay(precent,dt):
    t_temp=indexOf(precent,g.ATD)
    if t_temp+dt>=0:
        return g.ATD[t_temp+dt]
    else:
        t= datetime.datetime.strptime(g.ATD[0],'%Y-%m-%d')+datetime.timedelta(days = dt)
        t_str=datetime.datetime.strftime(t,'%Y-%m-%d')
        return t_str




'''
================================================================================
ÿ�����̺�
================================================================================
'''
# ÿ�����̺�Ҫ�������飨�������в���Ҫ��
def after_trading_end(context):
    return