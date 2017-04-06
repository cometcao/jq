def initialize(context):
    # ������ҵ���
    g.index = 'industry'
    if g.index == 'index':
        # ������ҵָ��list�Ա�ȥ��Ʊ
        # g.indexList = ['000104.XSHG','000105.XSHG','000106.XSHG','000107.XSHG','000108.XSHG','000109.XSHG','000110.XSHG','000111.XSHG','000112.XSHG','000113.XSHG']
        g.indexList = ['000928.XSHG','000929.XSHG','000930.XSHG','000931.XSHG','000932.XSHG','000933.XSHG','000934.XSHG','000935.XSHG','000936.XSHG','000937.XSHG','000938.XSHG']
    elif g.index == 'industry':
        # ������ҵlist�Ա�ȡ��Ʊ
        g.indexList = ['A01','A02','A03','A04','A05','B06',\
        'B07','B08','B09','B11','C13','C14','C15','C17','C18',\
        'C19','C20','C21','C22','C23','C24','C25','C26','C27',\
        'C28','C29','C30','C31','C32','C33','C34','C35','C36',\
        'C37','C38','C39','C40','C41','C42','D44','D45','D46',\
        'E47','E48','E50','F51','F52','G53','G54','G55','G56',\
        'G58','G59','H61','H62','I63','I64','I65','J66','J67',\
        'J68','J69','K70','L71','L72','M73','M74','N77','N78',\
        'P82','Q83','R85','R86','R87','S90']
    else:
        pass

        # ����ȫ�ֲ���ֵ
    g.indexThre = 0.2 #վ��pastDay�վ��ߵ���ҵ����
    g.pastDay = 30 # ��ȥpastDay�ղ���
    g.topK = 6 # 
    
# �������ǿ��RPSֵ
def calRPS(stocks,curDate,preDate):
    # ��ʼ��������Ϣ
    numStocks = len(stocks)
    rankValue = []

    # �����ǵ���
    for security in stocks:
        # ��ȡ��ȥpastDay��ָ��ֵ
        lastDf = get_price(security, start_date = curDate, end_date = curDate, frequency = '1d', fields = 'close')
        lastClosePrice = float(lastDf.iloc[0])
        firstClosePrice = float(lastDf.iloc[-1])
        # �����ǵ���
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

# ��Ʊ�أ�ȡǿ����
def findStockPool(indexList,curDate,preDate,index = 'index'):
    topK = g.topK
    stocks = [];rpsValue = [];industryCode = []
    # ��ÿ����ҵ��ѡȡRPSֵ��ߵ�topKֻ��Ʊ
    # for eachIndustry in industryList:
    for eachIndex in indexList:
        # ȡ������ҵ�Ĺ�Ʊ
        if index == 'index':
            stocks = get_index_stocks(eachIndex)
        elif index == 'industry':
            stocks = get_industry_stocks(eachIndex)
        else:
            return 'Error index order'
        
        # �����Ʊ�����ǿ��RPSֵ
        rpsStocks = calRPS(stocks,curDate,preDate)
        stocks += list(rpsStocks[:topK]['code'])
        # rpsValue += list(rpsStocks[:topK]['rpsValue'])
        # industryCode += [eachIndustry] * len(stocks)
    return stocks

# ѡ�ɣ������߶�������
def selectStocks(stocks,curDate,preDate,data):
    # ��ʼ��
    returnStocks = []

    # ɸѡ���ҽ����������̼���5�վ������ϵĹ�Ʊ
    for security in stocks:
        closePrice = get_price(security, start_date = curDate, end_date = curDate, frequency = '1d', fields = 'close')
        closePrice = float(closePrice.iloc[-1])
        ma5 = data[security].mavg(5,'close')
        ma15 = data[security].mavg(15,'close')
        # if closePrice > ma5:
        if closePrice > ma5 and ma5 > ma15:
            returnStocks += [security]
        else:
            continue

    return returnStocks

# ֹ��ţ�ֽܷ���
def calBuySign(indexList,pastDay,data,index = 'index'):
    # ��ʼ��
    indexThre = g.indexThre
    
    # �����ȥ�����ָ����ֵ,�ж��Ƿ�����ţ�ֽܷ�ֵ
    count = 0
    if index == 'index':
        for eachIndex in indexList:
            avgPrice = data[eachIndex].mavg(pastDay,'close')
            if data[eachIndex].mavg(1,'close') > avgPrice:
                count += 1
            else:
                continue
    elif index == 'industry':
        for eachIndustry in indexList:
            stocks = get_industry_stocks(eachIndustry)
            pastValue = 0
            curValue = 0
            for eachStocks in stocks:
                # pastValue += data[eachStocks].mavg(pastDay,'close')
                # curValue += data[eachStocks].mavg(1,'close') 
                stocksPastPrice = data[eachStocks].mavg(pastDay,'close')
                stocksCurrPrice = data[eachStocks].price
                if isnan(stocksPastPrice) or isnan(stocksCurrPrice):
                    continue
                else:
                    pastValue += stocksPastPrice
                    curValue += stocksCurrPrice
            if curValue > pastValue:
                count += 1
            else:
                continue

    else:
        return 'Error index order.'
    
    # ������ҵ���ط���ţ���г��ź�
    if float(count) / len(indexList) > indexThre:
        return True
    else:
        return False

# ÿ����λʱ��(�������ز�,��ÿ�����һ��,���������,��ÿ���ӵ���һ��)����һ��
def handle_data(context, data):
    # ��ʼ������
    index = g.index
    indexList =g.indexList
    indexThre = g.indexThre
    pastDay = g.pastDay
    curDate = datetime.date.today()
    preDate = curDate + datetime.timedelta(days = -pastDay)
    curDate = str(curDate)
    preDate = str(preDate)
    # ��ȡ�ʽ����
    cash = context.portfolio.cash
    topK = g.topK
    numSell = 0;numBuy = 0
    
    # ţ�ֽܷ��߷���ֹ���ź�
    buySign = calBuySign(indexList,pastDay,data,index)
    # buySign = True
    if buySign == True:
        # ȡǿ����ѡ�ɣ��������RPSָ��ѡȡ������ҵ����ǿ�ƵĹ�Ʊ�γɹ�Ʊ��
        candidateStocks = findStockPool(indexList,curDate,preDate,index)
        # ���ݾ��߲��Դӹ�Ʊ����ѡ������
        stocks = selectStocks(candidateStocks,curDate,preDate,data)
        countStocks = len(stocks)
        if countStocks > topK:
            rpsStocks = calRPS(stocks,curDate,preDate)
            stocks = list(rpsStocks[:topK]['code'])
        else:
            pass
        countStocks = len(stocks)
        
        # �жϵ�ǰ�Ƿ����Ŀǰ��Ʊ,���ѳ��й�Ʊ���µĺ�ѡ������������У���������
        for security in context.portfolio.positions.keys():
            if security in stocks:
                continue
            else:
                order_target(security,0)
                numSell += 1
                # print("Selling %s" %(security))
                
        # ���ݹ�Ʊ�������Ʊ
        for security in stocks:
            # ��ȡ��Ʊ������Ϣ���Ƿ�ͣ�ơ��Ƿ�ST,�ֹ�ͷ�硢�ɼ۵�
            currentData = get_current_data()
            pauseSign = currentData[security].paused
            STInfo = get_extras('is_st',security,start_date=preDate,end_date=curDate)
            STSign = STInfo.iloc[-1]
            stocksAmount = context.portfolio.positions[security].amount
            stocksPrice = data[security].price
            
            if not pauseSign and not STSign.bool():
                # ����ù�Ʊ����ÿɹ���Ĺ�Ʊ����
                buyAmount = int((cash / countStocks) / stocksPrice)
                order(security,buyAmount)
                numBuy += 1
                # print("Buying %s" % (security))
            else:
                continue
    else:
        # ��Ŀǰ���еĹ�Ʊ����
        for security in context.portfolio.positions:
            # ȫ������
            order_target(security, 0)
            numSell += 1
            # ��¼�������
            # print("Selling %s" % (security))
