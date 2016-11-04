'''
Created on 1 Oct 2016

@author: MetalInvest
'''

from kuanke.user_space_api import *

import config
import pandas as pd
import numpy as np
import datetime
from scipy.signal import argrelextrema

class chan_II_signal():
    '''
    This class analyze II signal (buy/sell) from Chan theory. A simplified version of II signal, 
    without any central region analysis
    '''
    buy_signal_record = {}
    recent_prime_level_top= {}
    recent_prime_level_change_pct = {}
    def __init__(self):
        '''
        Constructor
        '''
        pass
    
    def clearDict(self):
        # called at end of trading day
        #chan_II_signal.recent_prime_level_top = {}
        for stock in chan_II_signal.recent_prime_level_top.keys():
            if stock not in chan_II_signal.buy_signal_record.keys():
                del chan_II_signal.recent_prime_level_top[stock]
    
    def getPeriod(self, stock):
        recent_high_datetime, recent_low_datetime = chan_II_signal.recent_prime_level_top[stock]
        delta = recent_low_datetime - recent_high_datetime
        return delta.days
    
    def check_II_sell_signal(self, dataFrame_s):
        sell_signal = False
        
        sell_signal = self.checkInSellPoint(dataFrame_s)
        
        return sell_signal
    
    def check_II_buy_signal(self, dataFrame_p, dataFrame_s, stock):
        buy_signal = False
        
        # 1. check we had a primary level of price rise, and fallback followed
        isAtPrimeLevel = self.checkPrimeLevelInBuyPoint(dataFrame_p, stock)

        # 2. check we have a deficient of momentum in sub level
        if isAtPrimeLevel:
            buy_signal = self.checkSubLevelInBuyPoint(dataFrame_s, stock)
            
        # 3. check we have a deficient of central region divergence in super level (todo)
    
        return buy_signal
    
    def findMaxMin(self, df):
        high = df['high'].values
        low = df['low'].values
        topIndex = argrelextrema(high, np.greater_equal,order=1)[0]
        bottomIndex = argrelextrema(low, np.less_equal,order=1)[0]
        return topIndex, bottomIndex, high, low
    
    def checkPrimeLevelInBuyPoint_v2(self, prime_df, stock, advance_margin = config.margin['maximum_advacne_margin'], fallback_margin = config.margin['minimum_fallback_margin']):
        recent_price = prime_df['close'][-1]
        topIndex, bottomIndex, high, low = self.findMaxMin(prime_df)
        if topIndex.size and bottomIndex.size:
            minBot = min(low)
            minBot_datetime = prime_df['low'].idxmin()
            
            recent_low = low[bottomIndex[-1]] 
            recent_high= high[topIndex[-1]]
            
            recent_low_datetime = prime_df['low'].index[bottomIndex[-1]]
            recent_high_datetime = prime_df['high'].index[topIndex[-1]]
#             if stock == '300035.XSHE':
#                 print "check stock %s with recent_low %f recent_high %f min %f" % (stock, recent_low, recent_high, minBot)
#                 print "at time %s, %s, %s" % (recent_low_datetime, recent_high_datetime, minBot_datetime)

            if recent_low_datetime > recent_high_datetime > minBot_datetime and \
            recent_high > recent_price >= recent_low > minBot and \
            (recent_high - minBot) / minBot >= advance_margin and \
            (recent_high - recent_low) / (recent_high - minBot) >= fallback_margin:
                chan_II_signal.recent_prime_level_top[stock] = (recent_high_datetime, recent_low_datetime)
                return True
        return False
        
    
    def checkPrimeLevelInBuyPoint(self, prime_df, stock):
        recent_price = prime_df['close'][-1]
#         high = self.dataFrame_p['high'].values
#         low = self.dataFrame_p['low'].values
#         topIndex = argrelextrema(high, np.greater_equal,order=1)
#         bottomIndex = argrelextrema(high, np.less_equal,order=1)
        topIndex, bottomIndex, high, low = self.findMaxMin(prime_df)
        
        if len(topIndex) < 1 or len(bottomIndex) < 2:
            return False
    
        recent_low = low[bottomIndex[-1]] 
        previous_low = low[bottomIndex[-2]] 
        recent_high= high[topIndex[-1]]
        
        recent_low_datetime = prime_df['low'].index[bottomIndex[-1]]
        previous_low_datetime = prime_df['low'].index[bottomIndex[-2]]
        recent_high_datetime = prime_df['high'].index[topIndex[-1]]
        
        if recent_low_datetime < recent_high_datetime or recent_high_datetime < previous_low_datetime:
            return False
        
        # determine if we just had a rise followed by fallback at prime level
        if recent_high > recent_low and recent_low > previous_low:
            # we want to make sure this rise is big enough, and the fallback is legit
            if recent_high / previous_low >= config.margin['minimum_advance_margin'] and (recent_high - recent_low) / (recent_high - previous_low) >= config.margin['minimum_fallback_margin']:
                # check current price hasn't moved to far from recent low
                if recent_price / recent_low < config.margin['minimum_divergence_margin_upper'] and recent_price / recent_low > config.margin['minimum_divergence_margin_lower']:
                    chan_II_signal.recent_prime_level_top[stock] = (recent_high_datetime, recent_low_datetime)
                    return True
        return False

    def checkSubLevelInBuyPoint(self, sub_df, stock):
        '''
        This method depends on the following fields to be set previously
        self.recent_low_datetime = None
        self.recent_high_datetime = None
        self.previous_low_datetime = None
        
        we need to find if the movement momentum has been depleted from lower level
        use CHAN definition, we need to find at least two cenral regions in the sub level
        we however can not be very strict here with full central region definition as
        this is simplified version
        
        We need 6 local max/min
        
        '''
        #recent_price = sub_df['close'][-1]
        if stock not in chan_II_signal.recent_prime_level_top or stock in chan_II_signal.buy_signal_record:
            return False
        
        recent_high_datetime, recent_low_datetime = chan_II_signal.recent_prime_level_top[stock]
        
        work_df = sub_df.ix[recent_high_datetime:recent_low_datetime] 
        return self.checkInBuyPoint(work_df, stock)

    
    def checkInBuyPoint(self, df, stock):
        # we need to find if the movement momentum has been depleted from lower level
        # use strict CHAN definition, we need to find at least two cenral regions in the sub level
        topIndex, bottomIndex, high, low = self.findMaxMin(df)
        
        if len(topIndex) < 3 or len(bottomIndex) < 3:
            return False
        
        # We use simplified version here at least two sub central regions along the fallback trend
        recent_low = low[bottomIndex[-1]] 
        recent_high= high[topIndex[-1]]  
        
        recent_low_idx = bottomIndex[-1]
        recent_high_idx = topIndex[-1]
        
        second_low = low[bottomIndex[-2]] 
        second_high = high[topIndex[-2]]
        
        second_low_idx = bottomIndex[-2]
        second_high_idx = topIndex[-2]  
        
        third_low = low[bottomIndex[-3]]
        third_high = high[topIndex[-3]]
        
        third_low_idx = bottomIndex[-3]
        third_high_idx = topIndex[-3]
        
        #recent_price will have to be between the recent_low and recent_high
        if recent_high > recent_low and recent_low_idx > recent_high_idx:
            recent_ratio = (recent_high - recent_low) / (recent_low_idx - recent_high_idx)
            if second_high > second_low and second_low_idx > second_high_idx:
                second_ratio = (second_high - second_low) / (second_low_idx - second_high_idx)
                if third_high > third_low and third_low_idx > third_high_idx and recent_ratio < second_ratio:
                    third_ratio = (third_high - third_low) / (third_low_idx - third_high_idx)
                    if third_ratio > second_ratio:
                        chan_II_signal.buy_signal_record[stock] = df.index[-1].strftime("%Y-%m-%d %H:%M:%S")
                        return True
        return False        
    
    def checkInSellPoint(self, sub_df, stock):
        if sub_df.empty or stock not in chan_II_signal.buy_signal_record:
            return False
        
        _, past_low_datetime = chan_II_signal.recent_prime_level_top[stock]
        
        # the stock to sell has to be in the buy_signal_record dict 
        # otherwise we have some problems
        work_df = sub_df[sub_df.index > chan_II_signal.buy_signal_record[stock]]
        topIndex, bottomIndex, high, low = self.findMaxMin(work_df)

        if len(topIndex) < 2 or len(bottomIndex) < 2:
            return False
        
        recent_low = low[bottomIndex[-1]] 
        recent_high= high[topIndex[-1]]  
        
        recent_low_idx = bottomIndex[-1]
        recent_high_idx = topIndex[-1]
        
        second_low = low[bottomIndex[-2]] 
        second_high = high[topIndex[-2]]
        
        second_low_idx = bottomIndex[-2]
        second_high_idx = topIndex[-2] 
        
        second_low_datetime = work_df['low'].index[second_low_idx]
        #second_high_datetime = work_df['high'].index[second_high_idx]
        
        # make sure we have past previous time
        if second_low_datetime > past_low_datetime:
            if recent_high > recent_low and recent_high_idx > recent_low_idx:
                recent_ratio = (recent_high - recent_low) / (recent_high_idx - recent_low_idx)
                if second_high > second_low and second_high_idx > second_low_idx:
                    second_ratio = (second_high - second_low) / (second_high_idx - second_low_idx)
                    if recent_ratio < second_ratio or recent_high < second_high:
                        del chan_II_signal.buy_signal_record[stock]
                        return True
                    
        return False