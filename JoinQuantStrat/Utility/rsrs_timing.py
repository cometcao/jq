# -*- encoding: utf8 -*-
'''
Created on 11 Apr 2018

@author: MetalInvest
'''
try:
    from kuanke.user_space_api import *
except:
    pass
from jqdata import *
import statsmodels.api as sm
import numpy as np


class RSRS_Market_Timing(object):
    '''
    RSRS method of gauging market timing
    '''
    def __init__(self, params):
        # 设置买入和卖出阈值
        self.buy = params.get('buy', 0.7)
        self.sell = params.get('sell', -0.7)
        
        # 设置RSRS指标中N, M的值
        self.N = params.get('N', 18)
        self.M = params.get('M', 600)
        
        self.BETA = {}
        self.R2 = {}
        
        self.market_list = params.get('market_list', ['000016.XSHG','399300.XSHE', '399333.XSHE', '000905.XSHG', '399673.XSHE'])
        
    def calculate_RSRS(self):
        
        for market in self.market_list:
            prices = attribute_history(market, self.M+self.N, '1d', ['high', 'low'])
            highs = prices.high
            lows = prices.low
            
            beta_list = []
            r2_list = []
            for i in range(len(highs))[self.N:]:
                data_high = highs.iloc[i-self.N+1:i+1]
                data_low = lows.iloc[i-self.N+1:i+1]
                X = sm.add_constant(data_low)
                model = sm.OLS(data_high,X).fit()
                beta = model.params[1]
                r2 = model.rsquared
                beta_list.append(beta)
                r2_list.append(r2)
            self.BETA[market] = beta_list
            self.R2[market] = r2_list
    
    def add_new_RSRS(self):
        for market in self.market_list:        
            prices = attribute_history(market, self.N, '1d', ['high', 'low'])
            highs = prices.high
            lows = prices.low
            X = sm.add_constant(lows)
            model = sm.OLS(highs, X).fit()
            beta = model.params[1]
            r2 = model.rsquared
            self.BETA[market].append(beta)
            self.R2[market].append(r2)
            self.BETA[market].pop(0)
            self.R2[market].pop(0)
        
        
    def check_timing(self, market_symbol):
        beta_list = self.BETA[market_symbol]
        r2_list = self.R2[market_symbol]
        
        section = beta_list[-self.M:]
        mu = np.mean(section)
        sigma = np.std(section)
        zscore = (section-mu)/sigma

        #计算右偏RSRS标准分
        zscore_rightdev= zscore*beta_list[-1]*r2_list[-1]
        
        # 获得前10日交易量
        trade_vol10 = attribute_history(market_symbol, 10, '1d', 'volume')
        
        if zscore_rightdev[-1] > self.buy \
            and np.corrcoef(np.array([trade_vol10['volume'].values, (np.array(r2_list[-10:]) * np.array(zscore[-10:]))]))[0,1] > 0:
#             log.info("RSRS右偏标准分大于买入阈值, 且修正标准分与前10日交易量相关系数为正")
            return 1
        # 如果上一时间点的右偏RSRS标准分小于卖出阈值, （且修正标准分与前10日交易量相关系数为正）则空仓卖出
        elif zscore_rightdev[-1] < self.sell:
#             log.info("RSRS右偏标准分小于卖出阈值, 且修正标准分与前10日交易量相关系数为正")
            return -1
        return 0