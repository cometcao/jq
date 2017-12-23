# -*- encoding: utf8 -*-
'''
Created on 21 Sep 2016

@author: MetalInvest
'''
import talib
import numpy as np
from functools import partial
import pandas as pd
lower_ratio_range = 0.98


# global constants
macd_func = partial(talib.MACD, fastperiod=12,slowperiod=26,signalperiod=9)


class macd_divergence():
    '''
    classdocs
    '''


    def __init__(self):
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
        
    def checkAtBottomDoubleCross_chan_old(self, df, useZvalue=False):
        # shortcut
        if not (df.shape[0] > 2 and df['macd'][-1] < 0 and df['macd'][-1] > df['macd'][-2] and df['macd'][-1] > df['macd'][-3]):
            return False
        
        # gold
        mask = df['macd'] > 0
        mask = mask[mask==True][mask.shift(1) == False]
        
        # death
        mask2 = df['macd'] < 0
        mask2 = mask2[mask2==True][mask2.shift(1)==False]
        
        try:
            gkey1 = mask.keys()[-1]
            dkey2 = mask2.keys()[-2]
            dkey1 = mask2.keys()[-1]
            recent_low = previous_low = 0.0
            if useZvalue:
                low_mean = df.loc[dkey2:,'low'].mean(axis=0)
                low_std = df.loc[dkey2:,'low'].std(axis=0)
                df.loc[dkey2:, 'low_z'] = (df.loc[dkey2:,'low'] - low_mean) / low_std
                
                recent_low = df.loc[dkey1:,'low_z'].min(axis=0)
                previous_low = df.loc[dkey2:gkey1, 'low_z'].min(axis=0)
            else:
                recent_low = df.loc[dkey1:,'low'].min(axis=0)
                previous_low = df.loc[dkey2:gkey1, 'low'].min(axis=0)
                
            recent_min_idx = df.loc[dkey1:,'low'].idxmin()
            previous_min_idx = df.loc[dkey2:gkey1,'low'].idxmin()
            loc = df.index.get_loc(recent_min_idx)
            recent_min_idx_nx = df.index[loc+1]
            recent_area_est = abs(df.loc[dkey1:recent_min_idx_nx, 'macd'].sum(axis=0)) * 2
            
            previous_area = abs(df.loc[dkey2:gkey1, 'macd'].sum(axis=0))
            previous_close = df['close'][-1]
            
            result =  df.macd[-2] < df.macd[-1] < 0 and \
                    df.macd[-3] < df.macd[-1] and \
                    0 > df.macd_raw[-1] and \
                    df.macd[recent_min_idx] > df.macd[previous_min_idx] and \
                    recent_area_est < previous_area and \
                    previous_low >= recent_low and \
                    df.loc[dkey2,'vol_ma'] > df.vol_ma[-1]
                    # abs (recent_low / previous_low) > g.lower_ratio_range
                    # recent_area_est < recent_red_area and \
                    # > df.macd_raw[recent_min_idx]
                    #previous_low >= recent_low and \
                    #previous_close / df.loc[recent_min_idx, 'close'] < g.upper_ratio_range
                    # abs (recent_low / previous_low) > g.lower_ratio_range
            return result
        except IndexError:
            return False

    def checkAtBottomDoubleCross_chan(self, df):
        # shortcut
        if not (df.shape[0] > 2 and df['macd'][-1] < 0 and df['macd'][-1] > df['macd'][-2] and df['macd'][-1] > df['macd'][-3]):
            return False
        
        # gold
        mask = df['macd'] > 0
        mask = mask[mask==True][mask.shift(1) == False]
        
        # death
        mask2 = df['macd'] < 0
        mask2 = mask2[mask2==True][mask2.shift(1)==False]
        
        try:
            gkey1 = mask.keys()[-1]
            dkey2 = mask2.keys()[-2]
            dkey1 = mask2.keys()[-1]

            recent_low = df.loc[dkey1:,'low'].min(axis=0)
            previous_low = df.loc[dkey2:gkey1, 'low'].min(axis=0)
                
            recent_min_idx = df.loc[dkey1:,'low'].idxmin()
            previous_min_idx = df.loc[dkey2:gkey1,'low'].idxmin()
            loc = df.index.get_loc(recent_min_idx)
            recent_min_idx_nx = df.index[loc+1]
            recent_area_est = abs(df.loc[dkey1:recent_min_idx_nx, 'macd'].sum(axis=0)) * 2
            
            previous_area = abs(df.loc[dkey2:gkey1, 'macd'].sum(axis=0))
            recent_high = df.loc[dkey1:, 'high'].max(axis=0)
            
            result =  df.macd[-2] < df.macd[-1] < 0 and \
                    df.macd[-3] < df.macd[-1] and \
                    0 > df.macd_raw[-1] and \
                    df.macd[recent_min_idx] > df.macd[previous_min_idx] and \
                    recent_area_est < previous_area and \
                    previous_low >= recent_low and \
                    recent_high < previous_low and \
                    recent_low <= df.lower[recent_min_idx]
                    
            return result
        except IndexError:
            return False


    def checkAtBottomDoubleCross_v2(self, df):
        # bottom divergence gold
        mask = df['macd'] > 0
        mask = mask[mask==True][mask.shift(1) == False]#[mask.shift(2)==False]
        
        mask2 = df['macd'] < 0
        mask2 = mask2[mask2==True][mask2.shift(1)==False]#[mask2.shift(2)==False]#[mask2.shift(-1)==True]
        try:
            dkey2 = mask2.keys()[-2]
            dkey1 = mask2.keys()[-1]
            
            gkey2 = mask.keys()[-2]
            gkey1 = mask.keys()[-1]
            
            previous_raise_area = abs(df.loc[gkey2:dkey1,'macd'].sum(axis=0))
            previous_area = abs(df.loc[dkey2:gkey2, 'macd'].sum(axis=0))
            recent_area = abs(df.loc[dkey1:gkey1, 'macd'].sum(axis=0))
            previous_close = df['close'][-1]
            
            result = df.loc[dkey2:gkey2, 'low'].min(axis=0) > df.loc[dkey1:gkey1, 'low'].min(axis=0) * 1.01 and \
                   df.macd_raw[gkey2] < df.macd_raw[gkey1] < 0 and \
                   df.loc[dkey2:gkey2, 'macd_raw'].min(axis=0) < df.loc[dkey1:gkey1, 'macd_raw'].min(axis=0) and \
                   df.macd[-2] < 0 < df.macd[-1] and \
                   df.loc[dkey2,'vol_ma'] > df.vol_ma[-1] and \
                   previous_close < df.loc[dkey2:gkey2, 'low'].min(axis=0)
#                    recent_area * 1.191 < previous_area and \
#                    previous_raise_area > recent_area * 1.096 and \
                #   previous_raise_area * 1.191 > previous_area
                #   recent_area * 3.618 >= previous_area
            return result
        except IndexError:
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

    def checkAtTopDoubleCross_chan_old(self, df, useZvalue=False):
        if not (df.shape[0] > 2 and df['macd'][-1] > 0 and df['macd'][-1] < df['macd'][-2] and df['macd'][-1] < df['macd'][-3]):
            return False
        
        # gold
        mask = df['macd'] > 0
        mask = mask[mask==True][mask.shift(1) == False]
        
        # death
        mask2 = df['macd'] < 0
        mask2 = mask2[mask2==True][mask2.shift(1)==False]
        
        try:
            gkey1 = mask.keys()[-1]
            gkey2 = mask.keys()[-2]
            dkey1 = mask2.keys()[-1]
            recent_high = previous_high = 0.0
            if useZvalue:
                high_mean = df.loc[gkey2:,'high'].mean(axis=0)
                high_std = df.loc[gkey2:,'high'].std(axis=0)
                df.loc[gkey2:, 'high_z'] = (df.loc[gkey2:,'high'] - high_mean) / high_std       
                
                recent_high = df.loc[gkey1:,'high_z'].min(axis=0)
                previous_high = df.loc[gkey2:dkey1, 'high_z'].min(axis=0)
            else:
                recent_high = df.loc[gkey1:,'high'].max(axis=0)
                previous_high = df.loc[gkey2:dkey1, 'high'].max(axis=0)
            
            recent_high_idx = df.loc[gkey1:,'high'].idxmax()
            loc = df.index.get_loc(recent_high_idx)
            recent_high_idx_nx = df.index[loc+1]
            recent_area_est = abs(df.loc[gkey1:recent_high_idx_nx, 'macd'].sum(axis=0) * 2)
            previous_area = abs(df.loc[gkey2:dkey1, 'macd'].sum(axis=0))
            return df.macd[-2] > df.macd[-1] > 0 and \
                    df.macd_raw[recent_high_idx] > df.macd_raw[-1] > 0 and \
                    recent_area_est < previous_area and \
                    recent_high >= previous_high
                    # abs(recent_high / previous_high) > g.lower_ratio_range
        except IndexError:
            return False
    
    def checkAtTopDoubleCross_chan(self, df):
        if not (df.shape[0] > 2 and df['macd'][-1] > 0 and df['macd'][-1] < df['macd'][-2] and df['macd'][-1] < df['macd'][-3]):
            return False
        
        # gold
        mask = df['macd'] > 0
        mask = mask[mask==True][mask.shift(1) == False]
        
        # death
        mask2 = df['macd'] < 0
        mask2 = mask2[mask2==True][mask2.shift(1)==False]
        
        try:
            gkey1 = mask.keys()[-1]
            gkey2 = mask.keys()[-2]
            dkey1 = mask2.keys()[-1]
            
            recent_high = df.loc[gkey1:,'high'].max(axis=0)
            previous_high = df.loc[gkey2:dkey1, 'high'].max(axis=0)
            
            recent_high_idx = df.loc[gkey1:,'high'].idxmax()
            previous_high_idx = df.loc[gkey2:dkey1,'high'].idxmax()
            loc = df.index.get_loc(recent_high_idx)
            recent_high_idx_nx = df.index[loc+1]
            recent_area_est = abs(df.loc[gkey1:recent_high_idx_nx, 'macd'].sum(axis=0) * 2)
            previous_area = abs(df.loc[gkey2:dkey1, 'macd'].sum(axis=0))
      
            return df.macd[-2] > df.macd[-1] > 0 and \
                    df.macd[-3] > df.macd[-1] and \
                    df.macd_raw[recent_high_idx] > df.macd_raw[-1] > 0 and \
                    (df.macd[recent_high_idx] < df.macd[previous_high_idx] or recent_area_est < previous_area) and \
                    (recent_high >= previous_high or recent_high >= df.upper[recent_high_idx])

        except IndexError:
            return False



    def checkFast(self, stock, fastperiod=12, slowperiod=26, signalperiod=9, checkBot=True):    
        rows = (fastperiod + slowperiod + signalperiod) * 5
        h = attribute_history(security=stock, count=rows, unit='1d', fields=['close'], df=False)
        _close = h['close']  # type: np.ndarray
        _dif, _dea, _macd = talib.MACD(_close, fastperiod, slowperiod, signalperiod)
        if checkBot:
            return self.checkBottomFast(_close, _macd, _dif)
        else:
            return self.checkTopFast(_close, _macd, _dif)
        
    def checkAtBottomDoubleCross_v3(self, df, fastperiod=12, slowperiod=26, signalperiod=9,):
        _close = df['close']  # type: np.ndarray
        _dif, _dea, _macd = talib.MACD(_close, fastperiod, slowperiod, signalperiod)
        return self.checkBottomFast(_close, _macd, _dif)     

    def checkAtTopDoubleCross_v3(self, df, fastperiod=12, slowperiod=26, signalperiod=9,):
        _close = df['close']  # type: np.ndarray
        _dif, _dea, _macd = talib.MACD(_close, fastperiod, slowperiod, signalperiod)
        return self.checkTopFast(_close, _macd, _dif) 
        
    def checkBottomFast(self, close, macd, dif):
        ret_val = False
        # ----------- 底背离 ------------------------
        # 1.昨天[-1]金叉
        # 1.昨天[-1]金叉close < 上一次[-2]金叉close
        # 2.昨天[-1]金叉Dif值 > 上一次[-2]金叉Dif值
        if macd[-1] > 0 > macd[-2]:  # 昨天金叉
            # idx_gold: 各次金叉出现的位置
            idx_gold = np.where((macd[:-1] < 0) & (macd[1:] > 0))[0] + 1  # type: np.ndarray
            if len(idx_gold) > 1:
                if close[idx_gold[-1]] < close[idx_gold[-2]] and dif[idx_gold[-1]] > dif[idx_gold[-2]]:
                    ret_val = True
        return ret_val


    def checkTopFast(self, close, macd, dif):
        ret_val = False
        # ----------- 顶背离 ------------------------
        # 1.昨天[-1]死叉
        # 1.昨天[-1]死叉close > 上一次[-2]死叉close
        # 2.昨天[-1]死叉Dif值 < 上一次[-2]死叉Dif值
        if macd[-1] < 0 < macd[-2]:  # 昨天死叉
            # idx_dead: 各次死叉出现的位置
            idx_dead = np.where((macd[:-1] > 0) & (macd[1:] < 0))[0] + 1  # type: np.ndarray
            if len(idx_dead) > 1:
                if close[idx_dead[-1]] > close[idx_dead[-2]] and dif[idx_dead[-1]] < dif[idx_dead[-2]]:
                    ret_val = True
        return ret_val  