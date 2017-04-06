# 魔法公式选股+MACD择时 v0.8

import numpy as np
import pandas as pd
import datetime as dt
import talib as tl
import pickle

def initialize(context):
    # 设置费率
    set_commission(PerTrade(buy_cost=0.00025, sell_cost=0.00125, min_cost=5))
    # 设置基准指数：沪深300指数 '000300.XSHG'
    set_benchmark('000300.XSHG')
    # 使用真实价格回测
    set_option('use_real_price', True)
    
    # 昨天，防止引入未来数据
    g.yesterday = context.current_dt -dt.timedelta(1)
    
    # 当前选择的20只股票
    g.curr_stocks=None
    # 将当前20只股票的复权价格和看成一个自定义指数
    g.stocks_index = None
    
    # ----  季报完成日与季报统计最后一天的对应 ---
    # 5月份应该出完了去年4季报（年报）和本年1季报
    # 9月份应该出完了本年2季报（中报）
    # 11月应该出完了本年3季报
    # 还是没出完的股票抛弃（这种股票很少）
    g.map_stat_date = {5:'03-31',9:'06-30',11:'09-30'}

    g.finish_select_stocks = False
    run_monthly(monthly_handle, 2, time='open')

# 每月调用一次，但季报基本出完时才正式选股

# 每出完一次季报选一次股,然后重新构建等权重指数
def monthly_handle(context) :
    # 出完季报才选股
    if g.yesterday.month not in g.map_stat_date.keys() and not (g.stocks_index is None):
        return
    
    # 选出的20只股票
    g.curr_stocks = select_stocks(context,20)
    
    # 根据这20只股票构建等权重自定义指数，
    #    以后每天还需要更新指数数据
    #    注意该指数的成分股必须采用前复权数据
    stocks_close = history(60, unit='1d', field='close', security_list=g.curr_stocks, df=True)
    g.stocks_index = stocks_close.sum(axis=1).values
    
    # 标记刚完成了一次选股
    g.finish_select_stocks = True

# 要求按天回测
def handle_data(context, data):
    # 上个交易日
    g.yesterday = context.current_dt -dt.timedelta(1)
    
    # 从未选过股
    if g.stocks_index is None or g.curr_stocks is None:
        return
    
    # 补充自定指数
    stock_close = history(1, unit='1d', field='close', security_list=g.curr_stocks, df=True)
    _point = stock_close.sum(axis=1).values[-1]
    g.stocks_index = g.stocks_index.tolist()
    g.stocks_index.append(_point)
    g.stocks_index = np.array(g.stocks_index)
    
    sig = signal_MACD(g.stocks_index)
    unit_money = context.portfolio.portfolio_value/20
    
    # 如果刚选完股，首先将老股票卖掉
    if g.finish_select_stocks:
        buy_stocks = g.curr_stocks
        for _stock in context.portfolio.positions:
            if _stock in buy_stocks:
                buy_stocks = buy_stocks[buy_stocks != _stock]
                continue
            order_target(str(_stock), 0)
        if sig != -1:
            for _stock in buy_stocks:
                order_value(str(_stock), unit_money)
        log.info(u'调仓换股')
        g.finish_select_stocks = False
        return

    # 正常情况下，根据信号买卖
    if sig == 1:
        for _stock in g.curr_stocks:
            order_value(str(_stock), unit_money)
        log.info(u'金叉建仓')
    elif sig == -1:
        for _stock in context.portfolio.positions:
            order_target(str(_stock), 0)
        log.info(u'死叉清仓')

# TRIX信号（加入3天确认）
def signal_TRIX(close):
    trix = tl.TRIX(close,timeperiod=12) 
    trima = tl.MA(trix,timeperiod=20) 
    # 画出上一时间DIFF和DEA曲线
    #record(TRIX=trix[-1], TRIMA=trima[-1])
    record(TRIX_DELTA=trix[-1]-trima[-1])
    # 经过3天确认的金叉
    if trix[-1] > trima[-1] and trix[-2] > trima[-2] \
      and trix[-3] > trima[-3] and trix[-4] < trima[-4]:
        return 1
    # 经过3天确认的死叉
    if trix[-1] < trima[-1] and trix[-2] < trima[-2] \
      and trix[-3] < trima[-3] and trix[-4] > trima[-4]:
        return -1
    # 中间状态
    return 0

# MACD信号（加入3天确认）               
def signal_MACD(close):
    diff,dea,macd = tl.MACD(close)  # 这里的macd是同花顺的1/2
    # 画出上一时间DIFF和DEA曲线
    #record(diff=diff[-1], dea=dea[-1])
    record(MACD=2*macd[-1])
    # 经过3天确认的金叉
    if macd[-1] > 0 and macd[-2] > 0 and macd[-3] > 0 and macd[-4] < 0:
        return 1
    # 经过3天确认的死叉
    if macd[-1] < 0 and macd[-2] < 0 and macd[-3] < 0 and macd[-4] > 0:
        return -1
    # 中间状态
    return 0
    
                
# 根据魔法公式计算的结果进行选股
def select_stocks(context,num):
    ROC,EY = cal_magic_formula(context)

    # 按ROC 和 EY 构建表格
    ROC_EY = pd.DataFrame({'ROC': ROC,'EY': EY})

    # 对 ROC进行降序排序, 记录序号
    ROC_EY = ROC_EY.sort('ROC',ascending=False)
    idx = pd.Series(np.arange(1,len(ROC)+1), index=ROC_EY['ROC'].index.values)
    ROC_I = pd.DataFrame({'ROC_I': idx})
    ROC_EY = pd.concat([ROC_EY, ROC_I], axis=1)

    # 对 EY进行降序排序, 记录序号
    ROC_EY = ROC_EY.sort('EY',ascending=False)
    idx = pd.Series(np.arange(1,len(EY)+1), index=ROC_EY['EY'].index.values)
    EY_I = pd.DataFrame({'EY_I': idx})
    ROC_EY = pd.concat([ROC_EY, EY_I], axis=1)

    # 对序号求和，并记录之
    roci = ROC_EY['ROC_I']
    eyi = ROC_EY['EY_I']
    idx = roci + eyi
    SUM_I = pd.DataFrame({'SUM_I': idx})
    ROC_EY = pd.concat([ROC_EY, SUM_I], axis=1)

    # 按序号和，进行升序排序，然后选出排名靠前的20只股票
    ROC_EY = ROC_EY.sort('SUM_I')
    ROC_EY = ROC_EY.head(num)
    
    return ROC_EY.index.values
    
# 计算魔法公式
def cal_magic_formula(context):
    stocks = filter_stocks(context)
    
    q = query(    
        balance.code,                         # 股票代码
        balance.pubDate,                        # 公司发布财报日期
        balance.statDate,                       # 财报统计的季度的最后一天, 比如2015-03-31, 2015-06-30
        income.net_profit,                      # 净利润(元)
        income.financial_expense,               # 财务费用(元)
        income.income_tax_expense,              # 所得税费用(元)
        balance.fixed_assets,                   # 固定资产(元)
        balance.construction_materials,         # 工程物资(元)
        balance.constru_in_process,             # 在建工程(元)
        balance.fixed_assets_liquidation,       # 固定资产清理(元)
        balance.total_current_assets,           # 流动资产合计(元)
        balance.total_current_liability,        # 流动负债合计(元)
        valuation.market_cap,                   # 总市值(亿元)
        #valuation.circulating_cap,              # 流通股本(万股)  110000  160000
        balance.total_liability,                # 负债合计(元)
        cash_flow.cash_and_equivalents_at_end   # 期末现金及现金等价物余额(元)
    ).filter(
        income.net_profit > 0,
        #valuation.circulating_cap < 110000,   
        balance.code.in_(stocks)
    )
    df = get_fundamentals(q, date=g.yesterday.strftime('%Y-%m-%d')).fillna(value=0).set_index('code')
    _stat_date = g.map_stat_date.get(g.yesterday.month,None)
    if not (_stat_date is None):
        df=df[df.statDate == '%s-%s'%(g.yesterday.year,_stat_date)]
    
    # 息税前利润(EBIT) = 净利润 + 财务费用 + 所得税费用
    NP = df['net_profit']
    FE = df['financial_expense']
    TE = df['income_tax_expense']
    EBIT = NP + FE + TE

    # 固定资产净额(Net Fixed Assets) = 固定资产 - 工程物资 - 在建工程 - 固定资产清理
    FA = df['fixed_assets']
    CM = df['construction_materials']
    CP = df['constru_in_process']
    FAL = df['fixed_assets_liquidation']
    NFA = FA - CM - CP - FAL

    # 净营运资本(Net Working Capital)= 流动资产合计－流动负债合计
    TCA = df['total_current_assets']
    TCL = df['total_current_liability']
    NWC = TCA - TCL

    # 企业价值(Enterprise Value) = 总市值 + 负债合计 – 期末现金及现金等价物余额
    MC = df['market_cap']*100000000
    TL = df['total_liability']
    TC = df['cash_and_equivalents_at_end']
    EV = MC + TL - TC

    # Net Working Capital + Net Fixed Assets
    NCA = NWC + NFA

    # 剔除 NCA 和 EV 非正的股票
    tmp = set(df.index.values)-set(EBIT[EBIT<=0].index.values)-set(EV[EV<=0].index.values)-set(NCA[NCA<=0].index.values)
    EBIT = EBIT[tmp]
    NCA = NCA[tmp]
    EV = EV[tmp]

    # 计算魔法公式
    ROC = EBIT / NCA
    EY = EBIT / EV
    
    return [ROC,EY]
    
# 从所有A股中过滤掉：金融服务，公用事业，创业板，新股次新股，ST  
def filter_stocks(context):
    # 获取所有A股
    df = get_all_securities('stock')
    # 剔除金融服务，公用事业
    tmp = set(df.index.values)-set(get_industry_stocks('J66'))\
            -set(get_industry_stocks('J67'))\
            -set(get_industry_stocks('J68'))\
            -set(get_industry_stocks('J69'))\
            -set(get_industry_stocks('N78')) 
    tmp = np.array(list(tmp))
    df = df.select(lambda code: code in tmp)
    #  剔除创业板
    df = df.select(lambda code: not code.startswith('300'))
    #  剔除新股次新股
    one_year = dt.timedelta(365)
    df = df[df.start_date < g.yesterday.date() - one_year]
    # 剔除ST
    df = df[map(lambda s: not s.startswith("ST") and not s.startswith("*ST") ,df.display_name)]
    
    return df.index.values
