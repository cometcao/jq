# -*- encoding: utf8 -*-

import numpy as np
import copy
import talib
from biaoLiStatus import * 
from chan_common_include import GOLDEN_RATIO, MIN_PRICE_UNIT
from kBarProcessor import synchOpenPrice, synchClosePrice
from chan_common_include import float_less, float_more, float_less_equal, float_more_equal
from numpy.lib.recfunctions import append_fields
from scipy.ndimage.interpolation import shift

FEN_BI_COLUMNS = ['date', 'close', 'high', 'low', 'tb', 'real_loc']
FEN_DUAN_COLUMNS =  ['date', 'close', 'high', 'low', 'chan_price', 'tb', 'xd_tb', 'real_loc']

def gap_range_func(a):
#     print(len(a['low']))
#     print(len(a['high_s1']))
    if float_more(a['low'] - a['high_s1'], MIN_PRICE_UNIT):
        return [a['high_s1'], a['low']]
    elif float_less(a['high'] - a['low_s1'], -MIN_PRICE_UNIT):
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
        if self.isdebug:
            print("self.kDataFrame_origin head:{0}".format(self.kDataFrame_origin[:10]))
            print("self.kDataFrame_origin tail:{0}".format(self.kDataFrame_origin[-10:]))
        
    def checkInclusive(self, first, second):
        # output: 0 = no inclusion, 1 = first contains second, 2 second contains first
        isInclusion = InclusionType.noInclusion
        first_high = first['high'] if first['new_high']==0 else first['new_high']
        second_high = second['high'] if second['new_high']==0 else second['new_high']
        first_low = first['low'] if first['new_low']==0 else first['new_low']
        second_low = second['low'] if second['new_low']==0 else second['new_low']
        
        if float_less_equal(first_high, second_high) and float_more_equal(first_low, second_low):
            isInclusion = InclusionType.firstCsecond
        elif float_more_equal(first_high, second_high) and float_less_equal(first_low, second_low):
            isInclusion = InclusionType.secondCfirst
        return isInclusion
    
    def isBullType(self, first, second): 
        # this is assuming first second aren't inclusive
        f_high = first['high'] if first['new_high']==0 else first['new_high']
        s_high = second['high'] if second['new_high']==0 else second['new_high']
        return TopBotType.bot2top if float_less(f_high, s_high) else TopBotType.top2bot
            
        
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
        if float_more(first['high'], current['high']) and float_more(first['high'], second['high']):
            return TopBotType.top
        elif float_less(first['low'], current['low']) and float_less(first['low'], second['low']):
            return TopBotType.bot
        else:
            return TopBotType.noTopBot
    
    def markTopBot(self, initial_state=TopBotType.noTopBot, mark_last_kbar=True):
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
            if (initial_state == TopBotType.top and float_more_equal(felem['high'], selem['high'])) or \
                (initial_state == TopBotType.bot and float_less_equal(felem['low'], selem['low'])):
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
        if mark_last_kbar:
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
        return np.any(gap_working_df['gap']!=0)
    
    
    def gap_exists(self):
        high_shift = shift(self.kDataFrame_origin['high'], 1, cval=0)
        low_shift = shift(self.kDataFrame_origin['low'], 1, cval=0)
        self.kDataFrame_origin = append_fields(self.kDataFrame_origin,
                                               ['gap', 'high_shift', 'low_shift', 'gap_range_start', 'gap_range_end'],
                                               [
                                                   [0]*self.kDataFrame_origin.size,
                                                   high_shift,
                                                   low_shift,
                                                   [0]*self.kDataFrame_origin.size,
                                                   [0]*self.kDataFrame_origin.size
                                               ],
                                               [int, float, float, float, float],
                                               usemask=False)
        
        i = 0
        while i < self.kDataFrame_origin.size:
            item = self.kDataFrame_origin[i]
            if float_more(item['low'] - item['high_shift'], MIN_PRICE_UNIT): # upwards gap
                self.kDataFrame_origin[i]['gap'] = 1
                self.kDataFrame_origin[i]['gap_range_start'] = item['high_shift']
                self.kDataFrame_origin[i]['gap_range_end'] = item['low']
            elif float_less(item['high'] - item['low_shift'], -MIN_PRICE_UNIT): # downwards gap
                self.kDataFrame_origin[i]['gap'] = -1
                self.kDataFrame_origin[i]['gap_range_start'] = item['high']
                self.kDataFrame_origin[i]['gap_range_end'] = item['low_shift']
            i = i + 1
        
#         self.kDataFrame_origin = self.kDataFrame_origin[FEN_BI_COLUMNS + ['gap', 'gap_range_start', 'gap_range_end']]
#         if self.isdebug:
#             print(self.kDataFrame_origin[self.kDataFrame_origin['gap']])
    
    def gap_region(self, start_idx, end_idx, direction=TopBotType.noTopBot):
        # no need to drop first row, simple don't use = 
        gap_working_df = self.kDataFrame_origin[(start_idx < self.kDataFrame_origin['date']) & (self.kDataFrame_origin['date'] <= end_idx)]
        if direction == TopBotType.noTopBot:
            return gap_working_df[gap_working_df['gap']!=0][['gap_range_start', 'gap_range_end']].tolist()
        elif direction == TopBotType.top2bot:
            return gap_working_df[gap_working_df['gap']==-1][['gap_range_start', 'gap_range_end']].tolist()
        elif direction == TopBotType.bot2top:
            return gap_working_df[gap_working_df['gap']==1][['gap_range_start', 'gap_range_end']].tolist()

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

    def clean_first_two_tb(self, working_df):
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
            if firstFenXing[tb] == secondFenXing[tb] == TopBotType.top.value and float_less(firstFenXing[high], secondFenXing[high]):
                working_df[firstIdx][tb] = TopBotType.noTopBot.value
                firstIdx = get_next_loc(firstIdx, working_df)
                secondIdx=get_next_loc(firstIdx, working_df)
                thirdIdx=get_next_loc(secondIdx, working_df)
                continue
            elif firstFenXing[tb] == secondFenXing[tb] == TopBotType.top.value and float_more_equal(firstFenXing[high], secondFenXing[high]):
                working_df[secondIdx][tb] = TopBotType.noTopBot.value
                secondIdx = get_next_loc(secondIdx, working_df)
                thirdIdx=get_next_loc(secondIdx, working_df)
                continue
            elif firstFenXing[tb] == secondFenXing[tb] == TopBotType.bot.value and float_more(firstFenXing[low], secondFenXing[low]):
                working_df[firstIdx][tb] = TopBotType.noTopBot.value
                firstIdx = get_next_loc(firstIdx, working_df)
                secondIdx=get_next_loc(firstIdx, working_df)
                thirdIdx=get_next_loc(secondIdx, working_df)
                continue
            elif firstFenXing[tb] == secondFenXing[tb] == TopBotType.bot.value and float_less_equal(firstFenXing[low], secondFenXing[low]):
                working_df[secondIdx][tb] = TopBotType.noTopBot.value
                secondIdx = get_next_loc(secondIdx, working_df)
                thirdIdx=get_next_loc(secondIdx, working_df)
                continue
            elif secondFenXing[new_index] - firstFenXing[new_index] < 4:
                if firstFenXing[tb] == thirdFenXing[tb] == TopBotType.top.value and float_less(firstFenXing[high], thirdFenXing[high]):
                    working_df[firstIdx][tb] = TopBotType.noTopBot.value
                    firstIdx = get_next_loc(firstIdx, working_df)
                    secondIdx=get_next_loc(firstIdx, working_df)
                    thirdIdx=get_next_loc(secondIdx, working_df)
                    continue
                elif firstFenXing[tb] == thirdFenXing[tb] == TopBotType.top.value and float_more_equal(firstFenXing[high], thirdFenXing[high]):
                    working_df[secondIdx][tb] = TopBotType.noTopBot.value
                    secondIdx=get_next_loc(secondIdx, working_df)
                    thirdIdx=get_next_loc(secondIdx, working_df)
                    continue
                elif firstFenXing[tb] == thirdFenXing[tb] == TopBotType.bot.value and float_more(firstFenXing[low], thirdFenXing[low]):
                    working_df[firstIdx][tb] = TopBotType.noTopBot.value
                    firstIdx = get_next_loc(firstIdx, working_df)
                    secondIdx=get_next_loc(firstIdx, working_df)
                    thirdIdx=get_next_loc(secondIdx, working_df)
                    continue
                elif firstFenXing[tb] == thirdFenXing[tb] == TopBotType.bot.value and float_less_equal(firstFenXing[low], thirdFenXing[low]):
                    working_df[secondIdx][tb] = TopBotType.noTopBot.value
                    secondIdx=get_next_loc(secondIdx, working_df)
                    thirdIdx=get_next_loc(secondIdx, working_df)
                    continue
                else:
                    print("somthing WRONG!")
                    return
                    
            elif firstFenXing[tb] == TopBotType.top.value and secondFenXing[tb] == TopBotType.bot.value and float_less_equal(firstFenXing[high], secondFenXing[low]):
                working_df[firstIdx][tb] = TopBotType.noTopBot.value
                working_df[secondIdx][tb] = TopBotType.noTopBot.value
                firstIdx = get_next_loc(firstIdx, working_df)
                secondIdx=get_next_loc(firstIdx, working_df)
                thirdIdx=get_next_loc(secondIdx, working_df)
                continue
            elif firstFenXing[tb] == TopBotType.bot.value and secondFenXing[tb] == TopBotType.top.value and float_more_equal(firstFenXing[low], secondFenXing[high]):
                working_df[firstIdx][tb] = TopBotType.noTopBot.value
                working_df[secondIdx][tb] = TopBotType.noTopBot.value
                firstIdx = get_next_loc(firstIdx, working_df)
                secondIdx=get_next_loc(firstIdx, working_df)
                thirdIdx=get_next_loc(secondIdx, working_df)
                continue
            else:
                break
 
        working_df = working_df[working_df[tb]!=TopBotType.noTopBot.value]
        return working_df
        
    def check_gap_qualify(self, working_df, previous_index, current_index, next_index):
        # possible BI status 1 check top high > bot low 2 check more than 3 bars (strict BI) in between
        # under this section of code we expect there are no two adjacent fenxings with the same status
        gap_qualify = False
        if self.gap_exists_in_range(working_df[current_index]['date'], working_df[next_index]['date']):
            gap_direction = TopBotType.bot2top if working_df[next_index]['tb'] == TopBotType.top.value else\
                            TopBotType.top2bot if working_df[next_index]['tb'] == TopBotType.bot.value else\
                            TopBotType.noTopBot
            gap_ranges = self.gap_region(working_df[current_index]['date'], working_df[next_index]['date'], gap_direction)
            gap_ranges = self.combine_gaps(gap_ranges)
            for gap in gap_ranges:
                if previous_index is None:
                    return True
                    
                if working_df[previous_index]['tb'] == TopBotType.top.value: 
                    #gap higher than previous high
                    gap_qualify = float_less(gap[0], working_df[previous_index]['low']) and\
                                  float_less_equal(working_df[previous_index]['low'], working_df[previous_index]['high']) and\
                                  float_less(working_df[previous_index]['high'], gap[1])
                elif working_df[previous_index]['tb'] == TopBotType.bot.value:
                    #gap higher than previous low
                    gap_qualify = float_more(gap[1], working_df[previous_index]['high']) and\
                                  float_more_equal(working_df[previous_index]['high'], working_df[previous_index]['low']) and\
                                  float_more(working_df[previous_index]['low'], gap[0])
                if gap_qualify:
                    break
        return gap_qualify
        
    def same_tb_remove_previous(self, working_df, previous_index, current_index, next_index):
        working_df[previous_index]['tb'] = TopBotType.noTopBot.value
        previous_index = self.trace_back_index(working_df, previous_index) #current_index # 
        if previous_index is None:
            previous_index = current_index
            current_index = next_index
            next_index = self.get_next_tb(next_index, working_df)
        else:
            if previous_index in self.previous_skipped_idx:
                self.previous_skipped_idx.remove(previous_index)
            
        return previous_index, current_index, next_index

    def same_tb_remove_current(self, working_df, previous_index, current_index, next_index):
        working_df[current_index]['tb'] = TopBotType.noTopBot.value
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
        
        return previous_index, current_index, next_index
    
    def same_tb_remove_next(self, working_df, previous_index, current_index, next_index):
        working_df[next_index]['tb'] = TopBotType.noTopBot.value
        temp_index = previous_index
        previous_index = self.trace_back_index(working_df, previous_index)
        if previous_index is None:
            previous_index = temp_index
            next_index = self.get_next_tb(next_index, working_df)
        else:
            next_index = current_index
            current_index = temp_index
            if previous_index in self.previous_skipped_idx:
                self.previous_skipped_idx.remove(previous_index)
            
        return previous_index, current_index, next_index
    

    def defineBi(self):
        '''
        This method defines fenbi for all marked top/bot:
        three indices maintained. 
        if the first two have < 4 new_index distance, we move forward
        if the second two have < 4 new_index distance, we move forward, but mark the first index
        if the second two have >= 4 new_index distance, we make decision on which one to remove, and go backwards
        if we hit all good three kbars, we check marked record and start from there
        finally, if we hit end but still have marked index, we make decision to remove one kbar and resume till finishes
        '''
        
        self.gap_exists() # work out gap in the original kline
        working_df = self.kDataFrame_standardized[self.kDataFrame_standardized['tb']!=TopBotType.noTopBot.value]
        tb = 'tb'
        high = 'high'
        low = 'low'
        new_index = 'new_index'
        
        working_df = self.clean_first_two_tb(working_df)
        
        #################################
        previous_index = 0
        current_index = previous_index + 1
        next_index = current_index + 1
        #################################
        while next_index < working_df.size and previous_index is not None and next_index is not None:
            previousFenXing = working_df[previous_index]
            currentFenXing = working_df[current_index]
            nextFenXing = working_df[next_index]
            
            if currentFenXing[tb] == previousFenXing[tb]: # used to track back the skipped previous_index
                if currentFenXing[tb] == TopBotType.top.value:
                    if float_less(currentFenXing[high], previousFenXing[high]):
                        previous_index, current_index, next_index = self.same_tb_remove_current(working_df, 
                                                                                                 previous_index, 
                                                                                                 current_index, 
                                                                                                 next_index)
                    elif float_more(currentFenXing[high], previousFenXing[high]):
                        previous_index, current_index, next_index = self.same_tb_remove_previous(working_df, 
                                                                                                 previous_index, 
                                                                                                 current_index, 
                                                                                                 next_index)
                    else: # equal case
                        gap_qualify = self.check_gap_qualify(working_df, previous_index, current_index, next_index)
                        # only remove current if it's not valid with next in case of equality
                        if working_df[next_index][new_index] - working_df[current_index][new_index] < 4 and not gap_qualify:
                            previous_index, current_index, next_index = self.same_tb_remove_current(working_df, 
                                                                                                     previous_index, 
                                                                                                     current_index, 
                                                                                                     next_index)
                        else:
                            previous_index, current_index, next_index = self.same_tb_remove_previous(working_df, 
                                                                                                     previous_index, 
                                                                                                     current_index, 
                                                                                                     next_index)
                    continue
                elif currentFenXing[tb] == TopBotType.bot.value:
                    if float_more(currentFenXing[low], previousFenXing[low]):
                        previous_index, current_index, next_index = self.same_tb_remove_current(working_df, 
                                                                                                 previous_index, 
                                                                                                 current_index, 
                                                                                                 next_index)
                    elif float_less(currentFenXing[low], previousFenXing[low]):
                        previous_index, current_index, next_index = self.same_tb_remove_previous(working_df, 
                                                                                                 previous_index, 
                                                                                                 current_index, 
                                                                                                 next_index)
                    else:# equal case
                        gap_qualify = self.check_gap_qualify(working_df, previous_index, current_index, next_index)
                        # only remove current if it's not valid with next in case of equality
                        if working_df[next_index][new_index] - working_df[current_index][new_index] < 4 and not gap_qualify:
                            previous_index, current_index, next_index = self.same_tb_remove_current(working_df, 
                                                                                                     previous_index, 
                                                                                                     current_index, 
                                                                                                     next_index)
                        else:
                            previous_index, current_index, next_index = self.same_tb_remove_previous(working_df, 
                                                                                                     previous_index, 
                                                                                                     current_index, 
                                                                                                     next_index)
                    continue
            elif currentFenXing[tb] == nextFenXing[tb]:
                if currentFenXing[tb] == TopBotType.top.value:
                    if float_less(currentFenXing[high], nextFenXing[high]):
                        previous_index, current_index, next_index = self.same_tb_remove_current(working_df, 
                                                                                                 previous_index, 
                                                                                                 current_index, 
                                                                                                 next_index)
                        
                    elif float_more(currentFenXing[high], nextFenXing[high]):
                        previous_index, current_index, next_index = self.same_tb_remove_next(working_df, 
                                                                                                 previous_index, 
                                                                                                 current_index, 
                                                                                                 next_index)
                    else: #equality case
                        pre_pre_index = self.trace_back_index(working_df, previous_index)
                        if pre_pre_index is None:
                            previous_index, current_index, next_index = self.same_tb_remove_current(working_df, 
                                                                                                     previous_index, 
                                                                                                     current_index, 
                                                                                                     next_index)
                            continue
                        gap_qualify = self.check_gap_qualify(working_df, pre_pre_index, previous_index, current_index)
                        if working_df[current_index][new_index] - working_df[previous_index][new_index] >= 4 or gap_qualify:
                            previous_index, current_index, next_index = self.same_tb_remove_next(working_df, 
                                                                                                     previous_index, 
                                                                                                     current_index, 
                                                                                                     next_index)
                        else:
                            previous_index, current_index, next_index = self.same_tb_remove_current(working_df, 
                                                                                                     previous_index, 
                                                                                                     current_index, 
                                                                                                     next_index)
                    continue
                elif currentFenXing[tb] == TopBotType.bot.value:
                    if float_more(currentFenXing[low], nextFenXing[low]):
                        previous_index, current_index, next_index = self.same_tb_remove_current(working_df, 
                                                                                                 previous_index, 
                                                                                                 current_index, 
                                                                                                 next_index)
                    elif float_less(currentFenXing[low], nextFenXing[low]):
                        previous_index, current_index, next_index = self.same_tb_remove_next(working_df, 
                                                                                                 previous_index, 
                                                                                                 current_index, 
                                                                                                 next_index)
                    else:
                        pre_pre_index = self.trace_back_index(working_df, previous_index)
                        if pre_pre_index is None:
                            previous_index, current_index, next_index = self.same_tb_remove_current(working_df, 
                                                                                                     previous_index, 
                                                                                                     current_index, 
                                                                                                     next_index)
                            continue
                        gap_qualify = self.check_gap_qualify(working_df, pre_pre_index, previous_index, current_index)
                        if working_df[current_index][new_index] - working_df[previous_index][new_index] >= 4 or gap_qualify:
                            previous_index, current_index, next_index = self.same_tb_remove_next(working_df, 
                                                                                                     previous_index, 
                                                                                                     current_index, 
                                                                                                     next_index)
                        else:
                            previous_index, current_index, next_index = self.same_tb_remove_current(working_df, 
                                                                                                     previous_index, 
                                                                                                     current_index, 
                                                                                                     next_index)
                    continue
            
            gap_qualify = self.check_gap_qualify(working_df, previous_index, current_index, next_index)
            if currentFenXing[new_index] - previousFenXing[new_index] < 4:
                # comming from current next less than 4 new_index gap, we need to determine which ones to kill
                # once done we trace back
                if (nextFenXing[new_index] - currentFenXing[new_index]) >= 4 or gap_qualify:
                    pre_pre_index = self.trace_back_index(working_df, previous_index)
                    
                    # if previous current are good, we go next
                    if self.check_gap_qualify(working_df, pre_pre_index, previous_index, current_index):
                        pass
                    
                    elif currentFenXing[tb] == TopBotType.bot.value and\
                        previousFenXing[tb] == TopBotType.top.value and\
                        nextFenXing[tb] == TopBotType.top.value:
                        if float_more_equal(previousFenXing[high], nextFenXing[high]):
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
                            if float_more_equal(prepreFenXing[low], currentFenXing[low]):
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
                        if float_less(previousFenXing[low], nextFenXing[low]):
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
                            if float_less_equal(prepreFenXing[high], currentFenXing[high]):
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
                    temp_index = self.get_next_tb(next_index, working_df)
                    if temp_index == working_df.size: # we reached the end, need to go back
                        previous_index, current_index, next_index = self.work_on_end(previous_index, 
                                                                                     current_index, 
                                                                                     next_index, 
                                                                                     working_df)
                    else:
                        # leave it for next round again!
                        self.previous_skipped_idx.append(previous_index) # mark index so we come back 
                        previous_index = current_index
                        current_index = next_index
                        next_index = temp_index
                    continue
                
            elif (nextFenXing[new_index] - currentFenXing[new_index]) < 4 and not gap_qualify: 
                temp_index = self.get_next_tb(next_index, working_df)
                if temp_index == working_df.size: # we reached the end, need to go back
                    previous_index, current_index, next_index = self.work_on_end(previous_index, 
                                                                                 current_index, 
                                                                                 next_index, 
                                                                                 working_df)
                else:
                    # leave it for next round again!
                    self.previous_skipped_idx.append(previous_index) # mark index so we come back 
                    previous_index = current_index
                    current_index = next_index
                    next_index = temp_index
                continue
            elif (nextFenXing[new_index] - currentFenXing[new_index]) >= 4 or gap_qualify:
                if currentFenXing[tb] == TopBotType.top.value and nextFenXing[tb] == TopBotType.bot.value and float_more(currentFenXing[high], nextFenXing[high]):
                    pass
                elif currentFenXing[tb] == TopBotType.top.value and nextFenXing[tb] == TopBotType.bot.value and float_less_equal(currentFenXing[high], nextFenXing[high]):
                    working_df[current_index][tb] = TopBotType.noTopBot.value
                    current_index = next_index
                    next_index = self.get_next_tb(next_index, working_df)
                    continue
                
                elif currentFenXing[tb] == TopBotType.top.value and nextFenXing[tb] == TopBotType.bot.value and float_less_equal(currentFenXing[low],nextFenXing[low]):
                    working_df[next_index][tb] = TopBotType.noTopBot.value
                    next_index = self.get_next_tb(next_index, working_df)
                    continue
                elif currentFenXing[tb] == TopBotType.top.value and nextFenXing[tb] == TopBotType.bot.value and float_more(currentFenXing[low], nextFenXing[low]):
                    pass
                
                elif currentFenXing[tb] == TopBotType.bot.value and nextFenXing[tb] == TopBotType.top.value and float_less(currentFenXing[low], nextFenXing[low]):
                    pass
                elif currentFenXing[tb] == TopBotType.bot.value and nextFenXing[tb] == TopBotType.top.value and float_more_equal(currentFenXing[low], nextFenXing[low]):
                    working_df[current_index][tb] = TopBotType.noTopBot.value
                    current_index = next_index 
                    next_index = self.get_next_tb(next_index, working_df)
                    continue
                elif currentFenXing[tb] == TopBotType.bot.value and nextFenXing[tb] == TopBotType.top.value and float_less(currentFenXing[high], nextFenXing[high]):
                    pass
                elif currentFenXing[tb] == TopBotType.bot.value and nextFenXing[tb] == TopBotType.top.value and float_more_equal(currentFenXing[high], nextFenXing[high]):
                    working_df[next_index][tb] = TopBotType.noTopBot.value
                    next_index = self.get_next_tb(next_index, working_df)
                    continue
            
            if self.previous_skipped_idx: # if we still have some left to do
                previous_index = self.previous_skipped_idx.pop()
                if working_df[previous_index][tb] == TopBotType.noTopBot.value:
                    previous_index = self.get_next_tb(previous_index, working_df)
                current_index = self.get_next_tb(previous_index, working_df)
                next_index = self.get_next_tb(current_index, working_df)
                continue
            
            # only confirmed tb comes here
            previous_index = current_index
            current_index=next_index
            next_index = self.get_next_tb(next_index, working_df)

        # if nextIndex is the last one, final clean up
        if next_index == working_df.size:
            if ((working_df[current_index][tb]==TopBotType.top.value and float_more(self.kDataFrame_origin[-1][high], working_df[current_index][high])) \
                or (working_df[current_index][tb]==TopBotType.bot.value and float_less(self.kDataFrame_origin[-1][low], working_df[current_index][low]) )):
                working_df[-1][tb] = working_df[current_index][tb]
                working_df[current_index][tb] = TopBotType.noTopBot.value
            
            if working_df[current_index][tb] == TopBotType.noTopBot.value and\
                ((working_df[previous_index][tb]==TopBotType.top.value and float_more(self.kDataFrame_origin[-1][high], working_df[previous_index][high])) or\
                 (working_df[previous_index][tb]==TopBotType.bot.value and float_less(self.kDataFrame_origin[-1][low], working_df[previous_index][low]))):
                working_df[-1][tb] = working_df[previous_index][tb]
                working_df[previous_index][tb] = TopBotType.noTopBot.value
                
            if working_df[previous_index][tb] == working_df[current_index][tb]:
                if working_df[current_index][tb] == TopBotType.top.value:
                    if float_more(working_df[current_index][high],working_df[previous_index][high]):
                        working_df[previous_index][tb] = TopBotType.noTopBot.value
                    else:
                        working_df[current_index][tb] = TopBotType.noTopBot.value
                elif working_df[current_index][tb] == TopBotType.bot.value:
                    if float_less(working_df[current_index][low], working_df[previous_index][low]):
                        working_df[previous_index][tb] = TopBotType.noTopBot.value
                    else:
                        working_df[current_index][tb] = TopBotType.noTopBot.value
        ###################################    
        self.kDataFrame_marked = working_df[working_df[tb]!=TopBotType.noTopBot.value][FEN_BI_COLUMNS]
        if self.isdebug:
            print("self.kDataFrame_marked head 20:{0}".format(self.kDataFrame_marked[:20]))
            print("self.kDataFrame_marked tail 20:{0}".format(self.kDataFrame_marked[-20:]))


    def work_on_end(self, pre_idx, cur_idx, nex_idx, working_df):
        '''
        only triggered at the end of fenbi loop
        '''
        previousFenXing = working_df[pre_idx]
        currentFenXing = working_df[cur_idx]
        nextFenXing = working_df[nex_idx]

        if currentFenXing['tb'] == TopBotType.top.value:
            if float_more(previousFenXing['low'], nextFenXing['low']):
                working_df[pre_idx]['tb'] = TopBotType.noTopBot.value
                pre_idx = self.trace_back_index(working_df, pre_idx)
            else:
                working_df[nex_idx]['tb'] = TopBotType.noTopBot.value
                nex_idx = cur_idx
                cur_idx = pre_idx
                pre_idx = self.trace_back_index(working_df, pre_idx)
        else: # TopBotType.bot
            if float_less(previousFenXing['high'], nextFenXing['high']):
                working_df[pre_idx]['tb'] = TopBotType.noTopBot.value
                pre_idx = self.trace_back_index(working_df, pre_idx)
            else:
                working_df[nex_idx]['tb'] = TopBotType.noTopBot.value
                nex_idx = cur_idx
                cur_idx = pre_idx
                pre_idx = self.trace_back_index(working_df, pre_idx)
        if pre_idx in self.previous_skipped_idx:
            self.previous_skipped_idx.remove(pre_idx)
        return pre_idx, cur_idx, nex_idx

    def getMarkedBL(self):
        self.standardize()
        self.markTopBot()
        self.defineBi()
#         self.defineBi_new()
        self.getPureBi()
        return self.kDataFrame_marked
    
    def formed_tb(self, tb = TopBotType.bot):
        self.standardize()
        self.markTopBot(mark_last_kbar=False)
        
#         self.defineBi()
#         working_df = self.kDataFrame_marked
# #         working_df = self.kDataFrame_standardized
#         total_size = self.kDataFrame_origin.size
# #         print("tb info: {0}, total size: {1}".format(working_df, self.kDataFrame_origin.size))
#           
#         if working_df.size > 0 and\
#             working_df['tb'][-1] == tb.value and\
#             total_size - 1 - working_df['real_loc'][-1] <=2 :
#             if working_df.size > 2:
#                 check_price_result = float_less_equal(working_df['low'][-1], working_df['low'][-3])\
#                                      if tb == TopBotType.bot else\
#                                      float_more_equal(working_df['high'][-1], working_df['high'][-3])
#                 return True, check_price_result
#             else:
#                 return True, True
#         return False, False
        
        working_df = self.kDataFrame_standardized
        found_idx = np.where(working_df['tb']==tb.value)[0]
#         print(working_df)
#         print("tb location: {0}, total size: {1}".format(found_idx, working_df.size))
  
        if len(found_idx) > 0 and found_idx[-1] == working_df.size-2:
            if len(found_idx) >= 2:
                check_price_result = float_less_equal(working_df['low'][found_idx[-1]], min(self.kDataFrame_origin['low']))\
                                    if tb == TopBotType.bot else\
                                    float_more_equal(working_df['high'][found_idx[-1]], max(self.kDataFrame_origin['high']))
            else:
                check_price_result = False
            return True, check_price_result
        return False, False
        
    
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

    def getFenBi(self, initial_state=TopBotType.noTopBot, mark_last_kbar=True):
        self.standardize(initial_state)
        self.markTopBot(initial_state, mark_last_kbar=mark_last_kbar)
        self.defineBi()
        self.getPureBi()
        return self.kDataFrame_marked

    def getFenDuan(self, initial_state=TopBotType.noTopBot, mark_last_kbar=True):
        temp_df = self.getFenBi(initial_state, mark_last_kbar=mark_last_kbar)
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
                
                if float_less(first[chan_price], second[chan_price]):
                    found_direction = (float_less_equal(first[chan_price],third[chan_price]) and float_less(second[chan_price],forth[chan_price])) or\
                                        (float_more_equal(first[chan_price],third[chan_price]) and float_more(second[chan_price],forth[chan_price]))
                else:
                    found_direction = (float_less(first[chan_price],third[chan_price]) and float_less_equal(second[chan_price],forth[chan_price])) or\
                                        (float_more(first[chan_price],third[chan_price]) and float_more_equal(second[chan_price],forth[chan_price]))
                                    
                if found_direction:
                    initial_direction = TopBotType.bot2top if (float_less(first[chan_price],third[chan_price]) or float_less(second[chan_price],forth[chan_price])) else TopBotType.top2bot
                    initial_loc = current_loc
                    break
                else:
                    current_loc = current_loc + 1
            
        return initial_loc, initial_direction

    def combine_gaps(self, gap_regions):
        '''
        gap regions come in as ordered
        '''
        i = 0 
        if len(gap_regions) <= 1:
            return gap_regions
        
        # sort gap regions
        gap_regions = sorted(gap_regions, key=lambda tup: tup[0])
        
        new_gaps = []
        temp_range= None
        while i + 1 < len(gap_regions):
            current_range = gap_regions[i]
            next_range = gap_regions[i+1]
            
            if temp_range is None:
                if float_more_equal(current_range[1], next_range[0]):
                    temp_range = (current_range[0], next_range[1])
                else:
                    new_gaps.append(current_range)
                    temp_range = next_range
            else:
                if float_more_equal(temp_range[1], next_range[0]):
                    temp_range = (temp_range[0], next_range[1])
                else:
                    new_gaps.append(temp_range)
                    temp_range = next_range
            i = i + 1
        new_gaps.append(temp_range)
                
        return new_gaps

    def kbar_gap_as_xd(self, working_df, first_idx, second_idx, compare_idx):
        '''
        check given gapped kbar can be considered xd alone
        '''
        firstElem = working_df[first_idx]
        secondElem = working_df[second_idx]
        compareElem = working_df[compare_idx] if compare_idx is not None else None
        item_price_covered = False
        gap_range_in_portion = False
        if first_idx + 1 == second_idx and\
            self.gap_exists_in_range(firstElem['date'], secondElem['date']):
            gap_direction = TopBotType.bot2top if secondElem['tb'] == TopBotType.top.value else\
                            TopBotType.top2bot if secondElem['tb'] == TopBotType.bot.value else\
                            TopBotType.noTopBot
            regions = self.gap_region(firstElem['date'], secondElem['date'], gap_direction)
            if regions:
                regions = self.combine_gaps(regions)
    #             for re in regions:
    # #                 if float_less_equal(re[0], compareElem['chan_price']) and float_less_equal(compareElem['chan_price'], re[1]):
    # #                     item_price_covered = True
    #                 if float_more_equal((re[1]-re[0])/abs(firstElem['chan_price']-secondElem['chan_price']), GOLDEN_RATIO):
    #                     gap_range_in_portion = True
    #                 if gap_range_in_portion:
    #                     return gap_range_in_portion
                    
                gap_range = sum([(b-a) for a, b in regions])
                if float_more_equal(gap_range/abs(firstElem['chan_price']-secondElem['chan_price']), GOLDEN_RATIO):
                    gap_range_in_portion = True
                
                if compareElem is None:
                    item_price_covered = True
                else:
                    if gap_direction == TopBotType.top2bot:
                        item_price_covered = float_less_equal(regions[0][0], compareElem['chan_price'])
                    elif gap_direction == TopBotType.bot2top:
                        item_price_covered = float_more_equal(regions[-1][1], compareElem['chan_price'])
                    else:
                        item_price_covered = False
                
                if gap_range_in_portion and item_price_covered:
                    return True
        return False
    

    def xd_inclusion(self, firstElem, secondElem, thirdElem, forthElem):
        '''
        given four elem check the xd formed contain inclusive relationship, positive as True, negative as False
        '''
        if (float_less_equal(firstElem['chan_price'], thirdElem['chan_price']) and float_more_equal(secondElem['chan_price'], forthElem['chan_price'])) or\
            (float_more_equal(firstElem['chan_price'], thirdElem['chan_price']) and float_less_equal(secondElem['chan_price'], forthElem['chan_price'])):
            return True
        return False

    def build_feature_seq(self, working_df, start_loc):
        seq = []
        for i in range(start_loc, len(working_df)):
            otb = working_df[i]['original_tb']
            if otb != TopBotType.noTopBot.value:
                p = working_df[i]['high'] if otb == TopBotType.top.value else working_df[i]['low']
                seq.append({
                    'tb': otb,
                    'price': p,
                    'orig_price': p,
                    'orig_market_idx': i,
                    'is_merged': False
                })
        return seq

    def _has_feature_inclusion(self, e0, e1, e2, e3):
        return (float_less_equal(e0['price'], e2['price']) and float_more_equal(e1['price'], e3['price'])) or \
               (float_more_equal(e0['price'], e2['price']) and float_less_equal(e1['price'], e3['price']))

    def merge_feature_seq_pair(self, feature_seq, i, direction):
        e0 = feature_seq[i]
        e1 = feature_seq[i+1]
        e2 = feature_seq[i+2]
        e3 = feature_seq[i+3]

        if direction == TopBotType.bot2top:
            cmp_func = max
        else:
            cmp_func = min

        merged_price_0 = cmp_func(e0['price'], e2['price'])
        merged_orig_price_0 = cmp_func(e0['orig_price'], e2['orig_price'])
        if direction == TopBotType.bot2top:
            winner_idx_0 = e0['orig_market_idx'] if float_more_equal(e0['orig_price'], e2['orig_price']) else e2['orig_market_idx']
        else:
            winner_idx_0 = e0['orig_market_idx'] if float_less_equal(e0['orig_price'], e2['orig_price']) else e2['orig_market_idx']

        e0['price'] = merged_price_0
        e0['orig_price'] = merged_orig_price_0
        e0['orig_market_idx'] = winner_idx_0
        e0['is_merged'] = True

        merged_price_1 = cmp_func(e1['price'], e3['price'])
        merged_orig_price_1 = cmp_func(e1['orig_price'], e3['orig_price'])
        if direction == TopBotType.bot2top:
            winner_idx_1 = e1['orig_market_idx'] if float_more_equal(e1['orig_price'], e3['orig_price']) else e3['orig_market_idx']
        else:
            winner_idx_1 = e1['orig_market_idx'] if float_less_equal(e1['orig_price'], e3['orig_price']) else e3['orig_market_idx']

        e1['price'] = merged_price_1
        e1['orig_price'] = merged_orig_price_1
        e1['orig_market_idx'] = winner_idx_1
        e1['is_merged'] = True

        del feature_seq[i+3]
        del feature_seq[i+2]

    def process_inclusions(self, feature_seq, direction):
        if len(feature_seq) < 4:
            return

        expected_start_tb = TopBotType.top.value if direction == TopBotType.bot2top else TopBotType.bot.value

        start = 0
        while start < len(feature_seq) and feature_seq[start]['tb'] != expected_start_tb:
            start += 1
        if start >= len(feature_seq):
            return

        i = start
        while i + 3 < len(feature_seq):
            e0 = feature_seq[i]
            e1 = feature_seq[i+1]
            e2 = feature_seq[i+2]
            e3 = feature_seq[i+3]
            if self._has_feature_inclusion(e0, e1, e2, e3):
                self.merge_feature_seq_pair(feature_seq, i, direction)
                if i > start:
                    i -= 2
                else:
                    i = start
            else:
                i += 2

    def apply_clean_sequence(self, feature_seq, working_df, start_loc):
        if not feature_seq:
            return

        end_loc = feature_seq[-1]['orig_market_idx'] + 1
        for i in range(start_loc, min(end_loc, len(working_df))):
            if working_df[i]['tb'] != TopBotType.noTopBot.value:
                working_df[i]['tb'] = TopBotType.noTopBot.value

        for elem in feature_seq:
            idx = elem['orig_market_idx']
            if 0 <= idx < len(working_df):
                working_df[idx]['tb'] = elem['tb']
                working_df[idx]['chan_price'] = elem['orig_price']

    def _kbar_gap_as_xd_feature_seq(self, feature_seq, idx1, idx2, compare_idx, working_df):
        wdf_idx1 = feature_seq[idx1]['orig_market_idx']
        wdf_idx2 = feature_seq[idx2]['orig_market_idx']
        wdf_compare_idx = feature_seq[compare_idx]['orig_market_idx'] if compare_idx is not None else None
        if wdf_idx1 + 1 != wdf_idx2:
            return False
        return self.kbar_gap_as_xd(working_df, wdf_idx1, wdf_idx2, wdf_compare_idx)

    def find_xd_on_feature_seq(self, feature_seq, working_df, direction):
        result = {
            'found': False,
            'xd_market_idx': -1,
            'xd_type': TopBotType.noTopBot,
            'with_gap': False,
            'next_market_start': -1,
            'is_kg2_backstep': False,
            'rollback': -1
        }

        if len(feature_seq) < 6:
            return result

        target_tb = TopBotType.top.value if direction == TopBotType.bot2top else TopBotType.bot.value
        seq_pos = 0
        while seq_pos < len(feature_seq) and feature_seq[seq_pos]['tb'] != target_tb:
            seq_pos += 1
        if seq_pos + 5 >= len(feature_seq):
            return result

        i = seq_pos
        while i + 5 < len(feature_seq):
            e0 = feature_seq[i]
            e1 = feature_seq[i+1]
            e2 = feature_seq[i+2]
            e3 = feature_seq[i+3]
            e4 = feature_seq[i+4]
            e5 = feature_seq[i+5]

            xd_type = TopBotType.noTopBot
            with_gap = False
            kg2 = False

            if not self.previous_with_xd_gap:
                kg2 = self._kbar_gap_as_xd_feature_seq(feature_seq, i+2, i+3, i+1, working_df)
                if kg2:
                    self.previous_with_xd_gap = True
            if not kg2 and self.previous_with_xd_gap:
                self.previous_with_xd_gap = False
                kg2 = self._kbar_gap_as_xd_feature_seq(feature_seq, i+1, i+2, i, working_df)
                if kg2:
                    self.previous_with_xd_gap = True

            if kg2:
                if direction == TopBotType.bot2top and float_more(e2['orig_price'], e4['orig_price']):
                    xd_type = TopBotType.top
                elif direction == TopBotType.top2bot and float_less(e2['orig_price'], e4['orig_price']):
                    xd_type = TopBotType.bot
                if xd_type != TopBotType.noTopBot:
                    with_gap = True

            if xd_type == TopBotType.noTopBot:
                if direction == TopBotType.bot2top:
                    if e2['tb'] == TopBotType.top.value and \
                       float_more(e2['orig_price'], e0['orig_price']) and \
                       float_more(e2['orig_price'], e4['orig_price']) and \
                       float_more(e3['orig_price'], e5['orig_price']):
                        xd_type = TopBotType.top
                        with_gap = float_less(e0['orig_price'], e3['orig_price'])
                else:
                    if e2['tb'] == TopBotType.bot.value and \
                       float_less(e2['orig_price'], e0['orig_price']) and \
                       float_less(e2['orig_price'], e4['orig_price']) and \
                       float_less(e3['orig_price'], e5['orig_price']):
                        xd_type = TopBotType.bot
                        with_gap = float_more(e0['orig_price'], e3['orig_price'])

            if xd_type != TopBotType.noTopBot:
                if with_gap:
                    wdf_indices = [feature_seq[i+j]['orig_market_idx'] for j in range(6)]
                    with_gap = self.check_previous_elem_to_avoid_xd_gap(with_gap, wdf_indices, working_df)

                result['found'] = True
                result['xd_market_idx'] = e2['orig_market_idx']
                result['xd_type'] = xd_type
                result['with_gap'] = with_gap

                new_i = i + 1 if kg2 else i + 3
                if new_i < len(feature_seq):
                    result['next_market_start'] = feature_seq[new_i]['orig_market_idx']
                else:
                    result['next_market_start'] = e2['orig_market_idx'] + 1
                result['is_kg2_backstep'] = (new_i == i + 1)
                return result

            i += 1

        return result

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
            with_gap = float_less(first[chan_price], forth[chan_price])
            if float_more(third[chan_price], first[chan_price]) and\
             float_more(third[chan_price], fifth[chan_price]) and\
             float_more(forth[chan_price], sixth[chan_price]):
                result_status = TopBotType.top
                
        elif third[tb] == TopBotType.bot.value:
            with_gap = float_more(first[chan_price], forth[chan_price])
            if float_less(third[chan_price], first[chan_price]) and\
             float_less(third[chan_price], fifth[chan_price]) and\
             float_less(forth[chan_price], sixth[chan_price]):
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
        with_kline_gap_as_xd = False

        # check the corner case where xd can be formed by a single kline gap
        # if kline gap (from original data) exists between second and third or third and forth
        # A if so only check if third is top or bot comparing with first, 
        # B with_gap is determined by checking if the kline gap range cover between first and forth
        # C change direction as usual, and increment counter by 1 only
        chan_price = 'chan_price'
        if not self.previous_with_xd_gap and\
            self.kbar_gap_as_xd(working_df, next_valid_elems[2], next_valid_elems[3], next_valid_elems[1]):
            without_gap = with_kline_gap_as_xd = True
            self.previous_with_xd_gap = True
            if self.isdebug:
                print("XD represented by kline gap 2, {0}, {1}".format(working_df[next_valid_elems[2]]['date'], working_df[next_valid_elems[3]]['date']))
        
        if not with_kline_gap_as_xd and self.previous_with_xd_gap:
            self.previous_with_xd_gap=False # close status
            if self.kbar_gap_as_xd(working_df, next_valid_elems[1], next_valid_elems[2], next_valid_elems[0]):
                without_gap = with_kline_gap_as_xd = True
                if self.isdebug:
                    print("XD represented by kline gap 1, {0}, {1}".format(working_df[next_valid_elems[1]]['date'], working_df[next_valid_elems[2]]['date']))

        if with_kline_gap_as_xd: # we don't need to compare with the first elem
            if (direction == TopBotType.bot2top and float_more(third[chan_price], fifth[chan_price])): #and float_more(third[chan_price], first[chan_price])
                xd_gap_result = TopBotType.top
            elif (direction == TopBotType.top2bot and float_less(third[chan_price], fifth[chan_price])): #and float_less(third[chan_price], first[chan_price]) 
                xd_gap_result = TopBotType.bot
            else:
                if self.isdebug:
                    print("XD represented by kline gap 3")
        
        return xd_gap_result, not without_gap, with_kline_gap_as_xd
    
    
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
                with_gap = float_less(working_df[previous_elem][chan_price].max(), forth[chan_price])
            elif first[tb] == TopBotType.bot.value:
                with_gap = float_more(working_df[previous_elem][chan_price].min(), forth[chan_price])
            else:
                assert first[tb] == TopBotType.top.value or first[tb] == TopBotType.bot.value, "Invalid first elem tb"
        if not with_gap and self.isdebug:
            print("elem gap unchecked at {0}".format(working_df[next_valid_elems[0]]['date']))
        return with_gap  
    
    def defineXD(self, initial_status=TopBotType.noTopBot):
        working_df = self.kDataFrame_marked[['date', 'close', 'high', 'low', 'chan_price', 'tb','real_loc']]

        working_df = append_fields(working_df,
                                   ['original_tb', 'xd_tb'],
                                   [working_df['tb'], [TopBotType.noTopBot.value] * working_df.size],
                                   usemask=False)

        if working_df.size==0:
            self.kDataFrame_xd = working_df
            return working_df

        initial_i, initial_direction = self.find_initial_direction(working_df, initial_status)

        self.gap_XD = []
        self.previous_with_xd_gap = False

        tail_start = initial_i
        direction = initial_direction

        while tail_start < len(working_df):
            feature_seq = self.build_feature_seq(working_df, tail_start)
            if len(feature_seq) < 6:
                break

            self.process_inclusions(feature_seq, direction)

            self.apply_clean_sequence(feature_seq, working_df, tail_start)

            result = self.find_xd_on_feature_seq(feature_seq, working_df, direction)
            if not result['found']:
                break

            xd_idx = result['xd_market_idx']

            rollback_idx = -1
            if result['with_gap'] and self.gap_XD:
                previous_gap_elem = working_df[self.gap_XD[-1]]
                check_prices = [working_df[i]['chan_price'] for i in range(
                    xd_idx, min(xd_idx+4, len(working_df))) if working_df[i]['original_tb'] != TopBotType.noTopBot.value]
                if check_prices:
                    if direction == TopBotType.top2bot and float_more(max(check_prices), previous_gap_elem['chan_price']):
                        rollback_idx = self.gap_XD.pop()
                    elif direction == TopBotType.bot2top and float_less(min(check_prices), previous_gap_elem['chan_price']):
                        rollback_idx = self.gap_XD.pop()
                    if rollback_idx >= 0:
                        working_df[rollback_idx]['xd_tb'] = TopBotType.noTopBot.value
                        self.restore_tb_data(working_df, rollback_idx,
                                             result['next_market_start'] if result['next_market_start'] > 0 else len(working_df)-1)
                        direction = TopBotType.reverse(direction)
                        tail_start = rollback_idx
                        continue

            if rollback_idx < 0:
                prev_xd_locs = self.get_previous_N_elem(xd_idx, working_df, N=0,
                    end_tb=TopBotType.reverse(result['xd_type']), single_direction=True)
                if prev_xd_locs:
                    prev_idx = prev_xd_locs[0]
                    prev_xd = working_df[prev_idx]
                    if ((prev_xd['xd_tb'] == TopBotType.top.value and
                         result['xd_type'] == TopBotType.bot and
                         float_less(prev_xd['chan_price'], working_df[xd_idx]['chan_price'])) or
                        (prev_xd['xd_tb'] == TopBotType.bot.value and
                         result['xd_type'] == TopBotType.top and
                         float_more(prev_xd['chan_price'], working_df[xd_idx]['chan_price']))):
                        self.restore_tb_data(working_df, prev_idx, len(working_df)-1)
                        working_df[prev_idx]['xd_tb'] = TopBotType.noTopBot.value
                        direction = TopBotType.top2bot if result['xd_type'] == TopBotType.top else TopBotType.bot2top
                        tail_start = prev_idx
                        continue

            working_df[xd_idx]['xd_tb'] = result['xd_type'].value

            if result['with_gap']:
                self.gap_XD.append(xd_idx)

            tail_start = result['next_market_start']
            if not result['is_kg2_backstep'] and tail_start < xd_idx:
                tail_start = xd_idx

            direction = TopBotType.top2bot if result['xd_type'] == TopBotType.top else TopBotType.bot2top

        self._xd_tail_inference(working_df, direction)

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
            if current_elem['original_tb'] != TopBotType.noTopBot.value:
                if end_tb != TopBotType.noTopBot and current_elem['original_tb'] != end_tb.value and len(result_locs) == 0:
                    i = i - 1
                    continue
                if single_direction: 
                    if current_elem['original_tb'] == end_tb.value:
                        result_locs.insert(0, i)
                else:
                    result_locs.insert(0, i)
                if N != 0 and len(result_locs) == N:
                    break
                if N == 0 and (current_elem['xd_tb'] == TopBotType.top.value or current_elem['xd_tb'] == TopBotType.bot.value):
                    break
            i = i - 1
        return result_locs
    

    
    def restore_tb_data(self, working_df, from_idx, to_idx):
        working_df[from_idx:to_idx]['tb'] = working_df[from_idx:to_idx]['original_tb']
        if self.isdebug:
            print("tb data restored from {0} to {1} real_loc {2} to {3}".format(working_df[from_idx]['date'], 
                                                                                working_df[to_idx if to_idx is not None else -1]['date'], 
                                                                                working_df[from_idx]['real_loc'], 
                                                                                working_df[to_idx if to_idx is not None else -1]['real_loc']))
 
    
    def pop_gap(self, working_df, next_valid_elems, current_direction):
        chan_price = 'chan_price'
        tb = 'tb'
        original_tb = 'original_tb'
        xd_tb='xd_tb'
        date='date'
        real_loc='real_loc'
        i = None
        #################### pop gap_XD ##########################
        checking_elems_price = working_df[next_valid_elems[0]:next_valid_elems[-1]+1][chan_price]
        
        previous_gap_elem = working_df[self.gap_XD[-1]]
        if current_direction == TopBotType.top2bot:
            if float_more(max(checking_elems_price), previous_gap_elem[chan_price]):
                previous_gap_loc = self.gap_XD.pop()
                if self.isdebug:
                    print("xd_tb cancelled due to new high found: {0} {1}".format(working_df[previous_gap_loc][date], working_df[previous_gap_loc][real_loc]))
                working_df[previous_gap_loc][xd_tb] = TopBotType.noTopBot.value
                
                self.restore_tb_data(working_df, previous_gap_loc, next_valid_elems[-1])
                current_direction = TopBotType.reverse(current_direction)
                if self.isdebug:
                    print("gap closed 1:{0}, {1}".format(working_df[previous_gap_loc][date], TopBotType.value2type(working_df[previous_gap_loc][tb]))) 
                    [print("gap info 3:{0}, {1}".format(working_df[gap_loc][date], TopBotType.value2type(working_df[gap_loc][tb]))) for gap_loc in self.gap_XD]
                i = previous_gap_loc
                
        elif current_direction == TopBotType.bot2top:
            if float_less(min(checking_elems_price), previous_gap_elem[chan_price]):
                previous_gap_loc = self.gap_XD.pop()
                if self.isdebug:
                    print("xd_tb cancelled due to new low found: {0} {1}".format(working_df[previous_gap_loc][date], working_df[previous_gap_loc][real_loc]))
                working_df[previous_gap_loc][xd_tb] = TopBotType.noTopBot.value
                
                self.restore_tb_data(working_df, previous_gap_loc, next_valid_elems[-1])
                current_direction = TopBotType.reverse(current_direction)
                if self.isdebug:
                    print("gap closed 2:{0}, {1}".format(working_df[previous_gap_loc][date],  TopBotType.value2type(working_df[previous_gap_loc][tb])))
                    [print("gap info 3:{0}, {1}".format(working_df[gap_loc][date], TopBotType.value2type(working_df[gap_loc][tb]))) for gap_loc in self.gap_XD]
                i = previous_gap_loc
        return i, current_direction
        #################### pop gap_XD ##########################

    def _xd_tail_inference(self, working_df, current_direction):
        xd_tb = 'xd_tb'
        chan_price = 'chan_price'
        tb = 'tb'
        original_tb = 'original_tb'
        date = 'date'
        previous_xd_tb_locs = self.get_previous_N_elem(working_df.shape[0]-1, working_df, N=0, single_direction=False)
        if previous_xd_tb_locs:
            pre_pre_xd_tb_locs = self.get_previous_N_elem(previous_xd_tb_locs[0], working_df, N=0, single_direction=False)
            columns = ['date', chan_price, tb, original_tb]
            previous_xd_tb_loc = previous_xd_tb_locs[0]
            working_xd_tb_loc = previous_xd_tb_loc+3

            if working_xd_tb_loc < working_df.shape[0]:
                temp_df = working_df[working_xd_tb_loc:][columns]
                if temp_df.size > 0:
                    temp_df = temp_df[temp_df[tb] != TopBotType.noTopBot.value]
                    gapped_change = False
                    if self.gap_XD:
                        if current_direction == TopBotType.top2bot:
                            max_loc = temp_df[chan_price].argmax()
                            max_date = temp_df[max_loc][date]
                            max_price = temp_df[max_loc][chan_price]
                            working_loc = np.where(working_df[date]==max_date)[0][0]
                            if float_more(max_price, working_df[previous_xd_tb_loc][chan_price]):
                                working_df[previous_xd_tb_loc][xd_tb] = TopBotType.noTopBot.value
                                working_df[working_loc][xd_tb] = TopBotType.top.value
                                gapped_change = True
                            if self.isdebug:
                                print("final gapped xd_tb located from {0} for {1}".format(max_date, TopBotType.top))
                        elif current_direction == TopBotType.bot2top:
                            min_loc = temp_df[chan_price].argmin()
                            min_date = temp_df[min_loc][date]
                            min_price = temp_df[min_loc][chan_price]
                            working_loc = np.where(working_df[date]==min_date)[0][0]
                            if float_less(min_price, working_df[previous_xd_tb_loc][chan_price]):
                                working_df[previous_xd_tb_loc][xd_tb] = TopBotType.noTopBot.value
                                working_df[working_loc][xd_tb] = TopBotType.bot.value
                                gapped_change = True
                            if self.isdebug:
                                print("final gapped xd_tb located from {0} for {1}".format(min_date, TopBotType.bot))

                        if gapped_change:
                            working_xd_tb_loc = working_loc+3
                            previous_xd_tb_loc = working_loc
                            temp_df = working_df[working_xd_tb_loc:][columns]

                    if temp_df.size > 0:
                        max_price = temp_df[chan_price].max()
                        min_price = temp_df[chan_price].min()

                        if current_direction == TopBotType.top2bot:
                            if float_more(working_df[previous_xd_tb_loc][chan_price], max_price) or\
                                (pre_pre_xd_tb_locs and float_more(working_df[pre_pre_xd_tb_locs[0]][chan_price], min_price)):
                                min_loc = temp_df[chan_price].argmin()
                                min_date = temp_df[min_loc][date]
                                working_loc = np.where(working_df[date]==min_date)[0][0]
                                working_df[working_loc][xd_tb] = TopBotType.bot.value
                                if self.isdebug:
                                    print("final xd_tb located from {0} for {1}".format(min_date, TopBotType.bot))
                            elif float_less(working_df[previous_xd_tb_loc][chan_price], max_price):
                                max_loc = temp_df[chan_price].argmax()
                                max_date = temp_df[max_loc][date]
                                working_loc = np.where(working_df[date]==max_date)[0][0]
                                working_df[working_loc][xd_tb] = TopBotType.top.value
                                working_df[previous_xd_tb_loc][xd_tb] = TopBotType.noTopBot.value
                                if self.isdebug:
                                    print("final xd_tb located from {0} for {1}, replacing {2}".format(max_date,
                                                                                                   TopBotType.top,
                                                                                                   working_df[previous_xd_tb_loc][date]))
                        elif current_direction == TopBotType.bot2top:
                            if float_less(working_df[previous_xd_tb_loc][chan_price], min_price) or\
                                (pre_pre_xd_tb_locs and float_less(working_df[pre_pre_xd_tb_locs[0]][chan_price], max_price)):
                                max_loc = temp_df[chan_price].argmax()
                                max_date = temp_df[max_loc][date]
                                working_loc = np.where(working_df[date]==max_date)[0][0]
                                working_df[working_loc][xd_tb] = TopBotType.top.value
                                if self.isdebug:
                                    print("final xd_tb located from {0} for {1}".format(max_date, TopBotType.top))
                            elif float_more(working_df[previous_xd_tb_loc][chan_price], min_price):
                                min_loc = temp_df[chan_price].argmin()
                                min_date = temp_df[min_loc][date]
                                working_loc = np.where(working_df[date]==min_date)[0][0]
                                working_df[working_loc][xd_tb] = TopBotType.bot.value
                                working_df[previous_xd_tb_loc][xd_tb] = TopBotType.noTopBot.value
                                if self.isdebug:
                                    print("final xd_tb located from {0} for {1}, replacing {2}".format(min_date,
                                                                                                   TopBotType.bot,
                                                                                                   working_df[previous_xd_tb_loc][date]))
                        else:
                            print("Invalid direction")
                else:
                    print("empty temp_df, continue")

                
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
    
