'''
Created on 19 Sep 2016

@author: MetalInvest
'''

import math
import datetime
import numpy as np
import pandas as pd
from jqdata import *

class MyClass(object):
    '''
    Assume: we have defined stock domain, feasible stocks, on daily frequency
    This strategy takes all stocks in the domain and work out the one(s)
    with least market cap. 
    Use RSI on domain index to verify the timing(low point)
    By std of the market cap, list out the minumum ones
    '''


    def __init__(self, context, data, gl):
        '''
        Constructor
        '''
        self.context = context
        self.data = data
        self.gl = gl
        
    def check_timing(self):
        pass
    
    def buy_signal_list(self):
        
        df = get_fundamentals(query(
            valuation, income
        ).filter(
            # 这里不能使用 in 操作, 要使用in_()函数
            valuation.code.in_(gl.feasible_stocks)
        ), date='2015-10-15')
        
    
    def sell_signal_list(self):
        pass