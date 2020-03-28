# -*- encoding: utf8 -*-

import numpy as np
import copy
import talib
from biaoLiStatus import * 
from chan_common_include import GOLDEN_RATIO, MIN_PRICE_UNIT
from kBarProcessor import synchOpenPrice, synchClosePrice
from numpy.lib.recfunctions import append_fields
from scipy.ndimage.interpolation import shift

FEN_BI_COLUMNS = ['date', 'close', 'high', 'low', 'tb', 'real_loc']
FEN_DUAN_COLUMNS =  ['date', 'close', 'high', 'low', 'chan_price', 'tb', 'xd_tb', 'real_loc']

def gap_range_func(a):
    print(len(a['low']))
    print(len(a['high_s1']))
    if a['low'] - a['high_s1'] > MIN_PRICE_UNIT:
        return [a['high_s1'], a['low']]
    elif a['high'] - a['low_s1'] < -MIN_PRICE_UNIT:
        return [a['high'], a['low_s1']]
    else:
        return [0, 0]

def get_previous_loc(loc, working_df):
    i = loc - 1
    while i >= 0:
        if working_df[i]['tb'] == TopBotType.top.value or working_df[i]['tb'] == TopBotType.bot.value:
            return i
        else:
            i = i - 1
    return None

def get_next_loc(loc, working_df):
    i = loc + 1
    while i < len(working_df):
        if working_df[i]['tb'] == TopBotType.top.value or working_df[i]['tb'] == TopBotType.bot.value:
            return i
        else:
            i = i + 1
    return None


class KBarChan(object):
    '''
    This is a rewrite of KBarProcessor, that one is too slow!! we used pandas dataframe, we should use numpy array!
    df=False flag is used here
    '''
    
    def __init__(self, kDf, isdebug=False, clean_standardzed=False):
        self.isdebug = isdebug
        self.clean_standardzed = clean_standardzed
        self.kDataFrame_origin = kDf
        self.kDataFrame_standardized = copy.deepcopy(kDf)
        
        self.kDataFrame_standardized = append_fields(self.kDataFrame_standardized, 
                                                     ['new_high', 'new_low', 'trend_type', 'real_loc'],
                                                     [
                                                         [0]*len(self.kDataFrame_standardized),
                                                         [0]*len(self.kDataFrame_standardized),
                                                         [TopBotType.noTopBot.value]*len(self.kDataFrame_standardized),
                                                         [i for i in range(len(self.kDataFrame_standardized))]
                                                     ],
                                                     [float, float, int, int],
                                                     usemask=False)
        self.kDataFrame_marked = None
        self.kDataFrame_xd = None
        self.gap_XD = []
        self.previous_skipped_idx = []
        self.previous_with_xd_gap = False # help to check current gap as XD
        
    def checkInclusive(self, first, second):
        # output: 0 = no inclusion, 1 = first contains second, 2 second contains first
        isInclusion = InclusionType.noInclusion
        first_high = first['high'] if first['new_high']==0 else first['new_high']
        second_high = second['high'] if second['new_high']==0 else second['new_high']
        first_low = first['low'] if first['new_low']==0 else first['new_low']
        second_low = second['low'] if second['new_low']==0 else second['new_low']
        
        if first_high <= second_high and first_low >= second_low:
            isInclusion = InclusionType.firstCsecond
        elif first_high >= second_high and first_low <= second_low:
            isInclusion = InclusionType.secondCfirst
        return isInclusion
    
    def isBullType(self, first, second): 
        # this is assuming first second aren't inclusive
        f_high = first['high'] if first['new_high']==0 else first['new_high']
        s_high = second['high'] if second['new_high']==0 else second['new_high']
        return TopBotType.bot2top if f_high < s_high else TopBotType.top2bot
            
        
    def standardize(self, initial_state=TopBotType.noTopBot):
        # 1. We need to make sure we start with first two K-bars without inclusive relationship
        # drop the first if there is inclusion, and check again
        if initial_state == TopBotType.top or initial_state == TopBotType.bot:
            # given the initial state, make the first two bars non-inclusive, 
            # the first bar is confirmed as pivot, anything followed with inclusive relation 
            # will be merged into the first bar
            while len(self.kDataFrame_standardized) > 2:
                first_Elem = self.kDataFrame_standardized[0]
                second_Elem = self.kDataFrame_standardized[1]
                if self.checkInclusive(first_Elem, second_Elem) != InclusionType.noInclusion:
                    if initial_state == TopBotType.bot:
                        self.kDataFrame_standardized[0]['new_high'] = second_Elem['high']
                        self.kDataFrame_standardized[0]['new_low'] = first_Elem['low']
                    elif initial_state == TopBotType.top:
                        self.kDataFrame_standardized[0]['new_high'] = first_Elem['high']
                        self.kDataFrame_standardized[0]['new_low'] = second_Elem['low']
                    self.kDataFrame_standardized=np.delete(self.kDataFrame_standardized, 1, axis=0)
                else:
                    self.kDataFrame_standardized[0]['new_high'] = first_Elem['high']
                    self.kDataFrame_standardized[0]['new_low'] = first_Elem['low']
                    break                    
        else:
            while len(self.kDataFrame_standardized) > 2:
                first_Elem = self.kDataFrame_standardized[0]
                second_Elem = self.kDataFrame_standardized[1]
                if self.checkInclusive(first_Elem, second_Elem) != InclusionType.noInclusion:
                    self.kDataFrame_standardized=np.delete(self.kDataFrame_standardized, 0, axis=0)
                else:
                    self.kDataFrame_standardized[0]['new_high'] = first_Elem['high']
                    self.kDataFrame_standardized[0]['new_low'] = first_Elem['low']
                    break


        # 2. loop through the whole data set and process inclusive relationship
        pastElemIdx = 0
        firstElemIdx = pastElemIdx+1
        secondElemIdx = firstElemIdx+1
        high='high'
        low='low'
        new_high = 'new_high'
        new_low = 'new_low'
        trend_type = 'trend_type'
        
        while secondElemIdx < len(self.kDataFrame_standardized): # xrange
            pastElem = self.kDataFrame_standardized[pastElemIdx]
            firstElem = self.kDataFrame_standardized[firstElemIdx]
            secondElem = self.kDataFrame_standardized[secondElemIdx]
            inclusion_type = self.checkInclusive(firstElem, secondElem)
            if inclusion_type != InclusionType.noInclusion:
                trend = firstElem[trend_type] if firstElem[trend_type]!=TopBotType.noTopBot.value else self.isBullType(pastElem, firstElem).value
                compare_func = max if np.isclose(trend, TopBotType.bot2top.value) else min
                if inclusion_type == InclusionType.firstCsecond:
                    self.kDataFrame_standardized[secondElemIdx][new_high]=compare_func(firstElem[high] if firstElem[new_high]==0 else firstElem[new_high], secondElem[high] if secondElem[new_high]==0 else secondElem[new_high])
                    self.kDataFrame_standardized[secondElemIdx][new_low]=compare_func(firstElem[low] if firstElem[new_low]==0 else firstElem[new_low], secondElem[low] if secondElem[new_low]==0 else secondElem[new_low])
                    self.kDataFrame_standardized[secondElemIdx][trend_type] = trend
                    self.kDataFrame_standardized[firstElemIdx][new_high]=0
                    self.kDataFrame_standardized[firstElemIdx][new_low]=0
                    ############ manage index for next round ###########
                    firstElemIdx = secondElemIdx
                    secondElemIdx += 1
                else:
                    self.kDataFrame_standardized[firstElemIdx][new_high]=compare_func(firstElem[high] if firstElem[new_high]==0 else firstElem[new_high], secondElem[high] if secondElem[new_high]==0 else secondElem[new_high])
                    self.kDataFrame_standardized[firstElemIdx][new_low]=compare_func(firstElem[low] if firstElem[new_low]==0 else firstElem[new_low], secondElem[low] if secondElem[new_low]==0 else secondElem[new_low])                        
                    self.kDataFrame_standardized[firstElemIdx][trend_type]=trend
                    self.kDataFrame_standardized[secondElemIdx][new_high]=0
                    self.kDataFrame_standardized[secondElemIdx][new_low]=0
                    ############ manage index for next round ###########
                    secondElemIdx += 1
            else:
                if firstElem[new_high] == 0: 
                    self.kDataFrame_standardized[firstElemIdx][new_high] = firstElem[high]
                if firstElem[new_low] == 0: 
                    self.kDataFrame_standardized[firstElemIdx][new_low] = firstElem[low]
                if secondElem[new_high] == 0: 
                    self.kDataFrame_standardized[secondElemIdx][new_high] = secondElem[high]
                if secondElem[new_low] == 0: 
                    self.kDataFrame_standardized[secondElemIdx][new_low] = secondElem[low]
                ############ manage index for next round ###########
                pastElemIdx = firstElemIdx
                firstElemIdx = secondElemIdx
                secondElemIdx += 1
                
        # clean up
        self.kDataFrame_standardized[high] = self.kDataFrame_standardized[new_high]
        self.kDataFrame_standardized[low] = self.kDataFrame_standardized[new_low]
        self.kDataFrame_standardized=self.kDataFrame_standardized[['date', 'close', 'high', 'low', 'real_loc']]

        # remove standardized kbars
        self.kDataFrame_standardized = self.kDataFrame_standardized[self.kDataFrame_standardized['high']!=0]

        # new index add for later distance calculation => straight after standardization
        self.kDataFrame_standardized = append_fields(self.kDataFrame_standardized, 
                                                     'new_index',
                                                     [i for i in range(len(self.kDataFrame_standardized))],
                                                     usemask=False)
        return self.kDataFrame_standardized
    
    def checkTopBot(self, current, first, second):
        if first['high'] > current['high'] and first['high'] > second['high']:
            return TopBotType.top
        elif first['low'] < current['low'] and first['low'] < second['low']:
            return TopBotType.bot
        else:
            return TopBotType.noTopBot
    
    def markTopBot(self, initial_state=TopBotType.noTopBot):
        self.kDataFrame_standardized = append_fields(self.kDataFrame_standardized,
                                                     'tb',
                                                     [TopBotType.noTopBot.value]*self.kDataFrame_standardized.size,
                                                     usemask=False
                                                     )
        if self.kDataFrame_standardized.size < 7:
            return
        tb = 'tb'
        if initial_state == TopBotType.top or initial_state == TopBotType.bot:
            felem = self.kDataFrame_standardized[0]
            selem = self.kDataFrame_standardized[1]
            if (initial_state == TopBotType.top and felem['high'] >= selem['high']) or \
                (initial_state == TopBotType.bot and felem['low'] <= selem['low']):
                self.kDataFrame_standardized[0][tb] = initial_state.value
            else:
                if self.isdebug:
                    print("Incorrect initial state given!!!")
                
        # This function assume we have done the standardization process (no inclusion)
        last_idx = 0
        for idx in range(self.kDataFrame_standardized.size-2): #xrange
            currentElem = self.kDataFrame_standardized[idx]
            firstElem = self.kDataFrame_standardized[idx+1]
            secondElem = self.kDataFrame_standardized[idx+2]
            topBotType = self.checkTopBot(currentElem, firstElem, secondElem)
            if topBotType != TopBotType.noTopBot:
                self.kDataFrame_standardized[idx+1][tb] = topBotType.value
                last_idx = idx+1
                
        # mark the first kbar
        if (self.kDataFrame_standardized[0][tb] != TopBotType.top.value and\
            self.kDataFrame_standardized[0][tb] != TopBotType.bot.value):
            first_loc = get_next_loc(0, self.kDataFrame_standardized)
            if first_loc is not None:
                first_tb = TopBotType.value2type(self.kDataFrame_standardized[first_loc][tb])
                self.kDataFrame_standardized[0][tb] = TopBotType.reverse(first_tb).value
            
        # mark the last kbar 
        last_tb = TopBotType.value2type(self.kDataFrame_standardized[last_idx][tb])
        self.kDataFrame_standardized[-1][tb] = TopBotType.reverse(last_tb).value
        if self.isdebug:
            print("mark topbot on self.kDataFrame_standardized[20]:{0}".format(self.kDataFrame_standardized[:20]))
            
    def trace_back_index(self, working_df, previous_index):
        # find the closest FenXing with top/bot backwards from previous_index
        idx = previous_index-1
        while idx >= 0:
            fx = working_df[idx]
            if fx['tb'] == TopBotType.noTopBot.value:
                idx -= 1
                continue
            else:
                return idx
        if self.isdebug:
            print("We don't have previous valid FenXing")
        return None
    
    def prepare_original_kdf(self):
        if 'macd' not in self.kDataFrame_origin.dtype.names:
            _, _, macd = talib.MACD(self.kDataFrame_origin['close'])
            macd[np.isnan(macd)] = 0
            self.kDataFrame_origin = append_fields(self.kDataFrame_origin,
                                                    'macd',
                                                    macd,
                                                    float,
                                                    usemask=False)

    def gap_exists_in_range(self, start_idx, end_idx): # end_idx included
        # no need to drop first row, simple don't use = 
        gap_working_df = self.kDataFrame_origin[(start_idx < self.kDataFrame_origin['date']) & (self.kDataFrame_origin['date'] <= end_idx)]
        
        # drop the first row, as we only need to find gaps from start_idx(non-inclusive) to end_idx(inclusive)  
#         gap_working_df = np.delete(gap_working_df, 0, axis=0)
        return np.any(gap_working_df['gap'])
    
    
    def gap_exists(self):
        high_shift = shift(self.kDataFrame_origin['high'], 1, cval=0)
        low_shift = shift(self.kDataFrame_origin['low'], 1, cval=0)
        self.kDataFrame_origin = append_fields(self.kDataFrame_origin,
                                               ['gap', 'high_shift', 'low_shift', 'gap_range_start', 'gap_range_end'],
                                               [
                                                   [False]*self.kDataFrame_origin.size,
                                                   high_shift,
                                                   low_shift,
                                                   [0]*self.kDataFrame_origin.size,
                                                   [0]*self.kDataFrame_origin.size
                                               ],
                                               [bool, float, float, float, float],
                                               usemask=False)
#                                                ((self.kDataFrame_origin['low'] - high_shift) > MIN_PRICE_UNIT) | ((self.kDataFrame_origin['high'] - low_shift) < -MIN_PRICE_UNIT),
        
        i = 0
        while i < self.kDataFrame_origin.size:
            item = self.kDataFrame_origin[i]
            if item['low'] - item['high_shift'] > MIN_PRICE_UNIT:
                self.kDataFrame_origin[i]['gap'] = True
                self.kDataFrame_origin[i]['gap_range_start'] = item['high_shift']
                self.kDataFrame_origin[i]['gap_range_end'] = item['low']
            elif item['high'] - item['low_shift'] < -MIN_PRICE_UNIT:
                self.kDataFrame_origin[i]['gap'] = True
                self.kDataFrame_origin[i]['gap_range_start'] = item['high']
                self.kDataFrame_origin[i]['gap_range_end'] = item['low_shift']
            i = i + 1
        
#         self.kDataFrame_origin = self.kDataFrame_origin[FEN_BI_COLUMNS + ['gap', 'gap_range_start', 'gap_range_end']]
#         if self.isdebug:
#             print(self.kDataFrame_origin[self.kDataFrame_origin['gap']])
    
    def gap_region(self, start_idx, end_idx):
        # no need to drop first row, simple don't use = 
        gap_working_df = self.kDataFrame_origin[(start_idx < self.kDataFrame_origin['date']) & (self.kDataFrame_origin['date'] <= end_idx)]
        return gap_working_df[gap_working_df['gap']][['gap_range_start', 'gap_range_end']].tolist()

    def get_next_tb(self, idx, working_df):
        '''
        give the next loc from current idx(excluded) if overflow return size of working_df
        '''
        i = idx+1
        while i < working_df.size:
            if working_df[i]['tb'] == TopBotType.top.value or working_df[i]['tb'] == TopBotType.bot.value:
                break
            i += 1
        return i

    def defineBi(self):
        self.gap_exists() # work out gap in the original kline
        working_df = self.kDataFrame_standardized[self.kDataFrame_standardized['tb']!=TopBotType.noTopBot.value]
        
        ############################# make sure the first two Ding/Di are valid to start with ###########################
        firstIdx = 0
        secondIdx= firstIdx+1
        thirdIdx = secondIdx+1
        tb = 'tb'
        high = 'high'
        low = 'low'
        new_index = 'new_index'
        while thirdIdx is not None and thirdIdx < working_df.size:
            firstFenXing = working_df[firstIdx]
            secondFenXing = working_df[secondIdx]
            thirdFenXing = working_df[thirdIdx]
            if firstFenXing[tb] == secondFenXing[tb] == TopBotType.top.value and firstFenXing[high] < secondFenXing[high]:
                working_df[firstIdx][tb] = TopBotType.noTopBot.value
                firstIdx = get_next_loc(firstIdx, working_df)
                secondIdx=get_next_loc(firstIdx, working_df)
                thirdIdx=get_next_loc(secondIdx, working_df)
                continue
            elif firstFenXing[tb] == secondFenXing[tb] == TopBotType.top.value and firstFenXing[high] >= secondFenXing[high]:
                working_df[secondIdx][tb] = TopBotType.noTopBot.value
                secondIdx = get_next_loc(secondIdx, working_df)
                thirdIdx=get_next_loc(secondIdx, working_df)
                continue
            elif firstFenXing[tb] == secondFenXing[tb] == TopBotType.bot.value and firstFenXing[low] > secondFenXing[low]:
                working_df[firstIdx][tb] = TopBotType.noTopBot.value
                firstIdx = get_next_loc(firstIdx, working_df)
                secondIdx=get_next_loc(firstIdx, working_df)
                thirdIdx=get_next_loc(secondIdx, working_df)
                continue
            elif firstFenXing[tb] == secondFenXing[tb] == TopBotType.bot.value and firstFenXing[low] <= secondFenXing[low]:
                working_df[secondIdx][tb] = TopBotType.noTopBot.value
                secondIdx = get_next_loc(secondIdx, working_df)
                thirdIdx=get_next_loc(secondIdx, working_df)
                continue
            elif secondFenXing[new_index] - firstFenXing[new_index] < 4:
                if firstFenXing[tb] == thirdFenXing[tb] == TopBotType.top.value and firstFenXing[high] < thirdFenXing[high]:
                    working_df[firstIdx][tb] = TopBotType.noTopBot.value
                    firstIdx = get_next_loc(firstIdx, working_df)
                    secondIdx=get_next_loc(firstIdx, working_df)
                    thirdIdx=get_next_loc(secondIdx, working_df)
                    continue
                elif firstFenXing[tb] == thirdFenXing[tb] == TopBotType.top.value and firstFenXing[high] >= thirdFenXing[high]:
                    working_df[secondIdx][tb] = TopBotType.noTopBot.value
                    secondIdx=get_next_loc(secondIdx, working_df)
                    thirdIdx=get_next_loc(secondIdx, working_df)
                    continue
                elif firstFenXing[tb] == thirdFenXing[tb] == TopBotType.bot.value and firstFenXing[low] > thirdFenXing[low]:
                    working_df[firstIdx][tb] = TopBotType.noTopBot.value
                    firstIdx = get_next_loc(firstIdx, working_df)
                    secondIdx=get_next_loc(firstIdx, working_df)
                    thirdIdx=get_next_loc(secondIdx, working_df)
                    continue
                elif firstFenXing[tb] == thirdFenXing[tb] == TopBotType.bot.value and firstFenXing[low] <= thirdFenXing[low]:
                    working_df[secondIdx][tb] = TopBotType.noTopBot.value
                    secondIdx=get_next_loc(secondIdx, working_df)
                    thirdIdx=get_next_loc(secondIdx, working_df)
                    continue
                else:
                    print("somthing WRONG!")
                    return
                    
            elif firstFenXing[tb] == TopBotType.top.value and secondFenXing[tb] == TopBotType.bot.value and firstFenXing[high] <= secondFenXing[low]:
                working_df[firstIdx][tb] = TopBotType.noTopBot.value
                working_df[secondIdx][tb] = TopBotType.noTopBot.value
                firstIdx = get_next_loc(firstIdx, working_df)
                secondIdx=get_next_loc(firstIdx, working_df)
                thirdIdx=get_next_loc(secondIdx, working_df)
                continue
            elif firstFenXing[tb] == TopBotType.bot.value and secondFenXing[tb] == TopBotType.top.value and firstFenXing[low] >= secondFenXing[high]:
                working_df[firstIdx][tb] = TopBotType.noTopBot.value
                working_df[secondIdx][tb] = TopBotType.noTopBot.value
                firstIdx = get_next_loc(firstIdx, working_df)
                secondIdx=get_next_loc(firstIdx, working_df)
                thirdIdx=get_next_loc(secondIdx, working_df)
                continue
            else:
                break
 
        working_df = working_df[working_df[tb]!=TopBotType.noTopBot.value]
        
        #################################
        previous_index = 0
        current_index = previous_index + 1
        next_index = current_index + 1
        #################################
        while previous_index < working_df.size-2 and\
            current_index < working_df.size-1 and\
            next_index < working_df.size:
            previousFenXing = working_df[previous_index]
            currentFenXing = working_df[current_index]
            nextFenXing = working_df[next_index]
            
            if currentFenXing[tb] == previousFenXing[tb]: # used to track back the skipped previous_index
                if currentFenXing[tb] == TopBotType.top.value:
                    if currentFenXing[high] < previousFenXing[high]:
                        working_df[current_index][tb] = TopBotType.noTopBot.value
                        temp_index = previous_index
                        current_index = previous_index
                        previous_index = self.trace_back_index(working_df, previous_index)
                        if previous_index is None:
                            previous_index = temp_index
                            current_index = next_index
                            next_index = self.get_next_tb(next_index, working_df)
                        else:
                            if previous_index in self.previous_skipped_idx:
                                self.previous_skipped_idx.remove(previous_index)
                    else:
                        working_df[previous_index][tb] = TopBotType.noTopBot.value
                        previous_index = self.trace_back_index(working_df, previous_index) #current_index # 
                        if previous_index is None:
                            previous_index = current_index
                            current_index = next_index
                            next_index = self.get_next_tb(next_index, working_df)
                        else:
                            if previous_index in self.previous_skipped_idx:
                                self.previous_skipped_idx.remove(previous_index)
                    continue
                elif currentFenXing[tb] == TopBotType.bot.value:
                    if currentFenXing[low] > previousFenXing[low]:
                        working_df[current_index][tb] = TopBotType.noTopBot.value
                        temp_index = previous_index
                        current_index = previous_index
                        previous_index = self.trace_back_index(working_df, previous_index)
                        if previous_index is None:
                            previous_index = temp_index
                            current_index = next_index
                            next_index = self.get_next_tb(next_index, working_df)
                        else:
                            if previous_index in self.previous_skipped_idx:
                                self.previous_skipped_idx.remove(previous_index)
                    else:
                        working_df[previous_index][tb] = TopBotType.noTopBot.value
                        previous_index = self.trace_back_index(working_df, previous_index) #current_index # 
                        if previous_index is None:
                            previous_index = current_index
                            current_index = next_index
                            next_index = self.get_next_tb(next_index, working_df)
                        else:
                            if previous_index in self.previous_skipped_idx:
                                self.previous_skipped_idx.remove(previous_index)
                    continue
            elif currentFenXing[tb] == nextFenXing[tb]:
                if currentFenXing[tb] == TopBotType.top.value:
                    if currentFenXing[high] < nextFenXing[high]:
                        working_df[current_index][tb] = TopBotType.noTopBot.value
                        temp_index = previous_index
                        previous_index = self.trace_back_index(working_df, previous_index)
                        if previous_index is None:
                            previous_index = temp_index
                            current_index = next_index
                            next_index = self.get_next_tb(next_index, working_df)
                        else:
                            current_index = temp_index
                        
                    else:
                        working_df[next_index][tb] = TopBotType.noTopBot.value
                        temp_index = previous_index
                        previous_index = self.trace_back_index(working_df, previous_index)
                        if previous_index is None:
                            previous_index = temp_index
                            next_index = self.get_next_tb(next_index, working_df)
                        else:
                            next_index = current_index
                            current_index = temp_index
                            
                    continue
                elif currentFenXing[tb] == TopBotType.bot.value:
                    if currentFenXing[low] > nextFenXing[low]:
                        working_df[current_index][tb] = TopBotType.noTopBot.value
                        temp_index = previous_index
                        previous_index = self.trace_back_index(working_df, previous_index)
                        if previous_index is None:
                            previous_index = temp_index
                            current_index = next_index
                            next_index = self.get_next_tb(next_index, working_df)
                        else:
                            current_index = temp_index
                    else:
                        working_df[next_index][tb] = TopBotType.noTopBot.value
                        temp_index = previous_index
                        previous_index = self.trace_back_index(working_df, previous_index)
                        if previous_index is None:
                            previous_index = temp_index
                            next_index = self.get_next_tb(next_index, working_df)
                        else:
                            next_index = current_index
                            current_index = temp_index
                    continue
            
            # possible BI status 1 check top high > bot low 2 check more than 3 bars (strict BI) in between
            # under this section of code we expect there are no two adjacent fenxings with the same status
            gap_qualify = False
            if self.gap_exists_in_range(working_df[current_index]['date'], working_df[next_index]['date']):
                gap_ranges = self.gap_region(working_df[current_index]['date'], working_df[next_index]['date'])
                for gap in gap_ranges:
                    if working_df[previous_index][tb] == TopBotType.top.value: 
                        #gap higher than previous high
                        gap_qualify = gap[0] < working_df[previous_index][low] <= working_df[previous_index][high] < gap[1]
                    elif working_df[previous_index][tb] == TopBotType.bot.value:
                        #gap higher than previous low
                        gap_qualify = gap[1] > working_df[previous_index][high] >= working_df[previous_index][low] > gap[0]
                    if gap_qualify:
                        break
            
            if currentFenXing[new_index] - previousFenXing[new_index] < 4:
                # comming from current next less than 4 new_index gap, we need to determine which ones to kill
                # once done we trace back
                if (nextFenXing[new_index] - currentFenXing[new_index]) >= 4 or gap_qualify:
                    if currentFenXing[tb] == TopBotType.bot.value and\
                        previousFenXing[tb] == TopBotType.top.value and\
                        nextFenXing[tb] == TopBotType.top.value:
                        if previousFenXing[high] >= nextFenXing[high]:
                            # still can't make decision, but we can have idea about prepre case
                            pre_pre_index = self.trace_back_index(working_df, previous_index)
                            if pre_pre_index is None:
                                working_df[current_index][tb] = TopBotType.noTopBot.value
                                current_index = next_index
                                next_index = self.get_next_tb(next_index, working_df)
                                continue
                            
                            if pre_pre_index in self.previous_skipped_idx:
                                self.previous_skipped_idx.remove(pre_pre_index)
                            prepreFenXing = working_df[pre_pre_index]
                            if prepreFenXing[low] >= currentFenXing[low]:
                                working_df[pre_pre_index][tb] = TopBotType.noTopBot.value
                                temp_index = self.trace_back_index(working_df, pre_pre_index)
                                if temp_index is None:
                                    working_df[current_index][tb] = TopBotType.noTopBot.value
                                    current_index = next_index
                                    next_index = self.get_next_tb(next_index, working_df)
                                else:
                                    next_index = current_index
                                    current_index = previous_index
                                    previous_index = temp_index
                                    if previous_index in self.previous_skipped_idx:
                                        self.previous_skipped_idx.remove(previous_index)
                                continue
                            else:
                                working_df[current_index][tb] = TopBotType.noTopBot.value
                                current_index = previous_index
                                previous_index = self.trace_back_index(working_df, previous_index)
                                if previous_index in self.previous_skipped_idx:
                                    self.previous_skipped_idx.remove(previous_index)
                                continue
                        else: #previousFenXing[high] < nextFenXing[high]
                            working_df[previous_index][tb] = TopBotType.noTopBot.value
                            previous_index = self.trace_back_index(working_df, previous_index)
                            if previous_index in self.previous_skipped_idx:
                                self.previous_skipped_idx.remove(previous_index)
                            continue
                            
                    elif currentFenXing[tb] == TopBotType.top.value and\
                        previousFenXing[tb] == TopBotType.bot.value and\
                        nextFenXing[tb] == TopBotType.bot.value:
                        if previousFenXing[low] < nextFenXing[low]:
                            # still can't make decision, but we can have idea about prepre case
                            pre_pre_index = self.trace_back_index(working_df, previous_index)
                            if pre_pre_index is None:
                                working_df[current_index][tb] = TopBotType.noTopBot.value
                                current_index = next_index
                                next_index = self.get_next_tb(next_index, working_df)
                                continue
                            
                            if pre_pre_index in self.previous_skipped_idx:
                                self.previous_skipped_idx.remove(pre_pre_index)
                            prepreFenXing = working_df[pre_pre_index]
                            if prepreFenXing[high] <= currentFenXing[high]:
                                working_df[pre_pre_index][tb] = TopBotType.noTopBot.value
                                temp_index = self.trace_back_index(working_df, pre_pre_index)
                                if temp_index is None:
                                    working_df[current_index][tb] = TopBotType.noTopBot.value
                                    current_index = next_index
                                    next_index = self.get_next_tb(next_index, working_df)
                                else:
                                    next_index = current_index
                                    current_index = previous_index
                                    previous_index = temp_index
                                    if previous_index in self.previous_skipped_idx:
                                        self.previous_skipped_idx.remove(previous_index)
                                continue
                            else:
                                working_df[current_index][tb] = TopBotType.noTopBot.value
                                current_index = previous_index
                                previous_index = self.trace_back_index(working_df, previous_index)
                                if previous_index in self.previous_skipped_idx:
                                    self.previous_skipped_idx.remove(previous_index)
                                continue
                        else: #previousFenXing[low] >= nextFenXing[low]
                            working_df[previous_index][tb] = TopBotType.noTopBot.value
                            previous_index = self.trace_back_index(working_df, previous_index)
                            if previous_index in self.previous_skipped_idx:
                                self.previous_skipped_idx.remove(previous_index)
                            continue
                else: #(nextFenXing[new_index] - currentFenXing[new_index]) < 4 and not gap_qualify:
                    # leave it for next round again!
                    self.previous_skipped_idx.append(previous_index) # mark index so we come back 
                    previous_index = current_index
                    current_index = next_index
                    next_index = self.get_next_tb(next_index, working_df)
                    continue
                    
                
            elif (nextFenXing[new_index] - currentFenXing[new_index]) < 4 and not gap_qualify: 
                self.previous_skipped_idx.append(previous_index) # mark index so we come back 
                previous_index = current_index
                current_index = next_index
                next_index = self.get_next_tb(next_index, working_df)
                continue
            elif (nextFenXing[new_index] - currentFenXing[new_index]) >= 4 or gap_qualify:
                if currentFenXing[tb] == TopBotType.top.value and nextFenXing[tb] == TopBotType.bot.value and currentFenXing[high] > nextFenXing[high]:
                    pass
                elif currentFenXing[tb] == TopBotType.top.value and nextFenXing[tb] == TopBotType.bot.value and currentFenXing[high] <= nextFenXing[high]:
                    working_df[current_index][tb] = TopBotType.noTopBot.value
                    current_index = next_index
                    next_index = self.get_next_tb(next_index, working_df)
                    continue
                
                elif currentFenXing[tb] == TopBotType.top.value and nextFenXing[tb] == TopBotType.bot.value and currentFenXing[low] <= nextFenXing[low]:
                    working_df[next_index][tb] = TopBotType.noTopBot.value
                    next_index = self.get_next_tb(next_index, working_df)
                    continue
                elif currentFenXing[tb] == TopBotType.top.value and nextFenXing[tb] == TopBotType.bot.value and currentFenXing[low] > nextFenXing[low]:
                    pass
                
                elif currentFenXing[tb] == TopBotType.bot.value and nextFenXing[tb] == TopBotType.top.value and currentFenXing[low] < nextFenXing[low]:
                    pass
                elif currentFenXing[tb] == TopBotType.bot.value and nextFenXing[tb] == TopBotType.top.value and currentFenXing[low] >= nextFenXing[low]:
                    working_df[current_index][tb] = TopBotType.noTopBot.value
                    current_index = next_index 
                    next_index = self.get_next_tb(next_index, working_df)
                    continue
                elif currentFenXing[tb] == TopBotType.bot.value and nextFenXing[tb] == TopBotType.top.value and currentFenXing[high] < nextFenXing[high]:
                    pass
                elif currentFenXing[tb] == TopBotType.bot.value and nextFenXing[tb] == TopBotType.top.value and currentFenXing[high] >= nextFenXing[high]:
                    working_df[next_index][tb] = TopBotType.noTopBot.value
                    next_index = self.get_next_tb(next_index, working_df)
                    continue
            
            if self.previous_skipped_idx: # if we still have some left to do
                previous_index = self.previous_skipped_idx.pop()
                current_index = self.get_next_tb(previous_index, working_df)
                next_index = self.get_next_tb(current_index, working_df)
                continue
            
            # only confirmed tb comes here
            previous_index = current_index
            current_index=next_index
            next_index = self.get_next_tb(next_index, working_df)
                
        # if nextIndex is the last one, final clean up
        if next_index == working_df.size:
            if ((working_df[current_index][tb]==TopBotType.top.value and self.kDataFrame_origin[-1][high] > working_df[current_index][high]) \
                or (working_df[current_index][tb]==TopBotType.bot.value and self.kDataFrame_origin[-1][low] < working_df[current_index][low]) ):
                working_df[-1][tb] = working_df[current_index][tb]
                working_df[current_index][tb] = TopBotType.noTopBot.value
            
            if working_df[current_index][tb] == TopBotType.noTopBot.value and\
                ((working_df[previous_index][tb]==TopBotType.top.value and self.kDataFrame_origin[-1][high] > working_df[previous_index][high]) or\
                 (working_df[previous_index][tb]==TopBotType.bot.value and self.kDataFrame_origin[-1][low] < working_df[previous_index][low])):
                working_df[-1][tb] = working_df[previous_index][tb]
                working_df[previous_index][tb] = TopBotType.noTopBot.value
                
            if working_df[previous_index][tb] == working_df[current_index][tb]:
                if working_df[current_index][tb] == TopBotType.top.value:
                    if working_df[current_index][high] > working_df[previous_index][high]:
                        working_df[previous_index][tb] = TopBotType.noTopBot.value
                    else:
                        working_df[current_index][tb] = TopBotType.noTopBot.value
                elif working_df[current_index][tb] == TopBotType.bot.value:
                    if working_df[current_index][low] < working_df[previous_index][low]:
                        working_df[previous_index][tb] = TopBotType.noTopBot.value
                    else:
                        working_df[current_index][tb] = TopBotType.noTopBot.value
        ###################################    
        self.kDataFrame_marked = working_df[working_df[tb]!=TopBotType.noTopBot.value][FEN_BI_COLUMNS]
        if self.isdebug:
            print("self.kDataFrame_marked head 20:{0}".format(self.kDataFrame_marked[:20]))
            print("self.kDataFrame_marked tail 20:{0}".format(self.kDataFrame_marked[-20:]))

    def getMarkedBL(self):
        self.standardize()
        self.markTopBot()
        self.defineBi()
#         self.defineBi_new()
        self.getPureBi()
        return self.kDataFrame_marked
    
    def getPureBi(self):
        # only use the price relavent
        self.kDataFrame_marked = append_fields(self.kDataFrame_marked,
                                               'chan_price',
                                               [0]*len(self.kDataFrame_marked),
                                               float,
                                               usemask=False)
        i = 0
        while i < self.kDataFrame_marked.size:
            item = self.kDataFrame_marked[i]
            if item['tb'] == TopBotType.top.value:
                self.kDataFrame_marked[i]['chan_price'] = item['high']
            elif item['tb'] == TopBotType.bot.value:
                self.kDataFrame_marked[i]['chan_price'] = item['low']
            else:
                print("Invalid tb for chan_price")
            i = i + 1
            
        if self.isdebug:
            print("getPureBi:{0}".format(self.kDataFrame_marked[['date', 'chan_price', 'tb', 'real_loc']][-20:]))

    def getFenBi(self, initial_state=TopBotType.noTopBot):
        self.standardize(initial_state)
        self.markTopBot(initial_state)
        self.defineBi()
        self.getPureBi()
        return self.kDataFrame_marked

    def getFenDuan(self, initial_state=TopBotType.noTopBot):
        temp_df = self.getFenBi(initial_state)
        if temp_df.size==0:
            return temp_df
        self.defineXD(initial_state)
        return self.kDataFrame_xd
    
    def getOriginal_df(self):
        return self.kDataFrame_origin
    
    def getFenBI_df(self):
        return self.kDataFrame_marked
    
    def getFenDuan_df(self):
        return self.kDataFrame_xd


################################################## XD defintion ##################################################      

    def find_initial_direction(self, working_df, initial_status=TopBotType.noTopBot):
        chan_price = 'chan_price'
        if initial_status != TopBotType.noTopBot:
            # first six elem, this can only be used when we are sure about the direction of the xd
            if initial_status == TopBotType.top:
                initial_loc = working_df[:6]['chan_price'].argmax(axis=0)
            elif initial_status == TopBotType.bot:
                initial_loc = working_df[:6]['chan_price'].argmin(axis=0)
            else:
                initial_loc = None
                print("Invalid Initial TopBot type")
            working_df[initial_loc]['xd_tb'] = initial_status.value
            if self.isdebug:
                print("initial xd_tb:{0} located at {1}".format(initial_status, working_df[initial_loc]['date']))
            initial_direction = TopBotType.top2bot if initial_status == TopBotType.top else TopBotType.bot2top
        else:
            initial_loc = current_loc = 0
            initial_direction = TopBotType.noTopBot
            while current_loc + 3 < working_df.size:
                first = working_df[current_loc]
                second = working_df[current_loc+1]
                third = working_df[current_loc+2]
                forth = working_df[current_loc+3]
                
                if first[chan_price] < second[chan_price]:
                    found_direction = (first[chan_price]<=third[chan_price] and second[chan_price]<forth[chan_price]) or\
                                        (first[chan_price]>=third[chan_price] and second[chan_price]>forth[chan_price])
                else:
                    found_direction = (first[chan_price]<third[chan_price] and second[chan_price]<=forth[chan_price]) or\
                                        (first[chan_price]>third[chan_price] and second[chan_price]>=forth[chan_price])
                                    
                if found_direction:
                    initial_direction = TopBotType.bot2top if (first[chan_price]<third[chan_price] or second[chan_price]<forth[chan_price]) else TopBotType.top2bot
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
            if self.isdebug:
                print("Invalid number of elems found")
            return False
        
        firstElem = working_df[next_valid_elems[0]]
        secondElem = working_df[next_valid_elems[1]]
        thirdElem = working_df[next_valid_elems[2]]
        forthElem = working_df[next_valid_elems[3]]
        tb = 'tb'
        chan_price = 'chan_price'
        if direction == TopBotType.top2bot:
            assert firstElem[tb] == thirdElem[tb] == TopBotType.bot.value and secondElem[tb] == forthElem[tb] == TopBotType.top.value, "Invalid starting tb status for checking inclusion top2bot: {0}, {1}, {2}, {3}".format(firstElem, thirdElem, secondElem, forthElem)
        elif direction == TopBotType.bot2top:
            assert firstElem[tb] == thirdElem[tb] == TopBotType.top.value and  secondElem[tb] == forthElem[tb] == TopBotType.bot.value, "Invalid starting tb status for checking inclusion bot2top: {0}, {1}, {2}, {3}".format(firstElem, thirdElem, secondElem, forthElem)       
        
        if (firstElem[chan_price] <= thirdElem[chan_price] and secondElem[chan_price] >= forthElem[chan_price]) or\
            (firstElem[chan_price] >= thirdElem[chan_price] and secondElem[chan_price] <= forthElem[chan_price]):  
            
            ############################## special case of kline gap as XD ##############################
            # only checking if any one node is in pure gap range. The same logic as gap for XD
            if next_valid_elems[0] + 1 == next_valid_elems[1] and\
            self.gap_exists_in_range(working_df[next_valid_elems[0]]['date'], working_df[next_valid_elems[1]]['date']):
                regions = self.gap_region(working_df[next_valid_elems[0]]['date'], working_df[next_valid_elems[1]]['date'])
                for re in regions:
                    if re[0] <= thirdElem[chan_price] <= re[1] and\
                    (re[1]-re[0])/abs(working_df[next_valid_elems[0]][chan_price]-working_df[next_valid_elems[1]][chan_price]) >= GOLDEN_RATIO:
                        if self.isdebug:
                            print("inclusion ignored due to kline gaps, with loc {0}@{1}, {2}@{3}".format(working_df[next_valid_elems[0]]['date'], 
                                                                                                          working_df[next_valid_elems[0]][chan_price],
                                                                                                          working_df[next_valid_elems[1]]['date'],
                                                                                                          working_df[next_valid_elems[1]][chan_price]))
                        return True

            if next_valid_elems[2] + 1 == next_valid_elems[3] and\
            self.gap_exists_in_range(working_df[next_valid_elems[2]]['date'], working_df[next_valid_elems[3]]['date']):
                regions = self.gap_region(working_df[next_valid_elems[2]]['date'], working_df[next_valid_elems[3]]['date'])
                for re in regions:
                    if re[0] <= secondElem[chan_price] <= re[1] and\
                    (re[1]-re[0])/abs(working_df[next_valid_elems[2]][chan_price]-working_df[next_valid_elems[3]][chan_price]) >= GOLDEN_RATIO:
                        if self.isdebug:
                            print("inclusion ignored due to kline gaps, with loc {0}@{1}, {2}@{3}".format(working_df[next_valid_elems[2]]['date'],
                                                                                                          working_df[next_valid_elems[2]][chan_price],
                                                                                                          working_df[next_valid_elems[3]]['date'],
                                                                                                          working_df[next_valid_elems[3]][chan_price]))
                        return True             
            ############################## special case of kline gap as XD ##############################                
                  
            working_df[next_valid_elems[1]][tb] = TopBotType.noTopBot.value
            working_df[next_valid_elems[2]][tb] = TopBotType.noTopBot.value
            
            if self.isdebug:
                print("location {0}@{1}, {2}@{3} removed for combination".format(working_df[next_valid_elems[1]]['date'], 
                                                                                 working_df[next_valid_elems[1]][chan_price], 
                                                                                 working_df[next_valid_elems[2]]['date'], 
                                                                                 working_df[next_valid_elems[2]][chan_price]))
            return False
        
        return True
    

    def check_inclusion_by_direction(self, current_loc, working_df, direction, with_gap):
        '''
        make sure next 6 (with gap) / 4 (without gap) bi are inclusive free, assuming the starting loc is the start of characteristic elem
        We need to check 2 kbars extra!
        '''
        i = current_loc
        first_run = True

        count_num = 8 if with_gap else 6
            
        while first_run or (i+count_num-1 < working_df.shape[0]):
            first_run = False
            
            next_valid_elems = self.get_next_N_elem(i, working_df, count_num)
            if len(next_valid_elems) < count_num:
                break
            
            if with_gap:
                if self.is_XD_inclusion_free(direction, next_valid_elems[:4], working_df):
                    if self.is_XD_inclusion_free(direction, next_valid_elems[2:6], working_df):
                        if self.is_XD_inclusion_free(direction, next_valid_elems[-4:], working_df):
                            break
            else:
                if self.is_XD_inclusion_free(direction, next_valid_elems[:4], working_df):
                    if self.is_XD_inclusion_free(direction, next_valid_elems[-4:], working_df):
                        break
                

    def check_XD_topbot(self, first, second, third, forth, fifth, sixth):
        '''
        check if current 5 BI (6 bi tb) form XD top or bot
        check if gap between first and third BI
        '''
        tb = 'tb'
        chan_price = 'chan_price'
        assert first[tb] == third[tb] == fifth[tb] and second[tb] == forth[tb] == sixth[tb], "invalid tb status!"
        
        result_status = TopBotType.noTopBot
        with_gap = False
        
        if third[tb] == TopBotType.top.value:
            with_gap = first[chan_price] < forth[chan_price]
            if third[chan_price] > first[chan_price] and\
             third[chan_price] > fifth[chan_price] and\
             forth[chan_price] > sixth[chan_price]:
                result_status = TopBotType.top
                
        elif third[tb] == TopBotType.bot.value:
            with_gap = first[chan_price] > forth[chan_price]
            if third[chan_price] < first[chan_price] and\
             third[chan_price] < fifth[chan_price] and\
             forth[chan_price] < sixth[chan_price]:
                result_status = TopBotType.bot
                            
        else:
            print("Error, invalid tb status!")
        
        return result_status, with_gap
    

    def check_kline_gap_as_xd(self, next_valid_elems, working_df, direction):
        first = working_df[next_valid_elems[0]]
        second = working_df[next_valid_elems[1]]
        third = working_df[next_valid_elems[2]]
        forth = working_df[next_valid_elems[3]]
        fifth = working_df[next_valid_elems[4]]
        xd_gap_result = TopBotType.noTopBot
        without_gap = False
        with_xd_gap = False

        # check the corner case where xd can be formed by a single kline gap
        # if kline gap (from original data) exists between second and third or third and forth
        # A if so only check if third is top or bot comparing with first, 
        # B with_gap is determined by checking if the kline gap range cover between first and forth
        # C change direction as usual, and increment counter by 1 only
        chan_price = 'chan_price'
        if not self.previous_with_xd_gap and\
        next_valid_elems[2] + 1 == next_valid_elems[3] and\
        self.gap_exists_in_range(working_df[next_valid_elems[2]]['date'], working_df[next_valid_elems[3]]['date']):
            gap_ranges = self.gap_region(working_df[next_valid_elems[2]]['date'], working_df[next_valid_elems[3]]['date'])

            for (l,h) in gap_ranges:
                # make sure the gap break previous FIRST FEATURED ELEMENT
                without_gap = l <= second[chan_price] <= h and\
                (h-l)/abs(working_df[next_valid_elems[2]][chan_price]-working_df[next_valid_elems[3]][chan_price])>=GOLDEN_RATIO
                if without_gap:
                    with_xd_gap = True
                    self.previous_with_xd_gap = True #open status
                    if self.isdebug:
                        print("XD represented by kline gap 2, {0}, {1}".format(working_df[next_valid_elems[2]]['date'], working_df[next_valid_elems[3]]['date']))
        
        if not with_xd_gap and\
        self.previous_with_xd_gap and next_valid_elems[1] + 1 == next_valid_elems[2] and\
        self.gap_exists_in_range(working_df[next_valid_elems[1]]['date'], working_df[next_valid_elems[2]]['date']):
            gap_ranges = self.gap_region(working_df[next_valid_elems[1]]['date'], working_df[next_valid_elems[2]]['date'])
            self.previous_with_xd_gap=False # close status
            for (l,h) in gap_ranges:
                # make sure first is within the gap_XD range
                without_gap = l <= forth[chan_price] <= h and\
                (h-l)/abs(working_df[next_valid_elems[1]][chan_price]-working_df[next_valid_elems[2]][chan_price])>=GOLDEN_RATIO
                if without_gap:
                    with_xd_gap = True
                    if self.isdebug:
                        print("XD represented by kline gap 1, {0}, {1}".format(working_df[next_valid_elems[1]]['date'], working_df[next_valid_elems[2]]['date']))

        if with_xd_gap:
            if (direction == TopBotType.bot2top and third[chan_price] > fifth[chan_price] and third[chan_price] > first[chan_price]):
                xd_gap_result = TopBotType.top
            elif (direction == TopBotType.top2bot and third[chan_price] < first[chan_price] and third[chan_price] < fifth[chan_price]):
                xd_gap_result = TopBotType.bot
            else:
                if self.isdebug:
                    print("XD represented by kline gap 3")
        
        return xd_gap_result, not without_gap, with_xd_gap
    
    
    def check_previous_elem_to_avoid_xd_gap(self, with_gap, next_valid_elems, working_df):
        tb = 'tb'
        chan_price = 'chan_price'
        first = working_df[next_valid_elems[0]]
        forth = working_df[next_valid_elems[3]]
        previous_elem = self.get_previous_N_elem(next_valid_elems[0], 
                                                 working_df, 
                                                 N=0, 
                                                 end_tb=TopBotType.value2type(first[tb]), 
                                                 single_direction=True)
        if len(previous_elem) >= 1: # use single direction at least 1 needed
            if first[tb] == TopBotType.top.value:
                with_gap = working_df[previous_elem][chan_price].max() < forth[chan_price]
            elif first[tb] == TopBotType.bot.value:
                with_gap = working_df[previous_elem][chan_price].min() > forth[chan_price]
            else:
                assert first[tb] == TopBotType.top.value or first[tb] == TopBotType.bot.value, "Invalid first elem tb"
        if not with_gap and self.isdebug:
            print("elem gap unchecked at {0}".format(working_df[next_valid_elems[0]]['date']))
        return with_gap  
    
    def check_XD_topbot_directed(self, next_valid_elems, direction, working_df):
        first = working_df[next_valid_elems[0]]
        second = working_df[next_valid_elems[1]]
        third = working_df[next_valid_elems[2]]
        forth = working_df[next_valid_elems[3]]
        fifth = working_df[next_valid_elems[4]]
        sixth = working_df[next_valid_elems[5]]     
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
        working_df = self.kDataFrame_marked[['date', 'close', 'high', 'low', 'chan_price', 'tb','real_loc']] # real_loc used for central region
        
        working_df = append_fields(working_df,
                                   ['original_tb', 'xd_tb'],
                                   [working_df['tb'], [TopBotType.noTopBot.value] * working_df.size],
                                   usemask=False)

        if working_df.size==0:
            self.kDataFrame_xd = working_df
            return working_df
    
        # find initial direction
        initial_i, initial_direction = self.find_initial_direction(working_df, initial_status)
        
        # loop through to find XD top bot
        working_df = self.find_XD(initial_i, initial_direction, working_df)
        
        working_df = working_df[(working_df['xd_tb']==TopBotType.top.value) | (working_df['xd_tb']==TopBotType.bot.value)]
            
        self.kDataFrame_xd = working_df[FEN_DUAN_COLUMNS]
        if self.isdebug:
            print("self.kDataFrame_xd:{0}".format(self.kDataFrame_xd))
        return working_df
    
    def get_next_N_elem(self, loc, working_df, N=4, start_tb=TopBotType.noTopBot, single_direction=False):
        '''
        get the next N number of elems if tb isn't noTopBot, 
        if start_tb is set, find the first N number of elems starting with tb given
        starting from loc(inclusive)
        '''
        i = loc
        result_locs = []
        while i < working_df.size:
            current_elem = working_df[i]
            if current_elem['tb'] != TopBotType.noTopBot.value:
                if start_tb != TopBotType.noTopBot and current_elem['tb'] != start_tb.value and len(result_locs) == 0:
                    i = i + 1
                    continue
                if single_direction and current_elem['tb'] != start_tb.value:
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
            current_elem = working_df[i]
            if current_elem['original_tb'] != TopBotType.noTopBot:
                if end_tb != TopBotType.noTopBot and current_elem['original_tb'] != end_tb and len(result_locs) == 0:
                    i = i - 1
                    continue
                if single_direction: 
                    if current_elem['original_tb'] == end_tb:
                        result_locs.insert(0, i)
                else:
                    result_locs.insert(0, i)
                if N != 0 and len(result_locs) == N:
                    break
                if N == 0 and (current_elem['xd_tb'] == TopBotType.top.value or current_elem['xd_tb'] == TopBotType.bot.value):
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
        
        chan_price_list = [working_df[nv]['chan_price'] for nv in next_valid_elems]
            
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
        real_loc = 'real_loc'
        xd_tb = 'xd_tb'
        date = 'date'
        chan_price = 'chan_price'
        tb = 'tb'
        original_tb = 'original_tb'
        if self.isdebug:
            print("Initial direction {0} at location {1} with real_loc {2}".format(initial_direction, initial_i, working_df[initial_i][real_loc]))
        
        current_direction = initial_direction  
        i = initial_i
        while i+5 < working_df.size:
            
            if self.isdebug:
                print("working at {0}, {1}, {2}, {3}, {4}".format(working_df[i][date], 
                                                                  working_df[i][chan_price], 
                                                                  current_direction, 
                                                                  working_df[i][real_loc], 
                                                                  TopBotType.value2type(working_df[i][tb])))
            
            previous_gap = len(self.gap_XD) != 0
            
            if previous_gap:
                # do inclusion till find DING DI
                self.check_inclusion_by_direction(i, working_df, current_direction, previous_gap)
                
                next_valid_elems = self.get_next_N_elem(i, working_df, 6)
                if len(next_valid_elems) < 6:
                    break
                # make sure we are checking the right elem by direction
                if not self.direction_assert(working_df[next_valid_elems[0]], current_direction):
                    i = next_valid_elems[1]
                    continue
                
                #################### pop gap_XD ##########################
                secondElem = working_df[next_valid_elems[1]]
                previous_gap_elem = working_df[self.gap_XD[-1]]
                if current_direction == TopBotType.top2bot:
                    if secondElem[chan_price] > previous_gap_elem[chan_price]:
                        previous_gap_loc = self.gap_XD.pop()
                        if self.isdebug:
                            print("xd_tb cancelled due to new high found: {0} {1}".format(working_df[previous_gap_loc][date], working_df[previous_gap_loc][real_loc]))
                        working_df[previous_gap_loc][xd_tb] = TopBotType.noTopBot.value
                        
                        # restore any combined bi due to the gapped XD
                        working_df[previous_gap_loc:next_valid_elems[-1]][tb] = working_df[previous_gap_loc:next_valid_elems[-1]][original_tb]
                        current_direction = TopBotType.reverse(current_direction)
                        if self.isdebug:
                            print("gap closed 1:{0}, {1} tb info restored to {2}".format(working_df[previous_gap_loc][date], TopBotType.value2type(working_df[previous_gap_loc][tb]), working_df[next_valid_elems[-1]][date])) 
                            [print("gap info 3:{0}, {1}".format(working_df[gap_loc][date], TopBotType.value2type(working_df[gap_loc][tb]))) for gap_loc in self.gap_XD]
                        i = previous_gap_loc
                        continue
                elif current_direction == TopBotType.bot2top:
                    if secondElem[chan_price] < previous_gap_elem[chan_price]:
                        previous_gap_loc = self.gap_XD.pop()
                        if self.isdebug:
                            print("xd_tb cancelled due to new low found: {0} {1}".format(working_df[previous_gap_loc][date], working_df[previous_gap_loc][real_loc]))
                        working_df[previous_gap_loc][xd_tb] = TopBotType.noTopBot.value
                        
                        # restore any combined bi due to the gapped XD
                        working_df[previous_gap_loc:next_valid_elems[-1]][tb] = working_df[previous_gap_loc:next_valid_elems[-1]][original_tb]
                        current_direction = TopBotType.reverse(current_direction)
                        if self.isdebug:
                            print("gap closed 2:{0}, {1} tb info restored to {2}".format(working_df[previous_gap_loc][date],  TopBotType.value2type(working_df[previous_gap_loc][tb]), working_df[next_valid_elems[-1]][date]))
                            [print("gap info 3:{0}, {1}".format(working_df[gap_loc][date], TopBotType.value2type(working_df[gap_loc][tb]))) for gap_loc in self.gap_XD]
                        i = previous_gap_loc
                        continue
                #################### pop gap_XD ##########################
                
                current_status, with_gap, with_xd_gap = self.check_XD_topbot_directed(next_valid_elems, current_direction, working_df)  

                if current_status != TopBotType.noTopBot:
                    if with_gap:
                        # save existing gapped Ding/Di
                        self.gap_XD.append(next_valid_elems[2])
                        
                        if self.isdebug:
                            [print("gap info 1:{0}, {1}".format(working_df[gap_loc][date], TopBotType.value2type(working_df[gap_loc][tb]))) for gap_loc in self.gap_XD]
                        
                    else:
                        # fixed Ding/Di, clear the record
                        self.gap_XD = []
                        if self.isdebug:
                            print("gap cleaned!")
                    working_df[next_valid_elems[2]][xd_tb] = current_status.value
                    if self.isdebug:
                        print("xd_tb located {0} {1}".format(working_df[next_valid_elems[2]][date], working_df[next_valid_elems[2]][chan_price]))
                    current_direction = TopBotType.top2bot if current_status == TopBotType.top else TopBotType.bot2top
                    i = next_valid_elems[1] if with_xd_gap else next_valid_elems[3]
                    continue
                i = next_valid_elems[2]
            else:    # no gap case            
                # find next 3 elems with the same tb info
                next_valid_elems = self.get_next_N_elem(i, working_df, 3, start_tb = TopBotType.top if current_direction == TopBotType.bot2top else TopBotType.bot, single_direction=True)
                firstElem = working_df[next_valid_elems[0]]
                
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
                            [print("gap info 4:{0}, {1}".format(working_df[gap_loc][date], TopBotType.value2type(working_df[gap_loc][tb]))) for gap_loc in self.gap_XD]
                    
                    else:
                        # cleanest case
                        pass
                    current_direction = TopBotType.top2bot if current_status == TopBotType.top else TopBotType.bot2top
                    working_df[next_valid_elems[2]][xd_tb] = current_status.value
                    if self.isdebug:
                        print("xd_tb located {0} {1}".format(working_df[next_valid_elems[2]][date], working_df[next_valid_elems[2]][chan_price]))
                    i = next_valid_elems[1] if with_xd_gap else next_valid_elems[3]
                    continue
                else:
                    i = next_valid_elems[2]
                    
        # We need to deal with the remaining BI tb and make an assumption that current XD ends

        # + 3 to make sure we have 3 BI at least in XD
        previous_xd_tb_locs = self.get_previous_N_elem(working_df.shape[0]-1, working_df, N=0, single_direction=False)
        if previous_xd_tb_locs:
            columns = ['date', chan_price, tb, original_tb]
            previous_xd_tb_loc = previous_xd_tb_locs[0]+3
            
            if previous_xd_tb_loc < working_df.shape[0]:
                # restore tb info from loc found from original_tb as we don't need them?
                working_df[previous_xd_tb_loc:][tb] = working_df[previous_xd_tb_loc:][original_tb]
                
                temp_df = working_df[previous_xd_tb_loc:][columns]
                if temp_df.size > 0:
                    temp_df = temp_df[temp_df[tb] != TopBotType.noTopBot.value]
                    gapped_change = False
                    if self.gap_XD: 
                        # with gap we check if there is higher/lower tb for xd_tb
                        if current_direction == TopBotType.top2bot:
                            max_loc = temp_df[chan_price].argmax()
                            max_date = temp_df[max_loc][date]
                            max_price = temp_df[max_loc][chan_price]
                            working_loc = np.where(working_df[date]==max_date)[0][0]
                            if max_price > working_df[previous_xd_tb_locs[0]][chan_price]:
                                working_df[previous_xd_tb_locs[0]] = TopBotType.noTopBot.value
                                working_df[working_loc][xd_tb] = TopBotType.top.value
                                gapped_change = True
                            if self.isdebug:
                                print("final gapped xd_tb located from {0} for {1}".format(max_date, TopBotType.top))
                        elif current_direction == TopBotType.bot2top:
                            min_loc = temp_df[chan_price].argmin()
                            min_date = temp_df[min_loc][date]
                            min_price = temp_df[min_loc][chan_price]
                            working_loc = np.where(working_df[date]==min_date)[0][0]
                            if min_price < working_df[previous_xd_tb_locs[0]][chan_price]:
                                working_df[previous_xd_tb_locs[0]] = TopBotType.noTopBot.value
                                working_df[working_loc][xd_tb] = TopBotType.bot.value
                                gapped_change = True
                            if self.isdebug:
                                print("final gapped xd_tb located from {0} for {1}".format(min_date, TopBotType.bot))
                    
                        if gapped_change:
                            previous_xd_tb_loc = working_loc+3
                            temp_df = working_df[previous_xd_tb_loc:][columns]
                        
                    # We could make an assumption based on assumption. 
                    if temp_df.size > 0:
                        if current_direction == TopBotType.top2bot:
                            min_loc = temp_df[chan_price].argmin()
                            min_date = temp_df[min_loc][date]
                            working_loc = np.where(working_df[date]==min_date)[0][0]
                            working_df[working_loc][xd_tb] = TopBotType.bot.value
                            if self.isdebug:
                                print("final xd_tb located from {0} for {1}".format(min_date, TopBotType.bot))
                        elif current_direction == TopBotType.bot2top:
                            max_loc = temp_df[chan_price].argmax()
                            max_date = temp_df[max_loc][date]
                            working_loc = np.where(working_df[date]==max_date)[0][0]
                            working_df[working_loc][xd_tb] = TopBotType.top.value
                            if self.isdebug:
                                print("final xd_tb located from {0} for {1}".format(max_date, TopBotType.top))
                        else:
                            print("Invalid direction")
                else:
                    print("empty temp_df, continue")
        
        return working_df
                
    def direction_assert(self, firstElem, direction):
        # make sure we are checking the right elem by direction
        result = True
        if direction == TopBotType.top2bot:
            if firstElem['tb'] != TopBotType.bot.value:
                print("We have invalid elem tb value: {0}".format(firstElem['tb']))
                result = False
        elif direction == TopBotType.bot2top:
            if firstElem['tb'] != TopBotType.top.value:
                print("We have invalid elem tb value: {0}".format(firstElem['tb']))
                result = False
        else:
            result = False
            print("We have invalid direction value!!!!!")
        return result
    
