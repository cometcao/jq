import pandas as pd
import numpy as np
import statsmodels.formula as smFormula
import statsmodels.api as smApi
from operator import methodcaller

def initialize(context):
    # 定义行业指数list以便去股票
    # g.indexList = ['000300.XSHG','000001.XSHG','399905.XSHE','399005.XSHE','399006.XSHE']
    # g.indexList = ['000300.XSHG','000001.XSHG']
    g.indexList = ['399005.XSHE','399006.XSHE']

    # 定义全局参数值
    g.pastDay = 20 # 过去pastDay日参数
    g.topK = 8 # topK只股票
    g.herdSign = np.zeros((len(g.indexList),1))

    # 每周判断一次羊群效应
    # run_weekly(mainHerd, 1, time='before_open')
    run_monthly(mainHerd, 1, time='before_open')

# 计算相对强弱RPS值
def calRPS(stocks,curDate,preDate):
    # 初始化参数信息
    numStocks = len(stocks)
    rankValue = []

    # 计算涨跌幅
    for security in stocks:
        # 获取过去pastDay的指数值
        lastDf = get_price(security, start_date = preDate, end_date = curDate, frequency = '1d', fields = 'close')
        lastClosePrice = float(lastDf.iloc[-1])
        firstClosePrice = float(lastDf.iloc[0])
        # 计算涨跌幅
        errCloseOpen = [(lastClosePrice - firstClosePrice)/firstClosePrice]
        rankValue += errCloseOpen

    # 根据周涨跌幅排名
    rpsStocks = {'code':stocks,'rankValue':rankValue}
    rpsStocks = pd.DataFrame(rpsStocks)
    rpsStocks = rpsStocks.sort('rankValue',ascending = False)
    stocks = list(rpsStocks['code'])
    rankValue = list(rpsStocks['rankValue'])

    # 计算RPS值
    rpsValue = [99 - (100 * float(i)/numStocks) for i in range(numStocks)]
    rpsStocks = {'code':stocks,'rpsValue':rpsValue,'rankValue':rankValue}
    rpsStocks = pd.DataFrame(rpsStocks)

    return rpsStocks

# 判断：是否存在羊群效应
def calHerdSign(index,pastDay,curDate,preDate):
    # try:
    # 获取指数pastDay内的价格
    indexPrice = get_price(index,start_date = preDate, end_date = curDate, frequency = '1d',fields = ['close'])
    # 获取不同日期的Rmt
    # 初始化存储数组
    stockPeInfo = indexPrice
    stockPeInfo['Rmt'] = 0
    stockPeInfo['Rmt2'] = 0
    dateInfo = (stockPeInfo.T).columns

    # 计算Rmt
    stockPE = 0
    peIndex = 0
    dateInfo = dateInfo.map(methodcaller('date'))
    for days in dateInfo:
        # 获取指数内的股票
        stocks = get_index_stocks(index,days)
        numStocks = len(stocks)
        for security in stocks:
            peInfo = get_fundamentals(query(valuation.pe_ratio).filter(valuation.code.in_([security])), date = days)
            if len(peInfo) != 0:
                peInfo = float(peInfo['pe_ratio'])
                stockPE += peInfo
            else:
                print(security,days)
                continue
        peIndex += stockPE / numStocks
        stockPeInfo.loc[days,'Rmt'] = abs(float(peIndex))
        stockPeInfo.loc[days,'Rmt2'] = float(peIndex)**2
        # 重置参数
        stockPE = 0
        peIndex = 0
    # print(stockPeInfo)
    # formula需要解码：https://www.reddit.com/r/pystats/comments/2cn0go/troubleshooting_a_patsy_error/
    formula = 'close~Rmt+Rmt2';formula = formula.encode('ascii')
    olsResult = smFormula.api.ols(formula = formula, data=stockPeInfo).fit()
    # testInfo = smApi.stats.linear_rainbow(olsResult)
    coef = olsResult.params.loc['Rmt2']
    pvalues = olsResult.pvalues.loc['Rmt2']
    if pvalues < 0.01 and coef < 0:
        return 1
    else:
        return 0
        
    # except:
        # print('Turn to modify code in function "calHerdSign"')

# 每周计算一次羊群效应
def mainHerd(context):
    # 获取全局参数
    indexList = g.indexList
    pastDay = g.pastDay
    curDate = context.current_dt.date()
    preDate = curDate + datetime.timedelta(days = -pastDay)
    curDate = str(curDate);preDay = str(preDate)
    # 生成返回数组
    returnArr = g.herdSign
    for i,eachIndex in enumerate(indexList):
        returnArr[i] = calHerdSign(eachIndex,pastDay,curDate,preDate)

    g.herdSign = returnArr

# 回测
def handle_data(context, data):
    # 初始化参数
    indexList = g.indexList
    topK = g.topK
    herdSign = g.herdSign
    stocks = []
    # 计算日期参数
    pastDay = g.pastDay
    curDate = context.current_dt.date()
    preDate = curDate + datetime.timedelta(days = -pastDay)
    curDate = str(curDate);preDay = str(preDate)

    # 根据羊群效应选取股票
    for i,eachIndex in enumerate(indexList):
        # 避开羊群效应
        if herdSign[i] == 1:
            continue
        else:
            oriStocks = get_index_stocks(eachIndex,curDate)
            rpsStocks = calRPS(oriStocks,curDate,preDate)
            rpsStocks = list(rpsStocks[:topK]['code'])
            stocks += rpsStocks
        # 跟随羊群效应
        # if herdSign[i] == 1:
        #     oriStocks = get_index_stocks(eachIndex,curDate)
        #     rpsStocks = calRPS(oriStocks,curDate,preDate)
        #     rpsStocks = list(rpsStocks[:topK]['code'])
        #     stocks += rpsStocks
        # else:
        #     continue

    # 筛选股票：排除重复的，持股topK只
    stocks = list(set(stocks))
    numStocks = len(stocks)
    if numStocks > topK:
        stocks = calRPS(stocks,curDate,preDate)
        stocks = list(stocks[:topK]['code'])
    else:
        pass
    numStocks = len(stocks)

    # 根据候选池买卖股票
    if numStocks > 0:
        # 卖出操作
        # 判断当前是否持有目前股票,若已持有股票在新的候选池里则继续持有，否则卖出
        for security in context.portfolio.positions.keys():
            if security in stocks:
                continue
            else:
                order_target(security,0)
                # print("Selling %s" %(security))
        # 买入操作
        for security in stocks:
            # 根据均线动量策略买卖股票
            curPrice = data[security].price
            ma5 = data[security].mavg(5,'close')
            ma15 = data[security].mavg(15,'close')
            if curPrice > ma5 and ma5 > ma15:
                # 买入该股票
                # 获取股票基本信息：是否停牌、是否ST,持股头寸、股价等
                currentData = get_current_data()
                pauseSign = currentData[security].paused
                STInfo = get_extras('is_st',security,start_date=preDate,end_date=curDate)
                STSign = STInfo.iloc[-1]
                stocksAmount = context.portfolio.positions[security].amount
                stocksPrice = data[security].price
                cash = context.portfolio.cash
                # 买入操作
                if not pauseSign and not STSign.bool():
                    # 购买该股票，获得可购买的股票数量
                    buyAmount = int((cash / topK) / stocksPrice)
                    order(security,buyAmount)
                    # print("Buying %s" % (security))
                else:
                    continue
            else:
                continue
    else:
        # 没有龙头股，清仓操作
        for security in context.portfolio.positions.keys():
            order_target(security,0)
            # print("Selling %s" %(security))