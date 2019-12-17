# -*- encoding: utf8 -*-
'''
Created on 1 Aug 2017

@author: MetalInvest
'''
# from kuanke.user_space_api import *
from jqdata import *
import numpy as np
import copy
from biaoLiStatus import * 

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
    def __init__(self, kDf, isdebug=False, clean_standardzed=False):
        '''
        dataframe input must contain open, close, high, low columns
        '''
        self.isdebug = isdebug
        self.clean_standardzed = clean_standardzed
        self.kDataFrame_origin = kDf
        self.kDataFrame_standardized = copy.deepcopy(kDf)
        self.kDataFrame_standardized = self.kDataFrame_standardized.assign(new_high=np.nan, new_low=np.nan, trend_type=np.nan)
        self.kDataFrame_marked = None
        self.gap_XD = []
    
    def synchForChart(self):
        self.kDataFrame_standardized = self.kDataFrame_standardized.drop('new_high', 1)
        self.kDataFrame_standardized = self.kDataFrame_standardized.drop('new_low', 1)
        self.kDataFrame_standardized = self.kDataFrame_standardized.drop('trend_type', 1)
        self.kDataFrame_standardized['open'] = self.kDataFrame_standardized.apply(lambda row: synchOpenPrice(row['open'], row['close'], row['high'], row['low']), axis=1)
        self.kDataFrame_standardized['close'] = self.kDataFrame_standardized.apply(lambda row: synchClosePrice(row['open'], row['close'], row['high'], row['low']), axis=1)        
    
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
        
    def standardize(self, initial_state=TopBotType.noTopBot):
        # 1. We need to make sure we start with first two K-bars without inclusive relationship
        # drop the first if there is inclusion, and check again
        if initial_state == TopBotType.noTopBot:
            while self.kDataFrame_standardized.shape[0] > 2:
                first_Elem = self.kDataFrame_standardized.iloc[0]
                second_Elem = self.kDataFrame_standardized.iloc[1]
                if self.checkInclusive(first_Elem, second_Elem) != InclusionType.noInclusion:
                    self.kDataFrame_standardized.drop(self.kDataFrame_standardized.index[0], inplace=True)
                    pass
                else:
                    self.kDataFrame_standardized.ix[0,'new_high'] = first_Elem.high
                    self.kDataFrame_standardized.ix[0,'new_low'] = first_Elem.low
                    break
        else:
            # given the initial state, make the first two bars non-inclusive, 
            # the first bar is confirmed as pivot, anything followed with inclusive relation 
            # will be merged into the first bar
            while self.kDataFrame_standardized.shape[0] > 2:
                first_Elem = self.kDataFrame_standardized.iloc[0]
                second_Elem = self.kDataFrame_standardized.iloc[1]
                if self.checkInclusive(first_Elem, second_Elem) != InclusionType.noInclusion:
                    if initial_state == TopBotType.bot:
                        self.kDataFrame_standardized.ix[0,'new_high'] = second_Elem.high
                        self.kDataFrame_standardized.ix[0,'new_low'] = first_Elem.low
                    elif initial_state == TopBotType.top:
                        self.kDataFrame_standardized.ix[0,'new_high'] = first_Elem.high
                        self.kDataFrame_standardized.ix[0,'new_low'] = second_Elem.low               
                    self.kDataFrame_standardized.drop(self.kDataFrame_standardized.index[1], inplace=True)                        
                else:
                    self.kDataFrame_standardized.ix[0,'new_high'] = first_Elem.high
                    self.kDataFrame_standardized.ix[0,'new_low'] = first_Elem.low
                    break                    

        # 2. loop through the whole data set and process inclusive relationship
        pastElemIdx = 0
        firstElemIdx = pastElemIdx+1
        secondElemIdx = firstElemIdx+1
        while secondElemIdx < self.kDataFrame_standardized.shape[0]: # xrange
            pastElem = self.kDataFrame_standardized.iloc[pastElemIdx]
            firstElem = self.kDataFrame_standardized.iloc[firstElemIdx]
            secondElem = self.kDataFrame_standardized.iloc[secondElemIdx]
            inclusion_type = self.checkInclusive(firstElem, secondElem)
            if inclusion_type != InclusionType.noInclusion:
                trend = firstElem.trend_type if not np.isnan(firstElem.trend_type) else self.isBullType(pastElem, firstElem)
                compare_func = max if trend else min
                if inclusion_type == InclusionType.firstCsecond:
                    secondElem.new_high=compare_func(firstElem.high if np.isnan(firstElem.new_high) else firstElem.new_high, secondElem.high if np.isnan(secondElem.new_high) else secondElem.new_high)
                    secondElem.new_low=compare_func(firstElem.low if np.isnan(firstElem.new_low) else firstElem.new_low, secondElem.low if np.isnan(secondElem.new_low) else secondElem.new_low)
                    secondElem.trend_type=trend
                    firstElem.new_high=np.nan
                    firstElem.new_low=np.nan
                    ############ manage index for next round ###########
                    firstElemIdx = secondElemIdx
                    secondElemIdx += 1
                else: 
                    firstElem.new_high=compare_func(firstElem.high if np.isnan(firstElem.new_high) else firstElem.new_high, secondElem.high if np.isnan(secondElem.new_high) else secondElem.new_high)
                    firstElem.new_low=compare_func(firstElem.low if np.isnan(firstElem.new_low) else firstElem.new_low, secondElem.low if np.isnan(secondElem.new_low) else secondElem.new_low)                        
                    firstElem.trend_type=trend
                    secondElem.new_high=np.nan
                    secondElem.new_low=np.nan
                    ############ manage index for next round ###########
                    secondElemIdx += 1
            else:
                if np.isnan(firstElem.new_high): 
                    firstElem.new_high = firstElem.high 
                if np.isnan(firstElem.new_low): 
                    firstElem.new_low = firstElem.low
                if np.isnan(secondElem.new_high): 
                    secondElem.new_high = secondElem.high
                if np.isnan(secondElem.new_low): 
                    secondElem.new_low = secondElem.low
                ############ manage index for next round ###########
                pastElemIdx = firstElemIdx
                firstElemIdx = secondElemIdx
                secondElemIdx += 1
                

        self.kDataFrame_standardized['high'] = self.kDataFrame_standardized['new_high']
        self.kDataFrame_standardized['low'] = self.kDataFrame_standardized['new_low']

        self.kDataFrame_standardized = self.kDataFrame_standardized[np.isfinite(self.kDataFrame_standardized['high'])]
        # lines below is for chart drawing
        if self.clean_standardzed:
            self.synchForChart()
        return self.kDataFrame_standardized
    
    def checkTopBot(self, current, first, second):
        if first.high > current.high and first.high > second.high:
            return TopBotType.top
        elif first.low < current.low and first.low < second.low:
            return TopBotType.bot
        else:
            return TopBotType.noTopBot
        
    def markTopBot(self, initial_state=TopBotType.noTopBot):
        self.kDataFrame_standardized = self.kDataFrame_standardized.assign(tb=TopBotType.noTopBot)
        if initial_state != TopBotType.noTopBot:
            felem = self.kDataFrame_standardized.iloc[0]
            selem = self.kDataFrame_standardized.iloc[1]
            if (initial_state == TopBotType.top and felem.high >= selem.high) or \
                (initial_state == TopBotType.bot and felem.low <= selem.low):
                self.kDataFrame_standardized.ix[0, 'tb'] = initial_state
            else:
                print("Incorrect initial state given!!!")
                
        # This function assume we have done the standardization process (no inclusion)
        for idx in range(self.kDataFrame_standardized.shape[0]-2): #xrange
            currentElem = self.kDataFrame_standardized.iloc[idx]
            firstElem = self.kDataFrame_standardized.iloc[idx+1]
            secondElem = self.kDataFrame_standardized.iloc[idx+2]
            topBotType = self.checkTopBot(currentElem, firstElem, secondElem)
            if topBotType != TopBotType.noTopBot:
                self.kDataFrame_standardized.ix[idx+1, 'tb'] = topBotType
        if self.isdebug:
            print(self.kDataFrame_standardized)

    def trace_back_index(self, working_df, previous_index):
        # find the closest FenXing with top/bot backwards from previous_index
        idx = previous_index-1
        while idx >= 0:
            fx = working_df.iloc[idx]
            if fx.tb == TopBotType.noTopBot:
                idx -= 1
                continue
            else:
                return idx
        if self.isdebug:
            print("We don't have previous valid FenXing")
        return None
        

    def defineBi(self):
        self.kDataFrame_standardized = self.kDataFrame_standardized.assign(new_index=[i for i in range(len(self.kDataFrame_standardized))])
        working_df = self.kDataFrame_standardized[self.kDataFrame_standardized['tb']!=TopBotType.noTopBot]
        
        ############################# clean up the base case for Bi definition ###########################
        firstIdx = 0
        while firstIdx < working_df.shape[0]-2:
            firstFenXing = working_df.iloc[firstIdx]
            secondFenXing = working_df.iloc[firstIdx+1]
            if firstFenXing.tb == secondFenXing.tb:
                working_df.ix[firstIdx,'tb'] = TopBotType.noTopBot
            elif secondFenXing.new_index - firstFenXing.new_index < 4:
                working_df.ix[firstIdx,'tb'] = TopBotType.noTopBot
            elif firstFenXing.tb == TopBotType.top and secondFenXing.tb == TopBotType.bot and firstFenXing.high <= secondFenXing.high:
                working_df.ix[firstIdx,'tb'] = TopBotType.noTopBot
            elif firstFenXing.tb == TopBotType.bot and secondFenXing.tb == TopBotType.top and firstFenXing.low >= secondFenXing.low:
                working_df.ix[firstIdx,'tb'] = TopBotType.noTopBot
            else:
                break
            firstIdx += 1
        #################################
#         print (working_df)
        working_df = working_df[working_df['tb']!=TopBotType.noTopBot]
        previous_index = 0
        current_index = previous_index + 1
        next_index = current_index + 1
        #################################
        while previous_index < working_df.shape[0]-2 and current_index < working_df.shape[0]-1 and next_index < working_df.shape[0]:
            previousFenXing = working_df.iloc[previous_index]
            currentFenXing = working_df.iloc[current_index]
            nextFenXing = working_df.iloc[next_index]
            
            if currentFenXing.tb == previousFenXing.tb:
                if currentFenXing.tb == TopBotType.top:
                    if currentFenXing['high'] < previousFenXing['high']:
                        working_df.ix[current_index,'tb'] = TopBotType.noTopBot
                        current_index = next_index
                        next_index +=1
                    else:
                        working_df.ix[previous_index,'tb'] = TopBotType.noTopBot
                        previous_index = self.trace_back_index(working_df, previous_index) #current_index # 
                        if previous_index is None:
                            previous_index = current_index
                            current_index = next_index
                            next_index += 1
                    continue
                elif currentFenXing.tb == TopBotType.bot:
                    if currentFenXing['low'] > previousFenXing['low']:
                        working_df.ix[current_index,'tb'] = TopBotType.noTopBot
                        current_index = next_index
                        next_index += 1
                    else:
                        working_df.ix[previous_index,'tb'] = TopBotType.noTopBot
                        previous_index = self.trace_back_index(working_df, previous_index) #current_index # 
                        if previous_index is None:
                            previous_index = current_index
                            current_index = next_index
                            next_index += 1
                    continue
            elif currentFenXing.tb == nextFenXing.tb:
                if currentFenXing.tb == TopBotType.top:
                    if currentFenXing['high'] < nextFenXing['high']:
                        working_df.ix[current_index,'tb'] = TopBotType.noTopBot
                        current_index = next_index
                        next_index += 1
                    else:
                        working_df.ix[next_index,'tb'] = TopBotType.noTopBot
                        next_index += 1
                    continue
                elif currentFenXing.tb == TopBotType.bot:
                    if currentFenXing['low'] > nextFenXing['low']:
                        working_df.ix[current_index,'tb'] = TopBotType.noTopBot
                        current_index = next_index
                        next_index += 1
                    else:
                        working_df.ix[next_index,'tb'] = TopBotType.noTopBot
                        next_index += 1
                    continue

            # possible BI status 1 check top high > bot low 2 check more than 3 bars (strict BI) in between
            # under this section of code we expect there are no two adjacent fenxings with the same status
            if (nextFenXing.new_index - currentFenXing.new_index) >= 4:
                if currentFenXing.tb == TopBotType.top and nextFenXing.tb == TopBotType.bot and currentFenXing['high'] > nextFenXing['high']:
                    pass
                elif currentFenXing.tb == TopBotType.top and nextFenXing.tb == TopBotType.bot and currentFenXing['high'] <= nextFenXing['high']:
                    working_df.ix[current_index,'tb'] = TopBotType.noTopBot
                    current_index = next_index
                    next_index = next_index + 1
                    continue
                elif currentFenXing.tb == TopBotType.bot and nextFenXing.tb == TopBotType.top and currentFenXing['low'] < nextFenXing['low']:
                    pass
                elif currentFenXing.tb == TopBotType.bot and nextFenXing.tb == TopBotType.top and currentFenXing['low'] >= nextFenXing['low']:
                    working_df.ix[current_index,'tb'] = TopBotType.noTopBot   
                    current_index = next_index 
                    next_index = next_index + 1
                    continue
            else: 
                if currentFenXing.tb == TopBotType.top and previousFenXing['low'] < nextFenXing['low']:
                    working_df.ix[next_index,'tb'] = TopBotType.noTopBot     
                    next_index += 1
                    continue
                if currentFenXing.tb == TopBotType.top and previousFenXing['low'] >= nextFenXing['low']:
                    working_df.ix[current_index,'tb'] = TopBotType.noTopBot
                    current_index = next_index
                    next_index += 1
                    continue
                if currentFenXing.tb == TopBotType.bot and previousFenXing['high'] > nextFenXing['high']:
                    working_df.ix[next_index,'tb'] = TopBotType.noTopBot
                    next_index += 1
                    continue
                if currentFenXing.tb == TopBotType.bot and previousFenXing['high'] <= nextFenXing['high']:
                    working_df.ix[current_index,'tb'] = TopBotType.noTopBot
                    current_index = next_index
                    next_index += 1
                    continue
                
            previous_index = current_index
            current_index=next_index
            next_index = current_index+1
            
            # if nextIndex is the last one
            if next_index == working_df.shape[0]-1 \
            and ((working_df.ix[current_index,'tb']==TopBotType.top and self.kDataFrame_origin.ix[-1,'high'] > working_df.ix[current_index, 'high']) \
            or (working_df.ix[current_index,'tb']==TopBotType.bot and self.kDataFrame_origin.ix[-1, 'low'] < working_df.ix[current_index, 'low']) ):
                working_df.ix[current_index, 'tb'] = TopBotType.noTopBot

        ###################################    
        self.kDataFrame_marked = working_df[working_df['tb']!=TopBotType.noTopBot]
        if self.isdebug:
            print(self.kDataFrame_marked)

    def defineBi_new(self):
        self.kDataFrame_standardized = self.kDataFrame_standardized.assign(new_index=[i for i in range(len(self.kDataFrame_standardized))])
        working_df = self.kDataFrame_standardized[self.kDataFrame_standardized['tb']!=TopBotType.noTopBot]
        
        ############################# clean up the base case for Bi definition ###########################
        firstIdx = 0
        while firstIdx < working_df.shape[0]-2:
            firstFenXing = working_df.iloc[firstIdx]
            secondFenXing = working_df.iloc[firstIdx+1]
            if firstFenXing.tb == secondFenXing.tb:
                working_df.ix[firstIdx,'tb'] = TopBotType.noTopBot
            elif secondFenXing.new_index - firstFenXing.new_index < 4:
                working_df.ix[firstIdx,'tb'] = TopBotType.noTopBot
            elif firstFenXing.tb == TopBotType.top and secondFenXing.tb == TopBotType.bot and firstFenXing.high <= secondFenXing.high:
                working_df.ix[firstIdx,'tb'] = TopBotType.noTopBot
            elif firstFenXing.tb == TopBotType.bot and secondFenXing.tb == TopBotType.top and firstFenXing.low >= secondFenXing.low:
                working_df.ix[firstIdx,'tb'] = TopBotType.noTopBot
            else:
                break
            firstIdx += 1
        #################################
#         print (working_df)
        working_df = working_df[working_df['tb']!=TopBotType.noTopBot]
        previous_index = 0
        current_index = previous_index + 1
        next_index = current_index + 1
        #################################
        while previous_index < working_df.shape[0]-2 and current_index < working_df.shape[0]-1 and next_index < working_df.shape[0]:
            previousFenXing = working_df.iloc[previous_index]
            currentFenXing = working_df.iloc[current_index]
            nextFenXing = working_df.iloc[next_index]
            
            # possible BI status 1 check top high > bot low 2 check more than 3 bars (strict BI) in between
            # under this section of code we expect there are no two adjacent fenxings with the same status, and any fenxing got eleminated which cause 
            # two fenxing with the same status will be future dealt by the next session of code. So each loop we start with legitimate fenxing data
            if (nextFenXing.new_index - currentFenXing.new_index) >= 4:
                if currentFenXing.tb == TopBotType.top and nextFenXing.tb == TopBotType.bot and currentFenXing['high'] > nextFenXing['high']:
                    pass
                elif currentFenXing.tb == TopBotType.top and nextFenXing.tb == TopBotType.bot and currentFenXing['high'] <= nextFenXing['high']:
                    working_df.ix[current_index,'tb'] = TopBotType.noTopBot
                    current_index = next_index
                    next_index = next_index + 1
                elif currentFenXing.tb == TopBotType.bot and nextFenXing.tb == TopBotType.top and currentFenXing['low'] < nextFenXing['low']:
                    pass
                elif currentFenXing.tb == TopBotType.bot and nextFenXing.tb == TopBotType.top and currentFenXing['low'] >= nextFenXing['low']:
                    working_df.ix[current_index,'tb'] = TopBotType.noTopBot
                    current_index = next_index
                    next_index = next_index + 1
            else:
                if currentFenXing.tb == TopBotType.top and nextFenXing.tb == TopBotType.bot and previousFenXing['low'] < nextFenXing['low']:
                    working_df.ix[next_index,'tb'] = TopBotType.noTopBot
                    next_index += 1
                if currentFenXing.tb == TopBotType.top and nextFenXing.tb == TopBotType.bot and previousFenXing['low'] >= nextFenXing['low']:
                    working_df.ix[current_index,'tb'] = TopBotType.noTopBot
                    current_index = next_index
                    next_index += 1
                if currentFenXing.tb == TopBotType.bot and nextFenXing.tb == TopBotType.top and previousFenXing['high'] > nextFenXing['high']:
                    working_df.ix[next_index, 'tb'] = TopBotType.noTopBot
                    next_index += 1
                if currentFenXing.tb == TopBotType.bot and nextFenXing.tb == TopBotType.top and previousFenXing['high'] <= nextFenXing['high']:
                    working_df.ix[current_index,'tb'] = TopBotType.noTopBot
                    current_index = next_index
                    next_index += 1
            
            if currentFenXing.tb == previousFenXing.tb:
                if currentFenXing.tb == TopBotType.top:
                    if currentFenXing['high'] < previousFenXing['high']:
                        working_df.ix[current_index,'tb'] = TopBotType.noTopBot
                        current_index = next_index
                        next_index +=1
                    else:
                        working_df.ix[previous_index,'tb'] = TopBotType.noTopBot
                        previous_index = self.trace_back_index(working_df, previous_index) #current_index # 
                        if previous_index is None:
                            previous_index = current_index
                            current_index = next_index
                            next_index += 1
                    continue
                elif currentFenXing.tb == TopBotType.bot:
                    if currentFenXing['low'] > previousFenXing['low']:
                        working_df.ix[current_index,'tb'] = TopBotType.noTopBot
                        current_index = next_index
                        next_index += 1
                    else:
                        working_df.ix[previous_index,'tb'] = TopBotType.noTopBot
                        previous_index = self.trace_back_index(working_df, previous_index) #current_index # 
                        if previous_index is None:
                            previous_index = current_index
                            current_index = next_index
                            next_index += 1
                    continue
            elif currentFenXing.tb == nextFenXing.tb:
                if currentFenXing.tb == TopBotType.top:
                    if currentFenXing['high'] < nextFenXing['high']:
                        working_df.ix[current_index,'tb'] = TopBotType.noTopBot
                        current_index = next_index
                        next_index += 1
                    else:
                        working_df.ix[next_index,'tb'] = TopBotType.noTopBot
                        next_index += 1
                    continue
                elif currentFenXing.tb == TopBotType.bot:
                    if currentFenXing['low'] > nextFenXing['low']:
                        working_df.ix[current_index,'tb'] = TopBotType.noTopBot
                        current_index = next_index
                        next_index += 1
                    else:
                        working_df.ix[next_index,'tb'] = TopBotType.noTopBot
                        next_index += 1
                    continue
                
            previous_index = current_index
            current_index=next_index
            next_index = current_index+1
            
                    # if nextIndex is the last one
            if next_index == working_df.shape[0]-1 \
            and ((working_df.ix[current_index,'tb']==TopBotType.top and self.kDataFrame_origin.ix[-1,'high'] > working_df.ix[current_index, 'high']) \
            or (working_df.ix[current_index,'tb']==TopBotType.bot and self.kDataFrame_origin.ix[-1, 'low'] < working_df.ix[current_index, 'low']) ):
                working_df.ix[current_index, 'tb'] = TopBotType.noTopBot
                
        ###################################    
        self.kDataFrame_marked = working_df[working_df['tb']!=TopBotType.noTopBot]
        if self.isdebug:
            print(self.kDataFrame_marked)
    
    
    def getCurrentKBarStatus(self, isSimple=True):
        #  at Top or Bot FenXing
        resultStatus = KBarStatus.none_status
        
        # TODO, if not enough data given, long trend status can't be gauged here. We ignore it
        if self.kDataFrame_standardized.shape[0] < 2:
            return resultStatus
        
        if isSimple:
            if self.kDataFrame_standardized.ix[-2,'tb'] == TopBotType.top:
                resultStatus = KBarStatus.upTrendNode
            elif self.kDataFrame_standardized.ix[-2,'tb'] == TopBotType.bot:
                resultStatus = KBarStatus.downTrendNode
            elif self.kDataFrame_standardized.ix[-1, 'high'] > self.kDataFrame_standardized.ix[-2, 'high']:
                resultStatus = KBarStatus.upTrend
            elif self.kDataFrame_standardized.ix[-1, 'low'] < self.kDataFrame_standardized.ix[-2, 'low']:
                resultStatus = KBarStatus.downTrend
        else:
            if self.kDataFrame_marked.empty:
                return KBarStatus.upTrend if self.kDataFrame_standardized.ix[-1, 'high'] > self.kDataFrame_standardized.ix[-2, 'high'] else KBarStatus.downTrend
            
            if self.kDataFrame_marked.ix[-1, 'new_index'] == self.kDataFrame_standardized.shape[0]-2:
                if self.kDataFrame_marked.ix[-1,'tb'] == TopBotType.top:
                    resultStatus = KBarStatus.upTrendNode
                else:
                    resultStatus = KBarStatus.downTrendNode
            else:
                if self.kDataFrame_marked.ix[-1,'tb'] == TopBotType.top:
                    resultStatus = KBarStatus.downTrend
                else:
                    resultStatus = KBarStatus.upTrend
        return resultStatus
        
    def gaugeStatus(self, isSimple=True):
        self.standardize()
        self.markTopBot()
        if not isSimple:
            self.defineBi() # not necessary for biaoli status
            self.getPureBi()
        return self.getCurrentKBarStatus(isSimple)
    
    def getMarkedBL(self):
        self.standardize()
        self.markTopBot()
        self.defineBi()
        self.getPureBi()
        return self.kDataFrame_marked
    
    def getPureBi(self):
        # only use the price relavent
        self.kDataFrame_marked['chan_price'] = self.kDataFrame_marked.apply(lambda row: row['high'] if row['tb'] == TopBotType.top else row['low'], axis=1)
    
    def getStandardized(self):
        return self.standardize()
    
    def getIntegraded(self, initial_state=TopBotType.noTopBot):
        self.standardize(initial_state)
        self.markTopBot(initial_state)
        self.defineBi()
#         self.defineBi_new()
        return self.kDataFrame_origin.join(self.kDataFrame_marked[['new_index', 'tb']])
            
    def find_initial_direction(self, working_df):
        # use simple solution to find initial direction
        max_price_idx = working_df.head(6)['chan_price'].idxmax()
        min_price_idx = working_df.head(6)['chan_price'].idxmin()
        initial_idx = min(max_price_idx, min_price_idx)
        initial_direction = TopBotType.bot2top if max_price_idx > min_price_idx else TopBotType.top2bot
        return working_df.index.get_loc(initial_idx), initial_direction        
    
    
    def is_XD_inclusion_free(self, direction, next_valid_elems, working_df):
        '''
        check the 4 elems are inclusion free by direction, if not operate the inclusion
        '''
        if len(next_valid_elems) < 4:
            print("Invalid number of elems found")
            return False
        
        firstElem = working_df.iloc[next_valid_elems[0]]
        secondElem = working_df.iloc[next_valid_elems[1]]
        thirdElem = working_df.iloc[next_valid_elems[2]]
        forthElem = working_df.iloc[next_valid_elems[3]]
        
        if direction == TopBotType.top2bot:
            assert firstElem.tb == thirdElem.tb == TopBotType.bot and  secondElem.tb == forthElem.tb == TopBotType.top, "Invalid starting tb status for checking inclusion top2bot: {0}, {1}, {2}, {3}".format(firstElem, thirdElem, secondElem, forthElem)
        elif direction == TopBotType.bot2top:
            assert firstElem.tb == thirdElem.tb == TopBotType.top and  secondElem.tb == forthElem.tb == TopBotType.bot, "Invalid starting tb status for checking inclusion bot2top: {0}, {1}, {2}, {3}".format(firstElem, thirdElem, secondElem, forthElem)       
            
        if (firstElem.chan_price <= thirdElem.chan_price and secondElem.chan_price >= forthElem.chan_price) or\
            (firstElem.chan_price >= thirdElem.chan_price and secondElem.chan_price <= forthElem.chan_price):        
            working_df.iloc[next_valid_elems[1], working_df.columns.get_loc('tb')] = TopBotType.noTopBot
            working_df.iloc[next_valid_elems[2], working_df.columns.get_loc('tb')] = TopBotType.noTopBot
            
            print("location {0}, {1} removed for combination".format(working_df.index[next_valid_elems[1]], working_df.index[next_valid_elems[2]]))
            return False
        return True
    
    def check_inclusion_by_direction(self, current_loc, working_df, direction, with_gap):    
        '''
        make sure next 6 (with gap) / 4 (without gap) bi are inclusive free, assuming the starting loc is the start of characteristic elem
        '''
        i = current_loc
        first_run = True

        count_num = 6 if with_gap else 4

        while first_run or (i+count_num-1 < working_df.shape[0]):
            first_run = False
            
            next_valid_elems = self.get_next_N_elem(i, working_df, count_num)            
            
            firstElem = working_df.iloc[next_valid_elems[0]]
            secondElem = working_df.iloc[next_valid_elems[1]]
            thirdElem = working_df.iloc[next_valid_elems[2]]
            forthElem = working_df.iloc[next_valid_elems[3]]
            
            if with_gap:
                fifthElem = working_df.iloc[next_valid_elems[4]]
                sixthElem = working_df.iloc[next_valid_elems[5]]
            
                if self.is_XD_inclusion_free(direction, next_valid_elems[:4], working_df):
                    if self.is_XD_inclusion_free(direction, next_valid_elems[-4:], working_df):
                        break
            else:
                if self.is_XD_inclusion_free(direction, next_valid_elems[:4], working_df):
                    break
                
        pass
    
    def check_XD_topbot(self, first, second, third, forth, fifth, sixth):
        assert first.tb == third.tb == fifth.tb and second.tb == forth.tb == sixth.tb, "invalid tb status!"
        
        result_status = TopBotType.noTopBot
        with_gap = False
        
        if third.tb == TopBotType.top:    
            if third.chan_price > first.chan_price and\
             third.chan_price > fifth.chan_price and\
             forth.chan_price > sixth.chan_price:
                result_status = TopBotType.top
                with_gap = first.chan_price < forth.chan_price
                
        elif third.tb == TopBotType.bot:
            if third.chan_price < first.chan_price and\
             third.chan_price < fifth.chan_price and\
             forth.chan_price < sixth.chan_price:
                result_status = TopBotType.bot
                with_gap = first.chan_price > forth.chan_price
                            
        else:
            print("Error, invalid tb status!")
        
        return result_status, with_gap
    
    def defineXD(self):
        working_df = self.kDataFrame_marked[['chan_price', 'tb']]

#         working_df['original_tb'] = working_df['tb']
        working_df.loc[:,'original_tb'] = working_df['tb']
    
        # find initial direction
        initial_i, initial_direction = self.find_initial_direction(working_df)
        
        # loop through to find XD top bot
        working_df = self.find_XD(initial_i, initial_direction, working_df)
        
        working_df = working_df[(working_df['xd_tb']==TopBotType.top) | (working_df['xd_tb']==TopBotType.bot)]
        
        return working_df

    def get_next_N_elem(self, loc, working_df, N=4, start_tb=TopBotType.noTopBot):
        '''
        get the next N number of elems if tb isn't noTopBot, 
        if start_tb is set, find the first N number of elems starting with tb given
        '''
        i = loc
        result_locs = []
        while i < working_df.shape[0]:
            current_elem = working_df.iloc[i]
            if current_elem.tb != TopBotType.noTopBot:
                if start_tb != TopBotType.noTopBot and current_elem.tb != start_tb and len(result_locs) == 0:
                    i = i + 1
                    continue
                result_locs.append(i)
                if len(result_locs) == N:
                    break
            i = i + 1
        return result_locs

    def find_XD(self, initial_i, initial_direction, working_df):      
        current_direction = initial_direction  
        i = initial_i
        while i+5 < working_df.shape[0]:
            
            print("working at {0}, {1}".format(working_df.index[i], working_df.iloc[i].tb))
            
            previous_gap = len(self.gap_XD) != 0
            
            if previous_gap:
                # do inclusion till find DING DI
                self.check_inclusion_by_direction(i, working_df, current_direction, previous_gap)
                
                next_valid_elems = self.get_next_N_elem(i, working_df, 6)
                firstElem = working_df.iloc[next_valid_elems[0]]
                secondElem = working_df.iloc[next_valid_elems[1]]
                thirdElem = working_df.iloc[next_valid_elems[2]]
                forthElem = working_df.iloc[next_valid_elems[3]]
                fifthElem = working_df.iloc[next_valid_elems[4]]
                sixthElem = working_df.iloc[next_valid_elems[5]]
                
                # make sure we are checking the right elem by direction
                if not self.direction_assert(firstElem, current_direction):
                    i = self.get_next_N_elem(i+1, working_df, N=1, start_tb=TopBotType.top if current_direction==TopBotType.bot2top else TopBotType.bot)[0]
#                     i = i+1
                    continue     
                
                current_status, with_gap = self.check_XD_topbot(firstElem, secondElem, thirdElem, forthElem, fifthElem, sixthElem)  

                if current_status != TopBotType.noTopBot:
                    if with_gap:
                        # save existing gapped Ding/Di
                        self.gap_XD.append(next_valid_elems[2])
                        
                        [print("gap info 1:{0}, {1}".format(working_df.index[gap_loc], working_df.iloc[gap_loc].tb)) for gap_loc in self.gap_XD]
                        
                    else:
                        # fixed Ding/Di, clear the record
                        self.gap_XD = []
                        
                        [print("gap info 2:{0}, {1}".format(working_df.index[gap_loc], working_df.iloc[gap_loc].tb)) for gap_loc in self.gap_XD]
                    working_df.at[working_df.index[i+2], 'xd_tb'] = current_status
                    current_direction = TopBotType.top2bot if current_status == TopBotType.top else TopBotType.bot2top
                    i = self.get_next_N_elem(i+3, working_df, N=1, start_tb=TopBotType.top if current_direction==TopBotType.bot2top else TopBotType.bot)[0]
#                     i = i + 3
                    continue
                else:
                    previous_gap_elem = working_df.iloc[self.gap_XD[-1]]
                    if current_direction == TopBotType.top2bot:
                        if secondElem.chan_price < previous_gap_elem.chan_price:
                            # found new low
                            previous_gap_loc = self.gap_XD.pop()
                            working_df.at[working_df.index[previous_gap_loc], 'xd_tb'] = TopBotType.noTopBot
                            
                            # restore any combined bi due to the gapped XD
                            working_df.iloc[previous_gap_loc:i, working_df.columns.get_loc('tb')] = working_df.iloc[previous_gap_loc:i, working_df.columns.get_loc('original_tb')]
                            current_direction = TopBotType.top2bot if current_direction == TopBotType.bot2top else TopBotType.bot2top
                            i = previous_gap_loc
                            continue                            
                    elif current_direction == TopBotType.bot2top:
                        if secondElem.chan_price > previous_gap_elem.chan_price:
                            previous_gap_loc = self.gap_XD.pop()
                            working_df.at[working_df.index[previous_gap_loc], 'xd_tb'] = TopBotType.noTopBot
                            
                            # restore any combined bi due to the gapped XD
                            working_df.iloc[previous_gap_loc:i, working_df.columns.get_loc('tb')] = working_df.iloc[previous_gap_loc:i, working_df.columns.get_loc('original_tb')]
                            current_direction = TopBotType.top2bot if current_direction == TopBotType.bot2top else TopBotType.bot2top
                            i = previous_gap_loc
                            continue
                            
                    else:
                        print("Invalid current direction!")
                        break
                    [print("gap info 3:{0}, {1}".format(working_df.index[gap_loc],  working_df.iloc[gap_loc].tb)) for gap_loc in self.gap_XD]
                    i = self.get_next_N_elem(i+2, working_df, N=1, start_tb=TopBotType.top if current_direction==TopBotType.bot2top else TopBotType.bot)[0]
#                     i = i + 2 # check next bi with same direction
                    
            else:
                # find DING DI directly
                next_valid_elems = self.get_next_N_elem(i, working_df, 6)
                firstElem = working_df.iloc[next_valid_elems[0]]
                secondElem = working_df.iloc[next_valid_elems[1]]
                thirdElem = working_df.iloc[next_valid_elems[2]]
                forthElem = working_df.iloc[next_valid_elems[3]]
                fifthElem = working_df.iloc[next_valid_elems[4]]
                sixthElem = working_df.iloc[next_valid_elems[5]]
                
                # make sure we are checking the right elem by direction
                if not self.direction_assert(firstElem, current_direction):
                    i = self.get_next_N_elem(i+1, working_df, N=1, start_tb=TopBotType.top if current_direction==TopBotType.bot2top else TopBotType.bot)[0]
#                     i = i + 1
                    continue
                
                current_status, with_gap = self.check_XD_topbot(firstElem, secondElem, thirdElem, forthElem, fifthElem, sixthElem)                      
                
                if current_status != TopBotType.noTopBot:
                    # do inclusion till find DING DI
                    self.check_inclusion_by_direction(i+2, working_df, current_direction, previous_gap)
                    if with_gap:
                        # save existing gapped Ding/Di
                        self.gap_XD.append(next_valid_elems[2])
                        
                        [print("gap info 4:{0}, {1}".format(working_df.index[gap_loc], working_df.iloc[gap_loc].tb)) for gap_loc in self.gap_XD]
                    
                    else:
                        # cleanest case
                        pass
                    current_direction = TopBotType.top2bot if current_status == TopBotType.top else TopBotType.bot2top
                    working_df.at[working_df.index[i+2], 'xd_tb'] = current_status
                    i = self.get_next_N_elem(i+3, working_df, N=1, start_tb=TopBotType.top if current_direction==TopBotType.bot2top else TopBotType.bot)[0]
#                     i = i + 3
                    continue
                else:
                    i = self.get_next_N_elem(i+2, working_df, N=1, start_tb=TopBotType.top if current_direction==TopBotType.bot2top else TopBotType.bot)[0]
#                     i = i + 2
        
        return working_df
                
    def direction_assert(self, firstElem, direction):
        # make sure we are checking the right elem by direction
        result = True
        if direction == TopBotType.top2bot:
            if firstElem.tb != TopBotType.bot:
                print("We have invalid elem tb value: {0}".format(firstElem.tb))
                result = False
        elif direction == TopBotType.bot2top:
            if firstElem.tb != TopBotType.top:
                print("We have invalid elem tb value: {0}".format(firstElem.tb))
                result = False
        else:
            result = False
            print("We have invalid direction value!!!!!")
            
        return result