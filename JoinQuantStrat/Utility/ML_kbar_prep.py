# -*- encoding: utf8 -*-
try:
    from rqdatac import *
except:
    pass
try:
    from jqdata import *
except:
    pass
from common_include import *
from kBarProcessor import *
from biaoLiStatus import TopBotType
from pickle import dump
from pickle import load
import pandas as pd
import numpy as np
import talib
import datetime
from sklearn.model_selection import train_test_split
from securityDataManager import *
from utility_ts import *
from keras.preprocessing import sequence

# pd.options.mode.chained_assignment = None 

fixed_length = 1200

class MLKbarPrep(object):
    '''
    Turn multiple level of kbar data into Chan Biaoli status,
    return a dataframe with combined biaoli status
    data types:
    biaoli status, high/low prices, volume/turnover ratio/money, MACD, sequence index
    '''

    def __init__(self, count=100, 
                 isAnal=False, 
                 isNormalize=True, 
                 manual_select=False, 
                 norm_range=[-1, 1], 
                 sub_max_count=fixed_length, 
                 isDebug=False, 
                 include_now=False, 
                 sub_level_min_count = 0, 
                 use_standardized_sub_df=False,
                 monitor_level = ['1d', '30m'],
                 monitor_fields = ['open','close','high','low','money']):
        self.isDebug = isDebug
        self.isAnal = isAnal
        self.count = count
        self.isNormalize = isNormalize
        self.norm_range = norm_range
        self.manual_select = manual_select
        self.stock_df_dict = {}
        self.sub_level_min_count = sub_level_min_count
        self.sub_max_count = sub_max_count
        self.data_set = []
        self.label_set = []
        self.include_now = include_now
        self.use_standardized_sub_df = use_standardized_sub_df
        self.num_of_debug_display = 0
        self.monitor_level = monitor_level
        self.monitor_fields = monitor_fields

    def workout_count_num(self, level, count):
        return count if self.monitor_level[0] == level \
                        else count * 8 if self.monitor_level[0] == '1d' and level == '30m' \
                        else count * 16 if self.monitor_level[0] == '1d' and level == '15m' \
                        else count * 48 if self.monitor_level[0] == '1d' and level == '5m' \
                        else count * 8 if self.monitor_level[0] == '5d' and level == '150m' \
                        else count * 40 if self.monitor_level[0] == '5d' and level == '30m' \
                        else count * 20 if self.monitor_level[0] == '5d' and level == '60m' \
                        else count * 8

    def get_high_df(self):
        return self.stock_df_dict[self.monitor_level[0]]
    
    def get_low_df(self):
        return self.stock_df_dict[self.monitor_level[1]]

    def grab_stock_raw_data(self, stock, end_date, file_dir="."):
        temp_stock_df_dict = {}
        for level in self.monitor_level:
            local_count = self.workout_count_num(level, self.count)
            stock_df = None
            if not self.isAnal:
                stock_df = attribute_history(stock, local_count, level, fields = ['open', 'close','high','low','money'], skip_paused=True, df=True)  
            else:
                latest_trading_day = end_date if end_date is not None else get_trade_days(count=1)[-1]
                stock_df = get_price(stock, count=local_count, end_date=str(latest_trading_day), frequency=level, fields = ['open', 'close','high','low','money'], skip_paused=True)              
            if stock_df.empty:
                continue
            temp_stock_df_dict[level] = stock_df
        return temp_stock_df_dict
        
    def grab_stocks_raw_data(self, stocks, end_date=None, file_dir="."):
        # grab the raw data and save on files
        all_stock_df = []
        for stock in stocks:
            all_stock_df.append(self.grab_stock_raw_data(stock, end_date, file_dir))
        save_dataset(all_stock_df, "{0}/last_stock_{1}.pkl".format(file_dir, stocks[-1]), self.isDebug)
            
    def load_stock_raw_data(self, stock_df):
        self.stock_df_dict = stock_df
        for level in self.monitor_level:
            self.stock_df_dict[level] = self.prepare_df_data(self.stock_df_dict[level], level)
        
    
    def retrieve_stock_data(self, stock, end_date=None):
        for level in self.monitor_level:
            local_count = self.workout_count_num(level, self.count)
            stock_df = None
            if not self.isAnal:
                stock_df = attribute_history(stock, local_count, level, fields = ['open','close','high','low', 'money'], skip_paused=True, df=True)  
            else:
                latest_trading_day = str(end_date if end_date is not None else get_trade_days(count=1)[-1])
                latest_trading_day = latest_trading_day+" 14:30:00" if level == '30m' or level == '5m' else latest_trading_day
                stock_df = get_price(stock, count=local_count, end_date=str(latest_trading_day), frequency=level, fields = ['open','close','high','low', 'money'], skip_paused=True)          
            if stock_df.empty:
                continue
#             if self.isDebug:
#                 print("{0}, {1}, {2}, {3}".format(stock, local_count, end_date, level))
#                 print(stock_df.tail(self.num_of_debug_display))
            stock_df = self.prepare_df_data(stock_df, level)
            self.stock_df_dict[level] = stock_df
    
    def retrieve_stock_data_rq(self, stock, end_date=None):
        for level in self.monitor_level:
            stock_df = None
            if not self.isAnal:
                local_count = self.workout_count_num(level, self.count)
                stock_df = SecurityDataManager.get_data_rq(stock, count=local_count, period=level, fields=['open','close','high','low', 'total_turnover'], skip_suspended=True, df=True, include_now=self.include_now)
            else:
                today = end_date if end_date is not None else datetime.datetime.today()
                previous_trading_day=get_trading_dates(start_date='2006-01-01', end_date=today)[-self.count]
                stock_df = SecurityDataManager.get_research_data_rq(stock, start_date=previous_trading_day, end_date=today, period=level, fields = ['open','close','high','low', 'total_turnover'], skip_suspended=True)
            if stock_df.empty:
                continue
            stock_df = self.prepare_df_data(stock_df, level)
            self.stock_df_dict[level] = stock_df    
        
    def retrieve_stock_data_ts(self, stock, end_date=None):
        today = end_date if end_date is not None else datetime.datetime.today()
        previous_trading_day=get_trading_date_ts(count=self.count, end=today)[-self.count]
        for level in self.monitor_level:
            ts_level = 'D' if level == '1d' else '30' if level == '30m' else 'D' # 'D' as default
            stock_df = SecurityDataManager.get_data_ts(stock, start_date=previous_trading_day, end_date=today, period=ts_level)
            if stock_df is None or stock_df.empty:
                continue
            stock_df = self.prepare_df_data(stock_df, level)
            self.stock_df_dict[level] = stock_df          
    
    def prepare_df_data(self, stock_df, level):
        if level == self.monitor_level[1]: # only add the fields in sub level
            # SMA
            sma_period = 233 if level == '30m' else 89 # 5m
            stock_df.loc[:,'sma'] = talib.SMA(stock_df['close'].values, sma_period) # use 233
            # MACD 
            _, _, stock_df.loc[:,'macd']  = talib.MACD(stock_df['close'].values)            
        stock_df = stock_df.dropna() # make sure we don't get any nan data
        stock_df = self.prepare_biaoli(stock_df, level)
        return stock_df
        
    
    def prepare_biaoli(self, stock_df, level):
#         print(level)
#         print(stock_df)
        if level == self.monitor_level[0]:
            kb = KBarProcessor(stock_df)
            # for higher level, we only need the pivot dates, getMarketBL contains more than we need, no need for join
            stock_df = kb.getMarkedBL()

        elif level == self.monitor_level[1]:
            if self.use_standardized_sub_df:
                kb = KBarProcessor(stock_df)
                if self.sub_level_min_count != 0:
                    stock_df = kb.getMarkedBL()[['open','close','high','low', 'money', 'new_index', 'tb']]
                else:
                    # stock_df = kb.getStandardized()[['open','close','high','low', 'money']]
                    # logic change here use sub level pivot time for segmentation of background training data
                    stock_df = kb.getIntegraded()
            else:
                pass
        return stock_df
    
    def prepare_training_data(self):
        if len(self.stock_df_dict) == 0:
            return [], []
        higher_df = self.stock_df_dict[self.monitor_level[0]]
        lower_df = self.stock_df_dict[self.monitor_level[1]]
        high_df_tb = higher_df.dropna(subset=['new_index'])
        high_dates = high_df_tb.index
        for i in range(0, len(high_dates)-1):
            first_date = str(high_dates[i].date())
            second_date = str(high_dates[i+1].date())
            print("high date: {0}:{1}".format(first_date, second_date))
            # high level date is [) while using pd.loc func
            # low level timestamp is [] while using pd.loc func
            if self.monitor_level[0] == '5d': # find the full range of date for the week
                first_date = get_trade_days(count=5, end_date=first_date)[0]
                second_date = get_trade_days(start_date=second_date)[6] # 5 days after the peak Week bar
            elif self.monitor_level[0] == '1d':
                first_date = get_trade_days(count=2, end_date=first_date)[0]
                second_date = get_trade_days(start_date=second_date)[2] 
            trunk_lower_df = lower_df.loc[first_date:second_date,:]
            if self.use_standardized_sub_df:
                self.create_ml_data_set(trunk_lower_df, high_df_tb.ix[i+1, 'tb'].value)
            else:
                self.create_ml_data_set_dynamic(trunk_lower_df, high_df_tb.ix[i+1, 'tb'].value)
        return self.data_set, self.label_set
    
    def prepare_predict_data(self):    
        if len(self.stock_df_dict) == 0:
            return self.data_set   
        higher_df = self.stock_df_dict[self.monitor_level[0]]
        lower_df = self.stock_df_dict[self.monitor_level[1]]
        if higher_df.empty or lower_df.empty:
            return self.data_set
        high_df_tb = higher_df.dropna(subset=['new_index'])
        high_dates = high_df_tb.index
        if self.isDebug and self.num_of_debug_display != 0:
                print(high_df_tb.tail(self.num_of_debug_display)[['tb', 'new_index']])
        
        for i in range(-self.num_of_debug_display-1, 0, 1): #-5
            try:
                first_date = str(high_dates[i].date())
                if self.monitor_level[0] == '5d': # find the full range of date for the week
                    first_date = get_trade_days(count=5, end_date=first_date)[0]
                elif self.monitor_level[0] == '1d':
                    first_date = get_trade_days(count=2, end_date=first_date)[0]
            except IndexError:
                continue
            trunk_lower_df = None
            if i+1 < 0:
                second_date = str(high_dates[i+1].date())
                if self.monitor_level[0] == '5d': # find the full range of date for the week
                    second_date = get_trade_days(start_date=second_date)[6] # 5 days after the peak Week bar
                elif self.monitor_level[0] == '1d':
                    second_date = get_trade_days(start_date=second_date)[2]
                trunk_lower_df = lower_df.loc[first_date:second_date, :]
            else:
                trunk_lower_df = lower_df.loc[first_date:, :]
#             if self.isDebug:
#                 print(trunk_lower_df.tail(self.num_of_debug_display))
            result = self.create_ml_data_set_predict(trunk_lower_df, high_df_tb.ix[i,'tb'].value)
            if result is not None:
                if not result:
                    first_date = str(high_dates[i-1].date())
                    if self.monitor_level[0] == '5d': # find the full range of date for the week
                        first_date = get_trade_days(count=5, end_date=first_date)[0]
                    elif self.monitor_level[0] == '1d':
                        first_date = get_trade_days(count=2, end_date=first_date)[0] 
                    self.create_ml_data_set_predict(lower_df.loc[first_date:, :], high_df_tb.ix[i-1,'tb'].value)
        return self.data_set
            
    def prepare_predict_data_extra(self):
        higher_df = self.stock_df_dict[self.monitor_level[0]]
        lower_df = self.stock_df_dict[self.monitor_level[1]]
        high_df_tb = higher_df.dropna(subset=['new_index'])
        high_dates = high_df_tb.index
        # additional check trunk
        for i in range(-self.num_of_debug_display-1, -1, 2):#-5
            try:
                previous_date = str(high_dates[i].date())
                if self.monitor_level[0] == '5d': # find the full range of date for the week
                    previous_date = get_trade_days(count=5, end_date=previous_date)[0]
                elif self.monitor_level[0] == '1d':
                    previous_date = get_trade_days(count=2, end_date=previous_date)[0]
            except IndexError:
                continue
            trunk_df = lower_df.loc[previous_date:,:]
#             if self.isDebug:
#                 print(trunk_df.head(self.num_of_debug_display))
#                 print(trunk_df.tail(self.num_of_debug_display))
            self.create_ml_data_set_predict(trunk_df, high_df_tb.ix[-1,'tb'].value)
        return self.data_set
        
    def create_ml_data_set_predict(self, trunk_df, previous_high_label):  
        pivot_sub_counting_range = self.workout_count_num(self.monitor_level[1], 1)        

        start_high_idx = trunk_df.ix[:pivot_sub_counting_range*2,'high'].idxmax()
        start_low_idx = trunk_df.ix[:pivot_sub_counting_range*2,'low'].idxmin()            
              
        trunk_df = trunk_df.loc[start_high_idx:,:] if previous_high_label == TopBotType.top.value else trunk_df.loc[start_low_idx:,:]  

        if len(trunk_df) < pivot_sub_counting_range: 
            if self.isDebug:
                print("Sub-level data length too short for prediction!")
            return False
        
        if not self.use_standardized_sub_df: # the case of dynamic data gen
            kb = KBarProcessor(trunk_df)
            sub_trunk_df = kb.getIntegraded(TopBotType.bot if previous_high_label == TopBotType.bot.value else TopBotType.top)   
            
        tb_trunk_df = self.manual_wash(sub_trunk_df)
        if tb_trunk_df is None:
            return False

        if tb_trunk_df.isnull().values.any():
            print("NaN value found, ignore this data")
            print(tb_trunk_df)
            return
    
        if self.isNormalize:
            tb_trunk_df = normalize(tb_trunk_df.copy(deep=True), norm_range=self.norm_range, fields=self.monitor_fields)
        self.data_set.append(tb_trunk_df.values) #trunk_df
        return True
        
    def findFirstPivotIndexByMA(self, df, start_index, topbot, last_index=None): # only use last_index in dynamic mode
        if start_index > df.index[-1]:
            return last_index
        start_pos = df.index.get_loc(start_index)
        while start_pos < df.shape[0]:
            item = df.iloc[start_pos]
            if topbot == TopBotType.bot:
                if item.tb == TopBotType.bot:
                    if item.low > item.sma:
                        return df.index[start_pos]
            if topbot == TopBotType.top:
                if item.tb == TopBotType.top:
                    if item.high < item.sma:
                        return df.index[start_pos]
            start_pos += 1
        if self.isDebug:
            print("WE REACH THE END!!!!")
        return df.index[-1] if last_index is None else last_index
    
    def create_ml_data_set_dynamic(self, trunk_df, label):
        # at least 3 parts in the sub level
        if self.sub_level_min_count != 0: # we won't process sub level df
            sub_level_count = len(trunk_df['tb']) - trunk_df['tb'].isnull().sum()
            if sub_level_count < self.sub_level_min_count:
                return
                
        pivot_sub_counting_range = self.workout_count_num(self.monitor_level[1], 1)        

        if len(trunk_df) > pivot_sub_counting_range * 2:

            start_high_idx = trunk_df.ix[:pivot_sub_counting_range*2,'high'].idxmax()
            start_low_idx = trunk_df.ix[:pivot_sub_counting_range*2,'low'].idxmin()
            
            trunk_df = trunk_df.loc[start_high_idx:,:] if label == TopBotType.bot.value else \
                    trunk_df.loc[start_low_idx:,:] if label == TopBotType.top.value else None
                    
            end_low_idx = trunk_df.ix[-pivot_sub_counting_range*2:,'low'].idxmin()
            end_high_idx = trunk_df.ix[-pivot_sub_counting_range*2:,'high'].idxmax()
            
            
        else:
            print("Sub-level data length too short!")
            return


        for time_index in trunk_df.index[10:]: #  at least 10 bars to make 3 pivots
            sub_trunk_df = trunk_df.loc[:time_index, :].copy(deep=True)
            kb = KBarProcessor(sub_trunk_df)
            sub_trunk_df = kb.getIntegraded(TopBotType.top if label == TopBotType.bot.value else TopBotType.bot)   
            
            sub_tb_count = len(sub_trunk_df['tb']) - sub_trunk_df['tb'].isnull().sum()
            if sub_tb_count < 3:
                continue
            
            # first top pivot index with high below sma / first bot pivot index with low above sma
            sub_start_index = self.findFirstPivotIndexByMA(sub_trunk_df, 
                                                           start_high_idx if label == TopBotType.bot.value else start_low_idx, 
                                                           TopBotType.top if label == TopBotType.bot.value else TopBotType.bot,
                                                           trunk_df.index[-1])
        
            if time_index < sub_start_index:
                continue
            
            sub_end_index = self.findFirstPivotIndexByMA(sub_trunk_df,
                                                         end_low_idx if label == TopBotType.bot.value else end_high_idx,
                                                         TopBotType.bot if label == TopBotType.bot.value else TopBotType.top,
                                                         trunk_df.index[-1])
            
            if time_index >= sub_end_index:
                break

            sub_tb_trunk_df = self.manual_wash(sub_trunk_df)
            
            if sub_tb_trunk_df.isnull().values.any():
                print("NaN value found, ignore this data")
                print(sub_tb_trunk_df)
                return

            if self.isNormalize:
                sub_tb_trunk_df = normalize(sub_tb_trunk_df, norm_range=self.norm_range, fields=self.monitor_fields)
            
            if len(self.data_set) > 0 and len(sub_tb_trunk_df) == len(self.data_set[-1]) and np.isclose(sub_tb_trunk_df.values, self.data_set[-1]).all():
                continue
                
            if not sub_tb_trunk_df.empty:
                self.data_set.append(sub_tb_trunk_df.values)
                if label == TopBotType.bot.value:
                    if time_index < start_high_idx:
                        self.label_set.append(TopBotType.top.value)
                        if self.isDebug:
                            print("SOMETHING IS WRONG")
                    elif time_index >= end_low_idx:  
                        self.label_set.append(TopBotType.bot.value)
                    else:
                        self.label_set.append(TopBotType.top2bot.value) # change to 4 categories
#                             self.label_set.append(TopBotType.top.value) # change to binary classification
#                             self.label_set.append(TopBotType.noTopBot.value) # 3 categories
                elif label == TopBotType.top.value:
                    if time_index >= end_high_idx: 
                        self.label_set.append(TopBotType.top.value)
                    elif time_index < start_low_idx:
                        self.label_set.append(TopBotType.bot.value)
                        if self.isDebug:
                            print("SOMETHING IS WRONG")
                    else:
                        self.label_set.append(TopBotType.bot2top.value) # change to 4 categories
#                             self.label_set.append(TopBotType.bot.value) # change to binary classification
#                             self.label_set.append(TopBotType.noTopBot.value)
                else:
                    pass
    
    def create_ml_data_set(self, trunk_df, label): 
        # at least 3 parts in the sub level
        if self.sub_level_min_count != 0: # we won't process sub level df
            sub_level_count = len(trunk_df['tb']) - trunk_df['tb'].isnull().sum()
            if sub_level_count < self.sub_level_min_count:
                return

        pivot_sub_counting_range = self.workout_count_num(self.monitor_level[1], 1)        

        
        if len(trunk_df) > pivot_sub_counting_range * 2:

            start_high_idx = trunk_df.ix[:pivot_sub_counting_range,'high'].idxmax()
            start_low_idx = trunk_df.ix[:pivot_sub_counting_range,'low'].idxmin()        
            
            trunk_df = trunk_df.loc[start_high_idx:,:] if label == TopBotType.bot.value else \
                    trunk_df.loc[start_low_idx:,:] if label == TopBotType.top.value else None
                    
            # first top pivot index with high below sma / first bot pivot index with low above sma
            sub_start_index = self.findFirstPivotIndexByMA(trunk_df, 
                                                           start_high_idx if label == TopBotType.bot.value else start_low_idx, 
                                                           TopBotType.top if label == TopBotType.bot.value else TopBotType.bot)
            
#             sub_start_index_high = trunk_df.index[trunk_df.index.get_loc(start_high_idx) + pivot_sub_counting_range]
#             sub_start_index_low = trunk_df.index[trunk_df.index.get_loc(start_low_idx) + pivot_sub_counting_range]
        else:
            print("Sub-level data length too short!")
            return
        
#         if self.manual_select:
#             trunk_df = self.manual_select(trunk_df)
#         else: # manual_wash
        
            tb_trunk_df = self.manual_wash(trunk_df)
        
        if tb_trunk_df is None:
            return
        
        if tb_trunk_df.isnull().values.any():
            print("NaN value found, ignore this data")
            print(trunk_df)
            print(tb_trunk_df)
            return
    
        if not tb_trunk_df.empty:                            
            # increase the 1, -1 label sample
            end_low_idx = trunk_df.ix[-pivot_sub_counting_range*2:,'low'].idxmin()
            end_high_idx = trunk_df.ix[-pivot_sub_counting_range*2:,'high'].idxmax()

            sub_end_index = self.findFirstPivotIndexByMA(trunk_df,
                                                         end_low_idx if label == TopBotType.bot.value else end_high_idx,
                                                         TopBotType.bot if label == TopBotType.bot.value else TopBotType.top)
            
#             sub_early_end_index_low = trunk_df.index[trunk_df.index.get_loc(end_low_idx) - pivot_sub_counting_range]
#             sub_early_end_index_high = trunk_df.index[trunk_df.index.get_loc(end_high_idx) - pivot_sub_counting_range]          
#             
#             sub_end_pos_low = trunk_df.index.get_loc(end_low_idx) + pivot_sub_counting_range
#             sub_end_pos_high = trunk_df.index.get_loc(end_high_idx) + pivot_sub_counting_range    
#                         
#             sub_end_index_low = trunk_df.index[sub_end_pos_low if sub_end_pos_low < len(trunk_df.index) else -1]
#             sub_end_index_high = trunk_df.index[sub_end_pos_high if sub_end_pos_high < len(trunk_df.index) else -1]             
            
            for time_index in tb_trunk_df.index: #  tb_trunk_df.index
                if time_index < sub_start_index:
                    continue
                
                if time_index >= sub_end_index:
                    break
                
                sub_trunk_df = tb_trunk_df.loc[:time_index, :]
                            
                if self.isNormalize:
                    sub_trunk_df = normalize(sub_trunk_df.copy(deep=True), norm_range=self.norm_range, fields=self.monitor_fields)

                if sub_trunk_df.isnull().values.any():
                    print("NaN value found, ignore this data")
                    print(sub_trunk_df)
                    continue
                    
                    if not sub_trunk_df.empty:
                        self.data_set.append(sub_trunk_df.values)
                    if label == TopBotType.bot.value:
                        if time_index < start_high_idx: #  and tb_trunk_df.loc[time_index, 'tb'].value == TopBotType.top.value
                            self.label_set.append(TopBotType.top.value)
                            if self.isDebug:
                                print("SOMETHING IS WRONG")
                        elif time_index >= end_low_idx:  # sub_early_end_index_low and tb_trunk_df.loc[time_index, 'tb'].value == TopBotType.bot.value
                            self.label_set.append(TopBotType.bot.value)
                        else:
                            self.label_set.append(TopBotType.top2bot.value) # change to 4 categories
#                                 self.label_set.append(TopBotType.top.value) # change to binary classification
#                             self.label_set.append(TopBotType.noTopBot.value) # 3 categories
                    elif label == TopBotType.top.value:
                        if time_index >= end_high_idx: # sub_early_end_index_high and tb_trunk_df.loc[time_index, 'tb'].value == TopBotType.top.value
                            self.label_set.append(TopBotType.top.value)
                        elif time_index < start_low_idx: #  and tb_trunk_df.loc[time_index, 'tb'].value == TopBotType.bot.value
                            self.label_set.append(TopBotType.bot.value)
                            if self.isDebug:
                                print("SOMETHING IS WRONG")
                        else:
                            self.label_set.append(TopBotType.bot2top.value) # change to 4 categories
#                                 self.label_set.append(TopBotType.bot.value) # change to binary classification
#                             self.label_set.append(TopBotType.noTopBot.value)
                    else:
                        pass
        
##############Due to the limitation of hardward and model complexity, we can't expect precise pivot training
#             for time_index in tb_trunk_df.index[-5:]: #  counting from cutting start
#                 sub_trunk_df = trunk_df.loc[:time_index, :]
#                 if not sub_trunk_df.empty: 
#                     self.data_set.append(sub_trunk_df.values)
#                     if tb_trunk_df.loc[time_index, 'tb'].value == label:
#                         self.label_set.append(label)
#                     else:
#                         self.label_set.append(TopBotType.noTopBot.value)
#############################################################################################################
        
    def manual_select(self, df):
        df = df.dropna() # only concern BI
        df['new_index'] = df['new_index'].shift(-1) - df['new_index'] 
        df['tb'] = df.apply(lambda row: row['tb'].value, axis = 1)
        df['price'] = df.apply(lambda row: row['high'] if row['tb'] == 1 else row['low'])
        df.drop(['open', 'high', 'low'], 1)
        return df
        
    def manual_wash(self, df):
        # add accumulative macd value to the pivot
        df['tb_pivot'] = df.apply(lambda row: 0 if pd.isnull(row['tb']) else 1, axis=1)
        groups = df['tb_pivot'][::-1].cumsum()[::-1]
        df['tb_pivot_acc'] = groups
        
        df_macd_acc = df.groupby(groups)['macd'].agg([('macd_acc_negative' , lambda x : x[x < 0].sum()) , ('macd_acc_positive' , lambda x : x[x > 0].sum())])
        df = pd.merge(df, df_macd_acc, left_on='tb_pivot_acc', right_index=True)
        df['macd_acc'] = df.apply(lambda row: 0 if pd.isnull(row['tb']) else row['macd_acc_negative'] if row['tb'] == TopBotType.bot else row['macd_acc_positive'] if row['tb'] == TopBotType.top else 0, axis=1)
        
        df['money_acc'] = df.groupby(groups)['money'].transform('sum')
        
        # sub level trunks pivots are used to training / prediction
        df = df.dropna(subset=['tb'])
        
        if df.empty:
            if self.isDebug:
                print("We have empty dataframe return None")
            return None
        
        # use the new_index column as distance measure starting from the beginning of the sequence
        df['new_index'] = df['new_index'] - df.iat[0,df.columns.get_loc('new_index')]
        
        # work out the effective high / low price for the data row
        df['chan_price'] = df.apply(lambda row: row['high'] if row['tb'] == TopBotType.top else row['low'], axis=1)
        
        df = df[self.monitor_fields]
        return df
        
    def normalize_old(self, df):
        working_df = df.copy(deep=True)
        for column in working_df: 
            if column == 'new_index' or column == 'tb':
                continue
            if self.norm_range:
                # min-max -1 1 / 0 1
                col_min = working_df[column].min()
                col_max = working_df[column].max()
                col_mean = working_df[column].mean()
                working_df[column]=(working_df[column]-col_mean)/(col_max-col_min)
            else:
                # use zscore mean std
                col_mean = working_df[column].mean()
                col_std = working_df[column].std()
                working_df[column] = (working_df[column] - col_mean) / col_std
        return working_df


class MLDataPrep(object):
    def __init__(self, isAnal=False, max_length_for_pad=fixed_length, 
                 rq=False, ts=True, norm_range=[-1,1], isDebug=False,
                 detailed_bg=False, use_standardized_sub_df=True, 
                 monitor_level=['1d','30m'],
                 monitor_fields=['open','close','high','low','money','macd_acc']):
        self.isDebug = isDebug
        self.isAnal = isAnal
        self.detailed_bg = detailed_bg
        self.max_sequence_length = max_length_for_pad
        self.isRQ = rq
        self.isTS = ts
        self.use_standardized_sub_df = use_standardized_sub_df
        self.check_level = monitor_level
        self.norm_range = norm_range
        self.monitor_fields=monitor_fields
    
    def retrieve_stocks_data_from_raw(self, raw_file_path=None, filename=None):
        mlk = MLKbarPrep(isAnal=self.isAnal, 
                         isNormalize=True, 
                         sub_max_count=self.max_sequence_length, 
                         norm_range=self.norm_range,
                         isDebug=self.isDebug, 
                         sub_level_min_count=0, 
                         use_standardized_sub_df=self.use_standardized_sub_df, 
                         monitor_level=self.check_level,
                         monitor_fields=self.monitor_fields)

        df_array = load_dataset(raw_file_path, self.isDebug)
        for stock_df in df_array:
            mlk.load_stock_raw_data(stock_df)
            dl, ll = mlk.prepare_training_data()
            print("retrieve_stocks_data_from_raw sub: {0}".format(len(dl)))
        if filename:
            save_dataset((dl, ll), filename, self.isDebug)
        return (dl, ll)
    
    def retrieve_stocks_data(self, stocks, period_count=60, filename=None, today_date=None):
        for stock in stocks:
            if self.isAnal:
                print ("working on stock: {0}".format(stock))
            mlk = MLKbarPrep(isAnal=self.isAnal, 
                             count=period_count, 
                             isNormalize=True, 
                             sub_max_count=self.max_sequence_length, 
                             norm_range=self.norm_range,
                             isDebug=self.isDebug, 
                             sub_level_min_count=0, 
                             use_standardized_sub_df=self.use_standardized_sub_df, 
                             monitor_level=self.check_level,
                             monitor_fields=self.monitor_fields)
            if self.isTS:
                mlk.retrieve_stock_data_ts(stock, today_date)
            elif self.isRQ:
                mlk.retrieve_stock_data_rq(stock, today_date)
            else:
                mlk.retrieve_stock_data(stock, today_date)
            dl, ll = mlk.prepare_training_data()
        if filename:
            save_dataset((dl, ll), filename)
        return (dl, ll)
    
    def prepare_stock_data_predict(self, stock, period_count=100, today_date=None, predict_extra=False):
        mlk = MLKbarPrep(isAnal=self.isAnal, 
                         count=period_count, 
                         isNormalize=True, 
                         sub_max_count=self.max_sequence_length, 
                         norm_range=self.norm_range,
                         isDebug=self.isDebug, 
                         sub_level_min_count=0, 
                         use_standardized_sub_df=self.use_standardized_sub_df,
                         monitor_level=self.check_level,
                         monitor_fields=self.monitor_fields)
        if self.isTS:
            mlk.retrieve_stock_data_ts(stock, today_date)
        elif self.isRQ:
            mlk.retrieve_stock_data_rq(stock, today_date)
        else:
            mlk.retrieve_stock_data(stock, today_date)
        predict_dataset = mlk.prepare_predict_data()
        origin_pred_size = len(predict_dataset)
        if origin_pred_size == 0:
            return None, 0, 0
        if predict_extra:
            predict_dataset = mlk.prepare_predict_data_extra()

#         predict_dataset = pad_each_training_array(predict_dataset, self.max_sequence_length)
        predict_dataset = sequence.pad_sequences(predict_dataset, maxlen=None if self.max_sequence_length == 0 else self.max_sequence_length, padding='pre', truncating='pre')
        if self.isDebug:
#             print("original size:{0}".format(origin_pred_size))
            pass
        return predict_dataset, origin_pred_size, mlk.get_high_df().ix[-1, 'tb'].value
        
    def prepare_stock_data_cnn(self, filenames, padData=True, test_portion=0.1, random_seed=42, background_data_generation=False):
        data_list = []
        label_list = []
        for file in filenames:
            A, B = load_dataset(file, self.isDebug)
            
            A_check = True
            i = 0
            for item in A:     
                if (self.norm_range is not None and 
                    (not ((np.logical_or(item>self.norm_range[0],np.isclose(item, self.norm_range[0]))).all() and 
                         (np.logical_or(item<self.norm_range[1],np.isclose(item, self.norm_range[1]))).all()))) or \
                np.isnan(item).any() or item.size == 0:
                    print(item)
                    print(A[i])
                    print(B[i])
                    print(i)
                    A_check=False
                    break
                i += 1
            if not A_check:
                print("Data invalid in file {0}".format(file))
                continue

            data_list = data_list + A
            label_list = label_list + B

        return self.prepare_stock_data_set(data_list, label_list, padData, test_portion, random_seed, background_data_generation)
    
    def prepare_stock_data_set(self, data_list, label_list, padData=True, test_portion=0.1, random_seed=42, background_data_generation=False):

        if not data_list or not label_list:
            print("Invalid file content")
            return

#         if self.isDebug:
#             print (data_list)
#             print (label_list)

        if background_data_generation:
            data_list, label_list = self.prepare_background_data(data_list, label_list)

        if padData:
            data_list = self.pad_each_training_array(data_list, self.max_sequence_length)
        
        label_list = encode_category(label_list)  
        
        x_train, x_test, y_train, y_test = train_test_split(data_list, label_list, test_size=test_portion, random_state=random_seed)
        
        if self.isDebug:
#             print (x_train.shape)
#             print (x_train)
#             print (y_train)
            pass
        
        return x_train, x_test, y_train, y_test
    
    def prepare_background_data(self, data_set, label_set):
        # split existing samples to create sample for 0 label
        split_ratio = [0.191, 0.382, 0.5, 0.618, 0.809]
        new_background_data = []
        new_label_data = []
        for sample in data_set:
            length = sample.shape[0]
            if self.detailed_bg:
                for i in range(2, length-1, 2): # step by 2
                    new_data = sample[:i, :] 
                    new_background_data.append(new_data)
                    new_label_data.append(TopBotType.noTopBot.value)
            else:
                for split_index in split_ratio:
                    si = int(split_index * length)
                    new_data = sample[:si,:]
                    new_background_data.append(new_data)
                    new_label_data.append(TopBotType.noTopBot.value)
        
        data_set = data_set + new_background_data
        label_set = label_set + new_label_data
        return data_set, label_set
                
    def define_conv_lstm_dimension(self, x_train):
        x_train = np.expand_dims(x_train, axis=2)         #3
        x_train = np.expand_dims(x_train, axis=2)         
        return x_train
    

    def generate_from_data(self, data, label, batch_size):
        for i in batch(range(0, len(data)), batch_size):
            yield data[i[0]:i[1]], label[i[0]:i[1]]    
    
    def keepDimension(self, targetArray, indexList):
        tempArray = np.array(targetArray)
        tempArray = tempArray[:,:,indexList]
        return tempArray.tolist()
    
    def generate_from_file(self, filenames, padData=True, background_data_generation=False, batch_size=50, model_type='convlstm'):
        while True:
            for file in filenames:
                A, B = load_dataset(file, self.isDebug)
                A_check = True
                for item in A:     
                    if (self.norm_range is not None and 
                        (not ((np.logical_or(item>self.norm_range[0],np.isclose(item, self.norm_range[0]))).all() and 
                             (np.logical_or(item<self.norm_range[1],np.isclose(item, self.norm_range[1]))).all()))) or \
                    np.isnan(item).any() or \
                    item.size == 0: # min max value range or zscore
                        print(item)
                        A_check=False
                        break
                if not A_check:
                    print("Data invalid in file {0}".format(file))
                    continue
    
                if A is None or B is None:
                    print("Invalid file content")
                    return
    
                if background_data_generation:
                    A, B = self.prepare_background_data(A, B)
    
#                 if padData:
#                     A = sequence.pad_sequences(A, maxlen=None if self.max_sequence_length == 0 else self.max_sequence_length, padding='pre', truncating='pre')
#   
#                 if model_type == 'convlstm':
#                     A = self.define_conv_lstm_dimension(A)
                
#                 B = encode_category(B)
                
                for i in batch(range(0, len(A)), batch_size):
                    subA = A[i[0]:i[1]]               

                    if padData:
###                         subA = pad_each_training_array(subA, self.max_sequence_length)## not used
                        subA = sequence.pad_sequences(subA, maxlen=None if self.max_sequence_length == 0 else self.max_sequence_length, padding='pre', truncating='pre')
                    else:
                        subA = np.array(subA)
                    
                    if model_type == 'convlstm':
                        subA = self.define_conv_lstm_dimension(subA)
                    elif model_type == 'rnncnn':
                        pass                     
                    elif model_type == 'cnn':  
                        pass
                    yield subA, B[i[0]:i[1]] 
    
    def prepare_stock_data_gen(self, filenames, padData=True, background_data_generation=False, batch_size=50, model_type='convlstm'):
        return self.generate_from_file(filenames, padData=padData, background_data_generation=background_data_generation, batch_size=batch_size, model_type=model_type)
    
#                           open      close       high        low        money  \
# 2017-11-14 10:00:00  3446.5500  3436.1400  3450.3400  3436.1400  60749246464   
# 2017-11-14 10:30:00  3436.7000  3433.1700  3438.7300  3431.2600  39968927744   
# 2017-11-14 11:00:00  3433.3600  3437.7500  3439.4100  3429.8200  28573523968   

# 
#                       macd_raw      macd  new_index              tb  
# 2017-11-14 10:00:00   9.480639 -0.786244        NaN             NaN  
# 2017-11-14 10:30:00   8.310828 -1.564845        NaN             NaN  
# 2017-11-14 11:00:00   7.664954 -1.768575        NaN             NaN  
# 2017-11-14 11:30:00   6.671123 -2.209925        NaN             NaN  
# 2017-11-14 13:30:00   6.626142 -1.803925        NaN             NaN  
# 2017-11-14 14:00:00   6.067070 -1.890397        NaN             NaN  
# 2017-11-14 14:30:00   4.368913 -2.870843        NaN             NaN  
# 2017-11-14 15:00:00   3.564614 -2.940114        NaN             NaN  
# 2017-11-15 10:00:00   1.701251 -3.842782        NaN             NaN  
# 2017-11-15 10:30:00  -0.326071 -4.696083        NaN             NaN  
# 2017-11-15 11:00:00  -1.975328 -5.076272        NaN             NaN  
# 2017-11-15 11:30:00  -3.382178 -5.186497        NaN             NaN  
# 2017-11-15 13:30:00  -4.234472 -4.831033        NaN             NaN  
# 2017-11-15 14:00:00  -4.859551 -4.364890        NaN             NaN  
# 2017-11-15 14:30:00  -5.841940 -4.277823        NaN             NaN  
# 2017-11-15 15:00:00  -6.416611 -3.881995        NaN             NaN  
# 2017-11-16 10:00:00  -6.918969 -3.507483         51  TopBotType.bot  
# 2017-11-16 10:30:00  -7.690800 -3.423451        NaN             NaN  
# 2017-11-16 11:00:00  -7.859263 -2.873531        NaN             NaN  
# 2017-11-16 11:30:00  -7.935189 -2.359566        NaN             NaN  
# 2017-11-16 13:30:00  -8.347779 -2.217725        NaN             NaN  
# 2017-11-16 14:00:00  -7.629007 -1.199162        NaN             NaN  
# 2017-11-16 14:30:00  -7.446391 -0.813237         57  TopBotType.top  
# 2017-11-16 15:00:00  -7.247972 -0.491854        NaN             NaN  
# 2017-11-17 10:00:00  -7.885018 -0.903120        NaN             NaN  



