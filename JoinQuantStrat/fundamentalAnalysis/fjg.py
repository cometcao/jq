fja5 = [
    u'150008.XSHE', u'150018.XSHE', u'150030.XSHE', u'150051.XSHE', u'150076.XSHE',
    u'150083.XSHE', u'150085.XSHE', u'150088.XSHE', u'150090.XSHE', u'150092.XSHE', 
    u'150094.XSHE', u'150100.XSHE', u'150104.XSHE', u'150106.XSHE', u'150108.XSHE', 
    u'150112.XSHE', u'150117.XSHE', u'150121.XSHE', u'150123.XSHE', u'150130.XSHE', 
    u'150135.XSHE', u'150140.XSHE', u'150145.XSHE', u'150148.XSHE', u'150150.XSHE', 
    u'150152.XSHE', u'150157.XSHE', u'150171.XSHE', u'150173.XSHE', u'150177.XSHE', 
    u'150179.XSHE', u'150181.XSHE', u'150184.XSHE', u'150186.XSHE', u'150190.XSHE', 
    u'150192.XSHE', u'150194.XSHE', u'150196.XSHE', u'150198.XSHE', u'150203.XSHE', 
    u'150205.XSHE', u'150207.XSHE', u'150209.XSHE', u'150213.XSHE', u'150215.XSHE', 
    u'150217.XSHE', u'150221.XSHE', u'150225.XSHE', u'150227.XSHE', u'150241.XSHE', 
    u'150247.XSHE', u'150249.XSHE', u'150255.XSHE', u'150267.XSHE', u'150271.XSHE', 
    u'150291.XSHE', u'150295.XSHE', u'150299.XSHE', u'502001.XSHG', u'502004.XSHG', 
    u'502007.XSHG', u'502011.XSHG', u'502014.XSHG', u'502021.XSHG', u'502024.XSHG', 
    u'502027.XSHG', u'502031.XSHG', u'502037.XSHG', u'502041.XSHG', u'502049.XSHG', 
    u'502054.XSHG', u'502057.XSHG']

def initialize(context):
    set_universe([])
    g.riskbench = '000300.XSHG'
   
    # 设置手续费，买入时万分之三，卖出时万分之三加千分之一印花税, 每笔交易最低扣5块钱
    set_commission(PerTrade(buy_cost=0.0008, sell_cost=0.0013, min_cost=5))
    set_option('use_real_price', True)
    # 设置基准对比为沪深300指数
    
    # 初始化当日买卖列表
    g.stock_buy = []
    g.stock_sell = []
    g.stock_hold = []
    g.stock_clear = []
    g.choice_num = 8
    
    g.run_type = 0
    #run_daily(handle_daily, time='09:30')
    run_daily(handle_daily, time='10:00')
    run_daily(handle_daily, time='10:30')
    run_daily(handle_daily, time='11:00')
    run_daily(handle_daily, time='13:30')
    run_daily(handle_daily, time='14:30')
    run_daily(handle_daily, time='14:30')


def select_fja(stocks,context):
    date = g.d_yesterday
    #dt_end = datetime.datetime.strptime(date, "%Y-%m-%d").date()
    #begin = (dt_end  - timedelta(14)).strftime("%Y-%m-%d")
    df = get_extras('unit_net_value', stocks, end_date=date, df=True, count=1).T
    df.columns=['net_price']
    df['price']=0.0
    
    for code in df.index:
        dfs = attribute_history(code,1,'1m',('close'))
        price = dfs['close'][-1]
        if price == g.current_data[code].low_limit:
            price = g.current_data[code].high_limit
        #print dfs
        df['price'][code] = price
    df['score'] = df['price'] / df['net_price']
    g.stock_order =df.sort(columns='score',ascending=True)
    #print g.stock_order[:5]
    #g.stock_order = g.stock_order[ g.stock_order['score']<0.95 ]
    g.stock_buy = list(g.stock_order.index[:g.choice_num])
    #print g.stock_order[:5]

def if_change():
    log.debug("if_change : stock_buy:%s stock_sell:%s"%(str(g.stock_buy),str(g.stock_sell)))
    inter = 0.01
    sell_order = g.stock_order[ g.stock_order.index.isin(g.stock_sell) ]
    buy_order = g.stock_order[ g.stock_order.index.isin(g.stock_buy) ]
    max_len = min(len(buy_order),len(sell_order))
    for i in range(0,max_len):
        if (sell_order['score'][i] - buy_order['score'][-i-1])/buy_order['score'][-i-1] < inter :
            g.stock_buy.remove(buy_order.index[-i-1])
            g.stock_sell.remove(sell_order.index[i])
        else:
            break
        
    if len(g.stock_sell) > 2:
        g.stock_sell = []
        g.stock_sell.append(sell_order.index[-1])
        g.stock_sell.append(sell_order.index[-2])
        g.stock_buy = g.stock_buy[:2]
        
        
def compt_buy_sell(context):
    g.stock_buy = []
    g.stock_sell = []
    g.stock_hold = []
   
    select_fja(fja5,context)
    print "stock_buy:%s"%(str(g.stock_buy))
    holds = set(context.portfolio.positions.keys()) 
    
    g.stock_sell = holds - set(g.stock_buy)
    g.stock_buy = [ s for s in g.stock_buy if s not in holds ]
    g.stock_sell = [ s for s in g.stock_sell if (not g.current_data[s].paused) and \
        (g.current_data[s].day_open != g.current_data[s].high_limit) ]
    
    for code in context.portfolio.positions.keys():
        if context.portfolio.positions[code].closeable_amount == 0:
            if code in g.stock_sell:
                g.stock_sell.remove(code)
    
    max_len = g.choice_num - len(holds) + len(g.stock_sell)
    g.stock_buy = g.stock_buy[:max_len]
    
    if g.stock_sell and g.stock_buy:
        if_change()
        max_len = g.choice_num - len(holds) + len(g.stock_sell)
        g.stock_buy = g.stock_buy[:max_len]        

    g.stock_want_buy = g.stock_buy
    SendMessage("stock_buy:%s stock_sell:%s"%(str(g.stock_buy),str(g.stock_sell)))
    SendMessage()

def SendMessage(str=None):
    if str is None:
        if g.run_type == 2:
            send_message(g.msg)
            g.msg = ''
        return
    
    if g.run_type == 2:
        g.msg += str
        g.msg += '\n'
    log.info(str)
    
def before_trading_start(context):
    g.d_today = context.current_dt.strftime("%Y-%m-%d")
    g.d_yesterday = context.previous_date.strftime("%Y-%m-%d")
    
    g.current_data = get_current_data()
    log.info("------------------ " + g.d_today +" 交易开始 ------------------ ")
    g.stock_clear = set()

    #判断是否模拟盘：
    if g.run_type ==0 :
        if context.current_dt.date() == datetime.date.today():
            g.run_type = 2
            log.info("进入模拟盘")
        else:
            log.info("进入回测")
            g.run_type = 1
    g.is_stop = False
    

# 每个单位时间(如果按天回测,则每天调用一次,如果按分钟,则每分钟调用一次)调用一次
def handle_daily(context):
    compt_buy_sell(context)
    for code in g.stock_sell:
        order_target_value(code, 0)
            
    if g.stock_buy:
        cash = context.portfolio.portfolio_value * 1.1 / g.choice_num
        for code in g.stock_want_buy:
            order_target_value(code, cash)

    
    
