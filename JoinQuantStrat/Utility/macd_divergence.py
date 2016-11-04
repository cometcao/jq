'''
Created on 21 Sep 2016

@author: MetalInvest
'''
import talib
import numpy as np
from collections import OrderedDict
from functools import partial
import pandas as pd

lower_ratio_range = 0.98


# global constants
macd_func = partial(talib.MACD, fastperiod=12,slowperiod=26,signalperiod=9)


class macd_divergence(object):
    '''
    classdocs
    '''


    def __init__(self, params):
        '''
        Constructor
        '''
    
    def findNearestIndexPeakBottom(self, list):
        pass
    
    def macd_bottom_divergence(self, df, context):
        macd_raw, signal, hist = macd_func(df['low'])
        return self.checkAtBottomDoubleCross(macd_raw, hist, df['low'])
    

    def macd_top_divergence(self, df, context, data):
        macd_raw, signal, hist = macd_func(df['high'])
        return self.checkAtTopDoubleCross(macd_raw, hist, df['high']) 
     
    def isDeathCross(self, i,j, macd):
        # if macd sign change, we detect an immediate cross
        # sign changed from -val to +val and 
        if i == 0:
            return False
        if j<0 and macd[i-1] >0:
            return True
        return False
    
    def isGoldCross(self, i,j, macd):
        # if macd sign change, we detect an immediate cross
        # sign changed from -val to +val and 
        if i == 0:
            return False
        if j>0 and macd[i-1] <0:
            return True
        return False
    
    def checkAtTopDoubleCross(self, macd_raw, macd_hist, prices):
        # hist height less than 0.5 should be considered a crossing candidate
        # return True if we are close at MACD top reverse
        indexOfGoldCross = [i for i, j in enumerate(macd_hist) if self.isGoldCross(i,j,macd_hist)]   
        indexOfDeathCross = [i for i, j in enumerate(macd_hist) if self.isDeathCross(i,j,macd_hist)] 
        #print indexOfCross
        if (not indexOfGoldCross) or (not indexOfDeathCross) or (len(indexOfDeathCross)<2) or (len(indexOfGoldCross)<2) or \
        abs(indexOfGoldCross[-1]-indexOfDeathCross[-1]) <= 2 or \
        abs(indexOfGoldCross[-1]-indexOfDeathCross[-2]) <= 2 or \
        abs(indexOfGoldCross[-2]-indexOfDeathCross[-1]) <= 2 or \
        abs(indexOfGoldCross[-2]-indexOfDeathCross[-2]) <= 2:
            return False
        
        if macd_raw[-1] > 0 and macd_hist[-1] > 0 and macd_hist[-1] < macd_hist[-2]: 
            latest_hist_area = macd_hist[indexOfGoldCross[-1]:]
            max_val_Index = latest_hist_area.tolist().index(max(latest_hist_area))
            recentArea_est = abs(sum(latest_hist_area[:max_val_Index])) * 2
            
            previousArea = macd_hist[indexOfGoldCross[-2]:indexOfDeathCross[-1]]
            previousArea_sum = abs(sum(previousArea))
            
            prices_z = zscore(prices)
            if recentArea_est < previousArea_sum and (max(prices_z[indexOfGoldCross[-1]:]) / max(prices_z[indexOfGoldCross[-2]:indexOfDeathCross[-1]]) > lower_ratio_range ) :
                return True
        return False
    
    def checkAtBottomDoubleCross(self, macd_raw, macd_hist, prices):
        # find cross index for gold and death
        # calculate approximated areas between death and gold cross for bottom reversal
        # adjacent reducing negative hist bar areas(appx) indicated double bottom reversal signal
        
        indexOfGoldCross = [i for i, j in enumerate(macd_hist) if self.isGoldCross(i,j,macd_hist)]   
        indexOfDeathCross = [i for i, j in enumerate(macd_hist) if self.isDeathCross(i,j,macd_hist)] 
        
        if (not indexOfGoldCross) or (not indexOfDeathCross) or (len(indexOfDeathCross)<2) or (len(indexOfGoldCross)<2) or \
        abs(indexOfGoldCross[-1]-indexOfDeathCross[-1]) <= 2 or \
        abs(indexOfGoldCross[-1]-indexOfDeathCross[-2]) <= 2 or \
        abs(indexOfGoldCross[-2]-indexOfDeathCross[-1]) <= 2 or \
        abs(indexOfGoldCross[-2]-indexOfDeathCross[-2]) <= 2:
            # no cross found
            # also make sure gold cross isn't too close to death cross as we don't want that situation
            return False
    
        # check for standard double bottom macd divergence pattern
        # green bar is reducing
        if macd_raw[-1] < 0 and macd_hist[-1] < 0 and macd_hist[-1] > macd_hist[-2]: 
            # calculate current negative bar area 
            latest_hist_area = macd_hist[indexOfDeathCross[-1]:]
            min_val_Index = latest_hist_area.tolist().index(min(latest_hist_area))
            recentArea_est = abs(sum(latest_hist_area[:min_val_Index])) * 2
            
            previousArea = macd_hist[indexOfDeathCross[-2]:indexOfGoldCross[-1]]
            previousArea_sum = abs(sum(previousArea))
            
            # this is only an estimation
            #bottom_len = indexOfDeathCross[-1] - indexOfDeathCross[-2]
            # log.info("recentArea_est : %.2f, with min price: %.2f" % (recentArea_est, min(prices[indexOfDeathCross[-2]:indexOfGoldCross[-1]])))
            # log.info("previousArea_sum : %.2f, with min price: %.2f" % (previousArea_sum, min(prices[indexOfDeathCross[-1]:])) )
            # log.info("bottom_len: %d" % bottom_len)
            
            # standardize the price and macd_raw to Z value
            # return the diff of price zvalue and macd z value
            prices_z = zscore(prices)
            #macd_raw_z = zscore(np.nan_to_num(macd_raw))
            
            if recentArea_est < previousArea_sum and (min(prices_z[indexOfDeathCross[-2]:indexOfGoldCross[-1]]) / min(prices_z[indexOfDeathCross[-1]:]) > lower_ratio_range) :
                return True
        return False
    
        def zscore(self, series):
            return (series - series.mean()) / np.std(series)