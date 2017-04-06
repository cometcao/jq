import talib
import numpy as np
import pandas as pd
import math

'''
基于海龟交易法则的混合投资策略
'''

def set_options(context):
    #可选参数
    g.update_atr_interval=5 #更新ATR和头寸规模时间间隔（单位：天）
    g.break_in=20 #进入条件，20日最高
    g.break_out=10 #退出条件，10日最低
    g.k_type='1d' #参考k线类型  使用时K捕获小趋势(短期趋势)或日K周K捕获大趋势
    g.add_position_N_Multiple=0.5 #加仓步长，每涨1/2个波幅加仓一个头寸
    g.stock_position_uplimit=4 #单股票最多持有多少个头寸
    g.clear_position_N_Multiple=2 #止损条件，下跌2个波幅即刻平仓
    g.unit_volatility=0.04  #单位：百分比 默认为1 如果买入1Unit单位的资产，当天震幅使得总资产的变化不超过1%, 尽量分散化投资可降低收益波动和回撤
    g.max_position_size=200 #最多持有股票数 注意：持有更多股票可使投资更分散
    g.delay_buy_interval=24*60 #如果突破维持了多少时间才买入  防止假突破
    g.delay_sell_interval=60 #如果跌破维持了多少时间才卖出  防止假跌破
    g.add_positions_interval=50 #可用于配置系统激进程度，值越大越稳健，越小越激进。加仓的最小时间间隔(单位：分钟), 设置较大的值可以避免短时间满仓，可避免噪声，有利于捕获真正的趋势。 (建仓和加仓都同等对待)
    g.clear_positions_interval=15 #可用于配置系统激进程度，值越小越稳健，越大越激进。清仓一个股票的最小时间间隔(单位：分钟)。设置较大的值可以避免短时间清仓全部票，可避免噪声。 (平仓和止损都同等对待)
    g.handle_data_interval=15 #每五分钟执行一次handle_data，提高回测效率
    
    #黑名单
    g.blacklist=["600656.XSHG","300372.XSHE","600403.XSHG","600421.XSHG","600733.XSHG","300399.XSHE",
                 "600145.XSHG","002679.XSHE","000020.XSHE","002330.XSHE","300117.XSHE","300135.XSHE",
                 "002566.XSHE","002119.XSHE","300208.XSHE","002237.XSHE","002608.XSHE","000691.XSHE",
                 "002694.XSHE","002715.XSHE","002211.XSHE","000788.XSHE","300380.XSHE","300028.XSHE",
                 "000668.XSHE","300033.XSHE","300126.XSHE","300340.XSHE","300344.XSHE","002473.XSHE"]

def initialize(context):
    log.set_level('order', 'error')
    set_commission(PerTrade(buy_cost=0.0003, sell_cost=0.0013, min_cost=5))
    set_benchmark('000001.XSHG')
    set_option('use_real_price', True)
    
    #设置可选参数
    set_options(context)
    
    #不需要设置，程序内部用
    g.preselect_stocks=[] #每过几天会更新股票列表，作为备选标的
    g.stocks_atr_possize=None #每隔几天更新备选列表和持有股票列表的ATR和头寸规模
    g.update_atr_counter=0 #计数器
    g.handle_data_counter=0 #计数器
    g.stock_last_price={} #股票的最近加仓价格
    g.sell_tomorrow=[] #需要明日卖出的股票（因为T+1限制,当日因冻结无法卖出）
    g.init_portfolio_value=0 #昨天的净值，便于计算当日的净值涨跌幅
    run_daily(sell_stock,time='9:30')#卖出昨天没卖出去的票
    g.delay_buy_list={} #延期购买列表
    g.delay_sell_list={} #延期卖出列表
    g.success_num=0 #盈利次数
    g.failure_num=0 #亏损次数
    g.stock_last_buytime=context.current_dt-datetime.timedelta(365) #股票的最近买入时间，用于控制加仓时间间隔 (包括建仓和加仓两种情况)
    g.stock_last_selltime=context.current_dt-datetime.timedelta(365) #股票的最近处理平仓信号的时间
    
def sell_stock(context):
    stocks=list(set(g.sell_tomorrow))
    if len(stocks)>0:
        for s in stocks:
            avg_cost=context.portfolio.positions[s].avg_cost
            od=order_target(s, 0)
            if od!=None:
                if od.price>avg_cost:
                    g.success_num+=1
                else:
                    g.failure_num+=1
                print '------------卖出昨天没卖出去的票{}，已成交{}股。'.format(s, od.filled)
        g.sell_tomorrow=[]
        print '------------【明日卖出列表】已清空。'
             
#每分钟运行
def handle_data(context, data): 
    if g.handle_data_counter%g.handle_data_interval==0:
        #处理当前持仓(包括加仓，止损，平仓)
        for current_stock in context.portfolio.positions.keys():
            df=None
            if 'm' in g.k_type:
                df=get_price(current_stock, start_date=None, end_date=context.current_dt-datetime.timedelta(minutes=2), frequency=g.k_type, fields=('open', 'close', 'high', 'low'), skip_paused=True, fq='pre', count=100)
            else:
                df=get_price(current_stock, start_date=None, end_date=context.current_dt-datetime.timedelta(days=1), frequency=g.k_type, fields=('open', 'close', 'high', 'low'), skip_paused=True, fq='pre', count=100)
            open=df['open'].values
            close=df['close'].values
            high=df['high'].values
            low=df['low'].values
            current_price=attribute_history(current_stock, 1, '1m', ('close'))['close'].values[-1]        
            high20=max(high[-g.break_in:])
            min10=min(low[-g.break_out:])        
            if context.portfolio.positions[current_stock].total_amount>0:
                c_atr= g.stocks_atr_possize[g.stocks_atr_possize.index==current_stock]['ATR'][-1]
                c_posize=g.stocks_atr_possize[g.stocks_atr_possize.index==current_stock]['PSIZE'][-1]
                if current_price-g.stock_last_price[current_stock]>=c_atr*g.add_position_N_Multiple: #加仓
                    g.stock_last_price[current_stock]=current_price
                    if context.portfolio.positions[current_stock].total_amount<g.stock_position_uplimit*c_posize:
                        elapsedMins = ((context.current_dt - g.stock_last_buytime).total_seconds())/60
                        if elapsedMins>g.add_positions_interval:
                            print '------------{}满足加仓条件。准备加仓。距离上次加仓已过去{}分钟。'.format(current_stock,elapsedMins)
                            od=order(current_stock, c_posize)
                            if od!=None:
                                g.stock_last_buytime=context.current_dt
                                print '------------{}加仓成功。买入{}股，价格{}。'.format(current_stock,od.filled,od.price)
                            else:
                                print '------------{}加仓失败。余额{}。'.format(current_stock,context.portfolio.cash)
                        else:
                            print '------------{}因时间间隔太短，不允许加仓。'.format(current_stock)
                    else:
                        print '------------{}达到头寸上限，不允许加仓。'.format(current_stock)                        
                        
                if g.stock_last_price[current_stock]-current_price>=c_atr*g.clear_position_N_Multiple: #满足止损条件
                    if current_stock not in g.delay_sell_list.keys():
                        print '------------{}已跌破止损位，准备{}分钟后卖出。'.format(current_stock,g.delay_sell_interval)
                        g.delay_sell_list[current_stock]={'breaktime':context.current_dt,'breakprice':current_price}

                if current_price<min10: #满足平仓条件
                    if current_stock not in g.delay_sell_list.keys():
                        print '------------{}已跌破前N日最低点，准备{}分钟后卖出。'.format(current_stock,g.delay_sell_interval)
                        g.delay_sell_list[current_stock]={'breaktime':context.current_dt,'breakprice':current_price}
                        
        #建仓
        sz50_diff=attribute_history('000016.XSHG', 1, '1m', ('close'), True)['close'][0]-attribute_history('000016.XSHG', 20, '1d', ('close'), True)['close'][0] #中证50的大致走势
        cybz_diff=attribute_history('399006.XSHE', 1, '1m', ('close'), True)['close'][0]-attribute_history('399006.XSHE', 20, '1d', ('close'), True)['close'][0] #创业板指的大致走势
        if sz50_diff>0 and cybz_diff>0: #建仓加入了大盘轮动择时
            for current_stock in g.preselect_stocks:
                df=None
                if 'm' in g.k_type:
                    df=get_price(current_stock, start_date=None, end_date=context.current_dt-datetime.timedelta(minutes=2), frequency=g.k_type, fields=('open', 'close', 'high', 'low'), skip_paused=True, fq='pre', count=100)
                else:
                    df=get_price(current_stock, start_date=None, end_date=context.current_dt-datetime.timedelta(days=1), frequency=g.k_type, fields=('open', 'close', 'high', 'low'), skip_paused=True, fq='pre', count=100)
                open=df['open'].values
                close=df['close'].values
                high=df['high'].values
                low=df['low'].values
                current_price=attribute_history(current_stock, 1, '1m', ('close'))['close'].values[-1]        
                high20=max(high[-g.break_in:])
                min10=min(low[-g.break_out:])
                if context.portfolio.positions[current_stock].total_amount==0:
                    if len(context.portfolio.positions)<g.max_position_size:
                        if current_price>high20:
                            if current_stock not in g.delay_buy_list.keys():
                                print '------------{}已破位，准备{}分钟后买入。'.format(current_stock,g.delay_buy_interval)
                                g.delay_buy_list[current_stock]={'breaktime':context.current_dt,'breakprice':current_price,'psize':g.stocks_atr_possize[g.stocks_atr_possize.index==current_stock]['PSIZE'][-1]}
                            
        #处理延迟卖出列表
        processed=[]
        for current_stock in g.delay_sell_list.keys():
            breaktime=g.delay_sell_list[current_stock]['breaktime']
            breakprice=g.delay_sell_list[current_stock]['breakprice']
            elapsed_min=((context.current_dt-breaktime).total_seconds())/60
            if elapsed_min>g.delay_sell_interval:
                elapsedMins = ((context.current_dt - g.stock_last_selltime).total_seconds())/60
                if elapsedMins>g.clear_positions_interval:
                    processed.append(current_stock)
                    current_price=attribute_history(current_stock, 1, '1m', ('close'))['close'].values[-1]
                    if current_price<=breakprice:
                        print '------------{}准备平仓。'.format(current_stock)
                        avg_cost=context.portfolio.positions[current_stock].avg_cost
                        od=order(current_stock, -context.portfolio.positions[current_stock].sellable_amount)
                        g.stock_last_selltime=context.current_dt
                        if od!=None:
                            if od.price>avg_cost:
                                g.success_num+=1
                            else:
                                g.failure_num+=1
                            print '------------{}平仓成功(可能部分完成)。卖出{}股，价格{}。'.format(current_stock,od.filled,od.price)
                        else:
                            print '------------{}平仓失败。已冻结{}股。'.format(current_stock,context.portfolio.positions[current_stock].total_amount-context.portfolio.positions[current_stock].sellable_amount)
                            
                        #明日处理冻结的股票
                        if context.portfolio.positions[current_stock].sellable_amount<context.portfolio.positions[current_stock].total_amount:
                            print '------------{}已设置为明日卖出。'.format(current_stock)
                            g.sell_tomorrow.append(current_stock)
                    else:
                        print '------------{}价格已涨过平仓价。取消平仓操作。'.format(current_stock)    
                else:
                    print '------------{}因时间间隔太短，不允许平仓。'.format(current_stock)
        for current_stock in processed:
            print '------------{}已从延期卖出列表删除。'.format(current_stock)
            g.delay_sell_list.pop(current_stock, None)
                        
        #处理延迟购买列表
        processed=[]
        for current_stock in g.delay_buy_list.keys():
            breaktime=g.delay_buy_list[current_stock]['breaktime']
            breakprice=g.delay_buy_list[current_stock]['breakprice']
            psize=g.delay_buy_list[current_stock]['psize']
            elapsed_min=((context.current_dt-breaktime).total_seconds())/60
            if elapsed_min>g.delay_buy_interval*4:
                print '------------{}在延迟购买列表中已过期。准备删除。'.format(current_stock)
                processed.append(current_stock)
            elif elapsed_min>g.delay_buy_interval:
                elapsedMins = ((context.current_dt - g.stock_last_buytime).total_seconds())/60
                if elapsedMins>g.add_positions_interval:
                    processed.append(current_stock)
                    current_price=attribute_history(current_stock, 1, '1m', ('close'))['close'].values[-1]
                    if current_price>=breakprice:
                        print '------------{}准备建仓。距离上次加仓已过去{}分钟。'.format(current_stock,elapsedMins)
                        od=order(current_stock, psize)
                        if od!=None:
                            g.stock_last_price[current_stock]=od.price
                            g.stock_last_buytime=context.current_dt
                            print '------------{}建仓成功。买入{}股，价格{}。'.format(current_stock,od.filled,od.price)
                        else:
                            print '------------{}建仓失败。余额{}。'.format(current_stock,context.portfolio.cash)
                    else:
                        print '------------{}价格已跌破破位价。取消建仓操作。'.format(current_stock)
                else:
                    print '------------{}因时间间隔太短，不允许建仓。'.format(current_stock)
        for current_stock in processed:
            print '------------{}已从延期购买列表删除。'.format(current_stock)
            g.delay_buy_list.pop(current_stock, None)
            
    g.handle_data_counter+=1
    
def before_trading_start(context):
    #重置可选参数
    print '------------{} 已重置可选参数。'.format(context.current_dt)
    set_options(context)
    
    if g.update_atr_counter%g.update_atr_interval==0:
        g.preselect_stocks=[]
        
        #获取最小市值股票
        print '------------开始搜索小市值股票...'
        q=query(valuation.code, valuation.market_cap)
        q=q.filter(valuation.pe_ratio >= 0)
        q=q.filter(valuation.pb_ratio >= 0)
        q=q.order_by(valuation.market_cap.asc())
        q=q.limit(100)
        df = get_fundamentals(q)    
        target_stocks = list(df['code'])
        target_stocks = filter_black_list_stock(context, target_stocks)
        target_stocks = filter_paused_and_st_stock(target_stocks)
        target_stocks = target_stocks[:30]        
        g.preselect_stocks.extend(target_stocks)
        
        #获取大蓝筹
        print '------------开始搜索大蓝筹股票...'
        target_stocks = get_index_stocks('000016.XSHG')
        target_stocks = target_stocks[:20]        
        g.preselect_stocks.extend(target_stocks)

        #自定义ETF
        target_stocks=[ '159934.XSHE', #黄金etf
                        '518880.XSHG', #黄金etf
                        '513100.XSHG', #纳指etf
                        '159941.XSHE', #纳指etf
                        '159920.XSHE', #恒生etf
                        '159929.XSHE', #医药etf
                        '159931.XSHE', #金融etf
                        '513500.XSHG', #标普500
                        '513030.XSHG', #德国30etf
                        '513600.XSHG', #南方恒生etf
                        ]
        g.preselect_stocks.extend(target_stocks)

        #自定义股票  股票应该选择波动大的票。可降低资金利用量，提高资金利用率
        target_stocks=[ '300024.XSHE', #机器人
                        '002185.XSHE', #华天科技
                        '300465.XSHE', #高伟达
                        ]
        g.preselect_stocks.extend(target_stocks)
        
        #去掉重复的
        templist=g.preselect_stocks
        g.preselect_stocks=[]
        for tli in templist:
            if tli not in g.preselect_stocks:
                g.preselect_stocks.append(tli)
                
                
        print '------------预选列表更新完成(共{}个)。开始计算ATR,头寸规模...'.format(len(g.preselect_stocks))
        
        #计算预选列表，待购列表的ATR和头寸规模
        mergelist=g.preselect_stocks+g.delay_buy_list.keys()+g.delay_sell_list.keys()
        tcodes=[]
        tATR=[]
        tPS=[]
        for ts in mergelist:
            ah=attribute_history(ts, 100, unit='1d',fields=['close', 'high', 'low'])
            atr=None
            try:
                atr=talib.ATR(ah['high'].values,ah['low'].values,ah['close'].values, timeperiod=20)
            except Exception,e:
                print '------------获取ATR发生异常: {}'.format(e)
                atr=[NaN]
            position_size=math.floor((context.portfolio.portfolio_value*g.unit_volatility*0.01)/(atr[-1]*100))*100
            tcodes.append(ts)
            tATR.append(atr[-1])
            tPS.append(position_size)
        
        #计算持有列表ATR和头寸规模
        for current_stock in context.portfolio.positions.keys():
            ah=attribute_history(current_stock, 100, unit='1d',fields=['close', 'high', 'low'])
            atr=None
            try:
                atr=talib.ATR(ah['high'].values,ah['low'].values,ah['close'].values, timeperiod=20)
            except Exception,e:
                print '------------获取ATR发生异常: {}'.format(e)
                atr=[NaN]
            position_size=math.floor((context.portfolio.portfolio_value*g.unit_volatility*0.01)/(atr[-1]*100))*100
            tcodes.append(current_stock)
            tATR.append(atr[-1])
            tPS.append(position_size)
        
        #保存ATR,头寸规模 数据表
        g.stocks_atr_possize=pd.DataFrame({'ATR':tATR,'PSIZE':tPS},index=tcodes)
        print '------------更新后的ATR，头寸规模数据表:{}'.format(g.stocks_atr_possize)
        
    g.update_atr_counter+=1
    g.init_portfolio_value=context.portfolio.portfolio_value
    
def after_trading_end(context):
    print '===============今日信息==================='
    print '时间:{}'.format(context.current_dt)
    print '持仓:{}个股票'.format(len(context.portfolio.positions.keys()))
    for cs in context.portfolio.positions.keys():
        print '{}的平均持仓成本:{}元每股'.format(cs,context.portfolio.positions[cs].avg_cost)
    print '预选列表，ATR，头寸规模的更新周期{}/{}'.format((g.update_atr_counter-1)%g.update_atr_interval, g.update_atr_interval)
    print '已冻结（今天无法卖出明天早上再卖）:{}'.format(g.sell_tomorrow)
    print '账户目前持有现金：{}元'.format(context.portfolio.cash)
    print '账户权益：{}元'.format(context.portfolio.portfolio_value)
    if g.init_portfolio_value!=0:
        print '当日净值变化:{:.2f}%'.format(  (context.portfolio.portfolio_value-g.init_portfolio_value)/g.init_portfolio_value*100  )
        print '当日净值变化:{}元'.format(context.portfolio.portfolio_value-g.init_portfolio_value)
    else:
        print '无法计算净值变化 (昨日权益为零?)'
    if context.portfolio.portfolio_value>0:
        lyv=(context.portfolio.positions_value/context.portfolio.portfolio_value)*100
        print '资金利用率: {:.2f}%'.format(lyv)
        record(zhijin_liyonglv=lyv)
    print '当前的待购入列表：{}'.format(len(g.delay_buy_list))
    print '当前的待卖出列表：{}'.format(len(g.delay_sell_list))
    if g.success_num+g.failure_num>0:
        sl=(float(g.success_num)/(g.success_num+g.failure_num))*100
        print '目前系统胜率为: {:.2f}% 总交易次数：{}次, 成功：{}次,  失败：{}次'.format(sl,g.success_num+g.failure_num,g.success_num,g.failure_num)
        record(shenglv=sl)
    
def filter_black_list_stock(context, stock_list):
    return [s for s in stock_list if s not in g.blacklist]
        
def filter_paused_and_st_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list if not current_data[stock].paused and not current_data[stock].is_st 
        and 'ST' not in current_data[stock].name and '*' not in current_data[stock].name and '退' not in current_data[stock].name]
