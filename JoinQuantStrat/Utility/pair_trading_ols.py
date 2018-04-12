# -*- encoding: utf8 -*-
'''
Created on 7 Apr 2018

@author: MetalInvest
'''
import numpy as np
import pandas as pd
import statsmodels.api as sm

class PairTradingOls(object):
    '''
    classdocs
    '''

    def __init__(self, params):
        '''
        Pair Trading module
        '''
        self.return_pair = params.get('return_pair', 1)
        pass
    
    
    def get_regression_ratio(self, data_frame, pairs):
        zscores = []
        for pair in pairs:
            stock_df1 = data_frame[pair[0]]
            stock_df2 = data_frame[pair[1]]
            X = sm.add_constant(stock_df1)
            model = (sm.OLS(stock_df2, X)).fit()
            p_value = model.params[1]
            print("regression p_value: {0}".format(p_value))
            zscores.append(self.zscore(stock_df2 - p_value * stock_df1)[-1])
        return zscores
        
    def zscore(self, value_diff):
        diff_mean = np.mean(value_diff)
        sigma = np.std(value_diff)
        return (value_diff - diff_mean) / sigma
    
    def get_top_pair(self, dataframe):
        _, pairs = self.find_cointegrated_pairs(dataframe)
        if len(pairs) < 2:
            return []
        sorted_pair = sorted(pairs, key=lambda x: x[2])
        new_pair = []
        i = 0
        while i < self.return_pair:
            current_pair = sorted_pair[i]
            print("cointegrated_pair: {0}".format(current_pair))
            new_pair.append((current_pair[0], current_pair[1]))
            i+=1
        return new_pair
    
    # 输入是一DataFrame，每一列是一支股票在每一日的价格
    def find_cointegrated_pairs(self, dataframe):
        # 得到DataFrame长度
        n = dataframe.shape[1]
        # 初始化p值矩阵
        pvalue_matrix = np.ones((n, n))
        # 抽取列的名称
        keys = dataframe.keys()
        # 初始化强协整组
        pairs = []
        # 对于每一个i
        for i in range(n):
            # 对于大于i的j
            for j in range(i+1, n):
                # 获取相应的两只股票的价格Series
                stock1 = dataframe[keys[i]]
                stock2 = dataframe[keys[j]]
                # 分析它们的协整关系
                result = sm.tsa.stattools.coint(stock1, stock2)
                # 取出并记录p值
                pvalue = result[1]
                pvalue_matrix[i, j] = pvalue
                # 如果p值小于0.05
                if pvalue < 0.05:
                    # 记录股票对和相应的p值
                    pairs.append((keys[i], keys[j], pvalue))
        # 返回结果
        return pvalue_matrix, pairs