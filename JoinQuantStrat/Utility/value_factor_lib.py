# -*- encoding: utf8 -*-
try:
    from kuanke.user_space_api import *         
except ImportError as ie:
    print(str(ie))
from jqdata import *
import numpy as np
import pandas as pd
from quant_lib import *
import datetime as dt


class value_factor_lib():
    def __init__(self):
        self.quantlib = quantlib()

    def fun_get_stock_list(self, context, hold_number, statsDate=None, bad_stock_list=[]):
        relative_ps = self.fun_get_relative_ps(context, statsDate)
        low_ps = self.fun_get_low_ps(context, statsDate)
        
        good_stock_list = list(set(relative_ps) & set(low_ps))
        
        
        # 取净利润增长率为正的
        df = self.quantlib.get_fundamentals_sum('income', income.net_profit, statsDate)
        df = df.drop(['0Q', '1Q', '2Q', '3Q'], axis=1)
        df.rename(columns={'sum_value':'ttm_1y'}, inplace=True)
        df1 = self.quantlib.get_fundamentals_sum('income', income.net_profit, (statsDate - dt.timedelta(365)))
        df1 = df1.drop(['0Q', '1Q', '2Q', '3Q'], axis=1)
        df1.rename(columns={'sum_value':'ttm_2y'}, inplace=True)
 
        
        df = df.merge(df1, on='code')
        df = df.fillna(value=0)
        df['inc_net_profit'] = 1.0*(df['ttm_1y'] - df['ttm_2y'])
        df = df[(df.inc_net_profit > 0)]
        inc_net_profit_list = list(df.code)
        good_stock_list = list(set(good_stock_list) & set(inc_net_profit_list))
        #good_stock_list = list(set(inc_net_profit_list) & set(low_ps))
        
        # 按行业取营业收入增长率前 1/3
        df = self.quantlib.get_fundamentals_sum('income', income.operating_revenue, statsDate)
        df = df.drop(['0Q', '1Q', '2Q', '3Q'], axis=1)
        df.rename(columns={'sum_value':'ttm_1y'}, inplace=True)
        df1 = self.quantlib.get_fundamentals_sum('income', income.operating_revenue, (statsDate - dt.timedelta(365)))
        df1 = df1.drop(['0Q', '1Q', '2Q', '3Q'], axis=1)
        df1.rename(columns={'sum_value':'ttm_2y'}, inplace=True)

        df = df.merge(df1, on='code')
        df = df.fillna(value=0)
        df['inc_operating_revenue'] = 1.0*(df['ttm_1y'] - df['ttm_2y']) / abs(df['ttm_2y'])

        df = df.fillna(value = 0)
        industry_list = self.quantlib.fun_get_industry(cycle=None)
        #industry_list = self.quantlib.fun_get_industry_levelI()

        inc_operating_revenue_list = []
        for industry in industry_list:
            stock_list = self.quantlib.fun_get_industry_stocks(industry, 2, statsDate)
            df_inc_operating_revenue = df[df.code.isin(stock_list)]
            df_inc_operating_revenue = df_inc_operating_revenue.sort(columns='inc_operating_revenue', ascending=False)
            inc_operating_revenue_list = inc_operating_revenue_list + list(df_inc_operating_revenue[:int(len(df_inc_operating_revenue)*0.33)].code)
        
        good_stock_list = list(set(good_stock_list) & set(inc_operating_revenue_list))
        
        
        # 指标剔除资产负债率相对行业最高的1/3的股票
        df = get_fundamentals(query(balance.code, balance.total_liability, balance.total_assets), date = statsDate)
        df = df.fillna(value=0)
        df['liability_ratio'] = 1.0*(df['total_liability'] / df['total_assets'])

        #industry_list = self.quantlib.fun_get_industry(cycle=None)
        #industry_list = self.quantlib.fun_get_industry_levelI()

        liability_ratio_list = []
        for industry in industry_list:
            stock_list = self.quantlib.fun_get_industry_stocks(industry, 2, statsDate)
            df_liability_ratio = df[df.code.isin(stock_list)]
            df_liability_ratio = df_liability_ratio.sort(columns='liability_ratio', ascending=True)
            liability_ratio_list = liability_ratio_list + list(df_liability_ratio[:int(len(df_liability_ratio)*0.66)].code)

        good_stock_list = list(set(good_stock_list) & set(liability_ratio_list))

        # 剔除净利润率相对行业最低的1/3的股票；
        df = get_fundamentals(query(indicator.code, indicator.net_profit_to_total_revenue    ), date = statsDate)
        df = df.fillna(value=0)

        industry_list = self.quantlib.fun_get_industry(cycle=True)
        #industry_list = self.quantlib.fun_get_industry_levelI()

        profit_ratio_list = []
        for industry in industry_list:
            stock_list = self.quantlib.fun_get_industry_stocks(industry, 2, statsDate)
            df_profit_ratio = df[df.code.isin(stock_list)]
            df_profit_ratio = df_profit_ratio.sort(columns='net_profit_to_total_revenue', ascending=False)
            profit_ratio_list = profit_ratio_list + list(df_profit_ratio[:int(len(df_profit_ratio)*0.66)].code)

        good_stock_list = list(set(good_stock_list) & set(profit_ratio_list))
        
        
        stock_list = []
        for stock in relative_ps:
        #for stock in low_ps:
            if stock in good_stock_list:
                stock_list.append(stock)

        positions_list = context.portfolio.positions.keys()
        stock_list = self.quantlib.unpaused(stock_list, positions_list)
        stock_list = self.quantlib.remove_st(stock_list, statsDate)
        stock_list = self.quantlib.fun_delNewShare(context, stock_list, 30)

        #stock_list = stock_list[:hold_number*10]
        stock_list = self.quantlib.remove_bad_stocks(stock_list, bad_stock_list)
        stock_list = self.quantlib.remove_limit_up(stock_list, positions_list)
        stock_list = self.quantlib.fun_diversity_by_industry(stock_list, int(hold_number*0.4), statsDate)
            
        return stock_list[:hold_number]


    def fun_get_relative_ps(self, context, statsDate=None):
        def __fun_get_ps(statsDate, deltamonth):
            __df = get_fundamentals(query(valuation.code, valuation.ps_ratio), date = (statsDate - dt.timedelta(30*deltamonth)))
            __df.rename(columns={'ps_ratio':deltamonth}, inplace=True)
            return __df

        for i in range(48):
            df1 = __fun_get_ps(statsDate, i)
            if i == 0:
                df = df1
            else:
                df = df.merge(df1, on='code')

        df.index = list(df['code'])
        df = df.drop(['code'], axis=1)

        df = df.fillna(value=0, axis=0)
        # 1. 计算相对市收率，相对市收率等于个股市收率除以全市场的市收率，这样处理的目的是为了剔除市场估值变化的影响
        for i in range(len(df.columns)):
            s = df.iloc[:,i]
            median = s.median()
            df.iloc[:,i] = s / median

        length, stock_list, stock_dict = len(df), list(df.index), {}
        # 2. 计算相对市收率N个月的移动平均值的N个月的标准差，并据此计算布林带上下轨（N个月的移动平均值+/-N个月移动平均的标准差）。N = 24
        for i in range(length):
            s = df.iloc[i,:]
            if s.min() < 0:
                pass
            else:
                # tmp_list 是24个月的相对市收率均值
                tmp_list = []
                for j in range(24):
                    tmp_list.append(s[j:j+24].mean())
                # mean_value 是最近 24个月的相对市收率均值
                mean_value = tmp_list[0]
                # std_value 是相对市收率24个月的移动平均值的24个月的标准差
                std_value = np.std(tmp_list)
                tmp_dict = {}
                # (mean_value - std_value)，是布林线下轨（此处定义和一般布林线不一样，一般是 均线 - 2 倍标准差）
                '''
                研报原始的策略，选择 s[0] < mean_value - std_value 的标的，但因为 ps_ratio十分不稳定，跳跃很大，此区间里的测试结果非常不稳定
                本策略退而求其次，选择均线-1倍标准差 和 均线 - 2 倍标准差之间的标的
                大致反映策略的有效性
                '''
                if s[0] > (mean_value - 2.0*std_value) and s[0] < mean_value:
                    # 记录 相对市收率均值 / 当期相对市收率
                    stock_dict[stock_list[i]] = (1.0*mean_value/s[0])

        stock_list = []
        dict_score = stock_dict
        dict_score = sorted(dict_score.items(), key=lambda d:d[1], reverse=True)
        for idx in dict_score:
            stock = idx[0]
            stock_list.append(stock)

        return stock_list


    def fun_get_low_ps(self, context, statsDate=None):
        df = get_fundamentals(
            query(valuation.code, valuation.ps_ratio),
            date = statsDate
        )

        # 根据 sp 去极值、中性化、标准化后，跨行业选最佳的标的
        industry_list = self.quantlib.fun_get_industry(cycle=None)

        df = df.fillna(value = 0)
        sp_ratio = {}
        df['SP'] = 1.0/df['ps_ratio']

        df = df.drop(['ps_ratio'], axis=1)

        for industry in industry_list:
            tmpDict = self.quantlib.fun_get_factor(df, 'SP', industry, 2, statsDate).to_dict()
            for stock in tmpDict.keys():
                if stock in sp_ratio:
                    if sp_ratio[stock] < tmpDict[stock]:
                        sp_ratio[stock] = tmpDict[stock]
                else:
                    sp_ratio[stock] = tmpDict[stock]

        dict_score = sorted(sp_ratio.items(), key=lambda d:d[1], reverse=True)
        stock_list = []

        for idx in dict_score:
            stock = idx[0]
            stock_list.append(stock)

        return stock_list[:int(len(stock_list)*0.5)]