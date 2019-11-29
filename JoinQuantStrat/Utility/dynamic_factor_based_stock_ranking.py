# -*- encoding: utf8 -*-
'''
Created on 2 Aug 2017

@author: MetalInvest
'''
try:
    from kuanke.user_space_api import *         
except ImportError as ie:
    print(str(ie))
from jqdata import *
import numpy as np
import pandas as pd
import math
from jqfactor import *
from jqdata import *
from jqlib.technical_analysis import *


class Dynamic_factor_based_stock_ranking(object):
    '''
    This class use JQ interface to periodically rank existing factors based on IC and IR,
    and select stocks out of the ranking results
    '''
    def __init__(self, params):
        self.stock_num = params.get('stock_num', 5)
        self.index_scope = params.get('index_scope', 'hs300')
        self.period = params.get('period', 'month_3')
        self.model = params.get('model', 'long_only')
        self.category = params.get('category', ['basics'])
        self.factor_gauge = params.get('factor_gauge', 'ir')
        self.factor_num = params.get('factor_num', 10)
        self.factor_date_count = params.get('factor_date_count', 1)
        self.factor_method = params.get('factor_method', 'factor_intersection') # ranking_score
        self.ic_mean_threthold = params.get('ic_mean_threthold', 0.02)
        self.is_debug = params.get('is_debug', False)
        
        if self.category is None:
            print("category not supplied, get it from data source")
            self.category = get_all_factors()['category'].unique().tolist()
        
        
    def get_idx_code(self, scope):
        if scope == 'hs300':
            return '000300.XSHG'
        elif scope == 'zz500':
            return '000905.XSHG'
        elif scope == 'zz800':
            return '000906.XSHG'
        else:
            return '000300.XSHG'
    
    def get_pos_neg_factors(self, factor_rank, num_fac):
        factor_rank = factor_rank.drop_duplicates(subset=['code'],keep='first') # This is in case of bugs in get_factor_kanban_values 
        
        factor_rank = factor_rank[abs(factor_rank['ic_mean']) >= self.ic_mean_threthold]
        
        factor_rank.sort_values(by=self.factor_gauge, inplace=True, ascending=True) # from small to big with both + and -
        
        factor_code_list_positive = factor_rank['code'].tail(num_fac).tolist()

        factor_code_list_negative = factor_rank['code'].head(num_fac).tolist()
        
#         if self.is_debug:
#             print("positive factor candidates: {0}".format(factor_code_list_positive))
#             print("negative factor candidates: {0}".format(factor_code_list_negative))
        
        full_factor_list = factor_rank.reindex(factor_rank[self.factor_gauge].abs().sort_values(ascending=False).index)['code'].head(num_fac).tolist() # sort by abs ascending
        
#         if self.is_debug:
#             print(factor_rank.tail(5))
#             print(factor_rank.reindex(factor_rank[self.factor_gauge].abs().sort_values(ascending=False).index).head(5))
            
        pos_list, neg_list = [factor for factor in factor_code_list_positive if factor in full_factor_list], [factor for factor in factor_code_list_negative if factor in full_factor_list]
        
        if self.is_debug:
            print("positive factor list: {0}".format(pos_list))
            print("negative factor list: {0}".format(neg_list))
            print("full factor list: {0}".format(full_factor_list))
        
        return pos_list, neg_list, full_factor_list

    def get_ranked_factors_by_category(self):
        factor_rank = get_factor_kanban_values(universe=self.index_scope, bt_cycle=self.period, model = self.model, category=self.category)  
        
        num_fac = int(np.ceil(self.factor_num / len(cat_list)))
        full_list = []
        for cat in self.category:
            sub_factor_rank = factor_rank[factor_rank['category']==cat]
            _, _, sub_list = self.get_pos_neg_factors(sub_factor_rank, num_fac)
#             print("category {0}: {1}".format(cat, sub_list))
            full_list = full_list + sub_list
        return full_list
    
    def get_ranked_factors(self, factor_result_file_path=None):
        if factor_result_file_path is None:
            factor_rank = get_factor_kanban_values(universe=self.index_scope, bt_cycle=self.period, model = self.model, category=self.category)  
        else:
            factor_rank = self.get_factor_values_from_file(factor_result_file_path)
        
        return self.get_pos_neg_factors(factor_rank, self.factor_num)

    def get_factor_values_from_file(self, result_file_path):
        return read_file(result_file_path)
    
    def gaugeStocks(self, context, factor_result_file_path=None):
        factor_code_list_positive, factor_code_list_negative, factor_code_list = self.get_ranked_factors(factor_result_file_path)
        
#         factor_code_list = factor_code_list_positive + factor_code_list_negative
        index_code = self.get_idx_code(self.index_scope)
        stock_list = get_index_stocks(index_code)
        
        stock_factor_data = get_factor_values(securities=stock_list, factors=factor_code_list, count=self.factor_date_count, end_date=context.previous_date)
        
        if self.factor_method == 'factor_intersection':
            ranked_stock_list = {}
            for code in factor_code_list_positive:
                factor_stock_ranking = stock_factor_data[code].T
                factor_stock_ranking.sort_values(by=factor_stock_ranking.columns[0], inplace=True, ascending=False)
                ranked_stock_list[code] = factor_stock_ranking.index[:self.stock_num].tolist()
                
            for code in factor_code_list_negative:
                factor_stock_ranking = stock_factor_data[code].T
                factor_stock_ranking.sort_values(by=factor_stock_ranking.columns[0], inplace=True, ascending=True)
                ranked_stock_list[code] = factor_stock_ranking.index[:self.stock_num].tolist()                

            if self.is_debug:
                print(ranked_stock_list)
            
            selected_stocks = []
            for code in ranked_stock_list:
                selected_stocks = [stock for stock in ranked_stock_list[code] if stock in selected_stocks] if selected_stocks else ranked_stock_list[code]
            
            return selected_stocks[:self.stock_num] if len(selected_stocks) > self.stock_num else selected_stocks
            
        elif self.factor_method == 'ranking_score':
            ranked_stock_score = None
            for code in factor_code_list:
                factor_stock_tmp = stock_factor_data[code].T
                factor_stock_tmp.rename({factor_stock_tmp.columns[0]:code},axis=1, inplace=True)
                ranked_stock_score = factor_stock_tmp if ranked_stock_score is None else ranked_stock_score.join(factor_stock_tmp)
            
            # remove extreme value and standardize by column
            ranked_stock_score = winsorize(ranked_stock_score, scale = 5, axis = 0)
            ranked_stock_score = standardlize(ranked_stock_score, axis = 0)
            
            # sum all factors by rows
            ranked_stock_score["sum_rank_score"] = ranked_stock_score.sum(axis=1)
            
            if self.is_debug:
                print(ranked_stock_score)
                print(ranked_stock_score["sum_rank_score"].abs().sort_values(inplace=False, ascending=False))

            return ranked_stock_score["sum_rank_score"].abs().sort_values(inplace=False, ascending=False).index.tolist()[:self.stock_num]
        else:
            print("We shouldn't be HERE")
        
            
            
        