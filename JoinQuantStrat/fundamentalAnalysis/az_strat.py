#���Ը�������С��ֵ���ԸĽ��桷
#https://www.joinquant.com/post/2035?tag=new
#1.ѡ��eps>0�����й�Ʊ������ֵ��С��������ѡ��ǰ100֧��ѡ
#2.�޳���ҵ�壬ST,*,�ˣ�ͣ�Ƶȹ�Ʊ
#3.ѡ����ֵ��С��20ֻ��ǰ20ֻ����ѡ
#4.����ѡ��Ʊ����, ÿ������2��50��ִ�С�
#lowPrice130 = ǰ130������ͼ۸�
#highPrice130 = ǰ130������߼۸�
#avg15 = ǰ15�����
#currPrice = ��ǰ�۸�
#score = (currPrice-lowPrice130)+(currPrice-highPrice130)+(currPrice-avg15)
#5.����ѡ��Ʊ��score�÷֣���С��������ѡ����С��4֧�ֲ֡�
#6.�ֹ�3���ֻ������һ���ľͼ������У���һ���ľͻ�����
#7.����ֹ��ʹ����֤50������С��R ָ���������С��20��ǰ��101%������ղ�λ�����ס�


from sqlalchemy import desc
import numpy as np
import pandas as pd
from scipy import stats

def initialize(context):
    # �Աȱ��
    set_benchmark('000300.XSHG') 
    # ����Ӷ��
    set_commission(PerTrade(buy_cost=0.0003, sell_cost=0.0003, min_cost=5))
    g.stocks = []
    g.stockCount = 4
    g.buyStockCount = 10
    g.days = 0
    g.period = 3
    

def getStockPrice(stock, interval):
    h = attribute_history(stock, interval, unit='1d', fields=('close'), skip_paused=True)
    return h['close'].values[0]

def unpaused(stockspool):
    current_data=get_current_data()
    return [s for s in stockspool if not current_data[s].paused]    

#���˵���*����ST���Ʊ
def filterStarName(stock_list):
    curr_data = get_current_data()
    return  [stock for stock in stock_list if 'ST' not in curr_data[stock].name and
        '*' not in curr_data[stock].name and '��' not in curr_data[stock].name]

def sell_all_stocks(context):
    for stock in context.portfolio.positions.keys():
            order_target_value(stock, 0)
            print('Sell: ',stock)
    #�ܹؼ�����һ��д�����ʱ��û����һ�䣬�����������޷����롣
    g.days = 0          

def Multi_Select_Stocks(context, data):
    stocks = get_all_securities(['stock'])
    #�ų��¹�
    stocks = stocks[(context.current_dt.date() - stocks.start_date) > datetime.timedelta(60)].index
    #stocks  = stocks.index
    date=context.current_dt.strftime("%Y-%m-%d")
    st=get_extras('is_st', stocks, start_date=date, end_date=date, df=True)
    st=st.loc[date]
    stocks = list(st[st==False].index)
    stocks = unpaused(stocks)
    stocks = filterStarName(stocks)
    
    q = query(
        valuation.code,
        ).filter(
        valuation.pe_ratio > 0,
        valuation.code.in_(stocks)
    ).order_by(
        # ����ֵ��������
        valuation.market_cap.asc()
    ).limit(
        # ��෵��20��
        20
    )
    df = get_fundamentals(q)
    stocks = df.code.values
    
    stock_select={}
    for s in stocks:
        h = attribute_history(s, 130, unit='1d', fields=('close', 'high', 'low'), skip_paused=True)
        lowPrice130 = h.low.min()
        highPrice130 = h.high.max()
        avg15 = data[s].mavg(15)
        currPrice = data[s].close
        score = (currPrice-lowPrice130)+(currPrice-highPrice130)+(currPrice-avg15)
        stock_select[s] = score
        
    dfs = pd.DataFrame(stock_select.values(),index=stock_select.keys())
    dfs.columns=['score']
    dfs=dfs.sort(columns='score',ascending=True)
    return dfs.index[:g.stockCount]

# ÿ����λʱ��(�������ز�,��ÿ�����һ��,���������,��ÿ���ӵ���һ��)����һ��
def handle_data(context, data):
    # ��õ�ǰʱ��
    hour = context.current_dt.hour
    minute = context.current_dt.minute
    
    # ÿ������14:53����
    if hour ==14 and minute==50:
        lag = 20 # �ؿ�ǰ20��
        # ��õ�ǰ���ʲ�
        value = context.portfolio.portfolio_value
        
        zs2 =  '000016.XSHG' #��֤50ָ��
        zs8 =  '399006.XSHE' #��ҵ��ָ��
    
        hs2 = getStockPrice(zs2, lag)
        hs8 = getStockPrice(zs8, lag)
        cp2 = data[zs2].close
        cp8 = data[zs8].close
        
        if (not isnan(hs2)) and (not isnan(cp2)):
            ret2 = (cp2 - hs2) / hs2;
        else:
            ret2 = 0
        if (not isnan(hs8)) and (not isnan(cp8)):
            ret8 = (cp8 - hs8) / hs8;
        else:
            ret8 = 0
        #print(ret2,ret8)
        
        #��֣�����101%ʱ��֣��ز�Ч������úá�
        if ret2>0.01 or ret8>0.01 :   
            print('���У�ÿ3����е���')
            buy_stocks(context, data)
        else :
            print('���')
            sell_all_stocks(context)            

def buy_stocks(context, data):
    g.days += 1
    if g.days % g.period == 1:            
            
        buylist = Multi_Select_Stocks(context, data)
        
        #�ų���ͣ����ͣ��
        g.stocks = []
        for stock in buylist:
            if data[stock].low_limit < data[stock].close < data[stock].high_limit :
                g.stocks.append(stock)
            #�ѳ��е���ͣ�ɣ���������    
            elif (data[stock].close == data[stock].high_limit) and (stock in context.portfolio.positions.keys()):
                g.stocks.append(stock)
            if len(g.stocks)>=g.buyStockCount:
                break
        #print(g.stocks)
        set_universe(g.stocks)
        
        # close stock positions not in the current universe
        cntSuspension=0
        for stock in context.portfolio.positions.keys():
            if stock not in g.stocks:
                print('Rank Outof 10, Sell: ',stock)
                if order_target_value(stock, 0)==None :
                    cntSuspension +=1
        g.stocks = g.stocks[:len(g.stocks)-cntSuspension]
        
        valid_count = 0
        for stock in context.portfolio.positions.keys():
            if context.portfolio.positions[stock].total_amount > 0:
                valid_count = valid_count + 1
        # place equally weighted orders
        if len(g.stocks) == 0 or valid_count >= len(g.stocks):
            return
        
        for stock in g.stocks:
            order_target_value(stock, context.portfolio.portfolio_value/len(g.stocks))

