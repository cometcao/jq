# -*- encoding: utf8 -*-
'''
Created on 2 Aug 2019

@author: MetalInvest
'''
try:
    from kuanke.user_space_api import *         
except ImportError as ie:
    print(str(ie))
from jqdata import *
import numpy as np
import pandas as pd
import math
from jqfactor import *
from jqdata import *
from jqlib.technical_analysis import *

class Factor_Analyzer(object):
    '''
    This class use JQ interface to calculate IC and IR value for factors requested
    '''
    def __init__(self, params):
        self.period = params.get('period', ['month_3', 'year_1'])
        self.index_range = params.get('index_range', '000985.XSHG')
        self.model = params.get('model', 'long_only')
        self.category = params.get('category', ['quality', 'basics', 'emotion', 'growth', 'risk', 'pershare', 'barra', 'technical', 'momentum'])
        self.factor_date_count = params.get('factor_date_count', 750) # three years
        self.is_debug = params.get('is_debug', False)   
        
    def get_shift_days(self, period_str):
        return 60 if period_str == 'month_3' else 250 if period_str == 'year_1' else 60    
        
    def analyze_factors(self, factor_list, end_date):
        trade_days = get_trade_days(end_date=end_date, count=self.factor_date_count)
        
        index_stocks = get_index_stocks(self.index_range, date=end_date)
        
        stock_data = get_price(security=index_stocks, end_date=end_date, count=self.factor_date_count, frequency='daily', skip_paused=False, panel=False, fields='close')
        
        stock_data = self.cal_return(stock_data)
        
        stock_data = self.fill_factor_data(stock_data, index_stocks, factor_list, end_date, self.factor_date_count)
        
        ic_ir_data = self.cal_ic(stock_data, trade_days, factor_list)
        
        ic_ir_data = self.cal_ir(ic_ir_data, factor_list)
        
    def cal_ic(self, stock_data, trade_days, factor_list):
        ic_result_df = pd.DataFrame(columns=['ic_value'], index=trade_days)
        day_index = -1
        num_td = len(trade_days)
        while day_index > -num_td:
            end_day = trade_days[day_index]
            return_data = stock_data[stock_data['time'] == str(end_day)]
            for fac in factor_list:
                for pe in self.period:
                    shift_days = self.get_shift_days(pe)
                    if day_index - shift_days < -num_td:
                        continue
                    ref_day = trade_days[day_index - shift_days]
                    fac_data = stock_data[stock_data['time'] == str(ref_day)]
                    rank_ic = np.corrcoef(return_data[pe+'_return'].sort_values(by=pe+'_return', ascending=False).reset_index().index.tolist(),
                                fac_data[fac].sort_values(by=fac, ascending=False).reset_index().index.tolist())
                    ic_result_df.loc[end_day, fac+'_'+pe+'_ic'] = rank_ic[0][1]
                    print(ic_result_df)
            day_index = day_index - 1
        return ic_result_df
    
    def cal_ir(self, ic_ir_data, factor_list):
        for pe in self.period:
            shift_days = self.get_shift_days(pe)
            for fac in factor_list:
                ic_ir_data[fac+'_'+pe+'_ir'] = ic_ir_data[fac+'_'+pe+'_ic'].rolling(window=shift_days).mean() / ic_ir_data[fac+'_'+pe+'_ic'].rolling(window=shift_days).std()
        return ic_ir_data

    def get_factor_value_rolling(self, securities, factor, end_date, count):
        '''
        call the official API repeatatively due to data limitation
        '''
        fact_data = pd.DataFrame()
        for stock in securities:
            sub_fact_data = get_factor_values(securities = stock, factors = factor, end_date = end_date, count = count)[factor]
            if fact_data.empty:
                fact_data = sub_fact_data
            else:
                fact_data = pd.merge(fact_data, sub_fact_data, right_index=True, left_index=True)
        return fact_data
            
        

    def fill_factor_data(self, stock_data, stocks, factor_list, end_date, count):
        for fac in factor_list:
            fac_data = self.get_factor_value_rolling(securities=stocks, factor = fac, end_date = end_date, count = count)
            fac_data = fac_data.reset_index()
            fac_data = fac_data.melt(id_vars=["index"], 
                            var_name="code", 
                            value_name=fac)
            fac_data.rename({'index':'time'}, axis=1, inplace=True)
            stock_data = pd.merge(stock_data, fac_data, on=['time', 'code'], how='left')
        # save the data
        return stock_data
        
        
    def cal_return(self, stock_data):
        for pe in self.period:
            shift_days = self.get_shift_days(pe)
            stock_data[pe+'_return'] = stock_data.groupby(['code'])['close'].pct_change(periods=shift_days)
            stock_data = stock_data.dropna()
            
#             stock_data[pe+'_return'] = stock_data.groupby(['code']).shift(shift_days)['close']
#             stock_data[pe+'_return'] = (stock_data['close'] - stock_data[pe+'_return']) / stock_data[pe+'_return']
        
        return stock_data
    
    