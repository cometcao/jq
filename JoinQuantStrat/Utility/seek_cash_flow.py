'''
Created on 14 Jan 2017

@author: MetalInvest
'''
from kuanke.user_space_api import *

all_securities = get_index_stocks('000107.XSHG') \
                +get_index_stocks('000108.XSHG') \
                +get_index_stocks('000109.XSHG') \
                +get_index_stocks('000111.XSHG')

def fall_money_day_3line(security_list,n, n1=20, n2=60, n3=160):
    def fall_money_count(money, n, n1, n2, n3):
        i = 0
        count = 0
        while i < n:
            money_MA200 = money[i:n3-1+i].mean()
            money_MA60 = money[i+n3-n2:n3-1+i].mean()
            money_MA20 = money[i+n3-n1:n3-1+i].mean()
            if money_MA20 <= money_MA60 and money_MA60 <= money_MA200 :
                count = count + 1
            i = i + 1
        return count

    df = history(n+n3, unit='1d', field='money', security_list=security_list, skip_paused=True)
    s = df.apply(fall_money_count, args=(n,n1,n2,n3,))
    return s

def money_5_cross_60(security_list,n, n1=5, n2=60):
    def money_5_cross_60_count(money, n, n1, n2):
        i = 0
        count = 0
        while i < n :
            money_MA60 = money[i+1:n2+i].mean()
            money_MA60_before = money[i:n2-1+i].mean()
            money_MA5 = money[i+1+n2-n1:n2+i].mean()
            money_MA5_before = money[i+n2-n1:n2-1+i].mean()
            if (money_MA60_before-money_MA5_before)*(money_MA60-money_MA5) < 0 : 
                count=count+1
            i = i + 1
        return count

    df = history(n+n2+1, unit='1d', field='money', security_list=security_list, skip_paused=True)
    s = df.apply(money_5_cross_60_count, args=(n,n1,n2,))
    return s
    
def cow_stock_value(security_list, score_threthold = 20):
    df = get_fundamentals(query(
                                valuation.code, valuation.pb_ratio, valuation.circulating_market_cap
                            ).filter(
                                valuation.code.in_(security_list),
                                valuation.circulating_market_cap <= 200
                            ))
    df.set_index('code', inplace=True, drop=True)
    s_fall = fall_money_day_3line(df.index.tolist(), 120, 20, 60, 160)
    s_cross = money_5_cross_60(df.index.tolist(), 120)
    df = pd.concat([df, s_fall, s_cross], axis=1, join='inner')
    df.columns = ['pb', 'cap', 'fall', 'cross']
    df['score'] = df['fall'] * df['cross'] / (df['pb']*(df['cap']**0.5))
    df = df[df['score'] > score_threthold]
    df.sort(['score'], ascending=False, inplace=True)
    return(df)