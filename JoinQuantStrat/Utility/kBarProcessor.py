# -*- encoding: utf8 -*-
'''
Created on 1 Aug 2017

@author: MetalInvest
'''
# from kuanke.user_space_api import *
from jqdata import *
import numpy as np
import copy
from enum import Enum 

class InclusionType(Enum):
    # output: 0 = no inclusion, 1 = first contains second, 2 second contains first
    noInclusion = 0
    firstCsecond = 2
    secondCfirst = 3
    
class TopBotType(Enum):
    noTopBot = 0
    top = 1
    bot = -1

class KBarStatus(Enum):
    upTrendNode = (1, 0)
    upTrend = (1, 1)
    downTrendNode = (-1, 0)
    downTrend = (-1, 1)

def synchOpenPrice(open, close, high, low):
    if open > close:
        return high
    else:
        return low

def synchClosePrice(open, close, high, low):
    if open < close:
        return high
    else:
        return low    

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
    
    def synchOpenClosePrice(self):
        self.kDataFrame_modified['open'] = self.kDataFrame_modified.apply(lambda row: synchOpenPrice(row['open'], row['close'], row['high'], row['low']), axis=1)
        self.kDataFrame_modified['close'] = self.kDataFrame_modified.apply(lambda row: synchClosePrice(row['open'], row['close'], row['high'], row['low']), axis=1)        
    
    def checkInclusive(self, first, second):
        # output: 0 = no inclusion, 1 = first contains second, 2 second contains first
        isInclusion = InclusionType.noInclusion
        first_high = first.high if np.isnan(first.new_high) else first.new_high
        second_high = second.high if np.isnan(second.new_high) else second.new_high
        first_low = first.low if np.isnan(first.new_low) else first.new_low
        second_low = second.low if np.isnan(second.new_low) else second.new_low
        
        if first_high <= second_high and first_low >= second_low:
            isInclusion = InclusionType.firstCsecond
        elif first_high >= second_high and first_low <= second_low:
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
            firstElem = self.kDataFrame_modified.iloc[idx+1]
            secondElem = self.kDataFrame_modified.iloc[idx+2]
            if self.checkInclusive(firstElem, secondElem) != InclusionType.noInclusion:
                trend = self.kDataFrame_modified.ix[idx+1,'trend_type'] if not np.isnan(self.kDataFrame_modified.ix[idx+1,'trend_type']) else self.isBullType(currentElem, firstElem)
                if trend:
                    self.kDataFrame_modified.ix[idx+2,'new_high']=max(firstElem.high if np.isnan(firstElem.new_high) else firstElem.new_high, secondElem.high if np.isnan(secondElem.new_high) else secondElem.new_high)
                    self.kDataFrame_modified.ix[idx+2,'new_low']=max(firstElem.low if np.isnan(firstElem.new_low) else firstElem.new_low, secondElem.low if np.isnan(secondElem.new_low) else secondElem.new_low)
                    pass
                else: 
                    self.kDataFrame_modified.ix[idx+2,'new_high']=min(firstElem.high if np.isnan(firstElem.new_high) else firstElem.new_high, secondElem.high if np.isnan(secondElem.new_high) else secondElem.new_high)
                    self.kDataFrame_modified.ix[idx+2,'new_low']=min(firstElem.low if np.isnan(firstElem.new_low) else firstElem.new_low, secondElem.low if np.isnan(secondElem.new_low) else secondElem.new_low)
                    pass
                self.kDataFrame_modified.ix[idx+2,'trend_type']=trend
                self.kDataFrame_modified.ix[idx+1,'new_high']=np.nan
                self.kDataFrame_modified.ix[idx+1,'new_low']=np.nan
            else:
                if np.isnan(self.kDataFrame_modified.ix[idx+1,'new_high']): 
                    self.kDataFrame_modified.ix[idx+1,'new_high'] = firstElem.high 
                if np.isnan(self.kDataFrame_modified.ix[idx+1,'new_low']): 
                    self.kDataFrame_modified.ix[idx+1,'new_low'] = firstElem.low
                self.kDataFrame_modified.ix[idx+2,'new_high'] = secondElem.high
                self.kDataFrame_modified.ix[idx+2,'new_low'] = secondElem.low

        self.kDataFrame_modified['high'] = self.kDataFrame_modified['new_high']
        self.kDataFrame_modified['low'] = self.kDataFrame_modified['new_low']

        self.kDataFrame_modified = self.kDataFrame_modified[np.isfinite(self.kDataFrame_modified['high'])]
        self.kDataFrame_modified = self.kDataFrame_modified.drop('new_high', 1)
        self.kDataFrame_modified = self.kDataFrame_modified.drop('new_low', 1)
        self.kDataFrame_modified = self.kDataFrame_modified.drop('trend_type', 1)
        self.synchOpenClosePrice()
        return self.kDataFrame_modified
    
    def checkTopBot(self, current, first, second):
        if first.high > current.high and first.high > second.high:
            return TopBotType.top
        elif first.low < current.low and first.low < second.low:
            return TopBotType.bot
        else:
            return TopBotType.noTopBot
        
    def markTopBot(self):
        self.kDataFrame_modified = self.kDataFrame_modified.assign(tb=TopBotType.noTopBot)
        # This function assume we have done the standardization process (no inclusion)
        for idx in xrange(self.kDataFrame_modified.shape[0]-2):
            currentElem = self.kDataFrame_modified.iloc[idx]
            firstElem = self.kDataFrame_modified.iloc[idx+1]
            secondElem = self.kDataFrame_modified.iloc[idx+2]
            topBotType = self.checkTopBot(currentElem, firstElem, secondElem)
            if topBotType != TopBotType.noTopBot:
                self.kDataFrame_modified.ix[idx+1, 'tb'] = topBotType

    def defineBi(self):
        self.kDataFrame_modified = self.kDataFrame_modified.assign(new_index=[i for i in xrange(len(self.kDataFrame_modified))])
        working_df = self.kDataFrame_modified[self.kDataFrame_modified['tb']!=TopBotType.noTopBot]
#         print working_df
        currentStatus = firstStatus = TopBotType.noTopBot
        i = 0
        markedIndex = i + 1
        while i < working_df.shape[0]-1:
            currentFenXing = working_df.iloc[i]
            if markedIndex > working_df.shape[0]-1:
                break
            firstFenXing = working_df.iloc[markedIndex]
            
            currentStatus = TopBotType.bot if currentFenXing.tb == TopBotType.bot else TopBotType.top
            firstStatus = TopBotType.bot if firstFenXing.tb == TopBotType.bot else TopBotType.top
        
            if currentStatus == firstStatus:
                if currentStatus == TopBotType.top:
                    if currentFenXing['high'] < firstFenXing['high']:
                        working_df.ix[i,'tb'] = TopBotType.noTopBot
                        i = markedIndex
                        markedIndex = i+1
                        continue
                    else:
                        working_df.ix[markedIndex,'tb'] = TopBotType.noTopBot
                        i = markedIndex+1
                        markedIndex = i+1
                        continue
                elif currentStatus == TopBotType.bot:
                    if currentFenXing['low'] > firstFenXing['low']:
                        working_df.ix[i,'tb'] = TopBotType.noTopBot
                        i = markedIndex
                        markedIndex = i+1
                        continue
                    else:
                        working_df.ix[markedIndex,'tb'] = TopBotType.noTopBot
                        i = markedIndex+1
                        markedIndex = i+1
                        continue
            else: 
                # possible BI status 1 check top high > bot low 2 check more than 3 bars (strict BI) in between
                enoughKbarGap = (working_df.ix[markedIndex,'new_index'] - working_df.ix[i,'new_index']) >= 4
                if enoughKbarGap:
                    if currentStatus == TopBotType.top and currentFenXing['high'] > firstFenXing['low']:
                        pass
                    elif currentStatus == TopBotType.top and currentFenXing['high'] <= firstFenXing['low']:
                        working_df.ix[i,'tb'] = TopBotType.noTopBot
                    elif currentStatus == TopBotType.bot and currentFenXing['low'] < firstFenXing['high']:
                        pass
                    elif currentStatus == TopBotType.bot and currentFenXing['low'] >= firstFenXing['high']:
                        working_df.ix[i,'tb'] = TopBotType.noTopBot
                else:
                    working_df.ix[markedIndex,'tb'] = TopBotType.noTopBot
                    markedIndex += 1
                    continue # don't increment i
            i+=1
            markedIndex = i+1
        self.kDataFrame_modified = working_df[working_df['tb']!=TopBotType.noTopBot]
    
    def getCurrentKBarStatus(self):
        #  at Top or Bot FenXing
#         print self.kDataFrame_modified
        if self.kDataFrame_modified.ix[-1, 'new_index'] == self.kDataFrame_origin.shape[0]-2:
            if self.kDataFrame_modified.ix[-1,'tb'] == TopBotType.top:
                return KBarStatus.downTrendNode
            else:
                return KBarStatus.upTrendNode
        else:
            if self.kDataFrame_modified.ix[-1,'tb'] == TopBotType.top:
                return KBarStatus.downTrend
            else:
                return KBarStatus.upTrend
        
    