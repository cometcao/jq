import pandas as pd
import numpy as np
import statsmodels.formula as smFormula
import statsmodels.api as smApi
from operator import methodcaller

def initialize(context):
    # ������ҵָ��list�Ա�ȥ��Ʊ
    # g.indexList = ['A01','A02','A03','A04','A05','B06',\
    # 'B07','B08','B09','B11','C13','C14','C15','C17','C18',\
    # 'C19','C20','C21','C22','C23','C24','C25','C26','C27',\
    # 'C28','C29','C30','C31','C32','C33','C34','C35','C36',\
    # 'C37','C38','C39','C40','C41','C42','D44','D45','D46',\
    # 'E47','E48','E50','F51','F52','G53','G54','G55','G56',\
    # 'G58','G59','H61','H62','I63','I64','I65','J66','J67',\
    # 'J68','J69','K70','L71','L72','M73','M74','N77','N78',\
    # 'P82','Q83','R85','R86','R87','S90']
    g.indexList = ['A01','B06','C19','E47','G58','J68','I64','P82']
    # ����ȫ�ֲ���ֵ
    g.pastDay = 5 # ��ȥpastDay�ղ���
    g.topK = 5 # topKֻ��Ʊ
    g.gainThre = 0.05 # �Ƿ���ֵ
    g.herdSign = np.zeros((len(g.indexList),1))

    # ÿ���ж�һ����ȺЧӦ
    # run_daily(mainHerd, time='open')
    run_weekly(mainHerd, 1, time='open')
    # run_monthly(mainHerd, 1, time='open')

# �������ǿ��RPSֵ
def calRPS(stocks,preDate,curDate):
    # ��ʼ��
    numStocks = len(stocks)
    rankValue = []
    topK = g.topK

    # �����ǵ���
    for security in stocks:
        stocksPrice = get_price(security, start_date = preDate, end_date = curDate, frequency = '1d', fields = 'close')
        errCloseOpen = [float((stocksPrice.iloc[-1] - stocksPrice.iloc[0])/stocksPrice.iloc[0])]
        rankValue += errCloseOpen

    # �������ǵ�������
    rpsStocks = {'code':stocks,'rankValue':rankValue}
    rpsStocks = pd.DataFrame(rpsStocks)
    rpsStocks = rpsStocks.sort('rankValue',ascending = False)
    rpsStocks = rpsStocks.head(topK)
    rpsStocks = list(rpsStocks['code'])

    return rpsStocks
    
# ������ҵ������
def calRmt(index,preDate,curDate):
    Rmt = 0
    sign = 0
    stocks = get_industry_stocks(index)
    
    for security in stocks:
        stocksPrice = get_price(security, start_date = preDate, end_date = curDate, frequency = '1d', fields = 'close')
        stocksPrice = stocksPrice.dropna(how = 'any')
        if len(stocksPrice) != 0:
            registRmt = (float(stocksPrice.iloc[-1])-float(stocksPrice.iloc[0]))/float(stocksPrice.iloc[0])
            Rmt += registRmt
        else:
            Rmt += 0
            
    return Rmt/(len(stocks)-sign)

# �жϣ��Ƿ������ȺЧӦ
def calHerdSign(index,pastDay):
    # try:
    #��ʼ���洢����[CSAD,Rmt,Rmt2]
    stockRInfo = history(pastDay, '1d', 'close', ['000300.XSHG'])
    dateInfo = (stockRInfo.T).columns
    stockRInfo = pd.DataFrame({index:[0]*pastDay,'Rmt':[0]*pastDay,'Rmt2':[0]*pastDay},index=list(dateInfo))

    #����CSAD
    CSADt = 0
    RitIndex = 0
    dateInfo = dateInfo.map(methodcaller('date'))
    for days in dateInfo:
        # ��ʼ�����ڲ���
        inCurDate = days + datetime.timedelta(days = -1)
        inPreDate = inCurDate + datetime.timedelta(days = -pastDay)
        inCurDate = str(inCurDate);preDate = str(inPreDate)
        #���㵱���г�������Rmt
        Rmt = calRmt(index,inPreDate,inCurDate)
        stockRInfo.loc[days,'Rmt'] = Rmt
        stockRInfo.loc[days,'Rmt2'] = Rmt**2
        #��ȡָ���ڵĹ�Ʊ
        stocks = get_industry_stocks(index)
        numStocks = len(stocks)
        for security in stocks:
            # ����Rit
            Rit = get_price(security, start_date = inPreDate, end_date = inCurDate, frequency = '1d', fields = 'close')
            # print(Rmt,Rit)
            Rit = Rit.dropna(how = 'any')
            if len(Rit) != 0:
                Rit = (float(Rit.iloc[-1])-float(Rit.iloc[0]))/float(Rit.iloc[0])
                errRmi = abs(Rmt - Rit)
                CSADt += errRmi
            else:
                continue
        stockRInfo.loc[days,index] = float(CSADt / numStocks)
        #���ò���
        CSADt = 0
        RitIndex = 0
    # print(stockRInfo)
    olsResult = pd.stats.api.ols(y = stockRInfo[index],x = stockRInfo[['Rmt','Rmt2']])
    coef = olsResult.beta.loc['Rmt2']
    pvalues = olsResult.p_value.loc['Rmt2']
    if pvalues < 0.5 and coef < 0:
        return 1
    else:
        return 0
    # except:
        # print('Turn to modify code in function "calHerdSign"')
    
# �����Ƿ�ɸѡ��Ʊ
def filtGain(stocks,preDate,curDate):
    # ��ʼ��������Ϣ
    numStocks = len(stocks)
    rankValue = []

    # �����ǵ���
    for security in stocks:
        # ��ȡ��ȥpastDay��ָ��ֵ
        stocksPrice = get_price(security, start_date = preDate, end_date = curDate, frequency = '1d', fields = 'close')
        if len(stocksPrice)!=0:
            # �����ǵ���
            errCloseOpen = [(float(stocksPrice.iloc[-1]) - float(stocksPrice.iloc[0])) / float(stocksPrice.iloc[0])]
            rankValue += errCloseOpen
        else:
            rankValue += [0]

    # �������ǵ�������
    filtStocks = {'code':stocks,'rankValue':rankValue}
    filtStocks = pd.DataFrame(filtStocks)
    filtStocks = filtStocks.sort('rankValue',ascending = False)
    # �����ǵ���ɸѡ
    for i in range(numStocks):
        if filtStocks['rankValue'].iloc[i] > g.gainThre:
            continue
        else:
            break
    filtStocks = filtStocks.head(i)
    filtStocks = list(filtStocks['code'])

    return filtStocks

# ���ݳɽ���ɸѡ��Ʊ
def filtVol(stocks):
    # ��ʼ����������
    returnStocks = []

    # ɸѡ
    for security in stocks:
        stockVol = history(20, '1d', 'volume', [security])
        if float(mean(stockVol.iloc[-5:])) > float(mean(stockVol.iloc[-10:])):
            returnStocks += [security]
        else:
            continue
    return returnStocks

# ������ͨ��ֵɸѡ��Ʊ
def filtMarketCap(context,stocks,index):
    # ��ʼ����������
    returnStocks = []

    # ������ҵ��ͨ��ֵ
    oriStocks = get_industry_stocks(index)
    indexMarketCap = get_fundamentals(query(valuation.circulating_market_cap).filter(valuation.code.in_(oriStocks)), date = context.current_dt)
    totalMarketCap = float(sum(indexMarketCap['circulating_market_cap']))
    
    # ���������ͨ��ֵռ����ֵ�ٷֱ���ֵ�����ķ�λΪ��ֵ
    indexMarketCap = indexMarketCap.div(totalMarketCap,axis=0)
    porThre = indexMarketCap.describe()
    porThre = float(porThre.loc['25%'])

    # ɸѡ
    for security in stocks:
        stockMarketCap = get_fundamentals(query(valuation.circulating_market_cap).filter(valuation.code.in_([security])), date = context.current_dt)
        if float(stockMarketCap.iloc[0]) > totalMarketCap * porThre:
            returnStocks += [security]
        else:
            continue
    return returnStocks

# ������ҵ�Ƿ�
def calIndustryGain(stocks,preDate,curDate):
    gainIndex = 0
    for security in stocks:
        stocksPrice = get_price(security, start_date = preDate, end_date = curDate, frequency = '1d', fields = 'close')
        if len(stocksPrice) != 0:
            gainIndex += (float(stocksPrice.iloc[-1]) - float(stocksPrice.iloc[0])) / float(stocksPrice.iloc[0])
        else:
            continue
    return gainIndex/len(stocks)

# Ѱ��ָ������ͷ��
def findLeadStock(context,index,preDate,curDate,method = 0):
    # ��ʼ������
    topK = g.topK
    # ����
    # 1.�Ƿ�������ֵ��topKֻ��Ʊ��
    # 2.ָ���Ƿ�����ֵ���ķ�֮һ���ϣ�
    # 3.��ȥһ�ܳɽ������ڹ�ȥ���ܳɽ�����
    # 4.������ͨ��ֵռ����ֵ�ٷֱȴﵽ��ֵ
    # ȡ����ָ���Ĺ�Ʊ:
    oriStocks = get_industry_stocks(index)        
    # ���ݸ����Ƿ�ɸѡ
    filtStocks = filtGain(oriStocks,preDate,curDate)
    # ����ָ���Ƿ�
    gainIndex = calIndustryGain(oriStocks,preDate,curDate)
    
    # ���ݹ���ɸѡ��ͷ��
    if float(gainIndex)/g.gainThre > 0.5:
        if method == 0:
            # ��������
            return filtStocks
        elif method == 1:
            # ��������+�ɽ�������
            filtStocks = filtVol(filtStocks)
            return filtStocks
        elif method == 2:
            # ��������+��ͨ��ֵ����
            filtStocks = filtMarketCap(context,filtStocks,index)
            return filtStocks
        elif method == 3:
            # ��������+��ͨ��ֵ����+�ɽ�������
            filtStocks = filtVol(filtStocks)
            if len(filtStocks) != 0:
                filtStocks = filtMarketCap(context,filtStocks,index)
            else:
                pass
            return filtStocks
        else:
            return 'Error method order'
    else:
        return []

# ������Ʊ��������
def mainHandle(context,stocks,cash,preDate,curDate):
    # ��ʼ��
    numStocks = len(stocks)

    # ��������
    if numStocks > 0:
        # ��������
        # �жϵ�ǰ�Ƿ����Ŀǰ��Ʊ,���ѳ��й�Ʊ���µĺ�ѡ������������У���������
        for security in context.portfolio.positions.keys():
            if security in stocks:
                continue
            else:
                order_target(security,0)
                print("Selling %s" %(security))
        # �������
        # ��ȡ�ɲ����ʽ�,����Ȩ����
        if cash != 0:
            for security in stocks:
                # ����ù�Ʊ
                # ��ȡ��Ʊ������Ϣ���Ƿ�ͣ�ơ��Ƿ�ST,�ֹ�ͷ�硢�ɼ۵�
                currentData = get_current_data()
                pauseSign = currentData[security].paused
                STInfo = get_extras('is_st',security,start_date = context.current_dt, end_date=context.current_dt)
                STSign = STInfo.iloc[-1]
                # �������
                if not pauseSign and not STSign.bool():
                    # ����ù�Ʊ
                    order_value(security, cash/numStocks)
                    print("Buying %s" % (security))
                else:
                    continue
        else:
            pass
        
    else:
        # û�й�Ʊ�أ���ֲ���
        for security in context.portfolio.positions.keys():
            order_target(security,0)
            # print("Selling %s" %(security))

# ���߹�Ʊɸѡ
def myFiltMavg(stocks):
    returnArr = []
    for security in stocks:
        stocksPrice = history(1,'1m','price',[security])
        stocksPrice = float(stocksPrice.iloc[-1])
        ma5 = history(5,'1d','close',[security])
        ma5 = float(ma5.mean())
        ma15 = history(15,'1d','close',[security])
        ma15 = float(ma15.mean())
        if stocksPrice > ma5 and ma5 > ma15:
            returnArr += [security]
        else:
            continue
    return returnArr
    
# ÿ�ܣ��£�����һ����ȺЧӦ����ִ����������
def mainHerd(context):
    # ��ʼ������
    indexList = g.indexList
    topK = g.topK
    herdSign = g.herdSign
    indexList = g.indexList
    herdStocks = []
    rationalStocks = []
    
    # ��ȡȫ�ֲ���
    pastDay = g.pastDay
    # ��ʼ�����ڲ���
    # curDate = context.current_dt
    curDate = context.current_dt + datetime.timedelta(days = -1)
    preDate = curDate + datetime.timedelta(days = -pastDay)
    curDate = str(curDate);preDate = str(preDate)
    
    # �ж���ȺЧӦ
    returnArr = g.herdSign
    for i,eachIndex in enumerate(indexList):
        herdSign = calHerdSign(eachIndex,pastDay)
        if herdSign == 1:
            herdStocks += findLeadStock(context,eachIndex,preDate,curDate,method = 3)
        else:
            pass
    # ���ж���Ⱥ
    # for i,eachIndex in enumerate(indexList):
    #     herdStocks += findLeadStock(context,eachIndex,preDate,curDate,method = 3)
    
    # ���߶���ɸѡ
    herdStocks = myFiltMavg(herdStocks)
    
    # �����ʽ�
    cash = context.portfolio.cash
    # ִ����������
    if len(herdStocks) > topK:
        herdStocks = calRPS(herdStocks,preDate,curDate)
    else:
        pass
    mainHandle(context,herdStocks,cash,preDate,curDate)

# ����ֹ��
# �����߶�������ɸѡ
def filtMavg(security,data):
    # ɸѡ���ҽ�����ǰ�۸���5�վ������ϵĹ�Ʊ
    price = data[security].price
    ma5 = data[security].mavg(5,'close')
    ma15 = data[security].mavg(15,'close')

    if price < ma5 and ma5 < ma15:
        return True
    else:
        return False
        
#ֹ��
def stopLoss(context,data):
    for security in context.portfolio.positions.keys():
        stocksPrice = history(100,'1m','price',[security])
        errPrice = float((stocksPrice.iloc[-1] - stocksPrice.iloc[0])/stocksPrice.iloc[0])
        if errPrice < 0 or filtMavg(security,data):
            order_target(security,0)
            print("Selling %s" %(security))
        else:
            continue
# �ز�
def handle_data(context, data):
    day = context.current_dt.day
    if day > 24:
        for security in context.portfolio.positions.keys():
            order_target(security,0)
            print("Selling %s" %(security))
    else:
        stopLoss(context,data)
    
    
    
    