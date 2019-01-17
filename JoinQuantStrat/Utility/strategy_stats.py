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
    new_stats_columns = ['order_id','timestamp', 
                         'trade_action', 'trade_type', 
                         'stock', 'trade_value', 
                         'biaoli_status', 'TA_signal', 'TA_period']
    old_stats_columns = ['order_id','timestamp', 'stock', 
                         '5d_status_long','1d_status_long', '60m_status_long', 
                         'TA_signal_long', 'TA_period_long', 
                         '5d_status_short','1d_status_short','60m_status_short', 
                         'TA_signal_short', 'TA_period_short', 'pnl']
    def __init__(self):
        self.open_pos = pd.DataFrame(columns=StrategyStats.new_stats_columns)
        self.closed_pos = pd.DataFrame(columns=StrategyStats.old_stats_columns)
        
    def getOrderPnl(self, close_record, context):
        stocks_to_be_closed = close_record['stock'].values
        close_record.drop('trade_action', axis=1, inplace=True)
        close_record.drop('trade_type', axis=1, inplace=True)
        
        to_be_closed_pos = self.open_pos.loc[self.open_pos['stock'].isin(stocks_to_be_closed), ['stock','trade_value', 'biaoli_status', 'TA_signal', 'TA_period']]
        if to_be_closed_pos.empty: # if data corrupted return empty
            return (None, None)
        close_record = pd.merge(close_record, to_be_closed_pos, how='left', on='stock', suffixes=('_short', '_long'))
        close_record['pnl'] = (close_record['trade_value_short'] - close_record['trade_value_long']) / close_record['trade_value_long']
#         print close_record
#         print to_be_closed_pos
#         print self.open_pos
        long_values = close_record.biaoli_status_long.values
        close_record[['5d_status_long','1d_status_long', '60m_status_long']] = pd.DataFrame(long_values.tolist())
        short_values = close_record.biaoli_status_short.values
        close_record[['5d_status_short','1d_status_short', '60m_status_short']] = pd.DataFrame(short_values.tolist())
#         close_record.drop('trade_value_short', axis=1, inplace=True)
        close_record.drop('trade_value_long', axis=1, inplace=True)
        close_record.drop('biaoli_status_short', axis=1, inplace=True)
        close_record.drop('biaoli_status_long', axis=1, inplace=True)
        close_record['in_pos'] = close_record.apply(lambda row: self.check_stock_in_pos(row['stock'], context), axis=1)
        return (close_record[close_record['in_pos']==False][StrategyStats.old_stats_columns],
                close_record[close_record['in_pos']==True][StrategyStats.old_stats_columns+['trade_value_short']])
    
    def getPnL(self, record, context):
        open_record = record[record['trade_action']=='open']
        if not open_record.empty:
            self.open_pos = self.open_pos.append(open_record)
            self.open_pos = self.open_pos.groupby('stock').agg({
                                                                'order_id':'first',
                                                                'timestamp':'first',
                                                                'stock':'first',
                                                                'trade_action':'first',
                                                                'trade_type':'first',
                                                                'trade_value':np.sum,
                                                                'biaoli_status':'first', 
                                                                'TA_signal':'first', 
                                                                'TA_period':'first'
                                                                })
            self.open_pos.reset_index(drop=True, inplace=True)
        
        closed_record = record[record['trade_action']=='close']
        if not closed_record.empty:
            close_record, deduct_record = self.getOrderPnl(closed_record, context)
            if close_record is not None:
                self.open_pos = self.open_pos.loc[-self.open_pos['stock'].isin(close_record['stock'].values)]
                self.closed_pos = self.closed_pos.append(close_record)
                self.closed_pos.reset_index(drop=True, inplace=True)
            if deduct_record is not None:
                self.open_pos.loc[self.open_pos['stock'].isin(deduct_record['stock'].values), 'trade_value'] = \
                    self.open_pos.loc[self.open_pos['stock'].isin(deduct_record['stock'].values), 'trade_value'] - deduct_record['trade_value_short']
            
    def check_stock_in_pos(self, stock, context):
        return stock in context.portfolio.positions
            
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
                try:
                    BL_status = [item.value if item is not None else (np.nan,np.nan) for item in BL_status]
                except Exception as e:
                    print (str(e))
                    print (condition)
                    BL_status = [(np.nan,np.nan),(np.nan,np.nan),(np.nan,np.nan)]
#                 if BL_status is None or len(BL_status) != 3 \
#                     or BL_status == [(np.nan,np.nan),(np.nan,np.nan),(np.nan,np.nan)]: # hack
#                     BL_status = [(np.nan,np.nan),(np.nan,np.nan),(np.nan,np.nan)]
#                 else:
#                     BL_status = [item.value if item is not None else (np.nan,np.nan) for item in BL_status]
                    
                if TA_type is not None:
                    TA_type = TA_type.value
                pd_series = pd.Series([order_id, order_tms, order_action, order_side, order_stock, order_value, BL_status, TA_type, TA_period],index=StrategyStats.new_stats_columns)
                list_of_series += [pd_series]
        df = pd.DataFrame(list_of_series, columns=StrategyStats.new_stats_columns)
        return df
    
    def processOrder(self, order_record, context):
        if order_record:
            record = self.convertRecord(order_record)
            self.getPnL(record, context)
    
    def displayRecords(self):    
        print (self.open_pos)
        self.getStats()
        print (self.closed_pos[self.closed_pos['TA_signal_long']==TaType.RSI.value])
        print (self.closed_pos[self.closed_pos['TA_signal_long']==TaType.KDJ_CROSS.value])
    
    def getStats(self):
        self.closed_pos['pnl_sign'] = np.sign(self.closed_pos.pnl)
        # success rate on each long/short condition
#         print (self.closed_pos[self.closed_pos['pnl_sign']>=0].groupby(self.closed_pos.biaoli_status_long.apply(tuple)).agg({'pnl_sign':sum}))
        print (self.closed_pos[['5d_status_long','1d_status_long','60m_status_long','pnl_sign']].groupby(('5d_status_long','1d_status_long','60m_status_long')).pnl_sign.value_counts())
        print (self.closed_pos[['5d_status_short','1d_status_short','60m_status_short','pnl_sign']].groupby(('5d_status_short','1d_status_short','60m_status_short')).pnl_sign.value_counts())
        print (self.closed_pos[['TA_signal_long', 'TA_period_long', 'pnl_sign']].groupby(('TA_signal_long', 'TA_period_long')).pnl_sign.value_counts())
        print (self.closed_pos[['TA_signal_short', 'TA_period_short','pnl_sign']].groupby(('TA_signal_short', 'TA_period_short')).pnl_sign.value_counts()) #
        self.closed_pos.drop('pnl_sign', axis=1, inplace=True)
        
        
    
    