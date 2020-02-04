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
from centralRegion import Chan_Type
from biaoLiStatus import TopBotType

TYPE_III_NUM = 5
TYPE_I_NUM = 10

def filter_high_level_by_index(direction=TopBotType.top2bot, 
                               stock_index='000985.XSHG', 
                               df=False, 
                               periods = ['60m', '120m', '1d'],
                               end_dt=pd.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                               chan_types=[Chan_Type.III, Chan_Type.I]):
    all_stocks = get_index_stocks(stock_index)
    result_stocks = set()
    for stock in all_stocks:
        for p in periods:
            stock_high = get_bars(stock, 
                                    count=max(TYPE_I_NUM, TYPE_III_NUM), 
                                    end_dt=end_dt, 
                                    unit=p,
                                    fields= ['open',  'high', 'low','close'], 
                                    df = df,
                                    include_now=True)
            for ct in chan_types:
                if KBar.filter_high_level_kbar(stock_high, 
                                               direction=direction, 
                                               df=df, 
                                               chan_type=ct):
                    result_stocks.add(stock)
    print("qualifying stocks:{0}".format(result_stocks))
    
    return sorted(list(result_stocks))

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
    def chan_type_III_check(cls, kbar_list, direction):
        '''
        max 5 high level KBars
        '''
        # early check
        if (kbar_list[-1].close < max(kbar_list[-2].high, kbar_list[-3].high, kbar_list[-4].high) and direction == TopBotType.top2bot) or\
            (kbar_list[-1].close > min(kbar_list[-2].low, kbar_list[-3].low, kbar_list[-4].low) and direction == TopBotType.bot2top):
            return False
        
        first = kbar_list[-TYPE_III_NUM]
        second = kbar_list[-TYPE_III_NUM+1] 
        third = kbar_list[-TYPE_III_NUM+2]
        forth = kbar_list[-TYPE_III_NUM+3]
        fifth = kbar_list[-TYPE_III_NUM+4]
        result = False
        if fifth.close < fifth.open or fifth.close < (fifth.high + fifth.low)/2.0:
            check_result, k_m, k_l = cls.contain_zhongshu(first, second, third, return_core_range=False)
            if check_result:
                result = fifth.low > k_m if direction == TopBotType.top2bot else fifth.high < k_l
            if not result:
                check_result, k_m, k_l = cls.contain_zhongshu(second, third, forth, return_core_range=False)
                result = check_result and fifth.close > k_m if direction == TopBotType.top2bot else fifth.high < k_l 
        return result
    
    @classmethod
    def chan_type_I_check(cls, kbar_list, direction):
        '''
        Max number of high level Kbars.
        '''
        # early check for Type I, we expect straight up or down
        if ((kbar_list[0].high <= kbar_list[-1].low or\
            min([kl.low for kl in kbar_list]) != kbar_list[-1].low) and\
            direction == TopBotType.top2bot) or\
            ((kbar_list[0].low >= kbar_list[-1].high or\
             max([kl.high for kl in kbar_list]) != kbar_list[-1].high) and\
             direction == TopBotType.bot2top):
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
                            forth.low < mi if direction == TopBotType.top2bot else forth.high > ma 
                    if result:
                        break
                i = i + 1
                extra_count = extra_count - 1
        return result

    @classmethod
    def filter_high_level_kbar(cls, high_df, direction=TopBotType.top2bot, df=True, chan_type=Chan_Type.III):
        '''
        This method used by weekly (5d) data to find out rough 5m Zhongshu and 
        type III trade point
        
        It is used as initial filters for all stocks on markets
        
        1. find nearest 5m zhongshu => three consecutive weekly kbar share price region
        2. the kbar following the zhongshu escapes by direction, 
        3. the same kbar or next kbar's return attempt never touch the previous zhongshu (only strong case)
        '''
        result = False
        num_of_kbar = TYPE_III_NUM if chan_type == Chan_Type.III else TYPE_I_NUM
        if df:
            if high_df.shape[0] >= 4:
                i = -num_of_kbar
                kbar_list = []
                while i <= -1:
                    item = high_df.iloc[i]
                    kbar_list.append(item)
                    i = i + 1
                if chan_type == Chan_Type.III:
                    result = cls.chan_type_III_check(kbar_list, direction)
                elif chan_type == Chan_Type.I:
                    result = cls.chan_type_I_check(kbar_list, direction)
        else:
            if len(high_df['open']) >= 4:
                kbar_list = cls.create_N_kbar(high_df, n=num_of_kbar)
                if chan_type == Chan_Type.III:
                    result = cls.chan_type_III_check(kbar_list, direction)
                elif chan_type == Chan_Type.I:
                    result = cls.chan_type_I_check(kbar_list, direction)          
        return result