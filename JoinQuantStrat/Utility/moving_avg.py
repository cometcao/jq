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
            # ����ؼ��ִ��ڣ�˵��֮ǰ�Ѿ������EMA�ˣ�ֱ�ӵ�������
            if days in self.keys:
                #����alphaֵ
                alpha=(days-1.0)/(days+1.0)
                # ���ǰһ���EMA������Ǳ����������ˣ�
                EMA_pre=g.EMAs[days]
                # EMA��������
                EMA_now=EMA_pre*alpha+series[-1]*(1.0-alpha)
                # д���µ�EMAֵ
                self.keys[days]=EMA_now
                # ���û���������ͽ��������EMAֵ
                return (EMA_pre,EMA_now)
            # ����ؼ��ֲ����ڣ�˵��֮ǰû�м�������EMA�����Ҫ��ʼ��
            else:
                # ���days����ƶ�ƽ��
                ma=self.simple_moving_avg(series,days) 
                # �������ƽ�����ڣ�������NaN���Ļ�����ô�����Ѿ����㹻���ݿ��Զ����EMA��ʼ����
                if not(np.isnan(ma)):
                    self.keys[days]=ma
                    # ��Ϊ�ոճ�ʼ��������ǰһ�ڵ�EMA��������
                    return (float("nan"),ma)
                else:
                    # �ƶ�ƽ�����ݲ���days�죬ֻ�÷���NaNֵ
                    return (float("nan"),float("nan"))        

    def exp_moving_avg_talib(self, series,days,data):
        talib.EMA(series, timeperiod=days)
        
        