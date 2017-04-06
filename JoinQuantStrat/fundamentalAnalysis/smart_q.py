import pandas as pd
from six import StringIO

smartQFile=read_file("smartQ_test.csv")
smartQData=pd.read_csv(StringIO(smartQFile))
q_data = smartQData[smartQData.columns[0:]].set_index('tradeDate')
dates=q_data.index.values


def getDateStr(date):
    return date.strftime("%Y-%m-%d")
    
def initialize(context):
     #沪深300
    set_benchmark('000300.XSHG')
    # 如果您没有调用 set_slippage 函数, 系统默认的滑点是 PriceRelatedSlippage(0.00246)
    set_option('use_real_price', True)
    


# 每个单位时间(如果按天回测,则每天调用一次,如果按分钟,则每分钟调用一次)调用一次
def handle_data(context, data):
    if getDateStr(context.previous_date) not in dates:
        return
    
    q=q_data.ix[getDateStr(context.previous_date)]

    quantile_ten=1
    q_min = q.quantile((quantile_ten-1)*0.1)
    q_max = q.quantile(quantile_ten*0.1)
    # print q_min
    # print q_max
    my_univ = q[q>=q_min][q<q_max].index.values
    # print my_univ
    
    #卖出不在标的中的股票
    for stock in context.portfolio.positions.keys():
        if stock not in my_univ:
            order_target(stock,0)
    #买入股票
    amount=len(my_univ)
    if amount<= 0:
        return
    money=context.portfolio.available_cash/amount
    for stock in my_univ:
        order_value(stock,money)
        
    
    
    
    
    
    
    
    