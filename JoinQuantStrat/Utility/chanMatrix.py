'''
Created on 15 Aug 2017

@author: MetalInvest
'''
from kuanke.user_space_api import *
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
    @classmethod
    def matchStatus(self, *parameters):
        pass

class LongPivotCombo(StatusCombo):
    downNodeDownNode = (KBarStatus.downTrendNode, KBarStatus.downTrendNode) # (-1, 0) (-1, 0)
    downNodeUpTrend = (KBarStatus.downTrendNode, KBarStatus.upTrend)      # (-1, 0) (1, 0)
    downNodeUpNode = (KBarStatus.downTrendNode, KBarStatus.upTrendNode)   # (-1, 0) (1, 1)
    @classmethod
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
    upNodeDownTrend = (KBarStatus.upTrendNode, KBarStatus.downTrend)      # (1, 0) (-1, 0)
    upNodeDownNode = (KBarStatus.upTrendNode, KBarStatus.downTrendNode)   # (1, 0) (-1, 0)

class ShortStatusCombo(StatusCombo):
    downTrendDownTrend = (KBarStatus.downTrend, KBarStatus.downTrend)         # (-1, 1) (-1, 1)
    downTrendDownNode = (KBarStatus.downTrend, KBarStatus.downTrendNode)    # (-1, 1) (-1, 0)
    downNodeDownTrend = (KBarStatus.downTrendNode, KBarStatus.downTrend) # (-1, 0) (-1, 1)
    
class LongStatusCombo(StatusCombo):
    upTrendUpTrend = (KBarStatus.upTrend, KBarStatus.upTrend)             # (1, 1) (1, 1)
    upTrendUpNode = (KBarStatus.upTrend, KBarStatus.upTrendNode)        # (1, 1) (1, 0)
    upNodeUpTrend = (KBarStatus.upTrendNode, KBarStatus.upTrend)         # (1, 0) (1, 1)

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
    
    def __init__(self, stockList):
        '''
        Constructor
        '''
        self.count = 30
        self.stockList = stockList
        self.trendNodeMatrix = pd.DataFrame(index=self.stockList, columns=ChanMatrix.gauge_level)
    
    def gaugeStockList(self):
        for stock in self.stockList:
            sc = self.gaugeStock(stock, ChanMatrix.gauge_level)
            for (period,s) in zip(ChanMatrix.gauge_level, sc):
                self.trendNodeMatrix.loc[stock,period] = s
        
    def gaugeStock(self, stock, levels):
        gaugeList = []
        for level in levels:
            stock_df = attribute_history(stock, self.count, level, fields = ['open','close','high','low'], skip_paused=True, df=True)
            kb = KBarProcessor(stock_df)
            gaugeList.append(kb.gaugeStatus())
        return gaugeList
    
    def displayMonitorMatrix(self):
        print self.trendNodeMatrix
        
    def filterLongPivotCombo(self):
        # two column per layer
        working_df = self.trendNodeMatrix
        for i in xrange(len(ChanMatrix.gauge_level)-1): #2 
            if working_df.empty:
                break
            high_level = ChanMatrix.gauge_level[i]
            low_level = ChanMatrix.gauge_level[i+1]
#             working_df = working_df[((working_df[high_level]==LongPivotCombo.downNodeDownNode.value[0]) | \
#                                      (working_df[high_level]==LongPivotCombo.downNodeUpNode.value[0]) | \
#                                      (working_df[high_level]==LongPivotCombo.downNodeUpTrend.value[0])) & \
#                                      ((working_df[low_level]==LongPivotCombo.downNodeDownNode.value[1]) | \
#                                       (working_df[low_level]==LongPivotCombo.downNodeUpNode.value[1]) | \
#                                       (working_df[low_level]==LongPivotCombo.downNodeUpTrend.value[1]))]
            mask = working_df[[high_level,low_level]].apply(lambda x: LongPivotCombo.matchStatus(*x), axis=1)
            working_df = working_df[mask]
        return working_df