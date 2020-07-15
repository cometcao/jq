# -*- encoding: utf8 -*-
'''
Created on 18 Jan 2020

@author: MetalInvest
'''
try:
    from kuanke.user_space_api import *
except ImportError as ie:
    print(str(ie))
from jqdata import *
import numpy as np
import pandas as pd
from biaoLiStatus import TopBotType

from chan_common_include import *

def filter_high_level_by_index(direction=TopBotType.top2bot, 
                               stock_index=['000985.XSHG'], 
                               df=False, 
                               periods = ['60m', '120m', '1d'],
                               end_dt=pd.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                               chan_types=[Chan_Type.I, Chan_Type.III]):
    all_stocks = []
    for idx in stock_index:
        idx_stocks = get_index_stocks(idx, end_dt)
        all_stocks = all_stocks + idx_stocks
    
    all_stocks = list(set(all_stocks))
    
    return filter_high_level_by_stocks(
                                        direction,
                                        all_stocks,
                                        df=df,
                                        periods=periods,
                                        end_dt=end_dt,
                                        chan_types=chan_types
                                        )

def filter_high_level_by_stocks(direction, 
                               stock_list, 
                               df=False, 
                               periods = ['30m'],
                               end_dt=pd.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                               chan_types=[Chan_Type.I, Chan_Type.III]):
    
    result_stocks_I = set()
    result_stocks_III = set()
    result_stocks_PB = set()
    for stock in stock_list:
        for p in periods:
            result_stocks_I, result_stocks_III, result_stocks_PB = filter_high_level_by_stock(stock, 
                                                                            p, 
                                                                            end_dt, 
                                                                            df, 
                                                                            chan_types,
                                                                            direction,
                                                                            result_stocks_I, 
                                                                            result_stocks_III,
                                                                            result_stocks_PB)
    type_i = sorted(list(result_stocks_I))
    type_iii = sorted(list(result_stocks_III))
    type_pb = sorted(list(result_stocks_PB))
    print("qualifying type I stocks:{0} {1} \ntype III stocks: {2} {3} \ntype PB stocks: {4} {5}".format(type_i,
                                                                                                         len(type_i),
                                                                                             type_iii,
                                                                                             len(type_iii),
                                                                                             type_pb,
                                                                                             len(type_pb)))
    
    return sorted(list(set(type_i + type_iii + type_pb)))


def filter_high_level_by_stock(stock, 
                               period, 
                               end_dt, 
                               df, 
                               chan_types, 
                               direction,
                               result_stocks_I, 
                               result_stocks_III,
                               result_stocks_PB):
    stock_high = get_bars(stock, 
                           count=max(TYPE_I_NUM, TYPE_III_NUM), 
                           end_dt=end_dt, 
                           unit=period,
                           fields= ['open',  'high', 'low','close'], 
                           df = df,
                           include_now=True)
    
    chan_type_results = KBar.filter_high_level_kbar(stock_high, 
                                   direction=direction, 
                                   df=df, 
                                   chan_types=chan_types)
    if Chan_Type.I in chan_type_results or Chan_Type.I_weak in chan_type_results:
        result_stocks_I.add(stock)
    elif Chan_Type.III in chan_type_results:
        result_stocks_III.add(stock)
    elif Chan_Type.INVALID in chan_type_results:
        result_stocks_PB.add(stock)
    
    return result_stocks_I, result_stocks_III, result_stocks_PB

class KBar(object):
    '''
    used for initial filter with OCHL
    '''
    def __init__(self, open, close, high, low):
        self.open = open
        self.close = close
        self.high = high
        self.low = low
        
    def __repr__(self):
        return "\nOPEN:{0} CLOSE:{1} HIGH:{2} LOW:{3}".format(self.open, self.close, self.high, self.low)


    @classmethod
    def filter_high_level_kbar(cls, high_df, direction=TopBotType.top2bot, df=False, chan_types=[Chan_Type.III]):
        '''
        This method used by weekly (5d) data to find out rough 5m Zhongshu and 
        type III trade point
        
        It is used as initial filters for all stocks on markets
        
        1. find nearest 5m zhongshu => three consecutive weekly kbar share price region
        2. the kbar following the zhongshu escapes by direction, 
        3. the same kbar or next kbar's return attempt never touch the previous zhongshu (only strong case)
        '''
        chan_type_result = []
        num_of_kbar = TYPE_I_NUM if Chan_Type.I in chan_types else TYPE_III_NUM
        if df:
            if high_df.shape[0] >= num_of_kbar:
                i = -num_of_kbar
                kbar_list = []
                while i <= -1:
                    item = high_df.iloc[i]
                    kbar_list.append(item)
                    i = i + 1
            else:
                return chan_type_result
        else:
            if len(high_df['open']) >= num_of_kbar:
                kbar_list = cls.create_N_kbar(high_df, n=num_of_kbar)
            else:
                return chan_type_result
                
        if Chan_Type.III in chan_types and cls.chan_type_III_check(kbar_list, direction):
            chan_type_result.append(Chan_Type.III)
        elif Chan_Type.I in chan_types and cls.chan_type_I_check(kbar_list, direction):
            chan_type_result.append(Chan_Type.I)
        elif Chan_Type.INVALID in chan_types and cls.chan_type_PB_check(kbar_list, direction):
            chan_type_result.append(Chan_Type.INVALID)
            
        return chan_type_result


    @classmethod
    def contain_zhongshu(cls, first, second, third, return_core_range=False):
        '''
        check consecutive three kbars with intersection, 
        return_core_range controls return range type, 
        in case of true only core range
        otherwise, we take the max range of first three kbars
        TYPE III: False
        TYPE I : True
        '''
        if first.high >= second.high >= first.low or\
            first.high >= second.low >= first.low or\
            second.high >= first.high >= second.low or\
            second.high >= first.low >= second.low:
            new_high, new_low = min(first.high, second.high), max(first.low, second.low)
            if new_high >= third.high >= new_low or\
                new_high >= third.low >= new_low or\
                third.high >= new_high >= third.low or\
                third.high >= new_low >= third.low:
                if return_core_range:
                    return True, min(new_high, third.high), max(new_low, third.low)
                else:
                    return True, max(first.high, second.high, third.high), min(first.low, second.low, third.low)
        return False, 0, 0
    
    @classmethod 
    def create_N_kbar(cls, high_df, n = TYPE_III_NUM):
        i = -n
        kbar_list = []
        while i <= -1:
            kb = KBar(high_df['open'][i], high_df['close'][i], high_df['high'][i], high_df['low'][i])
            kbar_list.append(kb)
            i = i + 1
        return kbar_list
        
    @classmethod
    def chan_type_PB_check(cls, kbar_list, direction):
        '''
        maximum 5 Kbars, at high level used for pan bei
        '''
        if (
                direction == TopBotType.top2bot and\
                (
                    kbar_list[-5].close < kbar_list[-1].close or\
                    min(kbar_list[-2].high, kbar_list[-3].high, kbar_list[-4].high) < kbar_list[-1].close
#                     max(kbar_list[-2].low, kbar_list[-3].low, kbar_list[-4].low) > kbar_list[-5].high
                )
            ) or\
            (
                direction == TopBotType.bot2top and\
                (
                    kbar_list[-5].close > kbar_list[-1].close or\
                    max(kbar_list[-2].low, kbar_list[-3].low, kbar_list[-4].low) > kbar_list[-1].close
#                     min(kbar_list[-2].high, kbar_list[-3].high, kbar_list[-4].high) < kbar_list[-5].low
                )
            ):
            return False
        
        start_idx = -6
        end_idx = -4
        
        aa = kbar_list[start_idx]
        bb = kbar_list[start_idx+1] 
        cc = kbar_list[start_idx+2]
        last = kbar_list[-1]
        result = False
        if (last.close < last.open) or ((last.close-last.low)/(last.high-last.low) <= (1-GOLDEN_RATIO)):
            
            while start_idx <= end_idx:
                check_result, k_m, k_l = cls.contain_zhongshu(aa, bb, cc, return_core_range=False)
                
                if check_result:
                    first_max = max([kbar.high for kbar in kbar_list[:start_idx]])
                    first_min = min([kbar.low for kbar in kbar_list[:start_idx]])
                    result = (float_less_equal(last.low, k_l) and float_more_equal(first_max, k_m))\
                              if direction == TopBotType.top2bot else\
                              (float_more_equal(last.high, k_m) and float_less_equal(first_min, k_l))
                if result:
                    return result
                else:
                    start_idx = start_idx + 1
                    aa = kbar_list[start_idx]
                    bb = kbar_list[start_idx+1] 
                    cc = kbar_list[start_idx+2]
        
        return result
        
        
    @classmethod
    def chan_type_III_check(cls, kbar_list, direction):
        '''
        incase of 7 high level KBars
        assume we are given the data necessary, we need at least the last KBar to step back,
        so that means we have 4 steps for remaining 6 kbars to check zhongshu of 3 kbars
        '''
        # early check
        if (direction == TopBotType.top2bot and\
                (
                    max(kbar_list[0].high, kbar_list[1].high, kbar_list[2].high) >= kbar_list[-1].low or\
                    kbar_list[-1].close >= max(kbar_list[-2].high, kbar_list[-3].high)
                )
            ) or\
            (direction == TopBotType.bot2top and\
                (
                    min(kbar_list[0].low, kbar_list[1].low, kbar_list[2].low) <= kbar_list[-1].low or\
                    kbar_list[-1].close <= min(kbar_list[-2].low, kbar_list[-3].low)
                )
            ):
            return False
        
        start_idx = 0
        steps = 4
        first = kbar_list[start_idx]
        second = kbar_list[start_idx+1] 
        third = kbar_list[start_idx+2]
        last = kbar_list[-1]
        result = False
        if (last.close < last.open) or ((last.close-last.low)/(last.high-last.low) <= (1-GOLDEN_RATIO)):
            
            while start_idx < steps:
                check_result, k_m, k_l = cls.contain_zhongshu(first, second, third, return_core_range=False)
                
                if check_result:
                    result = (last.low > k_m if direction == TopBotType.top2bot else last.high < k_l) \
                                if (last.close < last.open) else \
                            (last.close > k_m if direction == TopBotType.top2bot else last.close < k_l)
                if result:
                    return result
                else:
                    start_idx = start_idx + 1
                    first = kbar_list[start_idx]
                    second = kbar_list[start_idx+1] 
                    third = kbar_list[start_idx+2]
        return result
    
    @classmethod
    def chan_type_I_check(cls, kbar_list, direction):
        '''
        Max number of high level Kbars.
        '''
        # early check for Type I, we expect straight up or down
        if (direction == TopBotType.top2bot and\
            (kbar_list[0].high <= kbar_list[-1].low or\
            min([kl.low for kl in kbar_list]) != kbar_list[-1].low)) or\
            (direction == TopBotType.bot2top and\
            (kbar_list[0].low >= kbar_list[-1].high or\
             max([kl.high for kl in kbar_list]) != kbar_list[-1].high)):
            return False
        
        result = False
        i = 0
        first_zs = False
        first_zs_ma = 0
        first_zs_mi = 0
        extra_count = 2 # the round of checks after finding the first ZS
        while i+4 < len(kbar_list) and extra_count > 0:
            first = kbar_list[i]
            second = kbar_list[i+1]
            third = kbar_list[i+2]
            check_result, ma, mi = cls.contain_zhongshu(first, second, third, return_core_range=False)
            if not first_zs:
                if check_result:
                    first_zs = True
                    first_zs_ma = ma
                    first_zs_mi = mi
                    i = i + 3
                else:
                    i = i + 1
            else:
                if check_result:
                    forth = kbar_list[i+3]
                    result = first_zs_ma < mi if direction == TopBotType.bot2top else first_zs_mi > ma and\
                            forth.close < mi if direction == TopBotType.top2bot else forth.close > ma 
                    if result:
                        break
                i = i + 1
                extra_count = extra_count - 1
        return result

