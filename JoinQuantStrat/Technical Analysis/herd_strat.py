import pandas as pd
import numpy as np
import statsmodels.formula as smFormula
import statsmodels.api as smApi
from operator import methodcaller

def initialize(context):
    # ������ҵָ��list�Ա�ȥ��Ʊ
    # g.indexList = ['000300.XSHG','000001.XSHG','399905.XSHE','399005.XSHE','399006.XSHE']
    # g.indexList = ['000300.XSHG','000001.XSHG']
    g.indexList = ['399005.XSHE','399006.XSHE']

    # ����ȫ�ֲ���ֵ
    g.pastDay = 20 # ��ȥpastDay�ղ���
    g.topK = 8 # topKֻ��Ʊ
    g.herdSign = np.zeros((len(g.indexList),1))

    # ÿ���ж�һ����ȺЧӦ
    # run_weekly(mainHerd, 1, time='before_open')
    run_monthly(mainHerd, 1, time='before_open')

# �������ǿ��RPSֵ
def calRPS(stocks,curDate,preDate):
    # ��ʼ��������Ϣ
    numStocks = len(stocks)
    rankValue = []

    # �����ǵ���
    for security in stocks:
        # ��ȡ��ȥpastDay��ָ��ֵ
        lastDf = get_price(security, start_date = preDate, end_date = curDate, frequency = '1d', fields = 'close')
        lastClosePrice = float(lastDf.iloc[-1])
        firstClosePrice = float(lastDf.iloc[0])
        # �����ǵ���
        errCloseOpen = [(lastClosePrice - firstClosePrice)/firstClosePrice]
        rankValue += errCloseOpen

    # �������ǵ�������
    rpsStocks = {'code':stocks,'rankValue':rankValue}
    rpsStocks = pd.DataFrame(rpsStocks)
    rpsStocks = rpsStocks.sort('rankValue',ascending = False)
    stocks = list(rpsStocks['code'])
    rankValue = list(rpsStocks['rankValue'])

    # ����RPSֵ
    rpsValue = [99 - (100 * float(i)/numStocks) for i in range(numStocks)]
    rpsStocks = {'code':stocks,'rpsValue':rpsValue,'rankValue':rankValue}
    rpsStocks = pd.DataFrame(rpsStocks)

    return rpsStocks

# �жϣ��Ƿ������ȺЧӦ
def calHerdSign(index,pastDay,curDate,preDate):
    # try:
    # ��ȡָ��pastDay�ڵļ۸�
    indexPrice = get_price(index,start_date = preDate, end_date = curDate, frequency = '1d',fields = ['close'])
    # ��ȡ��ͬ���ڵ�Rmt
    # ��ʼ���洢����
    stockPeInfo = indexPrice
    stockPeInfo['Rmt'] = 0
    stockPeInfo['Rmt2'] = 0
    dateInfo = (stockPeInfo.T).columns

    # ����Rmt
    stockPE = 0
    peIndex = 0
    dateInfo = dateInfo.map(methodcaller('date'))
    for days in dateInfo:
        # ��ȡָ���ڵĹ�Ʊ
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
        # ���ò���
        stockPE = 0
        peIndex = 0
    # print(stockPeInfo)
    # formula��Ҫ���룺https://www.reddit.com/r/pystats/comments/2cn0go/troubleshooting_a_patsy_error/
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

# ÿ�ܼ���һ����ȺЧӦ
def mainHerd(context):
    # ��ȡȫ�ֲ���
    indexList = g.indexList
    pastDay = g.pastDay
    curDate = context.current_dt.date()
    preDate = curDate + datetime.timedelta(days = -pastDay)
    curDate = str(curDate);preDay = str(preDate)
    # ���ɷ�������
    returnArr = g.herdSign
    for i,eachIndex in enumerate(indexList):
        returnArr[i] = calHerdSign(eachIndex,pastDay,curDate,preDate)

    g.herdSign = returnArr

# �ز�
def handle_data(context, data):
    # ��ʼ������
    indexList = g.indexList
    topK = g.topK
    herdSign = g.herdSign
    stocks = []
    # �������ڲ���
    pastDay = g.pastDay
    curDate = context.current_dt.date()
    preDate = curDate + datetime.timedelta(days = -pastDay)
    curDate = str(curDate);preDay = str(preDate)

    # ������ȺЧӦѡȡ��Ʊ
    for i,eachIndex in enumerate(indexList):
        # �ܿ���ȺЧӦ
        if herdSign[i] == 1:
            continue
        else:
            oriStocks = get_index_stocks(eachIndex,curDate)
            rpsStocks = calRPS(oriStocks,curDate,preDate)
            rpsStocks = list(rpsStocks[:topK]['code'])
            stocks += rpsStocks
        # ������ȺЧӦ
        # if herdSign[i] == 1:
        #     oriStocks = get_index_stocks(eachIndex,curDate)
        #     rpsStocks = calRPS(oriStocks,curDate,preDate)
        #     rpsStocks = list(rpsStocks[:topK]['code'])
        #     stocks += rpsStocks
        # else:
        #     continue

    # ɸѡ��Ʊ���ų��ظ��ģ��ֹ�topKֻ
    stocks = list(set(stocks))
    numStocks = len(stocks)
    if numStocks > topK:
        stocks = calRPS(stocks,curDate,preDate)
        stocks = list(stocks[:topK]['code'])
    else:
        pass
    numStocks = len(stocks)

    # ���ݺ�ѡ��������Ʊ
    if numStocks > 0:
        # ��������
        # �жϵ�ǰ�Ƿ����Ŀǰ��Ʊ,���ѳ��й�Ʊ���µĺ�ѡ������������У���������
        for security in context.portfolio.positions.keys():
            if security in stocks:
                continue
            else:
                order_target(security,0)
                # print("Selling %s" %(security))
        # �������
        for security in stocks:
            # ���ݾ��߶�������������Ʊ
            curPrice = data[security].price
            ma5 = data[security].mavg(5,'close')
            ma15 = data[security].mavg(15,'close')
            if curPrice > ma5 and ma5 > ma15:
                # ����ù�Ʊ
                # ��ȡ��Ʊ������Ϣ���Ƿ�ͣ�ơ��Ƿ�ST,�ֹ�ͷ�硢�ɼ۵�
                currentData = get_current_data()
                pauseSign = currentData[security].paused
                STInfo = get_extras('is_st',security,start_date=preDate,end_date=curDate)
                STSign = STInfo.iloc[-1]
                stocksAmount = context.portfolio.positions[security].amount
                stocksPrice = data[security].price
                cash = context.portfolio.cash
                # �������
                if not pauseSign and not STSign.bool():
                    # ����ù�Ʊ����ÿɹ���Ĺ�Ʊ����
                    buyAmount = int((cash / topK) / stocksPrice)
                    order(security,buyAmount)
                    # print("Buying %s" % (security))
                else:
                    continue
            else:
                continue
    else:
        # û����ͷ�ɣ���ֲ���
        for security in context.portfolio.positions.keys():
            order_target(security,0)
            # print("Selling %s" %(security))