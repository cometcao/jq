from math import *
from scipy.stats import zscore
from scipy.stats import pearsonr

def initialize(context):
    # ����һ��ȫ�ֱ���, ����Ҫ�����Ĺ�Ʊ
    # ȡ����300ָ��
    g.stocksIndex = '000300.XSHG'
    # ȡ��֤500ָ��
    # g.stocksIndex = '399905.XSHE'
    # ȡ��֤50ָ��
    # g.stocksIndex = '000016.XSHG'
    # ȡ��ָ֤��
    # g.stocksIndex = '000001.XSHG'
    # ȡ��С��ָ
    # g.stocksIndex = '399005.XSHE'
    # ȡ��ҵ��ָ
    # g.stocksIndex = '399006.XSHE'
    g.security = get_index_stocks(g.stocksIndex)
    
    # ��ʼ���˲���
    # ��������Ҫ�����Ĺ�Ʊ��, ��������ֻ����һ֧��Ʊ
    set_universe(g.security)
    
    # ����ȫ�����������Լ����ȥN��Ŀ��̼۵���Ϣ
    g.pastDay = 15
    if g.pastDay != 1:
        g.frequency = '1d'
    else:
        g.frequency = '1m'
        
    # ���ô洢���10���ָ������
    g.errS = []
    g.errB = []
    
def before_trading_start(context):
    # �õ����й�Ʊ��ȥpastDay�տ��̼�
    pastDay = g.pastDay
    frequency = g.frequency
    g.lastDf = history(pastDay,frequency,'close')
    
# �������ǿ��RPSֵ
def calRPS(stocks):
    # ��ʼ��
    numStocks = len(stocks)
    rankValue = []

    # �����ǵ���
    for security in stocks:
        lastClosePrice = g.lastDf[security][0]
        firstClosePrice = g.lastDf[security][-1]
        errCloseOpen = [lastClosePrice - firstClosePrice]
        rankValue += errCloseOpen

    # �������ǵ�������
    rpsStocks = {'code':stocks,'rankValue':rankValue}
    rpsStocks = pd.DataFrame(rpsStocks)
    rpsStocks = rpsStocks.sort('rankValue',ascending = False)
    stocks = list(rpsStocks['code'])

    # ����RPSֵ
    rpsValue = [99 - (100 * i/numStocks) for i in range(numStocks)]
    rpsStocks = {'code':stocks,'rpsValue':rpsValue}
    rpsStocks = pd.DataFrame(rpsStocks)

    return rpsStocks

# ���㲨����
def calVolatility(stocks,startDate,endDate,fValue):
    # ��ȡ���ڼ۸�
    price = get_price(stocks,start_date = startDate,end_date = endDate,frequency = fValue,fields = 'close')
    price = list(price['close'])

    # ���㲨����
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
                # ���в�����
                reg_uvolatility += [varPrice]
            else:
                # ���в�����
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

# �����ƶ���ֵ�Ĳ������������߷�������
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

# ���㲨����ֵ��ֵ
def calAvgRisk(error,days = 1):
    # �����ֵ����Ŀ����
    count = len(error)
    # ����days�������ֵ
    avgRisk = [mean(error[i:i + days]) for i in range(0,count,days)]

    return avgRisk
    
# ����buySignȷ���Ƿ���������    
def calAvgPriceErr(stocksIndex,data):
    # ��ȡ����
    avgPrice_5 = data[stocksIndex].mavg(5, 'close')
    avgPrice_15 = data[stocksIndex].mavg(15, 'close')
    avgPrice_30 = data[stocksIndex].mavg(30, 'close')
    err_5_15 = avgPrice_5 - avgPrice_15
    err_15_30 = avgPrice_15 - avgPrice_30
    rateErr = err_5_15 / err_15_30
    return err_5_15,err_15_30
def calBuySign(errS,errB):
    # ����������ϵ��
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

# �������Գ�С�׵�ֹ��������������
# def calBuySign(context,stocksIndex,days,bench):
#     hist1 = attribute_history(stocksIndex, days+1,'1d','close',df=False)
#     security_returns = (hist1['close'][-1]-hist1['close'][0])/hist1['close'][0]
#     if security_returns < bench:
#         return True
#     else:
#         return False
        
# �ز⺯��
def handle_data(context, data):
    # ��ָ���¹�Ʊ��Ϣ��ʼ��
    stocksIndex = g.stocksIndex
    stocks = g.security
    
    # ��ȡ����
    pastDay = g.pastDay
    frequency = g.frequency
    curDate = datetime.date.today()
    preDate = curDate + datetime.timedelta(days = -pastDay)
    curDate = str(curDate)
    preDate = str(preDate)
    # ��ȡ�ʽ����
    cash = context.portfolio.cash
    
    # �����Ʊ�����ǿ��RPSֵ
    rpsStocks = calRPS(stocks)
    topK = 10
    stocks = list(rpsStocks[:topK]['code'])
    rpsValue = list(rpsStocks[:topK]['rpsValue'])
    # print(stocks)

    # ������Ӧָ�����в����ʡ����в����ʼ����ߵĲ�ֵ
    iDownRisk,iUpRisk = calVolatility(stocksIndex,preDate,curDate,frequency)
    iErrDU = [eachvalue - iUpRisk[i] for i,eachvalue in enumerate(iDownRisk)]
    
    # ����buySign
    g.errS += [calAvgPriceErr(stocksIndex,data)[0]]
    g.errB += [calAvgPriceErr(stocksIndex,data)[1]]
    dayThre = pastDay
    if len(g.errS) > dayThre:
        g.errS = g.errS[-dayThre:]
    if len(g.errB) > dayThre:
        g.errB = g.errB[-dayThre:]
    buySign = calBuySign(g.errS,g.errB)
    
    # ������Ʊ
    if buySign == True:
        for j,security in enumerate(stocks):
            # ��ȡ��Ʊ������Ϣ���Ƿ�ͣ�ơ��Ƿ�ST,�ֹ�ͷ�硢�ɼ۵�
            currentData = get_current_data()
            pauseSign = currentData[security].paused
            STInfo = get_extras('is_st',security,start_date=preDate,end_date=curDate)
            STSign = STInfo.loc[curDate]
            stocksAmount = context.portfolio.positions[security].amount
            stocksPrice = data[security].price
            # print(security,pauseSign,STSign,stocksAmount,stocksPrice)
            
            # �����Ʊ�����в����ʣ����в����ʼ���ֵ
            sDownRisk,sUpRisk = calVolatility(security,preDate,curDate,frequency)
            sErrDU = [eachvalue - sUpRisk[i] for i,eachvalue in enumerate(sDownRisk)]
            timeInter = calSteps(float(j),topK,pastDay,'exp')
            # ���㵱��ָ�������ʲ�ֵ���ƶ���ֵ
            iAvgRisk = calAvgRisk(iErrDU,timeInter)
            sAvgRisk = calAvgRisk(sErrDU,timeInter)
            # print(security,mean(iAvgRisk),mean(sAvgRisk))
            
            # �����Ʊ�͹�ָ�������
            corrIndex = list(pearsonr(sAvgRisk,iAvgRisk))
            corrThre = 0.8
            # print(security,corrIndex,stocksAmount)
            # ���������������Ʊ������������룬���������(������������pvalue\���ϵ��\��ͣ��\��ST)
            if corrIndex[1] <= 0.05 and not pauseSign and not STSign.bool():
                if corrIndex[0] > corrThre:
                    if stocksAmount != 0:
                        # ����һ������ù�Ʊ����ÿɹ���Ĺ�Ʊ����
                        buyAmount = int((cash / topK) / stocksPrice)
                        order(security,buyAmount)
                        # print("Buying %s" % (security))
                        # �����������в��Ӳ�
                        # continue
                    else:
                        # ����ù�Ʊ����ÿɹ���Ĺ�Ʊ����
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
        # ��Ŀǰ���еĹ�Ʊ����
        for security in context.portfolio.positions:
            # ȫ������
            order_target(security, 0)
            # ��¼�������
            # print("Selling %s" % (security))
