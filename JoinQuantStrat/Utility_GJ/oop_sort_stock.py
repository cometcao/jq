# -*- encoding: utf8 -*-
'''
Created on 4 Dec 2017

@author: MetalInvest
'''
from oop_strategy_frame import *
from oop_select_stock import Filter_stock_list

# '''------------------截取欲购股票数-----------------'''
class Filter_buy_count(Filter_stock_list):
    def __init__(self, params):
        self.buy_count = params.get('buy_count', 3)

    def update_params(self, context, params):
        self.buy_count = params.get('buy_count', self.buy_count)

    def filter(self, context, data, stock_list):
        if len(stock_list) > self.buy_count:
            return stock_list[:self.buy_count]
        else:
            return stock_list

    def __str__(self):
        return '获取最终待购买股票数:[ %d ]' % (self.buy_count)
