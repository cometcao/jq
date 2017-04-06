import talib
import numpy as np
import pandas as pd
import math

'''
���ں��꽻�׷���Ļ��Ͷ�ʲ���
'''

def set_options(context):
    #��ѡ����
    g.update_atr_interval=5 #����ATR��ͷ���ģʱ��������λ���죩
    g.break_in=20 #����������20�����
    g.break_out=10 #�˳�������10�����
    g.k_type='1d' #�ο�k������  ʹ��ʱK����С����(��������)����K��K���������
    g.add_position_N_Multiple=0.5 #�Ӳֲ�����ÿ��1/2�������Ӳ�һ��ͷ��
    g.stock_position_uplimit=4 #����Ʊ�����ж��ٸ�ͷ��
    g.clear_position_N_Multiple=2 #ֹ���������µ�2����������ƽ��
    g.unit_volatility=0.04  #��λ���ٷֱ� Ĭ��Ϊ1 �������1Unit��λ���ʲ����������ʹ�����ʲ��ı仯������1%, ������ɢ��Ͷ�ʿɽ������沨���ͻس�
    g.max_position_size=200 #�����й�Ʊ�� ע�⣺���и����Ʊ��ʹͶ�ʸ���ɢ
    g.delay_buy_interval=24*60 #���ͻ��ά���˶���ʱ�������  ��ֹ��ͻ��
    g.delay_sell_interval=60 #�������ά���˶���ʱ�������  ��ֹ�ٵ���
    g.add_positions_interval=50 #����������ϵͳ�����̶ȣ�ֵԽ��Խ�Ƚ���ԽСԽ�������Ӳֵ���Сʱ����(��λ������), ���ýϴ��ֵ���Ա����ʱ�����֣��ɱ��������������ڲ������������ơ� (���ֺͼӲֶ�ͬ�ȶԴ�)
    g.clear_positions_interval=15 #����������ϵͳ�����̶ȣ�ֵԽСԽ�Ƚ���Խ��Խ���������һ����Ʊ����Сʱ����(��λ������)�����ýϴ��ֵ���Ա����ʱ�����ȫ��Ʊ���ɱ��������� (ƽ�ֺ�ֹ��ͬ�ȶԴ�)
    g.handle_data_interval=15 #ÿ�����ִ��һ��handle_data����߻ز�Ч��
    
    #������
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
    
    #���ÿ�ѡ����
    set_options(context)
    
    #����Ҫ���ã������ڲ���
    g.preselect_stocks=[] #ÿ���������¹�Ʊ�б���Ϊ��ѡ���
    g.stocks_atr_possize=None #ÿ��������±�ѡ�б�ͳ��й�Ʊ�б��ATR��ͷ���ģ
    g.update_atr_counter=0 #������
    g.handle_data_counter=0 #������
    g.stock_last_price={} #��Ʊ������Ӳּ۸�
    g.sell_tomorrow=[] #��Ҫ���������Ĺ�Ʊ����ΪT+1����,�����򶳽��޷�������
    g.init_portfolio_value=0 #����ľ�ֵ�����ڼ��㵱�յľ�ֵ�ǵ���
    run_daily(sell_stock,time='9:30')#��������û����ȥ��Ʊ
    g.delay_buy_list={} #���ڹ����б�
    g.delay_sell_list={} #���������б�
    g.success_num=0 #ӯ������
    g.failure_num=0 #�������
    g.stock_last_buytime=context.current_dt-datetime.timedelta(365) #��Ʊ���������ʱ�䣬���ڿ��ƼӲ�ʱ���� (�������ֺͼӲ��������)
    g.stock_last_selltime=context.current_dt-datetime.timedelta(365) #��Ʊ���������ƽ���źŵ�ʱ��
    
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
                print '------------��������û����ȥ��Ʊ{}���ѳɽ�{}�ɡ�'.format(s, od.filled)
        g.sell_tomorrow=[]
        print '------------�����������б�����ա�'
             
#ÿ��������
def handle_data(context, data): 
    if g.handle_data_counter%g.handle_data_interval==0:
        #����ǰ�ֲ�(�����Ӳ֣�ֹ��ƽ��)
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
                if current_price-g.stock_last_price[current_stock]>=c_atr*g.add_position_N_Multiple: #�Ӳ�
                    g.stock_last_price[current_stock]=current_price
                    if context.portfolio.positions[current_stock].total_amount<g.stock_position_uplimit*c_posize:
                        elapsedMins = ((context.current_dt - g.stock_last_buytime).total_seconds())/60
                        if elapsedMins>g.add_positions_interval:
                            print '------------{}����Ӳ�������׼���Ӳ֡������ϴμӲ��ѹ�ȥ{}���ӡ�'.format(current_stock,elapsedMins)
                            od=order(current_stock, c_posize)
                            if od!=None:
                                g.stock_last_buytime=context.current_dt
                                print '------------{}�Ӳֳɹ�������{}�ɣ��۸�{}��'.format(current_stock,od.filled,od.price)
                            else:
                                print '------------{}�Ӳ�ʧ�ܡ����{}��'.format(current_stock,context.portfolio.cash)
                        else:
                            print '------------{}��ʱ����̫�̣�������Ӳ֡�'.format(current_stock)
                    else:
                        print '------------{}�ﵽͷ�����ޣ�������Ӳ֡�'.format(current_stock)                        
                        
                if g.stock_last_price[current_stock]-current_price>=c_atr*g.clear_position_N_Multiple: #����ֹ������
                    if current_stock not in g.delay_sell_list.keys():
                        print '------------{}�ѵ���ֹ��λ��׼��{}���Ӻ�������'.format(current_stock,g.delay_sell_interval)
                        g.delay_sell_list[current_stock]={'breaktime':context.current_dt,'breakprice':current_price}

                if current_price<min10: #����ƽ������
                    if current_stock not in g.delay_sell_list.keys():
                        print '------------{}�ѵ���ǰN����͵㣬׼��{}���Ӻ�������'.format(current_stock,g.delay_sell_interval)
                        g.delay_sell_list[current_stock]={'breaktime':context.current_dt,'breakprice':current_price}
                        
        #����
        sz50_diff=attribute_history('000016.XSHG', 1, '1m', ('close'), True)['close'][0]-attribute_history('000016.XSHG', 20, '1d', ('close'), True)['close'][0] #��֤50�Ĵ�������
        cybz_diff=attribute_history('399006.XSHE', 1, '1m', ('close'), True)['close'][0]-attribute_history('399006.XSHE', 20, '1d', ('close'), True)['close'][0] #��ҵ��ָ�Ĵ�������
        if sz50_diff>0 and cybz_diff>0: #���ּ����˴����ֶ���ʱ
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
                                print '------------{}����λ��׼��{}���Ӻ����롣'.format(current_stock,g.delay_buy_interval)
                                g.delay_buy_list[current_stock]={'breaktime':context.current_dt,'breakprice':current_price,'psize':g.stocks_atr_possize[g.stocks_atr_possize.index==current_stock]['PSIZE'][-1]}
                            
        #�����ӳ������б�
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
                        print '------------{}׼��ƽ�֡�'.format(current_stock)
                        avg_cost=context.portfolio.positions[current_stock].avg_cost
                        od=order(current_stock, -context.portfolio.positions[current_stock].sellable_amount)
                        g.stock_last_selltime=context.current_dt
                        if od!=None:
                            if od.price>avg_cost:
                                g.success_num+=1
                            else:
                                g.failure_num+=1
                            print '------------{}ƽ�ֳɹ�(���ܲ������)������{}�ɣ��۸�{}��'.format(current_stock,od.filled,od.price)
                        else:
                            print '------------{}ƽ��ʧ�ܡ��Ѷ���{}�ɡ�'.format(current_stock,context.portfolio.positions[current_stock].total_amount-context.portfolio.positions[current_stock].sellable_amount)
                            
                        #���մ�����Ĺ�Ʊ
                        if context.portfolio.positions[current_stock].sellable_amount<context.portfolio.positions[current_stock].total_amount:
                            print '------------{}������Ϊ����������'.format(current_stock)
                            g.sell_tomorrow.append(current_stock)
                    else:
                        print '------------{}�۸����ǹ�ƽ�ּۡ�ȡ��ƽ�ֲ�����'.format(current_stock)    
                else:
                    print '------------{}��ʱ����̫�̣�������ƽ�֡�'.format(current_stock)
        for current_stock in processed:
            print '------------{}�Ѵ����������б�ɾ����'.format(current_stock)
            g.delay_sell_list.pop(current_stock, None)
                        
        #�����ӳٹ����б�
        processed=[]
        for current_stock in g.delay_buy_list.keys():
            breaktime=g.delay_buy_list[current_stock]['breaktime']
            breakprice=g.delay_buy_list[current_stock]['breakprice']
            psize=g.delay_buy_list[current_stock]['psize']
            elapsed_min=((context.current_dt-breaktime).total_seconds())/60
            if elapsed_min>g.delay_buy_interval*4:
                print '------------{}���ӳٹ����б����ѹ��ڡ�׼��ɾ����'.format(current_stock)
                processed.append(current_stock)
            elif elapsed_min>g.delay_buy_interval:
                elapsedMins = ((context.current_dt - g.stock_last_buytime).total_seconds())/60
                if elapsedMins>g.add_positions_interval:
                    processed.append(current_stock)
                    current_price=attribute_history(current_stock, 1, '1m', ('close'))['close'].values[-1]
                    if current_price>=breakprice:
                        print '------------{}׼�����֡������ϴμӲ��ѹ�ȥ{}���ӡ�'.format(current_stock,elapsedMins)
                        od=order(current_stock, psize)
                        if od!=None:
                            g.stock_last_price[current_stock]=od.price
                            g.stock_last_buytime=context.current_dt
                            print '------------{}���ֳɹ�������{}�ɣ��۸�{}��'.format(current_stock,od.filled,od.price)
                        else:
                            print '------------{}����ʧ�ܡ����{}��'.format(current_stock,context.portfolio.cash)
                    else:
                        print '------------{}�۸��ѵ�����λ�ۡ�ȡ�����ֲ�����'.format(current_stock)
                else:
                    print '------------{}��ʱ����̫�̣��������֡�'.format(current_stock)
        for current_stock in processed:
            print '------------{}�Ѵ����ڹ����б�ɾ����'.format(current_stock)
            g.delay_buy_list.pop(current_stock, None)
            
    g.handle_data_counter+=1
    
def before_trading_start(context):
    #���ÿ�ѡ����
    print '------------{} �����ÿ�ѡ������'.format(context.current_dt)
    set_options(context)
    
    if g.update_atr_counter%g.update_atr_interval==0:
        g.preselect_stocks=[]
        
        #��ȡ��С��ֵ��Ʊ
        print '------------��ʼ����С��ֵ��Ʊ...'
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
        
        #��ȡ������
        print '------------��ʼ�����������Ʊ...'
        target_stocks = get_index_stocks('000016.XSHG')
        target_stocks = target_stocks[:20]        
        g.preselect_stocks.extend(target_stocks)

        #�Զ���ETF
        target_stocks=[ '159934.XSHE', #�ƽ�etf
                        '518880.XSHG', #�ƽ�etf
                        '513100.XSHG', #��ָetf
                        '159941.XSHE', #��ָetf
                        '159920.XSHE', #����etf
                        '159929.XSHE', #ҽҩetf
                        '159931.XSHE', #����etf
                        '513500.XSHG', #����500
                        '513030.XSHG', #�¹�30etf
                        '513600.XSHG', #�Ϸ�����etf
                        ]
        g.preselect_stocks.extend(target_stocks)

        #�Զ����Ʊ  ��ƱӦ��ѡ�񲨶����Ʊ���ɽ����ʽ�������������ʽ�������
        target_stocks=[ '300024.XSHE', #������
                        '002185.XSHE', #����Ƽ�
                        '300465.XSHE', #��ΰ��
                        ]
        g.preselect_stocks.extend(target_stocks)
        
        #ȥ���ظ���
        templist=g.preselect_stocks
        g.preselect_stocks=[]
        for tli in templist:
            if tli not in g.preselect_stocks:
                g.preselect_stocks.append(tli)
                
                
        print '------------Ԥѡ�б�������(��{}��)����ʼ����ATR,ͷ���ģ...'.format(len(g.preselect_stocks))
        
        #����Ԥѡ�б������б��ATR��ͷ���ģ
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
                print '------------��ȡATR�����쳣: {}'.format(e)
                atr=[NaN]
            position_size=math.floor((context.portfolio.portfolio_value*g.unit_volatility*0.01)/(atr[-1]*100))*100
            tcodes.append(ts)
            tATR.append(atr[-1])
            tPS.append(position_size)
        
        #��������б�ATR��ͷ���ģ
        for current_stock in context.portfolio.positions.keys():
            ah=attribute_history(current_stock, 100, unit='1d',fields=['close', 'high', 'low'])
            atr=None
            try:
                atr=talib.ATR(ah['high'].values,ah['low'].values,ah['close'].values, timeperiod=20)
            except Exception,e:
                print '------------��ȡATR�����쳣: {}'.format(e)
                atr=[NaN]
            position_size=math.floor((context.portfolio.portfolio_value*g.unit_volatility*0.01)/(atr[-1]*100))*100
            tcodes.append(current_stock)
            tATR.append(atr[-1])
            tPS.append(position_size)
        
        #����ATR,ͷ���ģ ���ݱ�
        g.stocks_atr_possize=pd.DataFrame({'ATR':tATR,'PSIZE':tPS},index=tcodes)
        print '------------���º��ATR��ͷ���ģ���ݱ�:{}'.format(g.stocks_atr_possize)
        
    g.update_atr_counter+=1
    g.init_portfolio_value=context.portfolio.portfolio_value
    
def after_trading_end(context):
    print '===============������Ϣ==================='
    print 'ʱ��:{}'.format(context.current_dt)
    print '�ֲ�:{}����Ʊ'.format(len(context.portfolio.positions.keys()))
    for cs in context.portfolio.positions.keys():
        print '{}��ƽ���ֲֳɱ�:{}Ԫÿ��'.format(cs,context.portfolio.positions[cs].avg_cost)
    print 'Ԥѡ�б�ATR��ͷ���ģ�ĸ�������{}/{}'.format((g.update_atr_counter-1)%g.update_atr_interval, g.update_atr_interval)
    print '�Ѷ��ᣨ�����޷�������������������:{}'.format(g.sell_tomorrow)
    print '�˻�Ŀǰ�����ֽ�{}Ԫ'.format(context.portfolio.cash)
    print '�˻�Ȩ�棺{}Ԫ'.format(context.portfolio.portfolio_value)
    if g.init_portfolio_value!=0:
        print '���վ�ֵ�仯:{:.2f}%'.format(  (context.portfolio.portfolio_value-g.init_portfolio_value)/g.init_portfolio_value*100  )
        print '���վ�ֵ�仯:{}Ԫ'.format(context.portfolio.portfolio_value-g.init_portfolio_value)
    else:
        print '�޷����㾻ֵ�仯 (����Ȩ��Ϊ��?)'
    if context.portfolio.portfolio_value>0:
        lyv=(context.portfolio.positions_value/context.portfolio.portfolio_value)*100
        print '�ʽ�������: {:.2f}%'.format(lyv)
        record(zhijin_liyonglv=lyv)
    print '��ǰ�Ĵ������б�{}'.format(len(g.delay_buy_list))
    print '��ǰ�Ĵ������б�{}'.format(len(g.delay_sell_list))
    if g.success_num+g.failure_num>0:
        sl=(float(g.success_num)/(g.success_num+g.failure_num))*100
        print 'Ŀǰϵͳʤ��Ϊ: {:.2f}% �ܽ��״�����{}��, �ɹ���{}��,  ʧ�ܣ�{}��'.format(sl,g.success_num+g.failure_num,g.success_num,g.failure_num)
        record(shenglv=sl)
    
def filter_black_list_stock(context, stock_list):
    return [s for s in stock_list if s not in g.blacklist]
        
def filter_paused_and_st_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list if not current_data[stock].paused and not current_data[stock].is_st 
        and 'ST' not in current_data[stock].name and '*' not in current_data[stock].name and '��' not in current_data[stock].name]
