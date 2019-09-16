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
from sklearn.svm import SVR  
from sklearn.model_selection import GridSearchCV  
from sklearn.model_selection import learning_curve
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from jqfactor import standardlize
from jqfactor import winsorize_med
from jqdata import *
from sklearn.model_selection import KFold

class ML_Factor_Rank(object):
    '''
    This class use regression to periodically gauge stocks fartherest away from the 
    regressed frontier, and return the list of stocks
    '''
    def __init__(self, params):
        self.stock_num = params.get('stock_num', 5)
        self.index_scope = params.get('index_scope', '000985.XSHG')

        # 网格搜索是否开启
        self.__gridserach = False
        
        self.method='svr'
    
        ## 机器学习验证集及测试集评分记录之用（实际交易策略中不需要，请设定为False）#####
        # True：开启（写了到研究模块，文件名：score.json）
        # False：关闭
        self.__scoreWrite = False
        self.__valscoreSum = 0
        self.__testscoreSum = 0
        ## 机器学习验证集及测试集评分记录之用（实际交易策略中不需要，请设定为False）#####
    
        # 训练集长度
        self.__trainlength = 3
        # 训练集合成间隔周期（交易日）
        self.__intervals = 21
    
        # 离散值处理列表
        self.__winsorizeList = ['log_NC', 'LEV', 'NI_p', 'NI_n', 'g', 'RD',
                                'EP','BP','G_p','PEG','DP',
                                   'ROE','ROA','OPTP','GPM','FACR']
    
        # 标准化处理列表
        self.__standardizeList = ['log_mcap',
                            'log_NC', 
                            'LEV', 
                            'NI_p', 'NI_n', 
                            'g', 
                            'RD',
                            'EP',
                            'BP',
                            'G_p',
                            'PEG',
                            'DP',
                            'CMV',
                            'ROE',
                            'ROA',
                            'OPTP',
                            'GPM',
                            'FACR',
                            'CFP',
                            'PS']
                            
        # 聚宽一级行业
        self.__industry_set = ['HY001', 'HY002', 'HY003', 'HY004', 'HY005', 'HY006', 'HY007', 'HY008', 'HY009', 
              'HY010', 'HY011']
    
        '''
        # 因子列表（因子组合1）
        self.__factorList = [#估值
                        'EP',
                        #'BP',
                        #'PS',
                        #'DP',
                        'RD',
                        #'CFP',
                        #资本结构
                        'log_NC', 
                        'LEV', 
                        #'CMV',
                        #'FACR',
                        #盈利
                        'NI_p', 
                        'NI_n', 
                        #'GPM',
                        #'ROE',
                        #'ROA',
                        #'OPTP',
                        #成长
                        'PEG',
                        #'g', 
                        #'G_p',
                        #行业哑变量
                        'HY001', 'HY002', 'HY003', 'HY004', 'HY005', 'HY006', 'HY007', 'HY008', 'HY009', 'HY010', 'HY011']
        '''
        '''
        # 因子列表(因子组合2)
        self.__factorList = [#估值
                        'EP',
                        'BP',
                        #'PS',
                        #'DP',
                        'RD',
                        #'CFP',
                        #资本结构
                        'log_NC', 
                        'LEV', 
                        'CMV',
                        #'FACR',
                        #盈利
                        'NI_p', 
                        'NI_n', 
                        'GPM',
                        'ROE',
                        #'ROA',
                        #'OPTP',
                        #成长
                        'PEG',
                        #'g', 
                        #'G_p',
                        #行业哑变量
                        'HY001', 'HY002', 'HY003', 'HY004', 'HY005', 'HY006', 'HY007', 'HY008', 'HY009', 'HY010', 'HY011']
        '''
        # 因子列表(因子组合3)
        self.__factorList = [#估值
                        'EP',
                        'BP',
                        'PS',
                        'DP',
                        'RD',
                        'CFP',
                        #资本结构
                        'log_NC', 
                        'LEV', 
                        'CMV',
                        'FACR',
                        #盈利
                        'NI_p', 
                        'NI_n', 
                        'GPM',
                        'ROE',
                        'ROA',
                        'OPTP',
                        #成长
                        'PEG',
                        'g', 
                        'G_p',
                        #行业哑变量
                        'HY001', 'HY002', 'HY003', 'HY004', 'HY005', 'HY006', 'HY007', 'HY008', 'HY009', 'HY010', 'HY011']
    
    def gaugeStocks(self):
        sample = get_index_stocks(self.index_scope, date = None)
        if not sample:
            print("empty stock list")
            return []
        q = query(valuation.code, valuation.market_cap, 
                  balance.total_assets - balance.total_liability,
                  balance.total_assets / balance.total_liability, 
                  income.net_profit, income.net_profit + 1, 
                  indicator.inc_revenue_year_on_year, 
                  balance.development_expenditure).filter(valuation.code.in_(sample))
        df = get_fundamentals(q, date = None)
        df.columns = ['code', 'log_mcap', 'log_NC', 'LEV', 'NI_p', 'NI_n', 'g', 'log_RD']
        
        df['log_mcap'] = np.log(df['log_mcap'])
        df['log_NC'] = np.log(df['log_NC'])
        df['NI_p'] = np.log(np.abs(df['NI_p']))
        df['NI_n'] = np.log(np.abs(df['NI_n'][df['NI_n']<0]))
        df['log_RD'] = np.log(df['log_RD'])
        df.index = df.code.values
        del df['code']
        df = df.fillna(0)
        df[df>10000] = 10000
        df[df<-10000] = -10000
        industry_set = ['801010', '801020', '801030', '801040', '801050', '801080', '801110', '801120', '801130', 
                  '801140', '801150', '801160', '801170', '801180', '801200', '801210', '801230', '801710',
                  '801720', '801730', '801740', '801750', '801760', '801770', '801780', '801790', '801880','801890']
        
        for i in range(len(industry_set)):
            industry = get_industry_stocks(industry_set[i], date = None)
            s = pd.Series([0]*len(df), index=df.index)
            s[set(industry) & set(df.index)]=1
            df[industry_set[i]] = s
            
        X = df[['log_NC', 'LEV', 'NI_p', 'NI_n', 'g', 'log_RD','801010', '801020', '801030', '801040', '801050', 
                '801080', '801110', '801120', '801130', '801140', '801150', '801160', '801170', '801180', '801200', 
                '801210', '801230', '801710', '801720', '801730', '801740', '801750', '801760', '801770', '801780', 
                '801790', '801880', '801890']]
        Y = df[['log_mcap']]
        X = X.fillna(0)
        Y = Y.fillna(0)
        svr = SVR(kernel='rbf', gamma=0.1) 
        model = svr.fit(X, Y)
        factor = Y - pd.DataFrame(svr.predict(X), index = Y.index, columns = ['log_mcap'])
#         factor = factor.sort_index(by = 'log_mcap')
        factor = factor.sort_values(by = 'log_mcap')
        stockset = list(factor.index[:self.stock_num])
        
        return stockset
    
    
    def gaugeStocks_new(self, context):
        # 设置初始股票池
        sample = get_index_stocks(self.index_scope, date = None)
        # 设置可交易股票池
        self.__feasible_stocks = self.set_feasible_stocks(sample,context)
        # 因子获取Query
        factor_query = self.get_q_Factor(self.__feasible_stocks)        
        
        # 训练集合成
        yesterday = context.previous_date

        df_train = self.get_df_train(factor_query,yesterday,self.__trainlength,self.__intervals)
        df_train = self.initialize_df(df_train)

        # T日截面数据（测试集）
        df = get_fundamentals(factor_query, date = None)
        df = self.initialize_df(df)
        
        # 离散值处理
        for fac in self.__winsorizeList:
            df_train[fac] = winsorize_med(df_train[fac], scale=5, inclusive=True, inf2nan=True, axis=0)    
            df[fac] = winsorize_med(df[fac], scale=5, inclusive=True, inf2nan=True, axis=0)    
        
        # 标准化处理        
        for fac in self.__standardizeList:
            df_train[fac] = standardlize(df_train[fac], inf2nan=True, axis=0)
            df[fac] = standardlize(df[fac], inf2nan=True, axis=0)

        # 中性化处理（行业中性化）
        df_train = self.neutralize(df_train,self.__industry_set)
        df = self.neutralize(df,self.__industry_set)

        #训练集（包括验证集）
        X_trainval = df_train[self.__factorList]
        X_trainval = X_trainval.fillna(0)
        
        #定义机器学习训练集输出
        y_trainval = df_train[['log_mcap']]
        y_trainval = y_trainval.fillna(0)
 
        #测试集
        X = df[self.__factorList]
        X = X.fillna(0)
        
        #定义机器学习测试集输出
        y = df[['log_mcap']]
        y.index = df['code']
        y = y.fillna(0)
 
        kfold = KFold(n_splits=4)        
        
        if self.__gridserach == False:
            #不带网格搜索的机器学习
            if self.method == 'svr': #SVR
                from sklearn.svm import SVR
                model = SVR(C=100, gamma=1)
            elif self.method == 'lr':
                from sklearn.linear_model import LinearRegression
                model = LinearRegression()
            elif self.method == 'ridge': #岭回归
                from sklearn.linear_model import Ridge
                model = Ridge(random_state=42,alpha=100)
            elif self.method == 'rf': #随机森林
                from sklearn.ensemble import RandomForestRegressor
                model = RandomForestRegressor(random_state=42,n_estimators=500,n_jobs=-1)
            else:
                self.__scoreWrite = False
        else:
            # 带网格搜索的机器学习
            para_grid = {}
            if self.method == 'svr':
                from sklearn.svm import SVR  
                para_grid = {'C':[10,100],'gamma':[0.1,1,10]}
                grid_search_model = SVR()
            elif self.method == 'lr':
                from sklearn.linear_model import LinearRegression
                grid_search_model = LinearRegression()
            elif self.method == 'ridge':
                from sklearn.linear_model import Ridge
                para_grid = {'alpha':[1,10,100]}
                grid_search_model = Ridge()
            elif self.method == 'rf':
                from sklearn.ensemble import RandomForestRegressor
                para_grid = {'n_estimators':[100,500,1000]}
                grid_search_model = RandomForestRegressor()
            else:
                self.__scoreWrite = False
    
            from sklearn.model_selection import GridSearchCV
            model = GridSearchCV(grid_search_model,para_grid,cv=kfold,n_jobs=-1)
        
        # 拟合训练集，生成模型
        model.fit(X_trainval,y_trainval)
        # 预测值
        y_pred = model.predict(X)

        # 新的因子：实际值与预测值之差    
        factor = y - pd.DataFrame(y_pred, index = y.index, columns = ['log_mcap'])
        
        #对新的因子，即残差进行排序（按照从小到大）
        factor = factor.sort_values(by = 'log_mcap')        
        
        stockset = list(factor.index[:self.stock_num])
        return stockset

    # 获取初始特征值
    def get_q_Factor(self, feasible_stocks):
        q = query(valuation.code, 
              valuation.market_cap,#市值
              valuation.circulating_market_cap,
              balance.total_assets - balance.total_liability,#净资产
              balance.total_assets / balance.total_liability, 
              indicator.net_profit_to_total_revenue, #净利润/营业总收入
              indicator.inc_revenue_year_on_year,  #营业收入增长率（同比）
              balance.development_expenditure, #RD
              valuation.pe_ratio, #市盈率（TTM）
              valuation.pb_ratio, #市净率（TTM）
              indicator.inc_net_profit_year_on_year,#净利润增长率（同比）
              balance.dividend_payable,
              indicator.roe,
              indicator.roa,
              income.operating_profit / income.total_profit, #OPTP
              indicator.gross_profit_margin, #销售毛利率GPM
              balance.fixed_assets / balance.total_assets, #FACR
              valuation.pcf_ratio, #CFP
              valuation.ps_ratio #PS
            ).filter(
                valuation.code.in_(feasible_stocks)
            )
        return q
    
    # 训练集长度设置
    def get_df_train(self,q,d,trainlength,interval):
        
        #'''
        date1 = self.shift_trading_day(d,interval)
        date2 = self.shift_trading_day(d,interval*2)
        date3 = self.shift_trading_day(d,interval*3)
    
        d1 = get_fundamentals(q, date = date1)
        d2 = get_fundamentals(q, date = date2)
        d3 = get_fundamentals(q, date = date3)
    
        if trainlength == 1:
            df_train = d1
        elif trainlength == 3:
            # 3个周期作为训练集    
            df_train = pd.concat([d1, d2, d3],ignore_index=True)
        elif trainlength == 4:
            date4 = self.shift_trading_day(d,interval*4)
            d4 = get_fundamentals(q, date = date4)
            # 4个周期作为训练集    
            df_train = pd.concat([d1, d2, d3, d4],ignore_index=True)
        elif trainlength == 6:
            date4 = self.shift_trading_day(d,interval*4)
            date5 = self.shift_trading_day(d,interval*5)
            date6 = self.shift_trading_day(d,interval*6)
    
            d4 = get_fundamentals(q, date = date4)
            d5 = get_fundamentals(q, date = date5)
            d6 = get_fundamentals(q, date = date6)
    
            # 6个周期作为训练集
            df_train = pd.concat([d1,d2,d3,d4,d5,d6],ignore_index=True)
        elif trainlength == 9:
            date4 = self.shift_trading_day(d,interval*4)
            date5 = self.shift_trading_day(d,interval*5)
            date6 = self.shift_trading_day(d,interval*6)
            date7 = self.shift_trading_day(d,interval*7)
            date8 = self.shift_trading_day(d,interval*8)
            date9 = self.shift_trading_day(d,interval*9)
    
            d4 = get_fundamentals(q, date = date4)
            d5 = get_fundamentals(q, date = date5)
            d6 = get_fundamentals(q, date = date6)
            d7 = get_fundamentals(q, date = date7)
            d8 = get_fundamentals(q, date = date8)
            d9 = get_fundamentals(q, date = date9)
        
            # 9个周期作为训练集
            df_train = pd.concat([d1,d2,d3,d4,d5,d6,d7,d8,d9],ignore_index=True)
        else:
            pass
        
        return df_train
    
    # 特征值提取
    def initialize_df(self, df):
        #定义列名
        df.columns = ['code', 
                    'mcap', 
                    'CMV',
                    'log_NC', 
                    'LEV', 
                    'NI_p', 
                    'g', 
                    'development_expenditure',
                    'pe',
                    'BP',
                    'G_p',
                    'dividend_payable',
                    'ROE',
                    'ROA',
                    'OPTP',
                    'GPM',
                    'FACR',
                    'pcf_ratio',
                    'PS'
                    ]
        
        #标签：对数市值
        df['log_mcap'] = np.log(df['mcap'])
        
        #因子：
        df['EP'] = df['pe'].apply(lambda x: 1/x)
        
        df['BP'] = df['BP'].apply(lambda x: 1/x)
        df['DP'] = df['dividend_payable']/(df['mcap']*100000000)
        #因子：
        df['RD'] = df['development_expenditure']/(df['mcap']*100000000)
        # 因子：现金收益率
        df['CFP'] = df['pcf_ratio'].apply(lambda x: 1/x)
    
        df['log_NC'] = np.log(df['log_NC'])
        
        df['CMV'] = np.log(df['CMV'])
        
        #因子：净利润率
        df['NI_p'] = np.abs(df['NI_p'])
        #因子：
        df['NI_n'] = np.abs(df['NI_p'][df['NI_p']<0])   
    
        df['PEG'] = df['pe'] / (df['G_p']*100)
        
        del df['mcap']
        del df['pe']
        del df['dividend_payable']
        del df['pcf_ratio']
        del df['development_expenditure']
        
        df = df.fillna(0)
        
        return df

    # 中性化
    def neutralize(self, df,industry_set):
        for i in range(len(industry_set)):
            s = pd.Series([0]*len(df), index=df.index)
            df[industry_set[i]] = s
    
            industry = get_industry_stocks(industry_set[i])
            for j in range(len(df)):
                if df.iloc[j,0] in industry:
                    df.ix[j,industry_set[i]] = 1
                    
        return df   
    
    def set_feasible_stocks(self, initial_stocks,context):
        # 判断初始股票池的股票是否停牌，返回list
        paused_info = []
        current_data = get_current_data()
        for i in initial_stocks:
            paused_info.append(current_data[i].paused)
        df_paused_info = pd.DataFrame({'paused_info':paused_info},index = initial_stocks)
        unsuspened_stocks =list(df_paused_info.index[df_paused_info.paused_info == False])
        return unsuspened_stocks
    
    def shift_trading_day(self, date,shift):
        # 获取所有的交易日，返回一个包含所有交易日的 list,元素值为 datetime.date 类型.
        tradingday = get_all_trade_days()
        # 得到date之后shift天那一天在列表中的行标号 返回一个数
        shiftday_index = list(tradingday).index(date) - shift
        # 根据行号返回该日日期 为datetime.date类型
        return tradingday[shiftday_index]