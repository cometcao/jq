from pandas import DataFrame
import pandas as pd
import numpy as np
import statsmodels.api as sm
import scipy.stats as scs
import scipy.optimize as sco

def initialize(context):
    g.count = 20
    g.buy_stock = []
    g.cash = 100000
    run_weekly(select_stock,1,'before_open')

def select_stock(context):
    #CMV��FAP,PEG��������ԽС����Խ��,��ֵԽ��Ӧ�����ţ�B/M��P/RԽ������Խ��Ӧ˳����
    effective_factors = {'B/M':True,'PEG':False,'P/R':True,'FAP':False,'CMV':False}
    fdf = get_factors()
    score = {}
    for fac,value in effective_factors.items():
        score[fac] = fdf[fac].rank(ascending = value,method = 'first')
    buy_stock_set = list((DataFrame(score)*np.array([3,4,2,1,5])).T.sum().order(ascending = False).head(40).index)
    # ȥ��ͣ��
    date = context.current_dt.strftime("%Y-%m-%d")
    buylist =unpaused(buy_stock_set)
    # ȥ��ST��*ST
    st=get_extras('is_st', buylist, start_date=date, end_date=date, df=True)
    st=st.loc[date]
    g.buy_stock=list(st[st==False].index)[0:g.count]
    print g.buy_stock

def unpaused(stockspool):
    current_data=get_current_data()
    return [s for s in stockspool if not current_data[s].paused]

def get_factors():
    factors = ['B/M','PEG','P/R','FAP','CMV']
    stock_set = get_index_stocks('000001.XSHG')
    q = query(
        valuation.code,
        balance.total_owner_equities/valuation.market_cap/100000000,
        valuation.pe_ratio,
        income.net_profit/income.operating_revenue,
        balance.fixed_assets/balance.total_assets,
        valuation.circulating_market_cap
        ).filter(
        valuation.code.in_(stock_set)
    )
    fdf = get_fundamentals(q)
    fdf.index = fdf['code']
    fdf.columns = ['code'] + factors
    return fdf.iloc[:,-5:]

# �ֻ�ѡ�ɺ�����¹�Ʊ����ĳֲ�
def reset_position(context):
    if context.portfolio.positions.keys() !=[]:
        for stock in context.portfolio.positions.keys():
            if stock not in g.buy_stock:
                order_target_value(stock, 0)
def conduct_dapan_stoploss(context,security_code,days,bench):
    hist1 = attribute_history(security_code, days + 1, '1d', 'close',df=False)
    security_returns = (hist1['close'][-1]-hist1['close'][0])/hist1['close'][0]
    if security_returns <bench:
        for stock in g.buy_stock:
            order_target_value(stock,0)
            log.info("Sell %s for dapan nday stoploss" %stock)
        return True
    else:
        return False

# ��n������
def setup_position(step,context,data,stock,bench,status):
    value = context.portfolio.portfolio_value
    cash = context.portfolio.cash
    current_price = data[stock].price
    amount = int(value/g.count*2/current_price/step)
    returns = data[stock].returns
    if (status == 'bull' and returns > bench) \
    or (status == 'bear' and returns < bench):
        if context.portfolio.positions[stock].amount < step*amount\
        and cash > 0:
            order_value(stock,value/g.count/step)
            log.info("Buying %s"%stock)
    return None

def statistics(weights):
    weights = np.array(weights)
    port_returns = np.sum(g.returns.mean()*weights)*252
    port_variance = np.sqrt(np.dot(weights.T, np.dot(g.returns.cov()*252,weights)))
    return np.array([port_returns, port_variance, port_returns/port_variance])

#��С������ָ���ĸ�ֵ
def min_sharpe(weights):
    return -statistics(weights)[2]

def min_variance(weights):
    return statistics(weights)[1]

def port_weight(context):
    noa = len(g.buy_stock)
    df = history(400, '1d', 'close', g.buy_stock,df = True)
    g.returns = np.log(df / df.shift(1))

    #Լ�������в���(Ȩ��)���ܺ�Ϊ1���������minimize������Լ���������
    cons = ({'type':'eq', 'fun':lambda x: np.sum(x)-1})

    #���ǻ�������ֵ(Ȩ��)������0��1֮�䡣��Щֵ�Զ��Ԫ����ɵ�һ��Ԫ����ʽ�ṩ����С������
    bnds = tuple((0,1) for x in range(noa))

    #�Ż����������к��Ե�Ψһ��������ʼ�����б�(��Ȩ�صĳ�ʼ�²�)�����Ǽ򵥵�ʹ��ƽ���ֲ���
    optv = sco.minimize(min_variance, noa*[1./noa,],method = 'SLSQP', bounds = bnds, constraints = cons)
    print optv['x'].round(3)
    # opts = sco.minimize(min_sharpe, noa*[1./noa,], method = 'SLSQP', bounds = bnds, constraints = cons)
    # print opts['x'].round(3)
    port_value = context.portfolio.portfolio_value
    for stock in g.buy_stock:
        order_target_value(stock, optv['x'][g.buy_stock.index(stock)]*port_value)

def handle_data(context, data):
    day = context.current_dt.day
    if day > 24:
        for stock in g.buy_stock:
            order_target_value(stock,0)
        return
    reset_position(context) #�ֻ����
    # ָ��ֹ��
    if conduct_dapan_stoploss(context,'000001.XSHG',4,-0.05):
        return
    port_weight(context)
    # for stock in g.buy_stock:
    # #     #���֣�ÿ��0.1%��һ�ɲ�
    #     setup_position(1,context,data,stock,0.001,'bull')