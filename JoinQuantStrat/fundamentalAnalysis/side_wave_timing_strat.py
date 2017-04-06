from math import *
from scipy.stats import zscore
from scipy.stats import pearsonr

def initialize(context):
    # 定义一个全局变量, 保存要操作的股票
    # 取沪深300指数
    g.stocksIndex = '000300.XSHG'
    # 取中证500指数
    # g.stocksIndex = '399905.XSHE'
    # 取上证50指数
    # g.stocksIndex = '000016.XSHG'
    # 取上证指数
    # g.stocksIndex = '000001.XSHG'
    # 取中小板指
    # g.stocksIndex = '399005.XSHE'
    # 取创业板指
    # g.stocksIndex = '399006.XSHE'
    g.security = get_index_stocks(g.stocksIndex)
    
    # 初始化此策略
    # 设置我们要操作的股票池, 这里我们只操作一支股票
    set_universe(g.security)
    
    # 设置全局天数参数以计算过去N天的开盘价等信息
    g.pastDay = 15
    if g.pastDay != 1:
        g.frequency = '1d'
    else:
        g.frequency = '1m'
        
    # 设置存储最近10天的指数均价
    g.errS = []
    g.errB = []
    
def before_trading_start(context):
    # 得到所有股票过去pastDay日开盘价
    pastDay = g.pastDay
    frequency = g.frequency
    g.lastDf = history(pastDay,frequency,'close')
    
# 计算相对强弱RPS值
def calRPS(stocks):
    # 初始化
    numStocks = len(stocks)
    rankValue = []

    # 计算涨跌幅
    for security in stocks:
        lastClosePrice = g.lastDf[security][0]
        firstClosePrice = g.lastDf[security][-1]
        errCloseOpen = [lastClosePrice - firstClosePrice]
        rankValue += errCloseOpen

    # 根据周涨跌幅排名
    rpsStocks = {'code':stocks,'rankValue':rankValue}
    rpsStocks = pd.DataFrame(rpsStocks)
    rpsStocks = rpsStocks.sort('rankValue',ascending = False)
    stocks = list(rpsStocks['code'])

    # 计算RPS值
    rpsValue = [99 - (100 * i/numStocks) for i in range(numStocks)]
    rpsStocks = {'code':stocks,'rpsValue':rpsValue}
    rpsStocks = pd.DataFrame(rpsStocks)

    return rpsStocks

# 计算波动率
def calVolatility(stocks,startDate,endDate,fValue):
    # 获取往期价格
    price = get_price(stocks,start_date = startDate,end_date = endDate,frequency = fValue,fields = 'close')
    price = list(price['close'])

    # 计算波动率
    uvolatility = [];dvolatility = []
    for i,eachprice in enumerate(price):
        reg_uvolatility = [];reg_dvolatility = []
        for j in range(i + 1):
            if j != 0:
                meanPrice = sum(price[:j]) / j
                varPrice = (eachprice - meanPrice) **2
            else:
                meanPrice = 0
                varPrice = 0
            if eachprice < meanPrice:
                # 下行波动率
                reg_uvolatility += [varPrice]
            else:
                # 上行波动率
                reg_dvolatility += [varPrice]
        
        if len(reg_uvolatility) != 0:
            uvolatility += [sqrt(float(i) / len(reg_uvolatility) * sum(reg_uvolatility))]
        else:
            uvolatility += [0]
        if len(reg_dvolatility) != 0:
            dvolatility += [sqrt(float(i) / len(reg_dvolatility) * sum(reg_dvolatility))]
        else:
            dvolatility += [0]

    return uvolatility,dvolatility

# 计算移动均值的步长（天数或者分钟数）
def calSteps(rank,stocksNum,pastDay,method):
    zRank = (stocksNum - rank) / 10
    coeff = int(pastDay / 3)
    if method == 'exp':
        return int(exp(zRank) * coeff)
    elif method == 'square':
        return int(coeff * (zRank)**2 + 1)
    elif method == 'linear':
        return int(coeff * zRank + 1)
    else:
        return 'Error method'

# 计算波动差值均值
def calAvgRisk(error,days = 1):
    # 计算差值的条目总数
    count = len(error)
    # 按照days递增求均值
    avgRisk = [mean(error[i:i + days]) for i in range(0,count,days)]

    return avgRisk
    
# 计算buySign确定是否买卖操作    
def calAvgPriceErr(stocksIndex,data):
    # 获取均价
    avgPrice_5 = data[stocksIndex].mavg(5, 'close')
    avgPrice_15 = data[stocksIndex].mavg(15, 'close')
    avgPrice_30 = data[stocksIndex].mavg(30, 'close')
    err_5_15 = avgPrice_5 - avgPrice_15
    err_15_30 = avgPrice_15 - avgPrice_30
    rateErr = err_5_15 / err_15_30
    return err_5_15,err_15_30
def calBuySign(errS,errB):
    # 计算均线相关系数
    corrIndex = list(pearsonr(errS,errB))
    corrThre = 0.5
    if corrIndex[0] > corrThre and corrIndex[1] < 0.05:
        if mean(errS) > 0:
            return True
        else:
            return False
    else:
        if g.errS[-1] > 0 and g.errB[-1] > 0:
            return True
        else:
            return False

# 这是来自陈小米的止损函数，可以试试
# def calBuySign(context,stocksIndex,days,bench):
#     hist1 = attribute_history(stocksIndex, days+1,'1d','close',df=False)
#     security_returns = (hist1['close'][-1]-hist1['close'][0])/hist1['close'][0]
#     if security_returns < bench:
#         return True
#     else:
#         return False
        
# 回测函数
def handle_data(context, data):
    # 该指数下股票信息初始化
    stocksIndex = g.stocksIndex
    stocks = g.security
    
    # 获取日期
    pastDay = g.pastDay
    frequency = g.frequency
    curDate = datetime.date.today()
    preDate = curDate + datetime.timedelta(days = -pastDay)
    curDate = str(curDate)
    preDate = str(preDate)
    # 获取资金余额
    cash = context.portfolio.cash
    
    # 计算股票的相对强弱RPS值
    rpsStocks = calRPS(stocks)
    topK = 10
    stocks = list(rpsStocks[:topK]['code'])
    rpsValue = list(rpsStocks[:topK]['rpsValue'])
    # print(stocks)

    # 计算相应指数上行波动率、下行波动率及两者的差值
    iDownRisk,iUpRisk = calVolatility(stocksIndex,preDate,curDate,frequency)
    iErrDU = [eachvalue - iUpRisk[i] for i,eachvalue in enumerate(iDownRisk)]
    
    # 计算buySign
    g.errS += [calAvgPriceErr(stocksIndex,data)[0]]
    g.errB += [calAvgPriceErr(stocksIndex,data)[1]]
    dayThre = pastDay
    if len(g.errS) > dayThre:
        g.errS = g.errS[-dayThre:]
    if len(g.errB) > dayThre:
        g.errB = g.errB[-dayThre:]
    buySign = calBuySign(g.errS,g.errB)
    
    # 买卖股票
    if buySign == True:
        for j,security in enumerate(stocks):
            # 获取股票基本信息：是否停牌、是否ST,持股头寸、股价等
            currentData = get_current_data()
            pauseSign = currentData[security].paused
            STInfo = get_extras('is_st',security,start_date=preDate,end_date=curDate)
            STSign = STInfo.loc[curDate]
            stocksAmount = context.portfolio.positions[security].amount
            stocksPrice = data[security].price
            # print(security,pauseSign,STSign,stocksAmount,stocksPrice)
            
            # 计算股票的上行波动率，下行波动率及差值
            sDownRisk,sUpRisk = calVolatility(security,preDate,curDate,frequency)
            sErrDU = [eachvalue - sUpRisk[i] for i,eachvalue in enumerate(sDownRisk)]
            timeInter = calSteps(float(j),topK,pastDay,'exp')
            # 计算当天指数波动率差值的移动均值
            iAvgRisk = calAvgRisk(iErrDU,timeInter)
            sAvgRisk = calAvgRisk(sErrDU,timeInter)
            # print(security,mean(iAvgRisk),mean(sAvgRisk))
            
            # 计算股票和股指的相关性
            corrIndex = list(pearsonr(sAvgRisk,iAvgRisk))
            corrThre = 0.8
            # print(security,corrIndex,stocksAmount)
            # 根据相关性买卖股票，正相关则买入，负相关卖出(需满足条件：pvalue\相关系数\非停牌\非ST)
            if corrIndex[1] <= 0.05 and not pauseSign and not STSign.bool():
                if corrIndex[0] > corrThre:
                    if stocksAmount != 0:
                        # 方案一：购买该股票，获得可购买的股票数量
                        buyAmount = int((cash / topK) / stocksPrice)
                        order(security,buyAmount)
                        # print("Buying %s" % (security))
                        # 方案二：持有不加仓
                        # continue
                    else:
                        # 购买该股票，获得可购买的股票数量
                        buyAmount = int((cash / topK) / stocksPrice)
                        order(security,buyAmount)
                        # print("Buying %s" % (security))
                else:
                    if stocksAmount > 0:
                        order_target(security,0)
                        # print("Selling %s" % (security))
                    else:
                        continue
            else:
                if stocksAmount > 0:
                    order_target(security,0)
                    # print("Selling %s" % (security))
                else:
                    continue
    else:
        # 将目前所有的股票卖出
        for security in context.portfolio.positions:
            # 全部卖出
            order_target(security, 0)
            # 记录这次卖出
            # print("Selling %s" % (security))
