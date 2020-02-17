# -*- encoding: utf8 -*-
'''
Created on 1 Aug 2017

@author: MetalInvest
'''
# from kuanke.user_space_api import *
from jqdata import *
import numpy as np
import pandas as pd
import copy
import talib
from biaoLiStatus import * 
from chan_common_include import GOLDEN_RATIO, MIN_PRICE_UNIT

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

def get_previous_loc(loc, working_df):
    i = loc - 1
    while i >= 0:
        if working_df.iloc[i].tb == TopBotType.top or working_df.iloc[i].tb == TopBotType.bot:
            return i
        else:
            i = i - 1
    return None

def get_next_loc(loc, working_df):
    i = loc + 1
    while i < working_df.shape[0]:
        if working_df.iloc[i].tb == TopBotType.top or working_df.iloc[i].tb == TopBotType.bot:
            return i
        else:
            i = i + 1
    return None


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
        self.kDataFrame_standardized = self.kDataFrame_standardized.assign(new_high=np.nan, 
                                                                           new_low=np.nan, 
                                                                           trend_type=np.nan, 
                                                                           real_loc=[i for i in range(len(self.kDataFrame_standardized))])
        self.kDataFrame_marked = None
        self.kDataFrame_xd = None
        self.gap_XD = []
        self.previous_with_xd_gap = False # help to check current gap as XD
    
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
        if initial_state == TopBotType.top or initial_state == TopBotType.bot:
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
        else:
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


        # 2. loop through the whole data set and process inclusive relationship
        pastElemIdx = 0
        firstElemIdx = pastElemIdx+1
        secondElemIdx = firstElemIdx+1
        new_high_loc = self.kDataFrame_standardized.columns.get_loc('new_high')
        new_low_loc = self.kDataFrame_standardized.columns.get_loc('new_low')
        trend_type_loc = self.kDataFrame_standardized.columns.get_loc('trend_type')
        
        while secondElemIdx < self.kDataFrame_standardized.shape[0]: # xrange
            pastElem = self.kDataFrame_standardized.iloc[pastElemIdx]
            firstElem = self.kDataFrame_standardized.iloc[firstElemIdx]
            secondElem = self.kDataFrame_standardized.iloc[secondElemIdx]
            inclusion_type = self.checkInclusive(firstElem, secondElem)
            if inclusion_type != InclusionType.noInclusion:
                trend = firstElem.trend_type if not np.isnan(firstElem.trend_type) else self.isBullType(pastElem, firstElem)
                compare_func = max if trend else min
                if inclusion_type == InclusionType.firstCsecond:
                    self.kDataFrame_standardized.iloc[secondElemIdx,new_high_loc]=compare_func(firstElem.high if np.isnan(firstElem.new_high) else firstElem.new_high, secondElem.high if np.isnan(secondElem.new_high) else secondElem.new_high)
                    self.kDataFrame_standardized.iloc[secondElemIdx,new_low_loc]=compare_func(firstElem.low if np.isnan(firstElem.new_low) else firstElem.new_low, secondElem.low if np.isnan(secondElem.new_low) else secondElem.new_low)
                    self.kDataFrame_standardized.iloc[secondElemIdx,trend_type_loc] = trend
                    self.kDataFrame_standardized.iloc[firstElemIdx, new_high_loc]=np.nan
                    self.kDataFrame_standardized.iloc[firstElemIdx, new_low_loc]=np.nan
                    ############ manage index for next round ###########
                    firstElemIdx = secondElemIdx
                    secondElemIdx += 1
                else: 
                    self.kDataFrame_standardized.iloc[firstElemIdx, new_high_loc]=compare_func(firstElem.high if np.isnan(firstElem.new_high) else firstElem.new_high, secondElem.high if np.isnan(secondElem.new_high) else secondElem.new_high)
                    self.kDataFrame_standardized.iloc[firstElemIdx, new_low_loc]=compare_func(firstElem.low if np.isnan(firstElem.new_low) else firstElem.new_low, secondElem.low if np.isnan(secondElem.new_low) else secondElem.new_low)                        
                    self.kDataFrame_standardized.iloc[firstElemIdx,trend_type_loc]=trend
                    self.kDataFrame_standardized.iloc[secondElemIdx,new_high_loc]=np.nan
                    self.kDataFrame_standardized.iloc[secondElemIdx,new_low_loc]=np.nan
                    ############ manage index for next round ###########
                    secondElemIdx += 1
            else:
                if np.isnan(firstElem.new_high): 
                    self.kDataFrame_standardized.iloc[firstElemIdx, new_high_loc] = firstElem.high 
                if np.isnan(firstElem.new_low): 
                    self.kDataFrame_standardized.iloc[firstElemIdx, new_low_loc] = firstElem.low
                if np.isnan(secondElem.new_high): 
                    self.kDataFrame_standardized.iloc[secondElemIdx,new_high_loc] = secondElem.high
                if np.isnan(secondElem.new_low): 
                    self.kDataFrame_standardized.iloc[secondElemIdx,new_low_loc] = secondElem.low
                ############ manage index for next round ###########
                pastElemIdx = firstElemIdx
                firstElemIdx = secondElemIdx
                secondElemIdx += 1
                
        # clean up
        self.kDataFrame_standardized['high'] = self.kDataFrame_standardized['new_high']
        self.kDataFrame_standardized['low'] = self.kDataFrame_standardized['new_low']
        self.kDataFrame_standardized.drop(['new_high', 'new_low', 'trend_type'], axis=1, inplace=True)

        # remove standardized kbars
        self.kDataFrame_standardized = self.kDataFrame_standardized[np.isfinite(self.kDataFrame_standardized['high'])]

        # new index add for later distance calculation => straight after standardization
        self.kDataFrame_standardized = self.kDataFrame_standardized.assign(new_index=[i for i in range(len(self.kDataFrame_standardized))])

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
        if self.kDataFrame_standardized.empty or self.kDataFrame_standardized.shape[0] < 7:
            return
        if initial_state == TopBotType.top or initial_state == TopBotType.bot:
            felem = self.kDataFrame_standardized.iloc[0]
            selem = self.kDataFrame_standardized.iloc[1]
            if (initial_state == TopBotType.top and felem.high >= selem.high) or \
                (initial_state == TopBotType.bot and felem.low <= selem.low):
                self.kDataFrame_standardized.ix[0, 'tb'] = initial_state
            else:
                print("Incorrect initial state given!!!")
                
        # This function assume we have done the standardization process (no inclusion)
        last_idx = 0
        for idx in range(self.kDataFrame_standardized.shape[0]-2): #xrange
            currentElem = self.kDataFrame_standardized.iloc[idx]
            firstElem = self.kDataFrame_standardized.iloc[idx+1]
            secondElem = self.kDataFrame_standardized.iloc[idx+2]
            topBotType = self.checkTopBot(currentElem, firstElem, secondElem)
            if topBotType != TopBotType.noTopBot:
                self.kDataFrame_standardized.ix[idx+1, 'tb'] = topBotType
                last_idx = idx+1
                
        # mark the first kbar
        if (self.kDataFrame_standardized.ix[0, 'tb'] != TopBotType.top and\
            self.kDataFrame_standardized.ix[0, 'tb'] != TopBotType.bot):
            first_loc = get_next_loc(0, self.kDataFrame_standardized)
            if first_loc is not None:
                first_tb = self.kDataFrame_standardized.iloc[first_loc].tb
                self.kDataFrame_standardized.ix[0, 'tb'] = TopBotType.reverse(first_tb)
            
        # mark the last kbar 
        last_tb = self.kDataFrame_standardized.iloc[last_idx].tb
        self.kDataFrame_standardized.ix[-1, 'tb'] = TopBotType.reverse(last_tb)
        if self.isdebug:
            print("self.kDataFrame_standardized[20]:{0}".format(self.kDataFrame_standardized.tail(20)))

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
        
    def prepare_original_kdf(self):    
        _, _, self.kDataFrame_origin.loc[:,'macd'] = talib.MACD(self.kDataFrame_origin['close'].values)
        
    def gap_exists_in_range(self, start_idx, end_idx): # end_idx included
        gap_working_df = self.kDataFrame_origin.loc[start_idx:end_idx, :]
        
        # drop the first row, as we only need to find gaps from start_idx(non-inclusive) to end_idx(inclusive)        
        gap_working_df.drop(gap_working_df.index[0], inplace=True)
        return len(gap_working_df[gap_working_df['gap']==True]) > 0
        

    def gap_exists(self):
        self.kDataFrame_origin.loc[:, 'gap'] = ((self.kDataFrame_origin['low'] - self.kDataFrame_origin['high'].shift(1)) > MIN_PRICE_UNIT) | ((self.kDataFrame_origin['high'] - self.kDataFrame_origin['low'].shift(1)) < -MIN_PRICE_UNIT)
#         if self.isdebug:
#             print(self.kDataFrame_origin[self.kDataFrame_origin['gap']==True])

    def gap_region(self, start_idx, end_idx):
        gap_working_df = self.kDataFrame_origin.loc[start_idx:end_idx, :]
        
        # drop the first row, as we only need to find gaps from start_idx(non-inclusive) to end_idx(inclusive)        
        
        gap_working_df.loc[:,'high_s1'] = gap_working_df['high'].shift(1)
        gap_working_df.loc[:,'low_s1'] = gap_working_df['low'].shift(1)
        gap_working_df.drop(gap_working_df.index[0], inplace=True)
                
        # the gap take the pure range between two klines including the range of kline themself, 
        # ############# pure gap of high_s1, low / high, low_s1
        # ########## gap with kline low_s1, high / high_s1, low
        gap_working_df['gap_range'] = gap_working_df.apply(lambda row: (row['high_s1'], row['low']) if (row['low'] - row['high_s1']) > MIN_PRICE_UNIT else (row['high'], row['low_s1']) if (row['high'] - row['low_s1']) < -MIN_PRICE_UNIT else np.nan, axis=1)
        return gap_working_df[gap_working_df['gap'] == True]['gap_range'].tolist()
        

    def defineBi(self):
        self.gap_exists() # work out gap in the original kline
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
            gap_qualify = False
            if self.gap_exists_in_range(working_df.index[current_index], working_df.index[next_index]):
                gap_ranges = self.gap_region(working_df.index[current_index], working_df.index[next_index])
                for gap in gap_ranges:
                    if working_df.ix[previous_index, 'tb'] == TopBotType.top: 
                        #gap higher than previous high
                        gap_qualify = gap[0] < working_df.ix[previous_index, 'low'] <= working_df.ix[previous_index, 'high'] < gap[1]
                    elif working_df.ix[previous_index, 'tb'] == TopBotType.bot:
                        #gap higher than previous low
                        gap_qualify = gap[1] > working_df.ix[previous_index, 'high'] >= working_df.ix[previous_index, 'low'] > gap[0]
                    if gap_qualify:
                        break
            
            if (nextFenXing.new_index - currentFenXing.new_index) >= 4 or gap_qualify:
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
            
        # if nextIndex is the last one, final clean up
        tb_loc = working_df.columns.get_loc('tb')
        high_loc = working_df.columns.get_loc('high')
        low_loc = working_df.columns.get_loc('low')
        if next_index == working_df.shape[0]:
            if ((working_df.ix[current_index,'tb']==TopBotType.top and self.kDataFrame_origin.ix[-1,'high'] > working_df.ix[current_index, 'high']) \
                or (working_df.ix[current_index,'tb']==TopBotType.bot and self.kDataFrame_origin.ix[-1, 'low'] < working_df.ix[current_index, 'low']) ):
                working_df.ix[-1, 'tb'] = working_df.ix[current_index, 'tb']
                working_df.ix[current_index, 'tb'] = TopBotType.noTopBot

            if working_df.iloc[current_index, tb_loc] == TopBotType.noTopBot and\
                ((working_df.iloc[previous_index, tb_loc]==TopBotType.top and self.kDataFrame_origin.ix[-1,'high'] > working_df.ix[previous_index, 'high']) or\
                 (working_df.iloc[previous_index, tb_loc]==TopBotType.bot and self.kDataFrame_origin.ix[-1,'low'] < working_df.ix[previous_index, 'low'])):
                working_df.ix[-1, 'tb'] = working_df.ix[previous_index, 'tb']
                working_df.ix[previous_index, 'tb'] = TopBotType.noTopBot
                
            if working_df.iloc[previous_index, tb_loc] == working_df.iloc[current_index, tb_loc]:
                if working_df.iloc[current_index, tb_loc] == TopBotType.top:
                    if working_df.iloc[current_index, high_loc] > working_df.iloc[previous_index, high_loc]:
                        working_df.iloc[previous_index, tb_loc] = TopBotType.noTopBot
                    else:
                        working_df.iloc[current_index, tb_loc] = TopBotType.noTopBot
                elif working_df.iloc[current_index, tb_loc] == TopBotType.bot:
                    if working_df.iloc[current_index, low_loc] < working_df.iloc[previous_index, low_loc]:
                        working_df.iloc[previous_index, tb_loc] = TopBotType.noTopBot
                    else:
                        working_df.iloc[current_index, tb_loc] = TopBotType.noTopBot  
                                          
        ###################################    
        self.kDataFrame_marked = working_df[working_df['tb']!=TopBotType.noTopBot]

    def defineBi_new(self):
        self.gap_exists() # work out gap in the original kline
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
            if (nextFenXing.new_index - currentFenXing.new_index) >= 4 or self.gap_exists_in_range(working_df.index[current_index], working_df.index[next_index]):
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
            
        # if nextIndex is the last one, final clean up
        tb_loc = working_df.columns.get_loc('tb')
        high_loc = working_df.columns.get_loc('high')
        low_loc = working_df.columns.get_loc('low')
        if next_index == working_df.shape[0]:
            if ((working_df.ix[current_index,'tb']==TopBotType.top and self.kDataFrame_origin.ix[-1,'high'] > working_df.ix[current_index, 'high']) \
                or (working_df.ix[current_index,'tb']==TopBotType.bot and self.kDataFrame_origin.ix[-1, 'low'] < working_df.ix[current_index, 'low']) ):
                working_df.ix[-1, 'tb'] = working_df.ix[current_index, 'tb']
                working_df.ix[current_index, 'tb'] = TopBotType.noTopBot
                

            if working_df.iloc[current_index, tb_loc] == TopBotType.noTopBot and\
                ((working_df.iloc[previous_index, tb_loc]==TopBotType.top and self.kDataFrame_origin.ix[-1,'high'] > working_df.ix[previous_index, 'high']) or\
                 (working_df.iloc[previous_index, tb_loc]==TopBotType.bot and self.kDataFrame_origin.ix[-1,'low'] < working_df.ix[previous_index, 'low'])):
                working_df.ix[-1, 'tb'] = working_df.ix[previous_index, 'tb']
                working_df.ix[previous_index, 'tb'] = TopBotType.noTopBot
                
            if working_df.iloc[previous_index, tb_loc] == working_df.iloc[current_index, tb_loc]:
                if working_df.iloc[current_index, tb_loc] == TopBotType.top:
                    if working_df.iloc[current_index, high_loc] > working_df.iloc[previous_index, high_loc]:
                        working_df.iloc[previous_index, tb_loc] = TopBotType.noTopBot
                    else:
                        working_df.iloc[current_index, tb_loc] = TopBotType.noTopBot
                elif working_df.iloc[current_index, tb_loc] == TopBotType.bot:
                    if working_df.iloc[current_index, low_loc] < working_df.iloc[previous_index, low_loc]:
                        working_df.iloc[previous_index, tb_loc] = TopBotType.noTopBot
                    else:
                        working_df.iloc[current_index, tb_loc] = TopBotType.noTopBot  
                
        ###################################    
        self.kDataFrame_marked = working_df[working_df['tb']!=TopBotType.noTopBot]
    
    def defineBi_chan(self):
        self.gap_exists() # work out gap in the original kline
        working_df = self.kDataFrame_standardized[self.kDataFrame_standardized['tb']!=TopBotType.noTopBot]
        
        # 1. at least 1 kbar between DING DI
        working_df['new_index_diff'] = working_df.loc[:,'new_index'].shift(-1)-working_df.loc[:,'new_index']
        temp_index_list = working_df[working_df['new_index_diff']<4].index
        temp_loc_list = [working_df.index.get_loc(idx) for idx in temp_index_list]
        tb_loc = working_df.columns.get_loc('tb')
        count_idx = 0
        while count_idx < len(temp_loc_list):
            current = temp_loc_list[count_idx]

            # check not gap for XD TODO
            previous = get_previous_loc(current, working_df)
            next = get_next_loc(current, working_df)
            
            if previous is None:
                count_idx = count_idx + 1
                continue
            
            if next is None:
                break
            
            previous_elem = working_df.iloc[previous]
            current_elem = working_df.iloc[current]
            next_elem = working_df.iloc[next]
            
            if next_elem.new_index - current_elem.new_index >= 4 or\
                current_elem.tb == TopBotType.noTopBot:
                if self.isdebug:
                    print("current close distance ignored: {0}, {1}, {2}".format(previous_elem.new_index, current_elem.new_index, next_elem.new_index))
                count_idx = count_idx + 1
                continue
            
            gap_qualify = False
            if self.gap_exists_in_range(working_df.index[current], working_df.index[next]):
                gap_ranges = self.gap_region(working_df.index[current], working_df.index[next])
                for gap in gap_ranges:
                    if working_df.iloc[previous, tb_loc] == TopBotType.top: 
                        #gap higher than previous high
                        gap_qualify = gap[0] < working_df.ix[previous, 'low'] <= working_df.ix[previous, 'high'] < gap[1]
                    elif working_df.iloc[previous, tb_loc] == TopBotType.bot:
                        #gap higher than previous low
                        gap_qualify = gap[1] > working_df.ix[previous, 'high'] >= working_df.ix[previous, 'low'] > gap[0]
                    if gap_qualify:
                        if self.isdebug:
                            print("gap exists between two kbars used as BI:{0},{1}".format(working_df.index[current], working_df.index[next]))
                        count_idx = count_idx + 1
                        continue
            
            if previous_elem.tb == next_elem.tb:
                if previous_elem.tb == TopBotType.top:
                    if previous_elem.high >= next_elem.high:
                        working_df.iloc[next,tb_loc] = TopBotType.noTopBot
                    elif previous_elem.high < next_elem.high:
                        working_df.iloc[previous,tb_loc] = TopBotType.noTopBot
                elif previous_elem.tb == TopBotType.bot:
                    if previous_elem.low <= next_elem.low:
                        working_df.iloc[next,tb_loc] = TopBotType.noTopBot
                    elif previous_elem.low > next_elem.low:
                        working_df.iloc[previous,tb_loc] = TopBotType.noTopBot
                else:
                    print("something wrong here! 1")
            else:
                if previous_elem.tb == current_elem.tb:
                    if previous_elem.tb == TopBotType.top:
                        if previous_elem.high >= current_elem.high:
                            working_df.iloc[current,tb_loc] = TopBotType.noTopBot
                        elif previous_elem.high < current_elem.high:
                            working_df.iloc[previous,tb_loc] = TopBotType.noTopBot
                    elif previous_elem.tb == TopBotType.bot:
                        if previous_elem.low <= current_elem.low:
                            working_df.iloc[current,tb_loc] = TopBotType.noTopBot
                        elif previous_elem.low > current_elem.low:
                            working_df.iloc[previous,tb_loc] = TopBotType.noTopBot
                elif current_elem.tb == next_elem.tb:
                    if current_elem.tb == TopBotType.top:
                        if current_elem.high >= next_elem.high:
                            working_df.iloc[next,tb_loc] = TopBotType.noTopBot
                        elif current_elem.high < next_elem.high:
                            working_df.iloc[current,tb_loc] = TopBotType.noTopBot
                    elif current_elem.tb == TopBotType.bot:
                        if current_elem.low <= next_elem.low:
                            working_df.iloc[next,tb_loc] = TopBotType.noTopBot
                        elif current_elem.low > next_elem.low:
                            working_df.iloc[current,tb_loc] = TopBotType.noTopBot
                else:
                    print("something wrong here! 2")
            
        working_df = working_df.drop(['new_index_diff'], 1)
        working_df = working_df[working_df['tb'] != TopBotType.noTopBot]
        
        # 2. DING followed by DI and DI followed by DING
        working_df['adjacent_same_tb'] = working_df.loc[:,'tb'].shift(-1) == working_df.loc[:,'tb']
        temp_index_list = working_df[working_df['adjacent_same_tb']].index
        temp_loc_list = [working_df.index.get_loc(idx) for idx in temp_index_list]
        for loc in temp_loc_list:
            
            next_loc = get_next_loc(loc, working_df)
            current_loc = get_previous_loc(next_loc, working_df)
            
            current = working_df.iloc[current_loc]
            next = working_df.iloc[next_loc]
            
            if current.tb == next.tb != TopBotType.noTopBot:
                if current.tb == TopBotType.top:
                    if current.high >= next.high:
                        working_df.iloc[next_loc,tb_loc] = TopBotType.noTopBot
                    elif current.high < next.high:
                        working_df.iloc[current_loc,tb_loc] = TopBotType.noTopBot
                elif current.tb == TopBotType.bot:
                    if current.low <= next.low:
                        working_df.iloc[next_loc,tb_loc] = TopBotType.noTopBot
                    elif current.low > next.low:
                        working_df.iloc[current_loc,tb_loc] = TopBotType.noTopBot
                else:
                    print("something wrong here! 3")
        working_df = working_df.drop('adjacent_same_tb', 1)
        working_df = working_df[working_df['tb'] != TopBotType.noTopBot]
        
        # 3. DING must be higher and DI
        working_df['high_shift'] = working_df['high'].shift(-1)
        working_df['low_shift'] = working_df['low'].shift(-1)
        working_df['tb_shift'] = working_df['tb'].shift(-1)
        working_df['topbot_invalid'] = working_df.apply(lambda row: 
                                                        (row['tb'] == TopBotType.bot and row['tb_shift'] == TopBotType.top and row['high_shift'] < row['low']) or\
                                                        (row['tb'] == TopBotType.top and row['tb_shift'] == TopBotType.bot and row['low_shift'] > row['high']), axis=1)

        temp_index_list = working_df[working_df['topbot_invalid']].index
        temp_loc_list = [working_df.index.get_loc(idx) for idx in temp_index_list]
        for loc in temp_loc_list:
            current = working_df.iloc[loc]
            next = working_df.iloc[loc+1]
            
            if current.tb != next.tb and current.tb != TopBotType.noTopBot and next.tb != TopBotType.noTopBot:
                working_df.iloc[loc,tb_loc] = TopBotType.noTopBot
                working_df.iloc[loc+1,tb_loc] = TopBotType.noTopBot
                if self.isdebug:
                    print("DING/DI location removal:{0}, {1}".format(current.new_index, next.new_index))
            else:
                print("something wrong here!")
        working_df = working_df.drop('topbot_invalid', 1)
        working_df = working_df.drop('high_shift', 1)
        working_df = working_df.drop('low_shift', 1)
        working_df = working_df.drop('tb_shift', 1)        
        ############################################################################
        self.kDataFrame_marked = working_df[working_df['tb'] != TopBotType.noTopBot]
            
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
        
    def getXDStatus(self):
        gauge_df = self.kDataFrame_xd[self.kDataFrame_xd['xd_tb'] != TopBotType.noTopBot]
        if not gauge_df.empty:
            if gauge_df.iloc[-1, 'xd_tb'] == TopBotType.top:
                return TopBotType.top2bot
            elif gauge_df.iloc[-1, 'xd_tb'] == TopBotType.bot:
                return TopBotType.bot2top
        return TopBotType.noTopBot
        
        
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
#         self.defineBi_new()
        self.getPureBi()
        return self.kDataFrame_marked
    
    def getPureBi(self):
        # only use the price relavent
        try:
            self.kDataFrame_marked['chan_price'] = self.kDataFrame_marked.apply(lambda row: row['high'] if row['tb'] == TopBotType.top else row['low'], axis=1)
            if self.isdebug:
                print("self.kDataFrame_marked:{0}".format(self.kDataFrame_marked[['chan_price', 'tb','new_index', 'real_loc']]))
        except:
            print("empty dataframe")
            self.kDataFrame_marked['chan_price'] = None
    
    def getStandardized(self):
        return self.standardize()
    
    def getIntegraded(self, initial_state=TopBotType.noTopBot):
        self.standardize(initial_state)
        self.markTopBot(initial_state)
        self.defineBi()
#         self.defineBi_chan()
        self.getPureBi()
        return self.kDataFrame_origin.join(self.kDataFrame_marked[['real_loc', 'tb', 'chan_price']])
    
    def getIntegradedXD(self, initial_state=TopBotType.noTopBot):
        temp_df = self.getIntegraded(initial_state)
        if temp_df.empty:
            return temp_df
        self.defineXD(initial_state)
        
        return temp_df.join(self.kDataFrame_xd['xd_tb'])
            
################################################## XD defintion ##################################################            
            
    def find_initial_direction(self, working_df, initial_status=TopBotType.noTopBot):
        if initial_status != TopBotType.noTopBot:
            # first six elem, this can only be used when we are sure about the direction of the xd
            if initial_status == TopBotType.top:
                idx = working_df.iloc[:6,working_df.columns.get_loc('chan_price')].idxmax()
            elif initial_status == TopBotType.bot:
                idx = working_df.iloc[:6,working_df.columns.get_loc('chan_price')].idxmin()
            else:
                idx = None
                print("Invalid Initial TopBot type")
            working_df.loc[idx, 'xd_tb'] = initial_status
            if self.isdebug:
                print("initial xd_tb:{0} located at {1}".format(initial_status, idx))
            initial_loc = working_df.index.get_loc(idx) + 1
            initial_direction = TopBotType.top2bot if initial_status == TopBotType.top else TopBotType.bot2top
        else:
            initial_loc = current_loc = 0
            initial_direction = TopBotType.noTopBot
            while current_loc + 3 < working_df.shape[0]:
                first = working_df.iloc[current_loc]
                second = working_df.iloc[current_loc+1]
                third = working_df.iloc[current_loc+2]
                forth = working_df.iloc[current_loc+3]
                
                if first.chan_price < second.chan_price:
                    found_direction = (first.chan_price<=third.chan_price and second.chan_price<forth.chan_price) or\
                                        (first.chan_price>=third.chan_price and second.chan_price>forth.chan_price)
                else:
                    found_direction = (first.chan_price<third.chan_price and second.chan_price<=forth.chan_price) or\
                                        (first.chan_price>third.chan_price and second.chan_price>=forth.chan_price)
                                    
                if found_direction:
                    initial_direction = TopBotType.bot2top if (first.chan_price<third.chan_price or second.chan_price<forth.chan_price) else TopBotType.top2bot
                    initial_loc = current_loc
                    break
                else:
                    current_loc = current_loc + 1
            
        return initial_loc, initial_direction
    
    
    def is_XD_inclusion_free(self, direction, next_valid_elems, working_df):
        '''
        check the 4 elems are inclusion free by direction, if not operate the inclusion, gaps are defined as pure gap
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
            
            ############################## special case of kline gap as XD ##############################
            # only checking if any one node is in pure gap range. The same logic as gap for XD
            if next_valid_elems[0] + 1 == next_valid_elems[1] and\
            self.gap_exists_in_range(working_df.index[next_valid_elems[0]], working_df.index[next_valid_elems[1]]):
                regions = self.gap_region(working_df.index[next_valid_elems[0]], working_df.index[next_valid_elems[1]])
                for re in regions:
                    if re[0] <= thirdElem.chan_price <= re[1] and\
                    (re[1]-re[0])/abs(working_df.iloc[next_valid_elems[0]].chan_price-working_df.iloc[next_valid_elems[1]].chan_price) >= GOLDEN_RATIO:
                        if self.isdebug:
                            print("inclusion ignored due to kline gaps, with loc {0}@{1}, {2}@{3}".format(working_df.index[next_valid_elems[0]], 
                                                                                                          working_df.iloc[next_valid_elems[0]].chan_price,
                                                                                                          working_df.index[next_valid_elems[1]],
                                                                                                          working_df.iloc[next_valid_elems[1]].chan_price))
                        return True

            if next_valid_elems[2] + 1 == next_valid_elems[3] and\
            self.gap_exists_in_range(working_df.index[next_valid_elems[2]], working_df.index[next_valid_elems[3]]):
                regions = self.gap_region(working_df.index[next_valid_elems[2]], working_df.index[next_valid_elems[3]])
                for re in regions:
                    if re[0] <= secondElem.chan_price <= re[1] and\
                    (re[1]-re[0])/abs(working_df.iloc[next_valid_elems[2]].chan_price-working_df.iloc[next_valid_elems[3]].chan_price) >= GOLDEN_RATIO:
                        if self.isdebug:
                            print("inclusion ignored due to kline gaps, with loc {0}@{1}, {2}@{3}".format(working_df.index[next_valid_elems[2]],
                                                                                                          working_df.iloc[next_valid_elems[2]].chan_price,
                                                                                                          working_df.index[next_valid_elems[3]],
                                                                                                          working_df.iloc[next_valid_elems[3]].chan_price))
                        return True             
            ############################## special case of kline gap as XD ##############################                
                  
            working_df.iloc[next_valid_elems[1], working_df.columns.get_loc('tb')] = TopBotType.noTopBot
            working_df.iloc[next_valid_elems[2], working_df.columns.get_loc('tb')] = TopBotType.noTopBot
            
            if self.isdebug:
                print("location {0}@{1}, {2}@{3} removed for combination".format(working_df.index[next_valid_elems[1]], working_df.iloc[next_valid_elems[1]].chan_price, working_df.index[next_valid_elems[2]], working_df.iloc[next_valid_elems[2]].chan_price))
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
            if len(next_valid_elems) < count_num:
                break
            
            if with_gap:
                if self.is_XD_inclusion_free(direction, next_valid_elems[:4], working_df):
                    if self.is_XD_inclusion_free(direction, next_valid_elems[-4:], working_df):
                        break
            else:
                if self.is_XD_inclusion_free(direction, next_valid_elems[:4], working_df):
                    break
                
        pass
    
    def check_XD_topbot(self, first, second, third, forth, fifth, sixth):
        '''
        check if current 5 BI (6 bi tb) form XD top or bot
        check if gap between first and third BI
        '''
        assert first.tb == third.tb == fifth.tb and second.tb == forth.tb == sixth.tb, "invalid tb status!"
        
        result_status = TopBotType.noTopBot
        with_gap = False
        
        if third.tb == TopBotType.top:    
            with_gap = first.chan_price < forth.chan_price
            if third.chan_price > first.chan_price and\
             third.chan_price > fifth.chan_price and\
             forth.chan_price > sixth.chan_price:
                result_status = TopBotType.top
            
                
        elif third.tb == TopBotType.bot:
            with_gap = first.chan_price > forth.chan_price
            if third.chan_price < first.chan_price and\
             third.chan_price < fifth.chan_price and\
             forth.chan_price < sixth.chan_price:
                result_status = TopBotType.bot
            
        else:
            print("Error, invalid tb status!")
        
        return result_status, with_gap
    
    def check_kline_gap_as_xd(self, next_valid_elems, working_df, direction):
        first = working_df.iloc[next_valid_elems[0]]
        second = working_df.iloc[next_valid_elems[1]]
        third = working_df.iloc[next_valid_elems[2]]
        forth = working_df.iloc[next_valid_elems[3]]
        fifth = working_df.iloc[next_valid_elems[4]]
        xd_gap_result = TopBotType.noTopBot
        without_gap = False
        with_xd_gap = False        
        
        # check the corner case where xd can be formed by a single kline gap
        # if kline gap (from original data) exists between second and third or third and forth
        # A if so only check if third is top or bot comparing with first, 
        # B with_gap is determined by checking if the kline gap range cover between first and forth
        # C change direction as usual, and increment counter by 1 only
        
        if not self.previous_with_xd_gap and\
        next_valid_elems[2] + 1 == next_valid_elems[3] and\
        self.gap_exists_in_range(working_df.index[next_valid_elems[2]], working_df.index[next_valid_elems[3]]):
            gap_ranges = self.gap_region(working_df.index[next_valid_elems[2]], working_df.index[next_valid_elems[3]])
            
            for (l,h) in gap_ranges:
                # make sure the gap break previous FIRST FEATURED ELEMENT
                without_gap = l <= second.chan_price <= h and\
                (h-l)/abs(working_df.iloc[next_valid_elems[2]].chan_price-working_df.iloc[next_valid_elems[3]].chan_price)>=GOLDEN_RATIO
                if without_gap:
                    with_xd_gap = True
                    self.previous_with_xd_gap = True #open status
                    if self.isdebug:
                        print("XD represented by kline gap 2, {0}, {1}".format(working_df.index[next_valid_elems[2]], working_df.index[next_valid_elems[3]]))
                        
        if not with_xd_gap and\
        self.previous_with_xd_gap and next_valid_elems[1] + 1 == next_valid_elems[2] and\
        self.gap_exists_in_range(working_df.index[next_valid_elems[1]], working_df.index[next_valid_elems[2]]):
            gap_ranges = self.gap_region(working_df.index[next_valid_elems[1]], working_df.index[next_valid_elems[2]])
            self.previous_with_xd_gap=False # close status
            for (l,h) in gap_ranges:
                # make sure first is within the gap_XD range
                without_gap = l <= forth.chan_price <= h and\
                (h-l)/abs(working_df.iloc[next_valid_elems[1]].chan_price-working_df.iloc[next_valid_elems[2]].chan_price)>=GOLDEN_RATIO
                if without_gap:
                    with_xd_gap = True
                    if self.isdebug:
                        print("XD represented by kline gap 1, {0}, {1}".format(working_df.index[next_valid_elems[1]], working_df.index[next_valid_elems[2]]))
        

        if with_xd_gap:
            if (direction == TopBotType.bot2top and third.chan_price > fifth.chan_price and third.chan_price > first.chan_price):
                xd_gap_result = TopBotType.top
            elif (direction == TopBotType.top2bot and third.chan_price < first.chan_price and third.chan_price < fifth.chan_price):
                xd_gap_result = TopBotType.bot
            else:
                if self.isdebug:
                    print("XD represented by kline gap 3")
        
        return xd_gap_result, not without_gap, with_xd_gap
        ######################################################################################################
        
    def check_previous_elem_to_avoid_xd_gap(self, with_gap, next_valid_elems, working_df):
        first = working_df.iloc[next_valid_elems[0]]
        forth = working_df.iloc[next_valid_elems[3]]
        previous_elem = self.get_previous_N_elem(next_valid_elems[0], working_df, N=0, end_tb=first.tb, single_direction=True)
        if len(previous_elem) >= 1: # use single direction at least 1 needed
            if first.tb == TopBotType.top:
                with_gap = working_df.iloc[previous_elem, working_df.columns.get_loc('chan_price')].max() < forth.chan_price
            elif first.tb == TopBotType.bot:
                with_gap = working_df.iloc[previous_elem, working_df.columns.get_loc('chan_price')].min() > forth.chan_price
            else:
                assert first.tb == TopBotType.top or first.tb == TopBotType.bot, "Invalid first elem tb"
        if not with_gap and self.isdebug:
            print("elem gap unchecked at {0}".format(working_df.index[next_valid_elems[0]]))
        return with_gap  
    
    def check_XD_topbot_directed(self, next_valid_elems, direction, working_df):
        first = working_df.iloc[next_valid_elems[0]]
        second = working_df.iloc[next_valid_elems[1]]
        third = working_df.iloc[next_valid_elems[2]]
        forth = working_df.iloc[next_valid_elems[3]]
        fifth = working_df.iloc[next_valid_elems[4]]
        sixth = working_df.iloc[next_valid_elems[5]]     
        with_xd_gap = False
        
        xd_gap_result, with_gap, with_xd_gap = self.check_kline_gap_as_xd(next_valid_elems, working_df, direction)
        
        if with_xd_gap and xd_gap_result != TopBotType.noTopBot:
            return xd_gap_result, with_gap, with_xd_gap
        
        result, with_gap = self.check_XD_topbot(first, second, third, forth, fifth, sixth)
        
        if (result == TopBotType.top and direction == TopBotType.bot2top) or (result == TopBotType.bot and direction == TopBotType.top2bot):
            if with_gap: # check previous elements to see if the gap can be closed TESTED!
                with_gap = self.check_previous_elem_to_avoid_xd_gap(with_gap, next_valid_elems, working_df)
            return result, with_gap, with_xd_gap
        else:
            return TopBotType.noTopBot, with_gap, with_xd_gap
    
    def defineXD(self, initial_status=TopBotType.noTopBot):
        working_df = self.kDataFrame_marked[['chan_price', 'tb','new_index']] # new index used for central region

        working_df.loc[:,'original_tb'] = working_df['tb']
        working_df = working_df.assign(xd_tb=TopBotType.noTopBot)
    
        if working_df.empty:
            self.kDataFrame_xd = working_df
            return working_df
    
        # find initial direction
        initial_i, initial_direction = self.find_initial_direction(working_df, initial_status)
        
        # loop through to find XD top bot
        working_df = self.find_XD(initial_i, initial_direction, working_df)
        
        working_df = working_df[(working_df['xd_tb']==TopBotType.top) | (working_df['xd_tb']==TopBotType.bot)]
        
        self.kDataFrame_xd = working_df
        return working_df

    def get_next_N_elem(self, loc, working_df, N=4, start_tb=TopBotType.noTopBot, single_direction=False):
        '''
        get the next N number of elems if tb isn't noTopBot, 
        if start_tb is set, find the first N number of elems starting with tb given
        starting from loc(inclusive)
        '''
        i = loc
        result_locs = []
        while i < working_df.shape[0]:
            current_elem = working_df.iloc[i]
            if current_elem.tb != TopBotType.noTopBot:
                if start_tb != TopBotType.noTopBot and current_elem.tb != start_tb and len(result_locs) == 0:
                    i = i + 1
                    continue
                if single_direction and current_elem.tb != start_tb:
                    i = i + 1
                    continue
                result_locs.append(i)
                if len(result_locs) == N:
                    break
            i = i + 1
        return result_locs

    def get_previous_N_elem(self, loc, working_df, N=0, end_tb=TopBotType.noTopBot, single_direction=True):
        '''
        get the previous N number of elems if tb isn't noTopBot, 
        if start_tb is set, find the first N number of elems ending with tb given (order preserved)
        ending with loc (exclusive)
        We are only expecting elem from the same XD, meaning the same direction. So we fetch upto previous xd_tb if N == 0
        single_direction meaning only return elem with the same tb as end_tb
        We are checking the original_tb field to avoid BI been combined. 
        This function is only used for xd gap check
        '''
        i = loc-1
        result_locs = []
        while i >= 0:
            current_elem = working_df.iloc[i]
            if current_elem.original_tb != TopBotType.noTopBot:
                if end_tb != TopBotType.noTopBot and current_elem.original_tb != end_tb and len(result_locs) == 0:
                    i = i - 1
                    continue
                if single_direction: 
                    if current_elem.original_tb == end_tb:
                        result_locs.insert(0, i)
                else:
                    result_locs.insert(0, i)
                if N != 0 and len(result_locs) == N:
                    break
                if N == 0 and (current_elem.xd_tb == TopBotType.top or current_elem.xd_tb == TopBotType.bot):
                    break
            i = i - 1
        return result_locs

    def xd_topbot_candidate(self, next_valid_elems, current_direction, working_df):
        '''
        check current candidates BIs are positioned as idx is at tb
        we are only expecting newly found index to move forward
        '''
        result = None
        
        if len(next_valid_elems) != 3:
            print("Invalid number of tb elem passed in")
        
        chan_price_list = [working_df.iloc[nv].chan_price for nv in next_valid_elems]
            
        if current_direction == TopBotType.top2bot:
            min_value = min(chan_price_list) 
            min_index = chan_price_list.index(min_value)  
            if min_index > 1: 
                result = next_valid_elems[min_index-1] # navigate to the starting for current bot
             
        elif current_direction == TopBotType.bot2top:
            max_value = max(chan_price_list) 
            max_index = chan_price_list.index(max_value)
            if max_index > 1:
                result = next_valid_elems[max_index-1] # navigate to the starting for current bot
        
        else:
            print("Invalid direction!!! {0}".format(current_direction))
        return result


    def find_XD(self, initial_i, initial_direction, working_df):      
        if self.isdebug:
            print("Initial direction {0} at location {1} with new_index {2}".format(initial_direction, initial_i, working_df.iloc[initial_i].new_index))
        
        current_direction = initial_direction  
        i = initial_i
        while i+5 < working_df.shape[0]:
            
            if self.isdebug:
                print("working at {0}, {1}, {2}, {3}, {4}".format(working_df.index[i], working_df.iloc[i].chan_price, current_direction, working_df.iloc[i].new_index, working_df.iloc[i].tb))
            
            previous_gap = len(self.gap_XD) != 0
            
            if previous_gap:
                # do inclusion till find DING DI
                self.check_inclusion_by_direction(i, working_df, current_direction, previous_gap)
                
                next_valid_elems = self.get_next_N_elem(i, working_df, 6)
                if len(next_valid_elems) < 6:
                    break

                # make sure we are checking the right elem by direction
                if not self.direction_assert(working_df.iloc[next_valid_elems[0]], current_direction):
                    i = next_valid_elems[1]
                    continue     
                
                current_status, with_gap, with_xd_gap = self.check_XD_topbot_directed(next_valid_elems, current_direction, working_df)  

                if current_status != TopBotType.noTopBot:
                    if with_gap:
                        # save existing gapped Ding/Di
                        self.gap_XD.append(next_valid_elems[2])
                        
                        if self.isdebug:
                            [print("gap info 1:{0}, {1}".format(working_df.index[gap_loc], working_df.iloc[gap_loc].tb)) for gap_loc in self.gap_XD]
                        
                    else:
                        # fixed Ding/Di, clear the record
                        self.gap_XD = []
                        if self.isdebug:
                            print("gap cleaned!")
                    working_df.at[working_df.index[next_valid_elems[2]], 'xd_tb'] = current_status
                    if self.isdebug:
                        print("xd_tb located {0} {1}".format(working_df.index[next_valid_elems[2]], working_df.iloc[next_valid_elems[2]].chan_price))
                    current_direction = TopBotType.top2bot if current_status == TopBotType.top else TopBotType.bot2top
                    i = next_valid_elems[1] if with_xd_gap else next_valid_elems[3]
                    continue
                else:
                    secondElem = working_df.iloc[next_valid_elems[1]]
 
                    previous_gap_elem = working_df.iloc[self.gap_XD[-1]]
                    if current_direction == TopBotType.top2bot:
                        if secondElem.chan_price > previous_gap_elem.chan_price:
                            previous_gap_loc = self.gap_XD.pop()
                            if self.isdebug:
                                print("xd_tb cancelled due to new high found: {0} {1}".format(working_df.index[previous_gap_loc], working_df.iloc[previous_gap_loc].new_index))
                            working_df.at[working_df.index[previous_gap_loc], 'xd_tb'] = TopBotType.noTopBot
                            
                            # restore any combined bi due to the gapped XD
                            working_df.iloc[previous_gap_loc:next_valid_elems[-1], working_df.columns.get_loc('tb')] = working_df.iloc[previous_gap_loc:next_valid_elems[-1], working_df.columns.get_loc('original_tb')]
                            current_direction = TopBotType.reverse(current_direction)
                            if self.isdebug:
                                print("gap closed 1:{0}, {1} tb info restored to {2}".format(working_df.index[previous_gap_loc],  working_df.iloc[previous_gap_loc].tb, working_df.index[next_valid_elems[-1]])) 
                            i = previous_gap_loc
                            continue                            
                    elif current_direction == TopBotType.bot2top:
                        if secondElem.chan_price < previous_gap_elem.chan_price:
                            previous_gap_loc = self.gap_XD.pop()
                            if self.isdebug:
                                print("xd_tb cancelled due to new low found: {0} {1}".format(working_df.index[previous_gap_loc], working_df.iloc[previous_gap_loc].new_index))
                            working_df.at[working_df.index[previous_gap_loc], 'xd_tb'] = TopBotType.noTopBot
                            
                            # restore any combined bi due to the gapped XD
                            working_df.iloc[previous_gap_loc:next_valid_elems[-1], working_df.columns.get_loc('tb')] = working_df.iloc[previous_gap_loc:next_valid_elems[-1], working_df.columns.get_loc('original_tb')]
                            current_direction = TopBotType.reverse(current_direction)
                            if self.isdebug:
                                print("gap closed 2:{0}, {1} tb info restored to {2}".format(working_df.index[previous_gap_loc],  working_df.iloc[previous_gap_loc].tb, working_df.index[next_valid_elems[-1]]))
                            i = previous_gap_loc
                            continue
                            
                    else:
                        print("Invalid current direction!")
                        break
                    if self.isdebug:
                        [print("gap info 3:{0}, {1}".format(working_df.index[gap_loc],  working_df.iloc[gap_loc].tb)) for gap_loc in self.gap_XD]
                    i = next_valid_elems[2] #  i = i + 2 # check next bi with same direction
                    
            else:    # no gap case            
                # find next 3 elems with the same tb info
                next_valid_elems = self.get_next_N_elem(i, working_df, 3, start_tb = TopBotType.top if current_direction == TopBotType.bot2top else TopBotType.bot, single_direction=True)
                firstElem = working_df.iloc[next_valid_elems[0]]
                
                # make sure we are checking the right elem by direction
                if not self.direction_assert(firstElem, current_direction):
                    i = next_valid_elems[1]
                    continue

                # make sure we are targetting the min/max by direction
                possible_xd_tb_idx = self.xd_topbot_candidate(next_valid_elems, current_direction, working_df)
                if possible_xd_tb_idx is not None:
                    i = possible_xd_tb_idx
                    continue
                # all elem with the same tb
                self.check_inclusion_by_direction(next_valid_elems[1], working_df, current_direction, previous_gap)

                # find next 6 elems with both direction
                next_valid_elems = self.get_next_N_elem(next_valid_elems[0], working_df, 6)
                if len(next_valid_elems) < 6:
                    break                  
                current_status, with_gap, with_xd_gap = self.check_XD_topbot_directed(next_valid_elems, current_direction, working_df)                      
                
                if current_status != TopBotType.noTopBot:
#                     # do inclusion till find DING DI
                    self.check_inclusion_by_direction(next_valid_elems[2], working_df, current_direction, previous_gap)
                    if with_gap:
                        # save existing gapped Ding/Di
                        self.gap_XD.append(next_valid_elems[2])
                        if self.isdebug:
                            [print("gap info 4:{0}, {1}".format(working_df.index[gap_loc], working_df.iloc[gap_loc].tb)) for gap_loc in self.gap_XD]
                    
                    else:
                        # cleanest case
                        pass
                    current_direction = TopBotType.top2bot if current_status == TopBotType.top else TopBotType.bot2top
                    working_df.at[working_df.index[next_valid_elems[2]], 'xd_tb'] = current_status
                    if self.isdebug:
                        print("xd_tb located {0} {1}".format(working_df.index[next_valid_elems[2]], working_df.iloc[next_valid_elems[2]].chan_price))
                    i = next_valid_elems[1] if with_xd_gap else next_valid_elems[3]
                    continue
                else:
                    i = next_valid_elems[2]
        
        # We need to deal with the remaining BI tb and make an assumption that current XD ends

        # + 3 to make sure we have 3 BI at least in XD
        previous_xd_tb_locs = self.get_previous_N_elem(working_df.shape[0]-1, working_df, N=0, single_direction=False)
        if previous_xd_tb_locs:
            column_locs = [working_df.columns.get_loc(x) for x in ['chan_price', 'tb', 'original_tb']]
            previous_xd_tb_loc = previous_xd_tb_locs[0]+3
            
            if previous_xd_tb_loc < working_df.shape[0]:
                # restore tb info from loc found from original_tb as we don't need them?
                working_df.iloc[previous_xd_tb_loc:,column_locs[1]] = working_df.iloc[previous_xd_tb_loc:,column_locs[2]]
                
                temp_df = working_df.iloc[previous_xd_tb_loc:,column_locs]
                if not temp_df.empty:
                    temp_df = temp_df[temp_df['tb'] != TopBotType.noTopBot]
                    if current_direction == TopBotType.top2bot:
                        working_df.loc[temp_df['chan_price'].idxmin(), 'xd_tb'] = TopBotType.bot
                        if self.isdebug:
                            print("final xd_tb located from {0} for {1}".format(temp_df['chan_price'].idxmin(), TopBotType.bot))
                    elif current_direction == TopBotType.bot2top:
                        working_df.loc[temp_df['chan_price'].idxmax(), 'xd_tb'] = TopBotType.top
                        if self.isdebug:
                            print("final xd_tb located from {0} for {1}".format(temp_df['chan_price'].idxmax(), TopBotType.top))
                    else:
                        print("Invalid direction")
                else:
                    print("empty temp_df, continue")
        
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
    
                
