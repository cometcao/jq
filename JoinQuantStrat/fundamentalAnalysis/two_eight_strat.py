import datetime as dt
'''
=================================================
����ز�ǰ���ò����ͻز�
=================================================
'''
def initialize(context):
    set_params()    #1���ò߲���
    set_variables() #2�����м����
    set_backtest()  #3���ûز�����

    run_daily(fun_main, '14:53')

#1 ���ò���
def set_params():
    # ���û�׼����
    set_benchmark('000300.XSHG') 
    g.lag = 20
    #g.hour = 14
    #g.minute = 53
    
    g.hs =  '000300.XSHG' #300ָ��
    g.zz =  '000905.XSHG'#500ָ��

    g.ETF300 = '510300.XSHG'#'510300.XSHG'
    g.ETF500 = '510500.XSHG'#'510500.XSHG'

def fun_initialize(context):
    '''
    ��Ϊģ�⽻��ʱ���ᱣ��������ʷ��ֵ�����¸�ֵ�������
    Ϊ�˱�������������ģ�⽻���ﲻ��Ч��������ֵһ�Σ�
    �豣��״̬�Ĳ��������ܷŴ˺�����
    '''
    # ���÷��ճ���
    context.risk_money = context.portfolio.portfolio_value * 0.01

    # ��̬�ֲ����ʱ���׼����Լ�������
    # 1.96, 95%; 2.06, 96%; 2.18, 97%; 2.34, 98%; 2.58, 99%; 5, 99.9999%
    context.confidencelevel = 1.96

    context.moneyfund = ['511880.XSHG']
    
    context.moneyfund = fun_delNewShare(context, context.moneyfund, 60)


#2 �����м����
def set_variables():
    return

#3 ���ûز�����
def set_backtest():
    set_option('use_real_price', True) #����ʵ�۸���
    log.set_level('order', 'error')

'''
=================================================
ÿ�쿪��ǰ
=================================================
'''
#ÿ�쿪��ǰҪ��������
def before_trading_start(context):
    fun_initialize(context)
    set_slip_fee(context) 

#4 
# ���ݲ�ͬ��ʱ������û�����������

def set_slip_fee(context):
    # ����������Ϊ0
    set_slippage(FixedSlippage(0)) 
    # ���ݲ�ͬ��ʱ�������������
    dt=context.current_dt
    
    if dt>datetime.datetime(2013,1, 1):
        set_commission(PerTrade(buy_cost=0.0003, sell_cost=0.0003, min_cost=5)) 
        
    elif dt>datetime.datetime(2011,1, 1):
        set_commission(PerTrade(buy_cost=0.001, sell_cost=0.002, min_cost=5))
            
    elif dt>datetime.datetime(2009,1, 1):
        set_commission(PerTrade(buy_cost=0.002, sell_cost=0.003, min_cost=5))
                
    else:
        set_commission(PerTrade(buy_cost=0.003, sell_cost=0.004, min_cost=5))

'''
=================================================
ÿ�ս���ʱ
=================================================
''' 
def handle_data(context, data):
    pass

def fun_main(context):
    # ��õ�ǰʱ��
    #hour = context.current_dt.hour
    #minute = context.current_dt.minute
    
    # ÿ������ʱ������λ
    #if hour == g.hour and minute == g.minute:
    signal = get_signal(context)
        
    if signal == 'sell_the_stocks':
        sell_the_stocks(context)
    elif signal == 'ETF300' or signal == 'ETF500':
        buy_the_stocks(context,signal)
    else:
        fun_rebalance(context)

#5
#��ȡ�ź�
def get_signal(context):
    
    #����300����֤500�ĵ������̼�
    hs300,cp300 = getStockPrice(g.hs, g.lag)
    zz500,cp500  = getStockPrice(g.zz, g.lag)
        
    #����ǰ20�ձ䶯
    hs300increase = (cp300 - hs300) / hs300
    zz500increase = (cp500 - zz500) / zz500
        
    hold300 = context.portfolio.positions[g.ETF300].total_amount
    hold500 = context.portfolio.positions[g.ETF500].total_amount
    
    if (hs300increase<=0 and hold300>0) or (zz500increase<=0 and hold500>0):
        return 'sell_the_stocks'
    elif hs300increase>zz500increase and hs300increase>0 and (hold300==0 and hold500==0):
        return 'ETF300'
    elif zz500increase>hs300increase and zz500increase>0 and (hold300==0 and hold500==0):
        return 'ETF500'

#6
#ȡ�ù�Ʊĳ�������ڵ��������̼ۣ�����ȡǰ20�պ͵�ǰ ���̼ۣ�
def getStockPrice(stock, interval):
    h = attribute_history(stock, interval, unit='1d', fields=('close'), skip_paused=True)
    return (h['close'].values[0],h['close'].values[-1])

#7
#������Ʊ
def sell_the_stocks(context):
    for stock in context.portfolio.positions.keys():
        # ��δ��벻���Ͻ������Ʒ�ֶ��������⣬������ OK
        if stock not in context.moneyfund:
            equity_ratio = {}
            equity_ratio[stock] = 0
            trade_ratio = fun_getequity_value(context, equity_ratio)
            fun_trade(context, trade_ratio)

#8
#�����Ʊ
def buy_the_stocks(context,signal):
    equity_ratio = {}
    equity_ratio[eval('g.%s'% signal)] = 1.0
    trade_ratio = fun_getequity_value(context, equity_ratio)
    fun_trade(context, trade_ratio)
    #return (log.info("Buying %s"% signal ),order_value(eval('g.%s'% signal), context.portfolio.cash))
    
'''
=================================================
ÿ�����̺󣨱������в���Ҫ��
=================================================
'''  
def after_trading_end(context):
    return

'''
    ����Ԥ��� risk_money ��  confidencelevel �����㣬��������ö���Ȩ�����ʲ�
'''
def fun_getequity_value(context, equity_ratio):
    def __fun_getdailyreturn(stock, freq, lag):
        hStocks = history(lag, freq, 'close', stock, df=True)
        dailyReturns = hStocks.resample('D',how='last').pct_change().fillna(value=0, method=None, axis=0).values

        return dailyReturns

    def __fun_getStd(stock, freq, lag):
        dailyReturns = __fun_getdailyreturn(stock, freq, lag)
        std = np.std(dailyReturns)

        return std
    
    def __fun_getEquity_value(__equity_ratio, __risk_money, __confidence_ratio):
        __equity_list = list(__equity_ratio.keys())
        hStocks = history(1, '1d', 'close', __equity_list, df=False)

        __curVaR = 0
        __portfolio_VaR = 0

        for stock in __equity_list:
            # ÿ�ɵ� VaR��VaR = ��һ�յļ۸� * ���ŶȻ�������ı�׼���� * �������ʵı�׼��
            __curVaR = hStocks[stock] * __confidence_ratio * __fun_getStd(stock, '1d', 120)
            # һԪ���������ٹ�
            __curAmount = 1*__equity_ratio[stock] / hStocks[stock]      # 1����λ���ʽ𣬷���ʱ���ù�Ʊ��������ٹ�
            __portfolio_VaR += __curAmount * __curVaR                           # 1��λ�ʽ�ʱ���ù�Ʊ�ϵ�ʵ�ʷ��ճ���
    
        if __portfolio_VaR:
            __equity_value = __risk_money / __portfolio_VaR
        else:
            __equity_value = 0
        
        if isnan(__equity_value):
            __equity_value = 0
    
        return __equity_value

    risk_money = context.risk_money
    equity_value, bonds_value = 0, 0
    
    equity_value = __fun_getEquity_value(equity_ratio, risk_money, context.confidencelevel)
    portfolio_value = context.portfolio.portfolio_value
    if equity_value > portfolio_value:
        portfolio_value = equity_value
        bonds_value = 0
    else:
        bonds_value = portfolio_value - equity_value
    
    trade_ratio = {}
    equity_list = list(equity_ratio.keys())
    for stock in equity_list:
        if stock in trade_ratio:
            trade_ratio[stock] += round((equity_value * equity_ratio[stock] / portfolio_value), 3)
        else:
            trade_ratio[stock] = round((equity_value * equity_ratio[stock] / portfolio_value), 3)
    
    # û�ж� bonds ����֣���Ϊֻ��һ��
    if context.moneyfund:
        stock = '511880.XSHG'
        if stock in trade_ratio:
            trade_ratio[stock] += round((bonds_value * 1.0 / portfolio_value), 3)
        else:
            trade_ratio[stock] = round((bonds_value * 1.0 / portfolio_value), 3)
    print trade_ratio
    return trade_ratio

def fun_rebalance(context):
    myholdlist = list(context.portfolio.positions.keys())
    if myholdlist:
        for stock in myholdlist:
            if stock not in context.moneyfund:
                equity_ratio = {stock:1.0}
                trade_ratio = fun_getequity_value(context, equity_ratio)
                fun_trade(context, trade_ratio)

# �޳�����ʱ��϶̵Ĳ�Ʒ
def fun_delNewShare(context, equity, deltaday):
    deltaDate = context.current_dt.date() - dt.timedelta(deltaday)
    
    tmpList = []
    for stock in equity:
        if get_security_info(stock).start_date < deltaDate:
            tmpList.append(stock)
    
    return tmpList

# ���׺���
def fun_trade(context, trade_ratio):
    def __fun_trade(context, stock, value):
        print stock + " ���ֵ� " + str(round(value, 2)) + "\n"
        order_target_value(stock, value)
        
    def __fun_tradeBond(context, stock, Value):
        hStocks = history(1, '1d', 'close', stock, df=False)
        curPrice = hStocks[stock]
        curValue = float(context.portfolio.positions[stock].total_amount * curPrice)
        deltaValue = abs(Value - curValue)
        if deltaValue > (curPrice*100):
            if Value > curValue:
                cash = context.portfolio.cash
                if cash > (curPrice*100):
                    __fun_trade(context, stock, Value)
            else:
                # ������������������� 100 �ɣ��������������
                if stock == '511880.XSHG':
                    Value -= curPrice*100
                __fun_trade(context, stock, Value)

    def __fun_tradeStock(context, stock, ratio):
        total_value = context.portfolio.portfolio_value
        if stock in context.moneyfund:
            __fun_tradeBond(context, stock, total_value * ratio)
        else:
            curPrice = history(1,'1d', 'close', stock, df=False)[stock][-1]
            curValue = context.portfolio.positions[stock].total_amount * curPrice
            Quota = total_value * ratio
            if Quota:
                if abs(Quota - curValue) / Quota >= 0.25:
                    if Quota > curValue:
                        cash = context.portfolio.cash
                        if cash >= Quota * 0.25:
                            __fun_trade(context, stock, Quota)
                    else:
                        __fun_trade(context, stock, Quota)
            else:
                __fun_trade(context, stock, Quota)

    trade_list = list(trade_ratio.keys())

    hStocks = history(1, '1d', 'close', trade_list, df=False)

    myholdstock = list(context.portfolio.positions.keys())
    total_value = context.portfolio.portfolio_value

    # ���в�λ
    holdDict = {}
    hholdstocks = history(1, '1d', 'close', myholdstock, df=False)
    for stock in myholdstock:
        tmpW = round((context.portfolio.positions[stock].total_amount * hholdstocks[stock])/total_value, 2)
        holdDict[stock] = float(tmpW)

    # �����в�λ������
    tmpDict = {}
    for stock in holdDict:
        if stock in trade_ratio:
            tmpDict[stock] = round((trade_ratio[stock] - holdDict[stock]), 2)
    tradeOrder = sorted(tmpDict.items(), key=lambda d:d[1], reverse=False)

    _tmplist = []
    for idx in tradeOrder:
        stock = idx[0]
        __fun_tradeStock(context, stock, trade_ratio[stock])
        _tmplist.append(stock)

    # ����������Ʊ
    for i in range(len(trade_list)):
        stock = trade_list[i]
        if len(_tmplist) != 0 :
            if stock not in _tmplist:
                __fun_tradeStock(context, stock, trade_ratio[stock])
        else:
            __fun_tradeStock(context, stock, trade_ratio[stock])