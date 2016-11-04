"""
This is a long only strategy
stock filter
1. eight two stock index change between 000300.XSHG and 399006.XSHE
2. select stocks with smaller market cap

CHAN theory level definition used in this strategy:
�ʣ� �߶Σ� 1���ӣ� 5���ӣ� 30���ӣ� 1�죬 1��
A    B      C       D       E        F     G

������T+1�� ��������ѵȵ�ԭ��. ��ȡһ�ܽ�����������
�ṩ�����ü����Ӧ�����ڿ����޸�

���۶�����ʵ��Ӧ���������زȵ㡣�ڲ��۵���һ�������Ӳֵ㡣 ����һ���ǳ��ף� ������׷�����ƣ� ����
���������ϵ������

trade
buy: CHAN theory II buy signal, confirmed by sub level I buy signal
sell: stop loss or sub level I sell signal

Auther
hprotein

"""
from scipy.signal import argrelextrema
import chan_II_signal

def set_variables():
    g.total_num_of_pos = 3
    g.number_of_days = 5
    g.number_of_periods_backwards = 55 #133
    g.t = 0                # ��¼�ز����е�����
    g.if_trade = False     # �����Ƿ���
    g.tc = 1   # trigger action per # of days
    g.m = 0
    g.mbc = 60 # trigger buy action per X min / day 60
    g.msc = 60 # trigger sell action per X min / day 60
    g.sell_list = [] # if we have stocks failed to sell, we need to record it and try to sell the next day
    g.to_buy = []
    g.feasible_stocks = []
    g.stock_domain = '000002.XSHG' # All A share
    g.dynamic_stop_loss = False
    g.is_stop_loss = True
    g.period = {}
    g.pct_change = {}
    g.max_price = {} # this needs to be kept since bought and updated constantly, cleared after sold
    g.primary_level = g.F_level
    g.sub_level = g.E_level

def reset_var():
    g.period = {}
    g.pct_change = {}    
    g.chan2.clearDict()

def set_params():
    g.stop_loss = 0.92
    g.tailing_stop_loss = 0.95
    g.C_level = '1m'
    g.D_level = '5m'
    g.E_level = '60m'
    g.F_level = '1d'
    g.G_level = '5d'
    g.chan2 = chan_II_signal.chan_II_signal()

def set_backtest():
    set_benchmark(g.stock_domain) # ����bench�ز��׼�����й�ָ����2009��9�¿�ʼ��
    set_option('use_real_price',True) # ����ʵ�۸���
    log.set_level('order','error')    # ���ñ���ȼ�

# ���ݲ�ͬ��ʱ������û�����������
def set_slip_fee(context):
    # ����������Ϊ0
    set_slippage(FixedSlippage(0)) 
    # ���ݲ�ͬ��ʱ�������������
    dt=context.current_dt
    
    if dt>datetime.datetime(2013,1, 1):
        set_commission(PerTrade(buy_cost=0.0003, sell_cost=0.0013, min_cost=5)) 
        
    elif dt>datetime.datetime(2011,1, 1):
        set_commission(PerTrade(buy_cost=0.001, sell_cost=0.002, min_cost=5))
            
    elif dt>datetime.datetime(2009,1, 1):
        set_commission(PerTrade(buy_cost=0.002, sell_cost=0.003, min_cost=5))
                
    else:
        set_commission(PerTrade(buy_cost=0.003, sell_cost=0.004, min_cost=5))

# ���ÿ��й�Ʊ�أ�
# ���˵�����ͣ�ƵĹ�Ʊ,��ɸѡ��ǰdays��δͣ�ƹ�Ʊ
# ���룺stock_listΪlist����,��������daysΪint���ͣ�context����API��
# �����list
def set_feasible_stocks(stock_list,days,context):
    # �õ��Ƿ�ͣ����Ϣ��dataframe��ͣ�Ƶ�1��δͣ�Ƶ�0
    suspened_info_df = get_price(list(stock_list), start_date=context.current_dt, end_date=context.current_dt, frequency='daily', fields='paused')['paused'].T
    # ����ͣ�ƹ�Ʊ ����dataframe
    unsuspened_index = suspened_info_df.iloc[:,0]<1
    # �õ�����δͣ�ƹ�Ʊ�Ĵ���list:
    unsuspened_stocks = suspened_info_df[unsuspened_index].index
    # ��һ����ɸѡ��ǰdays��δ��ͣ�ƵĹ�Ʊlist:
    feasible_stocks=[]
    current_data=get_current_data()
    for stock in unsuspened_stocks:
        if sum(attribute_history(stock, days, unit='1d',fields=('paused'),skip_paused=False))[0]==0:
            feasible_stocks.append(stock)
    return feasible_stocks

#######################################################################

def initialize(context):
    """
    Called once at the start of the algorithm.
    """   
    set_params() 
    
    set_variables() 
    
    set_backtest()

#ÿ�������ս�������
def after_trading_end(context):
    # primary level check needs to be done again next time
    reset_var()  
    #�õ���ǰδ��ɶ���
    orders = get_open_orders()
    #ѭ������������
    for _order in orders.values():
        g.sell_list.append(_order.security)
        cancel_order(_order)
        
    if g.if_trade:
        g.if_trade = False

def before_trading_start(context):
    """
    Called every day before market open.
    """
    if g.t%g.tc==0:  #and two_eight_turn()
        #ÿg.tc�죬����һ��
        g.if_trade=True 
        # ������������������
        set_slip_fee(context) 
        # ���ÿ��й�Ʊ�أ���õ�ǰ����     ȫ������A��
        g.feasible_stocks = set_feasible_stocks(get_index_stocks(g.stock_domain),g.number_of_days,context)
        
        # initial screening for prime II point stocks
        g.feasible_stocks = filter_stock(context)
        #log.info("We have %d stock(s) showing primary II buying signal" % len(g.feasible_stocks))
    g.t+=1

# ÿ����λʱ��(�������ز�,��ÿ�����һ��,���������,��ÿ���ӵ���һ��)����һ��
def handle_data(context, data):
    if not g.if_trade:
        return
    hour = context.current_dt.hour
    minute = context.current_dt.minute
    #################################################
    if hour == 14 and minute == 42 and g.sell_list:
        for stock in g.sell_list:
            log.info("short %s from sell_list" % stock)
            order_target_value(stock, 0)
        g.sell_list = []
    #################################################
    
    if g.m%g.mbc==0: # try to check to buy 
        buy_stock_list = check_buy_stock(g.feasible_stocks, context, data)
        #log.info("We have the following stocks as buying candidates")
        #log.info(buy_stock_list)
        if buy_stock_list:
            mcap_buy_stock = getMcapInfo(buy_stock_list, context)
            # mcap_buy_stock.sort()
            only_buy_security_list = [x[1] for x in mcap_buy_stock[:g.total_num_of_pos]]
            action_buy_signal(buy_stock_list, context)
    #################################################
    if g.m%g.msc==0: # try to check to sell 
        sell_stock_list = check_sell_stock(context, data)
        action_sell_signal(sell_stock_list, context)
    g.m+=1
    
def inOpenOrder(security):
    orders = get_open_orders()
    for _order in orders.values():
        if _order.security == security:
            return True
    return False    

def filter_stock(context):
    filtered = []
    for stock in g.feasible_stocks:
        df_prime = attribute_history(stock, g.number_of_periods_backwards, g.primary_level, ('high', 'low', 'close', 'volume'), df=True)
        if g.chan2.checkPrimeLevelInBuyPoint(df_prime, stock):
            filtered.append(stock)
    return filtered

def action_buy_signal(buy_list, context):
    for security in buy_list:
        if context.portfolio.cash > context.portfolio.portfolio_value/g.total_num_of_pos and security not in context.portfolio.positions and not inOpenOrder(security):
            buy_order = order_target_value(security, context.portfolio.portfolio_value/g.total_num_of_pos)
            if buy_order and buy_order.status == OrderStatus.held:
                g.max_price[security] = buy_order.price # current order price is the max price
                log.info("long %s @ price %f" % (security, buy_order.price))
            # remove it from candidates list
            g.feasible_stocks.remove(security)

def action_sell_signal(sell_list, context):
    for security,reason in sell_list:
        if not inOpenOrder(security):
            log.info("short %s due to %s" % (security, reason))
            sell_order = order_target_value(security, 0)
            if sell_order and sell_order.status == OrderStatus.held:
                del g.max_price[security]

def check_sell_stock(context, data):
    to_sell = []
    for stock in context.portfolio.positions:
        pos = context.portfolio.positions[stock]
        if not pos.sellable_amount > 0:
            continue
        
        current_price = pos.price
        sl = g.stop_loss
        sg = g.tailing_stop_loss
        recent_period = 8
        if g.dynamic_stop_loss:
            recent_period = g.chan2.getPeriod(stock)
            threthold = get_stop_loss_threshold(stock, recent_period)
            if threthold:
                sl = 1 - threthold
                sg = 1 - (threthold / (current_price / pos.avg_cost)) # scale tailing_stop_loss
        
        df = attribute_history(stock, g.number_of_periods_backwards, g.sub_level, ('high', 'low', 'close','volume'), df=True)
        # current_price = df['close'][-1]
        if g.chan2.checkInSellPoint(df, stock) :
            #log.info("add %s in sell list due to sell point" % stock)
            to_sell.append((stock, "Sell signal @ sell point" ))

        if g.is_stop_loss:
            if current_price / pos.avg_cost < sl:
                to_sell.append((stock, "stop loss @ %f current price %f, avg cost %f" % (sl, current_price, pos.avg_cost)))
                #log.info("stock %s is set to be stop_loss at %f" % (stock, sl))
            elif current_price / g.max_price[stock] < sg:
                to_sell.append((stock, "tailing stop loss at %f current price %f max price %f with period %d" % (sg, current_price, g.max_price[stock], recent_period)))
                #log.info("stock %s is set to be tailing stop loss at %f current price %f max price %f with period %d" % (stock, sg, current_price, g.max_price[stock], recent_period))
            else:
                if current_price > g.max_price[stock]:
                    #log.info("stock %s max price is updated: %f" % (stock, g.max_price[stock]))
                    g.max_price[stock] = current_price
    return to_sell

def check_buy_stock(filtered_stock_list, context, data):
    to_buy = []
    for stock in filtered_stock_list:
        df_sub = attribute_history(stock, g.number_of_periods_backwards, g.sub_level, ('high', 'low', 'close', 'volume'), df=True)
        if g.chan2.checkSubLevelInBuyPoint(df_sub,stock):
            to_buy.append(stock)
    return to_buy

def getMcapInfo(stocks, context):
    if not stocks:
        return None
    # get yesterdays market cap
    queryDf = get_fundamentals(query(
        valuation.market_cap, valuation.code
    ).filter(
        valuation.code.in_(stocks),
        indicator.eps > 0
    ).order_by(
        valuation.market_cap.asc()
    )
    )
    
    stockinfo = []
    for j in xrange(0, len(queryDf['market_cap'])):
        stockinfo.append( (queryDf['market_cap'][j], queryDf['code'][j]) )
    return stockinfo


def two_eight_turn():
    '''
    if both price rise were negative, sell off
    '''
    hs300 = '000300.XSHG'
    #hs300 = '399405.XSHE'
    #zz500 = '000905.XSHG'
    zz500 = '399006.XSHE'
    price_hs300 = attribute_history(hs300, 5, '1d', ('close'), df=False)
    price_zz500 = attribute_history(zz500, 5, '1d', ('close'), df=False)
    hs300_delta = (price_hs300['close'][-1] - price_hs300['close'][0]) / price_hs300['close'][0]
    zz500_delta = (price_zz500['close'][-1] - price_zz500['close'][0]) / price_zz500['close'][0]
    if hs300_delta > zz500_delta:
        #g.stock_domain = hs300
        g.stock_domain = '399405.XSHE'
        g.stop_loss = 0.97
    else:
        #g.stock_domain = zz500
        g.stock_domain = '399664.XSHE'
        g.stop_loss = 0.93
    log.info("use %s as domain with past growth rate (hs300: %.2f, zz500: %.2f)" % (g.stock_domain, hs300_delta, zz500_delta))
    return not (hs300_delta < 0 and zz500_delta < 0)
    
######################################################################################################################
def findPeriod(stock):
    if stock not in g.period:
        df = attribute_history(stock, g.number_of_periods_backwards, g.primary_level, ('high', 'low'), skip_paused=True)
        topIndex = argrelextrema(df['high'].values, np.greater_equal,order=1)[0]
        bottomIndex = argrelextrema(df['low'].values, np.less_equal,order=1)[0]
        delta = None
        if topIndex[-1] > bottomIndex[-1]:
            delta = df['low'].index[bottomIndex[-1]] - df['high'].index[topIndex[-2]]
        else:
            delta = df['high'].index[bottomIndex[-1]] - df['low'].index[topIndex[-2]]
        g.period[stock] = delta.days
    return g.period[stock]


# ������ɻس�ֹ����ֵ
# �������ڳֲ�n�����ܳ��ܵ�������
# �㷨��(����250��������n�յ��� + ����250����ƽ����n�յ���)/2
# ������ֵ
def get_stop_loss_threshold(security, n = 3):
    pct_change = get_pct_change(security, 250, n)
    pct_change = pct_change[~np.isnan(pct_change)]
    #log.debug(pct_change)
    maxd = pct_change.min()
    #maxd = pct[pct<0].min()
    avgd = pct_change.mean()
    #avgd = pct[pct<0].mean()
    #log.debug("maxd %f, avgd %f" % (maxd, avgd))
    # maxd��avgd����Ϊ������ʾ���ʱ����һֱ�������������¹�
    bstd = (maxd + avgd) / 2

    # ���ݲ���ʱ�������bstdΪnan
    if not isnan(bstd):
        if bstd != 0:
            return abs(bstd)
        else:
            # bstd = 0���� maxd <= 0
            if maxd < 0:
                # ��ʱȡ������
                return abs(maxd)
    return 0.099 # Ĭ�����ûز�ֹ����ֵ������Ϊ-9.9%����ֵ��ò�ƻس�����
    
# ��ȡ����ǰn���m������ֵ����
# ���ӻ�����⵱�ն�λ�ȡ����
def get_pct_change(security, n, m):
    pct_change = None
    if security in g.pct_change.keys():
        pct_change = g.pct_change[security]
    else:
        h = attribute_history(security, n, unit=g.primary_level, fields=('close'), skip_paused=True, df=True)
        pct_change = h['close'].pct_change(m) # 3�յİٷֱȱ�ȣ���3���ǵ�����
        g.pct_change[security] = pct_change
    return pct_change