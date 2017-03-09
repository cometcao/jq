# enable_profile()
import talib
import numpy as np
import pandas as pd

def initialize(context):
    set_commission(PerTrade(buy_cost=0.0003, sell_cost=0.0013, min_cost=5))    # 设置手续费
    g.owning = 7                    # 持仓股票数
    g.muster = []                   # 预选股票池
    g.summit = {}                   # 区间最高价
    
def before_trading_start(context):
    # 取得当前日期
    g.today = context.current_dt.strftime('%Y-%m-%d')
    # 设置预选股票
    g.muster = doSelect(g.today)
    set_universe(g.muster)
    # 清理股票峰值信息
    for stock in g.summit.keys():
        if stock not in context.portfolio.positions: del g.summit[stock]

# 每个单位时间调用一次(如果按天回测,则每天调用一次,如果按分钟,则每分钟调用一次)
def handle_data(context, data):
    # H0、取得今天股票价格信息--------------------------------------------------
    grid = get_price(context.universe, g.today, g.today, fields=['paused', 'open', 'high_limit', 'low_limit'])
    # H1、清仓操作--------------------------------------------------遍历持仓股票
    for stock in context.portfolio.positions:
        # SS、记录股票峰值信息
        if g.summit.get(stock, 0)<data[stock].high: g.summit[stock]=data[stock].high
        # SP、跳过停牌股票
        if grid.paused[stock][0]: continue
        # S1、目前持仓不在预选股票池中(g.muster)则清仓
        if stock not in g.muster:
            doLaunch(g.owning, stock, '越界清仓')
        # S2、回撤10%则清仓
        elif grid.open[stock][0]/g.summit[stock]<0.9:
            doLaunch(g.owning, stock, '回撤清仓')
        # S3、指标卖出信号、止盈清仓
        if doDecide(stock)['dead']:
            doLaunch(g.owning, stock, '死叉清仓')
    # HS、趋势判断--------------------------------------------------判断大盘走势
    # if not doSafety(context, data, '000300.XSHG'): return
    # H2、建仓操作--------------------------------------------------遍历预选股票
    for stock in g.muster:
        # BP、跳过停牌股票
        if grid.paused[stock][0]: continue
        # B1、指标买入信号
        if doDecide(stock)['gold']:
            if doLaunch(g.owning, stock, '金叉建仓', context)['enough']: break

# 选股函数======================================================================
def doSelect(stamp, scale=0.14):
    # 1、选择所有股票按市值排序（代码、市值）-----------------------------------
    result = get_fundamentals(query(valuation.code, valuation.market_cap)) 
    result = result.dropna().sort(columns='market_cap',ascending=True)
    choice = int(len(result) * scale)
    result = result.head(choice)
    # 2、删除ＳＴ、＊ＳＴ-------------------------------------------------------
    result = list(result['code'])
    extras = get_extras('is_st', result, start_date=stamp, end_date=stamp, df=False)
    for stock in extras.keys():
        if extras[stock][0]: result.remove(stock)
    # 3、返回查询结果-----------------------------------------------------------
    return result

# 大盘趋势======================================================================
def doSafety(context, data, index='000300.XSHG'):
    fast = 11
    slow = 26
    sign =  5
    rows = (fast + slow + sign) * 5
    suit = {'dif':0, 'dea':0, 'macd':0, 'safe':False, 'gold':False, 'dead':False}
    grid = attribute_history(index, rows, fields=['open', 'high', 'low', 'close', 'high_limit', 'low_limit']).dropna()
    try:
        dif, dea, macd = talib.MACD(grid['close'].values, fastperiod=fast, slowperiod=slow, signalperiod=sign)
        suit['safe'] = macd[-1]>0
    except:
        pass
    return suit['safe']

# 下单函数======================================================================
def doLaunch(total, stock, title, context=None):
    assign = 0
    direct = None
    result = {'enough': False}
    # 判断买单还是卖单----------------------------------------------------------
    if context: # 买单
        assign = doAssign(total, context)
        if assign>0: direct = order_value(stock, assign)
        else:        result['enough'] = True
    else:       # 卖单
        direct = order_target(stock, 0)
    # 记录日志------------------------------------------------------------------
    if direct: 
        print '%s：stock=%s,下单数量=%d,成交数量=%d,成交价格=%.2f,成交金额=%.2f,目标金额=%.2f' % (title, stock, direct.amount, direct.filled, direct.price, direct.filled*direct.price, assign)
    else:
        print '%s：stock=%s,目标金额=%.2f,下单失败!' % (title, stock, assign)
    # 返回结果------------------------------------------------------------------
    return result

# 资金分配======================================================================
def doAssign(total, context):
    # 计算持仓股票数量、差额股票数量--------------------------------------------
    remain = 0
    for stock in context.portfolio.positions:
        if context.portfolio.positions[stock].amount>0: remain+=1
    for stock in context.portfolio.unsell_positions:
        if context.portfolio.unsell_positions[stock].amount>0: remain+=1
    margin = total - remain
    # 按差额股票数量平均分配剩余现金--------------------------------------------
    if context.portfolio.cash>0 and margin>0: 
        result = context.portfolio.cash/margin
    else:
        result = 0
    # 返回结果------------------------------------------------------------------
    return result

# 决策函数======================================================================
def doDecide(stock):
    fast = 11
    slow = 26
    sign =  5
    rows = (fast + slow + sign) * 5
    suit = {'dif':0, 'dea':0, 'macd':0, 'gold':False, 'dead':False}
    grid = attribute_history(stock, rows, fields=['close']).dropna()
    try:
        grid['dif'], grid['dea'], grid['macd'] = talib.MACD(grid['close'].values, fast, slow, sign)
        grid = grid.dropna()
        # 底背离----------------------------------------------------------------
        mask = grid['macd']>0
        mask = mask[mask==True][mask.shift(1)==False]
        key2 = mask.keys()[-2]
        key1 = mask.keys()[-1]
        suit['gold'] = grid.close[key2]>grid.close[key1] and \
                       grid.dif[key2]<grid.dif[key1]<0   and \
                       grid.macd[-2]<0<grid.macd[-1]
        # 顶背离----------------------------------------------------------------
        mask = grid['macd']<0
        mask = mask[mask==True][mask.shift(1)==False]
        key2 = mask.keys()[-2]
        key1 = mask.keys()[-1]
        suit['dead'] = grid.close[key2]<grid.close[key1] and \
                       grid.dif[key2]>grid.dif[key1]>0   and \
                       grid.macd[-2]>0>grid.macd[-1]
    except:
        pass
    return suit