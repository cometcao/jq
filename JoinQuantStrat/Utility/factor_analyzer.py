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
import os 


class Factor_Analyzer(object):
    '''
    This class use JQ interface to calculate IC and IR value for factors requested
    '''
    def __init__(self, params):
        self.period = params.get('period', ['month_3', 'year_1'])
        self.index_range = params.get('index_range', '000985.XSHG')
        self.model = params.get('model', 'long_only')
        self.category = params.get('category', ['basics', 'emotion', 'growth', 'momentum', 'pershare', 'quality', 'risk', 'style', 'technical'])
        self.factor_date_count = params.get('factor_date_count', 750) # three years
        self.is_debug = params.get('is_debug', False)   
        self.save_data = params.get('save_data', './temp/ic_ir.data')
        self.save_result = params.get('save_result', './temp/ic_ir.result')
        
    def get_shift_days(self, period_str):
        return 60 if period_str == 'month_3' else 250 if period_str == 'year_1' else 60    
        
    def get_factor_data(self, index_stocks, end_date, factor_list, csv_file=None): 
        if csv_file is None:
            stock_data = get_price(security=index_stocks, end_date=end_date, count=self.factor_date_count, frequency='daily', skip_paused=False, panel=False, fields='close')
            
            stock_data = self.cal_return(stock_data)
            
            stock_data = self.fill_factor_data(stock_data, index_stocks, factor_list, end_date, self.factor_date_count)
            return stock_data
        else:
            print('file {0} exists, load the data'.format(csv_file))
            return pd.read_csv(csv_file, index_col='INDEX')
    
    def cal_fac_data(self, stock_data, trade_days, factor_list):
        ic_ir_data = self.cal_ic(stock_data, trade_days, factor_list)
        
        ic_ir_data = self.cal_ir(ic_ir_data, factor_list)
        
        if self.save_result:
            ic_ir_data.index.name = 'INDEX'
            ic_ir_data.to_csv(self.save_result, encoding='utf-8', index=True)        
    
    def analyze_factors(self, factor_list, end_date):
        trade_days = get_trade_days(end_date=end_date, count=self.factor_date_count)
        
        index_stocks = get_index_stocks(self.index_range, date=end_date)
        
        exists = self.save_data if os.path.isfile(self.save_data) else None
        stock_data = self.get_factor_data(index_stocks, end_date, factor_list, csv_file=exists)
#         if self.is_debug:
#             print(stock_data)
        self.cal_fac_data(stock_data, trade_days, factor_list)
        
    def cal_ic(self, stock_data, trade_days, factor_list):
        ic_result = []
        day_index = 60 # we start with month_3 which is 60
        num_td = len(trade_days)
        while day_index < num_td:
            end_day = trade_days[day_index]
            return_data = stock_data[stock_data['time'] == str(end_day)]
            for fac in factor_list:
                for pe in self.period:
                    shift_days = self.get_shift_days(pe)
                    if day_index - shift_days < 0:
                        continue
                    ref_day = trade_days[day_index - shift_days]
                    fac_data = stock_data[stock_data['time'] == str(ref_day)]
                    rank_ic = np.corrcoef(return_data.sort_values(by=pe+'_return', ascending=False).index.tolist(),
                                fac_data.sort_values(by=fac, ascending=False).index.tolist())
                    ic_result.append({'date':end_day, 'ic':rank_ic[0][1], 'factor':fac, 'bt_cycle':pe})
            day_index = day_index + 1
        ic_result_df = pd.DataFrame(ic_result, columns=['date', 'ic', 'factor', 'bt_cycle'])
        return ic_result_df
    
    def cal_ir(self, ic_ir_data, factor_list):
        for pe in self.period:
            shift_days = self.get_shift_days(pe)
            for fac in factor_list:
#                 ic_ir_data['ic_mean'] = ic_ir_data.groupby([fac, pe])['ic'].rolling(window=shift_days).mean()
                if self.is_debug:
                    print(ic_ir_data)
#                     print(ic_ir_data.groupby(['factor', 'bt_cycle'])['ic'].apply(lambda x:x.rolling(window=shift_days).mean()))
                ic_ir_data['ic_mean'] = ic_ir_data.groupby(['factor', 'bt_cycle'])['ic'].apply(lambda x:x.rolling(window=shift_days).mean())
                ic_ir_data['ir'] = ic_ir_data['ic_mean'] / ic_ir_data.groupby(['factor', 'bt_cycle'])['ic'].apply(lambda x:x.rolling(window=shift_days).std())
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
        
#         if self.is_debug:
#             print("stock_data:{0}".format(stock_data))
        # save the data
        
        if self.save_data:
            stock_data.index.name = 'INDEX'
            stock_data.to_csv(self.save_data, encoding='utf-8', index=True)
        return stock_data
        
        
    def cal_return(self, stock_data):
        for pe in self.period:
            shift_days = self.get_shift_days(pe)
            stock_data[pe+'_return'] = stock_data.groupby(['code'])['close'].pct_change(periods=shift_days)
#             stock_data = stock_data.dropna()
#             stock_data[pe+'_return'] = stock_data.groupby(['code']).shift(shift_days)['close']
#             stock_data[pe+'_return'] = (stock_data['close'] - stock_data[pe+'_return']) / stock_data[pe+'_return']
        
        return stock_data
    
def combine_result_file(result_file_path, final_result_file):
    all_files = []
    for r, d, f in os.walk(result_file_path):
        for file in f:
            if file.endswith(".result"):
                all_files.append(file)
    
    result_data = pd.DataFrame()
    for fi in all_files:
        cat = fi.split('_')[0]
        sub_data_df = pd.read_csv(os.path.join(result_file_path, fi), index_col='INDEX')
        sub_data_df['category'] = cat
        print(sub_data_df)
        if result_data.empty:
            result_data = sub_data_df
        else:
            result_data = pd.merge(result_data, sub_data_df, on=['date', 'category', 'ic', 'factor', 'bt_cycle', 'ic_mean', 'ir'], how='outer')        

    print("result_data".format(result_data))
    print(result_data['date'].unique())
    print(result_data['factor'].unique())
    print(result_data['category'].unique())
    
    if final_result_file is not None:
        result_data.index.name = 'INDEX'
        result_data.to_csv(final_result_file, encoding='utf-8', index=True)   
        print("file written: {0}".format(final_result_file))
    
    return result_data

'''
from factor_analyzer import *

factor_rank = get_all_factors()
all_cat = factor_rank['category'].unique().tolist()
#['basics', 'emotion', 'growth', 'risk', 'pershare', 'style', 'technical', 'momentum', 'quality']
for cat in all_cat:
    print("working on {0}".format(cat))
    fa = Factor_Analyzer({'period':['month_3'],
                          'index_range':'000300.XSHG', 
                          'factor_date_count': 750,
                          'save_data':'./temp/{0}_ic_ir.data'.format(cat),
                          'save_result':'./temp/{0}_ic_ir.result'.format(cat),
                          'is_debug':True})
    factors = factor_rank[factor_rank['category'] == cat]['factor'].tolist()
    fa.analyze_factors(factors, '2019-11-21')
'''
    