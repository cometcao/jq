'''
Created on 28 Sep 2016

@author: MetalInvest
'''

import numpy as np
import pandas as pd
import talib

class moving_avg(object):
    '''
    unified methods of calculating moving average for the latest price of the series of date
    '''


    def __init__(self, params):
        '''
        Constructor
        '''
        self.keys = {}
    
    def simple_moving_avg(self, series, period):
        total = sum(series[-period:])
        return total/period
    
    def exp_moving_avg(self, series,days):
        if days==1:
            return series[-2],series[-1]
        else:
            # 如果关键字存在，说明之前已经计算过EMA了，直接迭代即可
            if days in self.keys:
                #计算alpha值
                alpha=(days-1.0)/(days+1.0)
                # 获得前一天的EMA（这个是保存下来的了）
                EMA_pre=g.EMAs[days]
                # EMA迭代计算
                EMA_now=EMA_pre*alpha+series[-1]*(1.0-alpha)
                # 写入新的EMA值
                self.keys[days]=EMA_now
                # 给用户返回昨天和今天的两个EMA值
                return (EMA_pre,EMA_now)
            # 如果关键字不存在，说明之前没有计算过这个EMA，因此要初始化
            else:
                # 获得days天的移动平均
                ma=self.simple_moving_avg(series,days) 
                # 如果滑动平均存在（不返回NaN）的话，那么我们已经有足够数据可以对这个EMA初始化了
                if not(np.isnan(ma)):
                    self.keys[days]=ma
                    # 因为刚刚初始化，所以前一期的EMA还不存在
                    return (float("nan"),ma)
                else:
                    # 移动平均数据不足days天，只好返回NaN值
                    return (float("nan"),float("nan"))        

    def exp_moving_avg_talib(self, series,days,data):
        talib.EMA(series, timeperiod=days)
        
        