'''
Created on 15 Aug 2017

@author: MetalInvest
'''
try:
    from kuanke.user_space_api import *      
except ImportError as ie:
    print(str(ie))
from jqdata import *    
import numpy as np
import pandas as pd
from enum import Enum 
from kBarProcessor import *

# class KBarStatus(Enum):
#     upTrendNode = (1, 0)
#     upTrend = (1, 1)
#     downTrendNode = (-1, 0)
#     downTrend = (-1, 1)

class StatusCombo(Enum):
    @staticmethod
    def matchStatus(*parameters):
        pass

class LongPivotCombo(StatusCombo):
    downNodeDownNode = (KBarStatus.downTrendNode, KBarStatus.downTrendNode) # (-1, 0) (-1, 0)
    downNodeUpTrend = (KBarStatus.downTrendNode, KBarStatus.upTrend)      # (-1, 0) (1, 1)
    downNodeUpNode = (KBarStatus.downTrendNode, KBarStatus.upTrendNode)   # (-1, 0) (1, 0)
    @staticmethod
    def matchStatus(*params): # at least two parameters
        first = params[0]
        second = params[1]
        if (first == LongPivotCombo.downNodeDownNode.value[0] or \
        first == LongPivotCombo.downNodeUpNode.value[0] or \
        first == LongPivotCombo.downNodeUpTrend.value[0]) and \
        (second == LongPivotCombo.downNodeDownNode.value[1] or \
         second == LongPivotCombo.downNodeUpNode.value[1] or \
         second == LongPivotCombo.downNodeUpTrend.value[1]):
            return True
        return False

class ShortPivotCombo(StatusCombo):
    upNodeUpNode = (KBarStatus.upTrendNode, KBarStatus.upTrendNode)     # (1, 0) (1, 0)
    upNodeDownTrend = (KBarStatus.upTrendNode, KBarStatus.downTrend)      # (1, 0) (-1, 1)
    upNodeDownNode = (KBarStatus.upTrendNode, KBarStatus.downTrendNode)   # (1, 0) (-1, 0)
    @staticmethod
    def matchStatus(*params): # at least two parameters
        first = params[0]
        second = params[1]
        if (first == ShortPivotCombo.upNodeUpNode.value[0] or \
        first == ShortPivotCombo.upNodeDownTrend.value[0] or \
        first == ShortPivotCombo.upNodeDownNode.value[0]) and \
        (second == ShortPivotCombo.upNodeUpNode.value[1] or \
         second == ShortPivotCombo.upNodeDownTrend.value[1] or \
         second == ShortPivotCombo.upNodeDownNode.value[1]):
            return True
        return False

class ShortStatusCombo(StatusCombo):
    downTrendDownTrend = (KBarStatus.downTrend, KBarStatus.downTrend)         # (-1, 1) (-1, 1)
    downTrendDownNode = (KBarStatus.downTrend, KBarStatus.downTrendNode)    # (-1, 1) (-1, 0)
    downNodeDownTrend = (KBarStatus.downTrendNode, KBarStatus.downTrend) # (-1, 0) (-1, 1)
    @staticmethod
    def matchStatus(*params): # at least two parameters
        first = params[0]
        second = params[1]
        if (first == ShortStatusCombo.downTrendDownTrend.value[0] or \
        first == ShortStatusCombo.downTrendDownNode.value[0] or \
        first == ShortStatusCombo.downNodeDownTrend.value[0]) and \
        (second == ShortStatusCombo.downTrendDownTrend.value[1] or \
         second == ShortStatusCombo.downTrendDownNode.value[1] or \
         second == ShortStatusCombo.downNodeDownTrend.value[1]):
            return True
        return False
    
class LongStatusCombo(StatusCombo):
    upTrendUpTrend = (KBarStatus.upTrend, KBarStatus.upTrend)             # (1, 1) (1, 1)
    upTrendUpNode = (KBarStatus.upTrend, KBarStatus.upTrendNode)        # (1, 1) (1, 0)
    upNodeUpTrend = (KBarStatus.upTrendNode, KBarStatus.upTrend)         # (1, 0) (1, 1)
    @staticmethod
    def matchStatus(*params): # at least two parameters
        first = params[0]
        second = params[1]
        if (first == LongStatusCombo.upTrendUpTrend.value[0] or \
        first == LongStatusCombo.upTrendUpNode.value[0] or \
        first == LongStatusCombo.upNodeUpTrend.value[0]) and \
        (second == LongStatusCombo.upTrendUpTrend.value[1] or \
         second == LongStatusCombo.upTrendUpNode.value[1] or \
         second == LongStatusCombo.upNodeUpTrend.value[1]):
            return True
        return False

class StatusQueCombo(StatusCombo):
    downTrendUpNode = (KBarStatus.downTrend, KBarStatus.upTrendNode)# (-1, 1) (1, 0)
    downTrendUpTrend = (KBarStatus.downTrend, KBarStatus.upTrend)   # (-1, 1) (1, 1)
    upTrendDownNode = (KBarStatus.upTrend, KBarStatus.downTrendNode)# (1, 1) (-1, 0)
    upTrendDownTrend = (KBarStatus.upTrend, KBarStatus.downTrend)   # (1, 1) (-1, 1)  
    
class ChanMatrix(object):
    '''
    classdocs
    '''
    gauge_level = ['5d', '1d', '30m']
    
    def __init__(self, stockList, isAnal=False):
        '''
        Constructor
        '''
        self.isAnal=isAnal
        self.count = 15 # 30
        self.stockList = stockList
        self.trendNodeMatrix = pd.DataFrame(index=self.stockList, columns=ChanMatrix.gauge_level)
    
    def gaugeStockList(self, l=None):
        self.updateGaugeStockList(levels=ChanMatrix.gauge_level if not l else l)
        
    def updateGaugeStockList(self, levels, newStockList=None):
        candidate_list = newStockList if newStockList else self.stockList
        for stock in candidate_list:
            sc = self.gaugeStock_analysis(stock, levels) if self.isAnal else self.gaugeStock(stock, levels)
            for (level, s) in zip(levels, sc):
                self.trendNodeMatrix.loc[stock, level] = s
    
    def removeGaugeStockList(self, to_be_removed):
        self.trendNodeMatrix.drop(to_be_removed, inplace=True)
        
    def getGaugeStockList(self, stock_list):
        return self.trendNodeMatrix.loc[stock_list]
    
    def appendStockList(self, stock_list_df):
        self.trendNodeMatrix=self.trendNodeMatrix.append(stock_list_df, verify_integrity=True)
        
    def gaugeStock(self, stock, levels):
        gaugeList = []
        for level in levels:
            stock_df = attribute_history(stock, self.count, level, fields = ['open','close','high','low'], skip_paused=True, df=True)
            kb = KBarProcessor(stock_df)
            gaugeList.append(kb.gaugeStatus())
        return gaugeList

    def gaugeStock_analysis(self, stock, levels):
        print("retrieving data using get_price!!!")
        gaugeList = []
        for level in levels:
            latest_trading_day = get_trade_days()[-1]
            stock_df = get_price(stock, count=self.count, end_date=latest_trading_day, frequency=level, fields = ['open','close','high','low'], skip_paused=True)
            kb = KBarProcessor(stock_df)
            gaugeList.append(kb.gaugeStatus())
        return gaugeList
    
    def displayMonitorMatrix(self, stock_list=None):
        print(self.trendNodeMatrix.loc[stock_list] if stock_list else self.trendNodeMatrix)
                
    def filterLongPivotCombo(self, stock_list=None, level_list=None, update_df=False):
        return self.filterCombo_sup(LongPivotCombo.matchStatus, stock_list, level_list, update_df)  
    
    def filterShortPivotCombo(self, stock_list=None, level_list=None, update_df=False):
        return self.filterCombo_sup(ShortPivotCombo.matchStatus, stock_list, level_list, update_df)
    
    def filterLongStatusCombo(self, stock_list=None, level_list=None, update_df=False):
        return self.filterCombo_sup(LongStatusCombo.matchStatus, stock_list, level_list, update_df)
    
    def filterShortStatusCombo(self, stock_list=None, level_list=None, update_df=False):
        return self.filterCombo_sup(ShortStatusCombo.matchStatus, stock_list, level_list, update_df)

    def filterCombo_sup(self, filter_method, stock_list=None, level_list=None, update_df=False):
        # two column per layer
        working_df = self.trendNodeMatrix.loc[stock_list] if stock_list else self.trendNodeMatrix # slice rows by input
        working_level = [l1 for l1 in ChanMatrix.gauge_level if l1 in level_list] if level_list else ChanMatrix.gauge_level
        for i in range(len(working_level)-1): #xrange
            if working_df.empty:
                break
            high_level = working_level[i]
            low_level = working_level[i+1]
            mask = working_df[[high_level,low_level]].apply(lambda x: filter_method(*x), axis=1)
            working_df = working_df[mask]
        if update_df:
            self.trendNodeMatrix = working_df
            self.stockList=list(working_df.index)
        return list(working_df.index)