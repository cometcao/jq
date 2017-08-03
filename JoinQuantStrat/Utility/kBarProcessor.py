# -*- encoding: utf8 -*-
'''
Created on 1 Aug 2017

@author: MetalInvest
'''
# from kuanke.user_space_api import *
from jqdata import *
import numpy as np
import copy
from drawKChart import drawKChart
from enum import Enum 

class InclusionType(Enum):
    # output: 0 = no inclusion, 1 = first contains second, 2 second contains first
    noInclusion = 0
    firstCsecond = 2
    secondCfirst = 3
    
class KBarProcessor(object):
    '''
    This lib takes financial instrument data, and process it according the Chan(Zen) theory
    We need at least 100 K-bars in each input data set
    '''
    def __init__(self, kDf):
        '''
        dataframe input must contain open, close, high, low columns
        '''
        self.kDataFrame_origin = kDf
        self.kDataFrame_modified = copy.deepcopy(kDf)
        self.kDataFrame_modified = self.kDataFrame_modified.assign(new_high=np.nan, new_low=np.nan, trend_type=np.nan)
    
    def checkInclusive(self, first, second):
        # output: 0 = no inclusion, 1 = first contains second, 2 second contains first
        isInclusion = InclusionType.noInclusion
        if first.high <= second.high and first.low >= second.low:
            isInclusion = InclusionType.firstCsecond
        elif first.high >= second.high and first.low <= second.low:
            isInclusion = InclusionType.secondCfirst
        return isInclusion
    
    def isBullType(self, first, second): 
        # this is assuming first second aren't inclusive
        isBull = False
        if first.high < second.high:
            isBull = True
        return isBull
        
    
    def standardize(self):
        # 1. We need to make sure we start with first two K-bars without inclusive relationship
        # drop the first if there is inclusion, and check again
        while self.kDataFrame_modified.shape[0] > 2:
            firstElem = self.kDataFrame_modified.iloc[0]
            secondElem = self.kDataFrame_modified.iloc[1]
            if self.checkInclusive(firstElem, secondElem) != InclusionType.noInclusion:
                self.kDataFrame_modified.drop(self.kDataFrame_modified.index[0], inplace=True)
                pass
            else:
                self.kDataFrame_modified.ix[0,'new_high'] = firstElem.high
                self.kDataFrame_modified.ix[0,'new_low'] = firstElem.low
                break
            
        # 2. loop through the whole data set and process inclusive relationship
        for idx in xrange(self.kDataFrame_modified.shape[0]-2):
            currentElem = self.kDataFrame_modified.iloc[idx]
            firstElem = self.kDataFrame_modified.ix[idx+1]
            secondElem = self.kDataFrame_modified.ix[idx+2]
            if self.checkInclusive(firstElem, secondElem) != InclusionType.noInclusion:
                trend = self.kDataFrame_modified.ix[idx+1,'trend_type'] if not np.isnan(self.kDataFrame_modified.ix[idx+1,'trend_type']) else self.isBullType(currentElem, firstElem)
                if trend:
                    self.kDataFrame_modified.ix[idx+2,'new_high']=max(firstElem.high, secondElem.high)
                    self.kDataFrame_modified.ix[idx+2,'new_low']=max(firstElem.low, secondElem.low)
                    pass
                else: 
                    self.kDataFrame_modified.ix[idx+2,'new_high']=min(firstElem.high, secondElem.high)
                    self.kDataFrame_modified.ix[idx+2,'new_low']=min(firstElem.low, secondElem.low)
                    pass
                self.kDataFrame_modified.ix[idx+2,'trend_type']=trend
                self.kDataFrame_modified.ix[idx+1,'new_high']=np.nan
                self.kDataFrame_modified.ix[idx+1,'new_low']=np.nan
            else:
                self.kDataFrame_modified.ix[idx+1,'new_high'] = firstElem.high
                self.kDataFrame_modified.ix[idx+1,'new_low'] = firstElem.low
                self.kDataFrame_modified.ix[idx+2,'new_high'] = secondElem.high
                self.kDataFrame_modified.ix[idx+2,'new_low'] = secondElem.low
        
        self.kDataFrame_modified['high'] = self.kDataFrame_modified['new_high']
        self.kDataFrame_modified['low'] = self.kDataFrame_modified['new_low']
        self.kDataFrame_modified = self.kDataFrame_modified[np.isfinite(self.kDataFrame_modified['high'])]
        self.kDataFrame_modified = self.kDataFrame_modified.drop('new_high', 1)
        self.kDataFrame_modified = self.kDataFrame_modified.drop('new_low', 1)
        self.kDataFrame_modified = self.kDataFrame_modified.drop('trend_type', 1)
        return self.kDataFrame_modified
    
    def markTopBot(self):
        
        pass
        

    def defineBi(self):
        pass
    
    