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
from biaoLiStatus import * 
from kBarProcessor import *

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
        self.stockList = list(self.trendNodeMatrix.index)
        
    def getGaugeStockList(self, stock_list):
        return self.trendNodeMatrix.loc[stock_list]
    
    def appendStockList(self, stock_list_df):
        to_append = [stock for stock in stock_list_df.index if stock not in self.trendNodeMatrix.index]
        self.trendNodeMatrix=self.trendNodeMatrix.append(stock_list_df.loc[to_append], verify_integrity=True)
        self.stockList = list(self.trendNodeMatrix.index)
        
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