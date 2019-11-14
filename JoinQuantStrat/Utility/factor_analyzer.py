# -*- encoding: utf8 -*-
'''
Created on 2 Aug 2019

@author: MetalInvest
'''
from tensorflow.python.ops.gen_user_ops import fact
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

            
            
    def analyze_factors(self, factor_list, end_date, date_count):
        index_stocks = get_index_stocks(self.index_range)
        
        stock_data = get_price(security=index_stocks, end_date=end_date, count=date_count, frequency='daily', skip_paused=True, panel=False, fields='close')
        
        stock_data = self.cal_return(stock_data)
        
        stock_data = self.fill_factor_data(stock_data, index_stocks, factor_list, end_date, date_count)
        
        stock_data = self.cal_ic(stock_data)
        
        stock_data = self.cal_ir(stock_data)
        
    def cal_ic(self, stock_data):
        pass
    
    def cal_ir(self, stock_data):
        pass

    def fill_factor_data(self, stock_data, stocks, factor_list, end_date, count):
        for fac in factor_list:
            fac_data = get_factor_values(securities = stocks, factors = fac, end_date = end_date, count = count)[fac]
            fac_data = fac_data.shift(self.shift_days).dropna()
            fac_data = fac_data.reset_index()
            fac_data.melt(id_vars=["index"], 
                            var_name="code", 
                            value_name=fac)
            fac_data.rename({'index':'time'}, axis=1, , inplace=True)
            
            stock_data = pd.merge(stock_data, fac_data, on=['time', 'code'], how='left')
        
        # save the data
            
        
    def cal_return(self, stock_data):
        for pe in self.period:
            shift_days = 60 if pe == 'month_3' else 250 if pe == 'year_1' else 63
            stock_data[pe+'_return'] = stock_data.groupby(['code']).shift(shift_days)['close']
            stock_data[pe+'_return'] = (stock_data['close'] - stock_data[pe+'_return']) / stock_data[pe+'_return']
            stock_data = stock_data.dropna()
        
        return stock_data
    
    