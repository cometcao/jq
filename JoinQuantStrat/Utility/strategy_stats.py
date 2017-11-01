'''
Created on 24 Oct 2017

@author: MetalInvest
'''
try:
    from kuanke.user_space_api import *         
except ImportError as ie:
    print(str(ie))
from jqdata import *
from biaoLiStatus import * 
from common_include import *
import numpy as np
import pandas as pd

class StrategyStats(object):
    '''
    class used to monitor/record all trades, and provide statistics. 
    Two Pandas dataframe kept at the same time, one for open position, one for closed position
    '''
    stats_columns = ['order_id','timestamp', 'trade_action', 'trade_type', 'stock', 'trade_price', 'biaoli_status', 'TA_signal', 'TA_period', 'pnl']
    def __init__(self):
        self.open_pos = None
        self.closed_pos = None
        
    def getOrderPnl(self, close_record):
        stocks_to_be_closed = close_record['stock'].values
        to_be_closed_pos = self.open_pos.loc[self.open_pos['stock'].isin(stocks_to_be_closed)]
        close_record['pnl'] = (close_record['trade_price'].values - to_be_closed_pos['trade_price'].values) / to_be_closed_pos['trade_price'].values
        self.open_pos = self.open_pos.loc[-self.open_pos['stock'].isin(stocks_to_be_closed)]
        return close_record
    
    def getPnL(self, record):
        open_record = record[record['trade_action']=='open']
        if not open_record.empty:
            if self.open_pos is not None:
                self.open_pos = self.open_pos.append(open_record, verify_integrity=True)
            else:
                self.open_pos = open_record
        
        closed_record = record[record['trade_action']=='close']
        if not closed_record.empty:
            if self.closed_pos is not None:
                self.closed_pos = self.closed_pos.append(self.getOrderPnl(closed_record), verify_integrity=True)
            else:
                self.closed_pos = self.getOrderPnl(closed_record)
            
    def convertRecord(self, order_record):
        # trade_record contains dict with order as key tuple of biaoli and TA signal as value
        # output pandas dataframe contains all orders processed
        list_of_series = []
        for order, condition in order_record:
            if order.status == OrderStatus.held:
                order_id = order.order_id
                order_tms = np.datetime64(order.add_time) 
                order_price = order.price
                order_action = order.action
                order_side = order.side
                order_stock = order.security
                BL_status, TA_type, TA_period = condition
                pnl = 0
                pd_series = pd.Series([order_id, order_tms, order_action, order_side, order_stock, order_price, BL_status, TA_type, TA_period, pnl],index=StrategyStats.stats_columns)
                list_of_series += [pd_series]
        df = pd.DataFrame(list_of_series, columns=StrategyStats.stats_columns)
        df.set_index(StrategyStats.stats_columns[:2], verify_integrity=True,inplace=True)
        return df
    
    def processOrder(self, order_record):
        if order_record:
            record = self.convertRecord(order_record)
            self.getPnL(record)
    
    def displayRecords(self):    
        print self.open_pos
        print self.closed_pos
        pass
    
    def getStats(self):
        pass
    
    