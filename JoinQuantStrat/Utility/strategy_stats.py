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
    new_stats_columns = ['order_id','timestamp', 'trade_action', 'trade_type', 'stock', 'trade_value', 'biaoli_status', 'TA_signal', 'TA_period']
    old_stats_columns = ['order_id','timestamp', 'stock', 'biaoli_status_long', 'TA_signal_long', 'TA_period_long', 'biaoli_status_short', 'TA_signal_short', 'TA_period_short', 'pnl']
    def __init__(self):
        self.open_pos = pd.DataFrame(columns=StrategyStats.new_stats_columns)
        self.closed_pos = pd.DataFrame(columns=StrategyStats.old_stats_columns)
        
    def getOrderPnl(self, close_record):
        stocks_to_be_closed = close_record['stock'].values
        close_record.drop('trade_action', axis=1, inplace=True)
        close_record.drop('trade_type', axis=1, inplace=True)
        
        to_be_closed_pos = self.open_pos.loc[self.open_pos['stock'].isin(stocks_to_be_closed), ['stock','trade_value', 'biaoli_status', 'TA_signal', 'TA_period']]
        close_record = pd.merge(close_record, to_be_closed_pos, how='left', on='stock', suffixes=('_short', '_long'))
        close_record['pnl'] = (close_record['trade_value_short'] - close_record['trade_value_long']) / close_record['trade_value_long']
        close_record.drop('trade_value_short', axis=1, inplace=True)
        close_record.drop('trade_value_long', axis=1, inplace=True)
        return close_record
    
    def getPnL(self, record):
        open_record = record[record['trade_action']=='open']
        if not open_record.empty:
            self.open_pos = self.open_pos.append(open_record)
        
        closed_record = record[record['trade_action']=='close']
        if not closed_record.empty:
            close_record = self.getOrderPnl(closed_record)
            self.open_pos = self.open_pos.loc[-self.open_pos['stock'].isin(close_record['stock'].values)]
            self.closed_pos = self.closed_pos.append(close_record)
            
    def convertRecord(self, order_record):
        # trade_record contains dict with order as key tuple of biaoli and TA signal as value
        # output pandas dataframe contains all orders processed
        list_of_series = []
        for order, condition in order_record:
            if order.status == OrderStatus.held:
                order_id = order.order_id
                order_tms = np.datetime64(order.add_time) 
                order_value = order.price * order.filled
                order_action = order.action
                order_side = order.side
                order_stock = order.security
                BL_status, TA_type, TA_period = condition
                pd_series = pd.Series([order_id, order_tms, order_action, order_side, order_stock, order_value, BL_status, TA_type, TA_period],index=StrategyStats.new_stats_columns)
                list_of_series += [pd_series]
        df = pd.DataFrame(list_of_series, columns=StrategyStats.new_stats_columns)
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
    
    