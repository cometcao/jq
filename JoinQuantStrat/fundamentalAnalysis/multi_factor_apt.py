# 多因子策略-APT模型（Multi-factor） 
# 2006-01-01 到 2016-05-29, ￥200000, 每天
import math
import datetime
import numpy as np
import pandas as pd
from jqdata import *
# 导入多元线性规划需要的工具包
import statsmodels.api as sm
from statsmodels import regression

'''
================================================================================
总体回测前
================================================================================
'''
#总体回测前要做的事情
def initialize(context):
    set_params()      # 1设置策参数
    set_variables()   # 2设置中间变量
    set_backtest()    # 3设置回测条件
    
#1
#设置策略参数
def set_params():
    g.tc = 63         # 设置调仓天数
    g.lag= 4          # 用过去多少期的财报回归
    g.N = 20          # 需要前多少天的数据
    g.num_stocks= 20  # 默认值选表现最好的20个股票
    # 自己选取的一些因子
    g.factors=['eps','adjusted_profit','inc_return','operation_profit_to_total_revenue',
               'net_profit_margin','gross_profit_margin','ga_expense_to_total_revenue',
               'goods_sale_and_service_to_revenue','inc_total_revenue_year_on_year']

#2
#设置中间变量
def set_variables():
    g.t = 0                # 记录回测运行的天数
    g.if_trade = False     # 当天是否交易
    a=get_all_trade_days() 
    g.ATD=['']*len(a)      # 记录这个脚本已经运行的天数
    for i in range(0,len(a)):
        g.ATD[i]=a[i].isoformat()

#3
#设置回测条件
def set_backtest():
    set_option('use_real_price',True) # 用真实价格交易
    log.set_level('order','error')    # 设置报错等级




'''
================================================================================
每天开盘前
================================================================================
'''
#每天开盘前要做的事情
def before_trading_start(context):
    if g.t%g.tc==0:
        #每g.tc天，交易一次
        g.if_trade=True 
        # 设置手续费与手续费
        set_slip_fee(context) 
        # 设置可行股票池：获得当前开盘的沪深300股票池并剔除当前或者计算样本期间停牌的股票
        g.feasible_stocks = set_feasible_stocks(get_index_stocks('000300.XSHG'),g.N,context)
    g.t+=1
    
#4 
# 设置可行股票池：
# 过滤掉当日停牌的股票,且筛选出前days天未停牌股票
# 输入：stock_list为list类型,样本天数days为int类型，context（见API）
# 输出：list
def set_feasible_stocks(stock_list,days,context):
    # 得到是否停牌信息的dataframe，停牌的1，未停牌得0
    suspened_info_df = get_price(list(stock_list), start_date=context.current_dt, end_date=context.current_dt, frequency='daily', fields='paused')['paused'].T
    # 过滤停牌股票 返回dataframe
    unsuspened_index = suspened_info_df.iloc[:,0]<1
    # 得到当日未停牌股票的代码list:
    unsuspened_stocks = suspened_info_df[unsuspened_index].index
    # 进一步，筛选出前days天未曾停牌的股票list:
    feasible_stocks=[]
    current_data=get_current_data()
    for stock in unsuspened_stocks:
        if sum(attribute_history(stock, days, unit='1d',fields=('paused'),skip_paused=False))[0]==0:
            feasible_stocks.append(stock)
    return feasible_stocks

#5
# 根据不同的时间段设置滑点与手续费
def set_slip_fee(context):
    # 将滑点设置为0
    set_slippage(FixedSlippage(0)) 
    # 根据不同的时间段设置手续费
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
每天交易时
================================================================================
'''
def handle_data(context, data):
    if g.if_trade==True:
        
        # 按照当前总资产决定分配到每个股票上面的资金
        g.everyStock=context.portfolio.portfolio_value/g.num_stocks
        # 依本策略，得到待买入的股票列表
        toBuy = to_buy(context)
        #执行卖出操作
        order_sell(context,toBuy)
        #执行买入操作
        order_buy(toBuy)
        
    g.if_trade = False

#6
# 依本策略，得到待买入的股票列表
# 输入：context（见聚宽API文档）
# 输出：待买入的股票列表-list类型
def to_buy(context):
    # 获得今天的日期的字符串
    todayStr=str(context.current_dt)[0:10]
    # 获得当前的因子
    current_factors=getOriginalFactors(g.factors,todayStr)
        
    factors_table=getDS(g.feasible_stocks,todayStr,g.lag)

    weights=linreg(factors_table[g.factors],factors_table[['return']])
        
    betas=weights[1:]
    # 假设上一期的回归参数对于下一期仍然适用，对股票下一期的收益进行估计
    points=current_factors.dot(betas)+weights[0]
    points.sort(ascending=False)

    NoB=0
    for i in range(0,g.num_stocks):
        if points[i]>0:
            NoB+=1
            
    to_buy=array(points.index[0:NoB])
    return to_buy
    
#7
# 执行卖出操作
# 输入：context,toBuy-list类型
# 输出：none
def order_sell(context,toBuy):
    #如果现有持仓股票不在股票池，清空
    list_position=context.portfolio.positions.keys()
    #有持仓，但是不在要买的名单里
    for i in range(0,len(g.feasible_stocks)):
        if indexOf(g.feasible_stocks[i],toBuy)==-1 and indexOf(g.feasible_stocks[i],list_position)>-1:
            order_target_value(g.feasible_stocks[i], 0)
    return

#8
# 执行买入操作
# 输入：context,toBuy-list类型
# 输出：none
def order_buy(toBuy):
    # 如果股票在待持仓列表，按所分配的份额持仓
    for i in range(0,len(g.feasible_stocks)):
        if indexOf(g.feasible_stocks[i],toBuy)>-1:
            order_target_value(g.feasible_stocks[i], g.everyStock)

#9
# 查找一个元素在数组里面的位置，如果不存在，则返回-1
# 输入：a为list类型
# 输出：int类型
def indexOf(e,a):
    for i in range(0,len(a)):
        if e<=a[i]:
            return i
    return -1

#10
# 取数据的函数
# 输入：因子-list类型，日期d-str类型（XXXX-XX-XX）
# 输出df-dataframe类型
def getOriginalFactors(factors,d):
    # 用于查询基本面数据的查询语句
    q = query(valuation,balance,cash_flow,income,indicator).filter(valuation.code.in_(g.feasible_stocks))
    # 获得股票的基本面数据，
    df = get_fundamentals(q,d)
    code=array(df['code'])
    df = df[factors]
    df.index=code
    df = df.dropna()
    return df

#11
# 这个函数用来协助进行线性回归的
# 输入：factors是所有股票的上一期因子值-list，returns是股票上一期的收益
# 输出：class类
def linreg(factors,returns):
    # 加入一列常数列，表示市场的状态以及因子以外没有考虑到的因素
    X=sm.add_constant(factors)
    # 进行多元线性回归
    results = regression.linear_model.OLS(returns, X).fit()
    # 返回多元线性回归的参数值
    return results.params



#12
# 获得有效的回归样本因子值和收益率。取前lags个季度的数据以及其之后一段时间的收益率
# 输入：stocks为list类型，dateStr为str类型，lags为int
# 输出：DataFrame
def getDS(stocks,dateStr,lags):
    #生成一个空的dataframe,列除了day还有 pubDate
    cols=g.factors+['day','pubDate','return']
    code_list=[val+'_lag'+str(i) for val in stocks for i in range(lags)]
    len_rows=len(code_list)
    len_cols=len(cols)
    table=np.zeros((len_rows,len_cols)) #生成0矩阵
    table[:,:]=nan
    table_factors=pd.DataFrame(table,columns=cols,index=code_list)
    
    cols2=g.factors+['day','pubDate']
    for i in stocks:
        # 获得前一个交易日的日期（因为当前交易日你是不知道当前收盘价的）
        D=getDay(dateStr,-1)
        # 一个循环，对每一个财务季度进行获取因子
        for j in range(0,lags):
            # 查询财务因子的语句
            q = query(indicator,valuation).filter(indicator.code.in_([i]))
            f_temp=get_fundamentals(q,D)
            #先判定是否上市，如果上市，才将其装入
            row_name=i+'_lag'+str(j)
            if len(f_temp)>0:
                f_temp=f_temp[cols2]
                f_temp.index=[row_name]
                table_factors.ix[[row_name],cols2]=f_temp
                #得到本期财报的披露日期向前推一个日期:
                LD=getDay(table_factors['pubDate'][row_name],-1)
                p1=getHistory(i,LD)
                p2=getHistory(i,D)
                # 获得两个日期隔了多少个交易日
                getDayDifferent = indexOf(D,g.ATD)-indexOf(LD,g.ATD)
                r=math.log(p2/p1)/getDayDifferent
                table_factors.ix[[row_name],['return']]=r
            else:
                LD=D
            D=LD
    table_factors=table_factors.dropna() # 将所有含有nan项的行(每行代表一只股票)删除
    return table_factors

#13
# 获得历史上某个股票某一天的收盘价
# 输入：stock为str类型，dateStr为str类型
# 输出：DataFrame
def getHistory(stock,dateStr):
    # 获得股价数据
    df = get_price(stock, start_date=dateStr, end_date=dateStr, frequency='daily', fields=['close'])
    # 如果数据存在，那么返回当天收盘价
    if len(df)>0:
        return df['close'][0]
    # 如果数据不存在，返回NaN
    else:
        return float("nan")

# 14
# 日期计算之获得某个日期之前或者之后dt个交易日的日期
# 输入：precent-str类型，dt-int类型
# 输出：日期-str
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
每天收盘后
================================================================================
'''
# 每日收盘后要做的事情（本策略中不需要）
def after_trading_end(context):
    return