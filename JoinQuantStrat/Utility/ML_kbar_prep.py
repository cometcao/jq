from kBarProcessor import *
from jqdata import *
import pandas as pd
import numpy as np
import talib

class MLKbarPrep(object):
    '''
    Turn multiple level of kbar data into Chan Biaoli status,
    return a dataframe with combined biaoli status
    data types:
    biaoli status, high/low prices, volume/turnover ratio/money, MACD, sequence index
    '''

    monitor_level = ['1d', '30m']
    def __init__(self, count=100, isAnal=False):
        self.isAnal = isAnal
        self.count = count
        self.stock_df_dict = {}
    
    def retrieve_stock_data(self, stock):
        for level in MLKbarPrep.monitor_level:
            local_count = self.count if level == '1d' else self.count * 8
            stock_df = None
            if not self.isAnal:
                stock_df = attribute_history(stock, local_count, level, fields = ['open','close','high','low', 'money'], skip_paused=True, df=True)  
            else:
                latest_trading_day = get_trade_days(count=1)[-1]
                stock_df = get_price(stock, count=local_count, end_date=latest_trading_day, frequency=level, fields = ['open','close','high','low', 'money'], skip_paused=True)          
            stock_df = self.prepare_df_data(stock_df)
            self.stock_df_dict[level] = stock_df
    
    def prepare_df_data(self, stock_df):
        # MACD
        stock_df.loc[:,'macd_raw'], _, stock_df.loc[:,'macd']  = talib.MACD(stock_df['close'].values)
        # BiaoLi
        stock_df = self.prepare_biaoli(stock_df)
        return stock_df
        
    
    def prepare_biaoli(self, stock_df):
        kb = KBarProcessor(stock_df)
        kb_marked = kb.getMarkedBL()
        stock_df = stock_df.join(kb_marked[['new_index', 'tb']])
        if self.isAnal:
            print stock_df
        return stock_df
    
    def prepare_training_data(self):
        higher_df = self.stock_df_dict[MLKbarPrep.monitor_level[0]]
        lower_df = self.stock_df_dict[MLKbarPrep.monitor_level[1]]
        high_df_tb = higher_df.dropna(subset=['new_index'])
        if self.isAnal:
            print high_df_tb
        high_dates = high_df_tb.index
        for i in range(0, len(high_dates)-1):
            first_date = high_dates[i]
            second_date = high_dates[i+1]
            trunk_lower_df = lower_df.loc[first_date:second_date,:]
            if self.isAnal:
                print trunk_lower_df
            self.create_ml_data_set(trunk_lower_df, high_df_tb.ix[i, 'tb'])
        
    def create_ml_data_set(self, trunk_df, label):
        pass
            
        