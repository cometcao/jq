# 羊驼交易系统 (基于动量策略)
# 日期2008年10月1日到2016年10月26日

from jqdata import *

'''
================================================================================
总体回测前
================================================================================
'''

#总体回测前要做的事情
def initialize(context):
    set_params()      #1 设置策参数
    set_variables()   #2 设置中间变量
    set_backtest()    #3 设置回测条件

#1 设置策略参数
def set_params():
    # 每次剔除手中收益率最低的change_No支股票
    g.change_No = 2
    g.N = 60             # 设置收益率回测区间（天数）
    g.tc = 60            # 设置调仓天数
    g.num_stocks = 20    # 设置持仓股票数目
    # 定义股票池，创业板指数成分股
    g.index='000300.XSHG'
    
#2 设置中间变量
def set_variables():
    g.t = 0                    # 记录回测运行的天数
    g.if_trade = False         # 当天是否交易
    g.feasible_stocks = []     # 当前可交易股票池

#3 设置回测条件
def set_backtest():
    set_benchmark('000300.XSHG')              # 设置为基准
    set_option('use_real_price', True)        # 用真实价格交易
    log.set_level('order', 'error')           # 设置报错等级

'''
================================================================================
每天开盘前
================================================================================
'''
#每天开盘前要做的事情
def before_trading_start(context):
    if g.t%g.tc==0:
        #每g.tc天，交易一次行
        g.if_trade=True 
        #4 设置可行股票池：获得当前开盘的股票池并剔除当前或者计算样本期间停牌的股票
        g.feasible_stocks = set_feasible_stocks(get_index_stocks(g.index),g.N,context)
        #5 设置手续费与手续费
        set_slip_fee(context) 
    g.t+=1


#4    
# 设置可行股票池
# 过滤掉当日停牌的股票,且筛选出前days天未停牌股票
# 输入：stock_list为list类型,样本天数days为int类型，context（见API）
# 输出：list=g.feasible_stocks
def set_feasible_stocks(stock_list,days,context):
    # 得到是否停牌信息的dataframe，停牌的1，未停牌得0
    suspened_info_df = get_price(list(stock_list), 
                       start_date=context.current_dt, 
                       end_date=context.current_dt, 
                       frequency='daily', 
                       fields='paused'
    )['paused'].T
    # 过滤停牌股票 返回dataframe
    unsuspened_index = suspened_info_df.iloc[:,0]<1
    # 得到当日未停牌股票的代码list:
    unsuspened_stocks = suspened_info_df[unsuspened_index].index
    # 进一步，筛选出前days天未曾停牌的股票list:
    feasible_stocks = []
    current_data = get_current_data()
    for stock in unsuspened_stocks:
        if sum(attribute_history(stock, days, unit = '1d',fields = ('paused'), skip_paused = False))[0] == 0:
            feasible_stocks.append(stock)
    return feasible_stocks
    
#5 根据不同的时间段设置滑点与手续费
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
def handle_data(context,data):
    # 如果为交易日
    if g.if_trade == True: 
        #6 获得买入卖出信号，输入context，输出股票列表list
        (sell,buy)=get_signals(context) 
        #7 重新调整仓位，输入context,使用信号结果sell和buy
        rebalance(context, buy, sell)
    g.if_trade = False

#6
# 依本策略的卖出信号，得到应该卖出的股票列表
# 输入：context（见API）
# 输出：应该卖的股票列表，list类型
def get_signals(context):
    # 将昨天设置为收益率计算最后一天 返回datetime.date对象
    enddate = context.previous_date
    # 将昨日日期向前推g.N(这是个整数）得到收益率计算周期第一天 返回datetime.date对象
    startdate = shift_trading_day(enddate,-g.N)
    # 得到回测收益率的股票列表（由于上市、退市等因素，此列表与我们实际可交易股票有一定差异）返回list
    stocks = g.feasible_stocks
    # 按收益率降序排列 返回list
    sorted_list = stock_ret(stocks,startdate,enddate,asc = True)
    # 截取最高的g.num_stocks个可能进行购买的股票
    should_buy = sorted_list[0:g.change_No]
    # 当前持仓股票
    holding = list(context.portfolio.positions.keys())  
    # 如果当前空仓
    if len(list(context.portfolio.positions.keys()))==0:
        # 按照排名最差的g.num_stocks支股票建仓
        should_buy = sorted_list[0:g.num_stocks]
        # 卖出为空
        should_sell = []
    else:
        # 生成卖出股票list，当前为空
        should_sell = stock_ret(holding, startdate, enddate, asc = True)[0:g.change_No]
    # 如果一支持仓股票收益不好该卖
    for both in should_sell[:]:
        # 同时在所有可行股票里收益排名低该买
        if both in should_buy[:]:
            # 既不买入
            list(should_buy).remove(both)
            # 也不卖出
            list(should_sell).remove(both)
    # 返回两个list的元组
    return should_sell,should_buy

#7
# 依本策略的买入信号，得到应该买的股票列表
# 借用买入信号结果，不需额外输入
# 输入：context（见API）
def rebalance(context, buy, sell):
    # 卖出在卖出list中的股票
    for stock_to_sell in list(sell)[:]: 
        order_target_value(stock_to_sell, 0)
    # 把当前持仓股票和需要买入股票生成新的buy的列表，包括调仓头所有需要持有股票
    for stock in buy[:]:
        if stock in list(context.portfolio.positions.keys()):
            buy.append(stock)
    # 调整每个股票到当前总市值/g.num_stocks金额
    for stock_to_buy in buy[:]:
        # 因order函数调整为顺序调整，为防止先行调仓股票由于后行调仓股票占金额过大不能一次调整到位，这里运行两次以解决这个问题
        order_target_value(stock_to_buy, context.portfolio.cash/g.num_stocks)
        order_target_value(stock_to_buy, context.portfolio.cash/g.num_stocks)
            
#8
# 某一日的前shift个交易日日期 
# 输入：date为datetime.date对象(是一个date，而不是datetime)；shift为int类型
# 输出：datetime.date对象(是一个date，而不是datetime)
def shift_trading_day(date,shift):
    # 获取所有的交易日，返回一个包含所有交易日的 list,元素值为 datetime.date 类型.
    tradingday = get_all_trade_days()
    # 得到date之后shift天那一天在列表中的行标号 返回一个数
    shiftday_index = list(tradingday).index(date)+shift
    # 根据行号返回该日日期 为datetime.date类型
    return tradingday[shiftday_index]

#9  
# 根据期间收益率（用前复权收盘价计算）给股票排名
# 输入：stock_list为list类型；startdate enddate为datetime.date对象；asc为布尔类型
# 输出：list类型
def stock_ret(stock_list,startdate,enddate,asc = False):
    # 得到回测区间内股票收盘价 返回dataframe
    log.info(startdate)
    df_close = get_price(list(stock_list),start_date = startdate, end_date = enddate, fields = 'close')['close'].T
    # 删去空值 返回dataframe
    df_close = df_close.dropna(axis = 0)
    # 计算回测区间收益率 返回dataframe
    df_close['ret']=(df_close[enddate]-df_close[startdate])/df_close[startdate]
    #按收益率降序排列，获取股票代码，返回list
    stocks = list(df_close.sort('ret', ascending = asc).index)
    # 返回股票代码list
    return stocks

'''
================================================================================
每天收盘后
================================================================================
'''
# 每日收盘后要做的事情（本策略中不需要）
def after_trading_end(context):
    return