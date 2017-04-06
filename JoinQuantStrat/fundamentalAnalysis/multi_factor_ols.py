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
    #CMV，FAP,PEG三个因子越小收益越大,分值越大，应降序排；B/M，P/R越大收益越大应顺序排
    effective_factors = {'B/M':True,'PEG':False,'P/R':True,'FAP':False,'CMV':False}
    fdf = get_factors()
    score = {}
    for fac,value in effective_factors.items():
        score[fac] = fdf[fac].rank(ascending = value,method = 'first')
    buy_stock_set = list((DataFrame(score)*np.array([3,4,2,1,5])).T.sum().order(ascending = False).head(40).index)
    # 去除停牌
    date = context.current_dt.strftime("%Y-%m-%d")
    buylist =unpaused(buy_stock_set)
    # 去除ST，*ST
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

# 轮换选股后清除新股票池外的持仓
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

# 分n步建仓
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

#最小化夏普指数的负值
def min_sharpe(weights):
    return -statistics(weights)[2]

def min_variance(weights):
    return statistics(weights)[1]

def port_weight(context):
    noa = len(g.buy_stock)
    df = history(400, '1d', 'close', g.buy_stock,df = True)
    g.returns = np.log(df / df.shift(1))

    #约束是所有参数(权重)的总和为1。这可以用minimize函数的约定表达如下
    cons = ({'type':'eq', 'fun':lambda x: np.sum(x)-1})

    #我们还将参数值(权重)限制在0和1之间。这些值以多个元组组成的一个元组形式提供给最小化函数
    bnds = tuple((0,1) for x in range(noa))

    #优化函数调用中忽略的唯一输入是起始参数列表(对权重的初始猜测)。我们简单的使用平均分布。
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
    reset_position(context) #轮换清仓
    # 指数止损
    if conduct_dapan_stoploss(context,'000001.XSHG',4,-0.05):
        return
    port_weight(context)
    # for stock in g.buy_stock:
    # #     #建仓，每涨0.1%加一成仓
    #     setup_position(1,context,data,stock,0.001,'bull')