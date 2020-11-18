# -*- encoding: utf8 -*-
'''
Created on 4 Dec 2017

@author: MetalInvest
'''
try:
    from kuanke.user_space_api import *
except:
    pass
from jqdata import *
import tushare as ts
from oop_strategy_frame import *
from chanMatrix import *
from sector_selection import *
from herd_head import *
# from ml_factor_rank import *
# from dynamic_factor_based_stock_ranking import *
from pair_trading_ols import *
from value_factor_lib import *
from quant_lib import *
from functools import reduce
from chan_common_include import Chan_Type, float_less_equal, float_more_equal, float_equal, get_bars_new
from biaoLiStatus import TopBotType
from chan_kbar_filter import *
from equilibrium import *
from kBar_Chan import *
import datetime
import talib


'''=========================选股规则相关==================================='''

def sort_by_sector_try(sector_list, value):
    try:
        return sector_list.index(value)
    except:
        return 999

# '''-----------------选股组合器2-----------------------'''
class Pick_stocks2(Group_rules):
    def __init__(self, params):
        Group_rules.__init__(self, params)
        self.has_run = False
        self.file_path = params.get('write_to_file', None)
        self.add_etf = params.get('add_etf', False)

    def handle_data(self, context, data):
        try:
            to_run_one = self._params.get('day_only_run_one', False)
        except:
            to_run_one = False
        if to_run_one and self.has_run:
            # self.log.info('设置一天只选一次，跳过选股。')
            return

#         self.log.debug("DEBUG 4: stock cache: {0}, stock list: {1}, monitor_list: {2}, filtered_sectors: {3}, industry_sector_list: {4}".format(g.stock_chan_type.keys(), 
#                                                                            self.g.buy_stocks,
#                                                                            self.g.monitor_buy_list,
#                                                                            self.g.filtered_sectors,
#                                                                            self.g.industry_sector_list))

        stock_list = self.g.buy_stocks
        for rule in self.rules:
            if isinstance(rule, Filter_stock_list):
                stock_list = rule.filter(context, data, stock_list)
                
        # add the ETF index into list this is already done in oop_stop_loss, dirty hack
        self.g.monitor_buy_list = stock_list 
        self.log.info('今日选股:\n' + join_list(["[%s]" % (show_stock(x)) for x in stock_list], ' ', 10))
        self.has_run = True

    def before_trading_start(self, context):
        self.has_run = False
        self.g.buy_stocks = [] # clear the buy list this variable stores the initial list of candidates for the day
        for rule in self.rules:
            if isinstance(rule, Create_stock_list):
                self.g.buy_stocks = self.g.buy_stocks + rule.before_trading_start(context)

#         self.g.buy_stocks = list(set(self.g.buy_stocks))
        
        for rule in self.rules:
            if isinstance(rule, Early_Filter_stock_list):
                rule.before_trading_start(context)

        for rule in self.rules:
            if isinstance(rule, Early_Filter_stock_list):
                self.g.buy_stocks = rule.filter(context, self.g.buy_stocks)
                
#         self.log.debug("DEBUG 3: stock cache: {0}, stock list: {1}, monitor_list: {2}, filtered_sectors: {3}, industry_sector_list: {4}".format(g.stock_chan_type.keys(), 
#                                                                            self.g.buy_stocks,
#                                                                            self.g.monitor_buy_list,
#                                                                            self.g.filtered_sectors,
#                                                                            self.g.industry_sector_list))
    
        checking_stocks = [stock for stock in list(set(self.g.buy_stocks+list(context.portfolio.positions.keys()))) if stock not in g.money_fund]
        if self.add_etf:
            checking_stocks = checking_stocks + g.etf
        if self.file_path:
            if self.file_path == "daily":
                write_file("daily_stocks/{0}.txt".format(str(context.current_dt.date())), ",".join(checking_stocks))    
            else:
                write_file(self.file_path, ",".join(checking_stocks))
                self.log.info('file written:{0}'.format(self.file_path))
        
    def __str__(self):
        return self.memo

# 根据多字段财务数据一次选股，返回一个Query
class Pick_financial_data(Filter_query):
    def filter(self, context, data, q):
        if q is None:
            #             q = query(valuation,balance,cash_flow,income,indicator)
            q = query(valuation)

        for fd_param in self._params.get('factors', []):
            if not isinstance(fd_param, FD_Factor):
                continue
            if fd_param.min is None and fd_param.max is None:
                continue
            factor = eval(fd_param.factor)
            if fd_param.min is not None:
                q = q.filter(
                    factor > fd_param.min
                )
            if fd_param.max is not None:
                q = q.filter(
                    factor < fd_param.max
                )
        order_by = eval(self._params.get('order_by', None))
        sort_type = self._params.get('sort', SortType.asc)
        if order_by is not None:
            if sort_type == SortType.asc:
                q = q.order_by(order_by.asc())
            else:
                q = q.order_by(order_by.desc())

        limit = self._params.get('limit', None)
        if limit is not None:
            q = q.limit(limit)

        return q

    def __str__(self):
        s = ''
        for fd_param in self._params.get('factors', []):
            if not isinstance(fd_param, FD_Factor):
                continue
            if fd_param.min is None and fd_param.max is None:
                continue
            s += '\n\t\t\t\t---'
            if fd_param.min is not None and fd_param.max is not None:
                s += '[ %s < %s < %s ]' % (fd_param.min, fd_param.factor, fd_param.max)
            elif fd_param.min is not None:
                s += '[ %s < %s ]' % (fd_param.min, fd_param.factor)
            elif fd_param.max is not None:
                s += '[ %s > %s ]' % (fd_param.factor, fd_param.max)

        order_by = self._params.get('order_by', None)
        sort_type = self._params.get('sort', SortType.asc)
        if order_by is not None:
            s += '\n\t\t\t\t---'
            sort_type = '从小到大' if sort_type == SortType.asc else '从大到小'
            s += '[排序:%s %s]' % (order_by, sort_type)
        limit = self._params.get('limit', None)
        if limit is not None:
            s += '\n\t\t\t\t---'
            s += '[限制选股数:%s]' % (limit)
        return '多因子选股:' + s

class Filter_financial_data2(Early_Filter_stock_list):
    def normal_filter(self, context, stock_list):
        print("before filter: {0}".format(stock_list))
        is_by_sector = self._params.get('by_sector', False)
        q = query(
            valuation
        ).filter(
            valuation.code.in_(stock_list)
        )
        # complex_factor = []
        for fd_param in self._params.get('factors', []):
            if not isinstance(fd_param, FD_Factor):
                continue
            if fd_param.min is None and fd_param.max is None:
                continue
            factor = eval(fd_param.factor)
            if fd_param.isComplex:
                q = q.add_column(factor)
                
            if not is_by_sector:
                if fd_param.min is not None:
                    q = q.filter(
                        factor > fd_param.min
                    )
                if fd_param.max is not None:
                    q = q.filter(
                        factor < fd_param.max
                    )
        order_by = eval(self._params.get('order_by', None))
        sort_type = self._params.get('sort', SortType.asc)
        if order_by is not None:
            if sort_type == SortType.asc:
                q = q.order_by(order_by.asc())
            else:
                q = q.order_by(order_by.desc())
        limit = self._params.get('limit', None)
        if limit is not None and not is_by_sector:
            q = q.limit(limit)
        df_data = get_fundamentals(q)
        stock_list = list(df_data['code'])
        if self._params.get('isdebug', False):
            print(df_data)
        print("after filter: {0}".format(stock_list))
        return stock_list    
    
    def filter_by_sector(self, context):
        final_list = []
        threthold_limit = self._params.get('limit', None)
        industry_sectors, concept_sectors = self.g.filtered_sectors
        total_sector_num = len(industry_sectors) + len(concept_sectors)
        limit_num = threthold_limit/total_sector_num if threthold_limit is not None else 3
        for sector in industry_sectors:
            stock_list = get_industry_stocks(sector)
            stock_list = self.normal_filter(context, stock_list)
            final_list += stock_list[:limit_num]
        
        for con in concept_sectors:
            stock_list = get_concept_stocks(con)
            stock_list = self.normal_filter(context, stock_list)
            final_list += stock_list[:limit_num]
        return final_list
    
    def filter(self, context, stock_list):
        if self._params.get('by_sector', False):
            return self.filter_by_sector(context)
        else:
            return self.normal_filter(context, stock_list)

    def __str__(self):
        s = ''
        for fd_param in self._params.get('factors', []):
            if not isinstance(fd_param, FD_Factor):
                continue
            if fd_param.min is None and fd_param.max is None:
                continue
            s += '\n\t\t\t\t---'
            if fd_param.min is not None and fd_param.max is not None:
                s += '[ %s < %s < %s ]' % (fd_param.min, fd_param.factor, fd_param.max)
            elif fd_param.min is not None:
                s += '[ %s < %s ]' % (fd_param.min, fd_param.factor)
            elif fd_param.max is not None:
                s += '[ %s > %s ]' % (fd_param.factor, fd_param.max)

        order_by = self._params.get('order_by', None)
        sort_type = self._params.get('sort', SortType.asc)
        if order_by is not None:
            s += '\n\t\t\t\t---'
            sort_type = '从小到大' if sort_type == SortType.asc else '从大到小'
            s += '[排序:%s %s]' % (order_by, sort_type)
        limit = self._params.get('limit', None)
        if limit is not None:
            s += '\n\t\t\t\t---'
            s += '[限制选股数:%s]' % (limit)
        return '多因子筛选:' + s

class Filter_black_stocks(Early_Filter_stock_list):
    
    def filter(self, context, stock_list):
#         print("before filter: {0}".format(stock_list))
        q = query(
            income.np_parent_company_owners
        ).filter(
            valuation.code.in_(stock_list)
        )

        df = get_fundamentals_continuously(q, 
                                           end_date=context.previous_date, 
                                           count=250, 
                                           panel=False)
        df = df[df['np_parent_company_owners'] < 0]
        result_df = df.groupby('code').nunique()
        remove_list = result_df[result_df['np_parent_company_owners'] >= 3].index.tolist()
        print("{0} filtered OUT".format(remove_list))

        stock_list = [stock for stock in stock_list if stock not in remove_list]
#         print("after filter: {0}".format(stock_list))
        return stock_list

    def __str__(self):
        s = ''
        for fd_param in self._params.get('factors', []):
            if not isinstance(fd_param, FD_Factor):
                continue
            if fd_param.min is None and fd_param.max is None:
                continue
            s += '\n\t\t\t\t---'
            if fd_param.min is not None and fd_param.max is not None:
                s += '[ %s < %s < %s ]' % (fd_param.min, fd_param.factor, fd_param.max)
            elif fd_param.min is not None:
                s += '[ %s < %s ]' % (fd_param.min, fd_param.factor)
            elif fd_param.max is not None:
                s += '[ %s > %s ]' % (fd_param.factor, fd_param.max)

        order_by = self._params.get('order_by', None)
        sort_type = self._params.get('sort', SortType.asc)
        if order_by is not None:
            s += '\n\t\t\t\t---'
            sort_type = '从小到大' if sort_type == SortType.asc else '从大到小'
            s += '[排序:%s %s]' % (order_by, sort_type)
        limit = self._params.get('limit', None)
        if limit is not None:
            s += '\n\t\t\t\t---'
            s += '[限制选股数:%s]' % (limit)
        return '多因子筛选:' + s


class Filter_FX_data(Early_Filter_stock_list):
    def __init__(self, params):
        self.limit = params.get('limit', 100)
        self.quantlib = quantlib()
        self.value_factor = value_factor_lib()
    
    def filter(self, context, stock_list):
#         statsDate = context.current_dt.date() - dt.timedelta(1)
        statsDate = context.previous_date
        #获取坏股票列表，将会剔除
        bad_stock_list = self.quantlib.fun_get_bad_stock_list(statsDate)
        # 低估值策略
        fx_stock_list = self.value_factor.fun_get_stock_list(context, self.limit, statsDate, bad_stock_list)
        return [stock for stock in fx_stock_list if stock in stock_list]
        
    def __str__(self):
        return '小佛雪选股 选取:%s' % self.limit

# 根据财务数据对Stock_list进行过滤。返回符合条件的stock_list
class Filter_financial_data(Early_Filter_stock_list):
    def filter(self, context, stock_list):
        q = query(valuation).filter(
            valuation.code.in_(stock_list)
        )
        factor = eval(self._params.get('factor', None))
        min = self._params.get('min', None)
        max = self._params.get('max', None)
        if factor is None:
            return stock_list
        if min is None and max is None:
            return stock_list
        if min is not None:
            q = q.filter(
                factor > min
            )
        if max is not None:
            q = q.filter(
                factor < max
            )
        
        order_by = eval(self._params.get('order_by', None))
        sort_type = self._params.get('sort', SortType.asc)
        if order_by is not None:
            if sort_type == SortType.asc:
                q = q.order_by(order_by.asc())
            else:
                q = q.order_by(order_by.desc())
        stock_list = list(get_fundamentals(q)['code'])
        return stock_list

    def __str__(self):
        factor = self._params.get('factor', None)
        min = self._params.get('min', None)
        max = self._params.get('max', None)
        s = self.memo + ':'
        if min is not None and max is not None:
            s += ' [ %s < %s < %s ]' % (min, factor, max)
        elif min is not None:
            s += ' [ %s < %s ]' % (min, factor)
        elif max is not None:
            s += ' [ %s > %s ]' % (factor, max)
        else:
            s += '参数错误'
        return s    

################## Chan Filter ##################
class Pick_Chan_Stocks(Create_stock_list):
    def __init__(self, params):
        Create_stock_list.__init__(self, params)
        self.index = params.get('stock_index', '000985.XSHG')
        self.periods = params.get('periods', ['1w'])
        self.chan_types = params.get('chan_types', [Chan_Type.I, Chan_Type.III])
        self.is_debug = params.get('isdebug', False)
        self.num_of_stocks = params.get('number_of_stock', 8)
        self.num_of_data = params.get('number_of_data', 2000)
        
    def update_params(self, context, params):
        pass
    
    def before_trading_start(self, context):
        stock_list = filter_high_level_by_index(direction=TopBotType.top2bot, 
                                   stock_index=[self.index], 
                                   df=False, 
                                   periods = self.periods,
                                   end_dt=context.current_dt, #strftime("%Y-%m-%d %H:%M:%S")
                                   chan_types=self.chan_types)
        stock_list = [stock for stock in stock_list if stock not in context.portfolio.positions.keys()]
        stock_list = stock_list[:self.num_of_stocks]
        for stock in stock_list:
            result, xd_result, chan_profile = check_chan_by_type_exhaustion(stock,
                                                                          end_time=context.current_dt, 
                                                                          periods=['5m'], 
                                                                          count=self.num_of_data, 
                                                                          direction=TopBotType.top2bot,
                                                                          chan_type=self.chan_types,
                                                                          isdebug=self.is_debug, 
                                                                          is_anal=True)
            if result and xd_result:
                g.stock_chan_type[stock] = chan_profile
        if self.is_debug:
            print(str(g.stock_chan_type))
        return list(g.stock_chan_type.keys())
    
    def __str__(self):
        return "Chan Selection Params: {0}, {1}, {2}".format(self.index, self.periods, self.chan_types)

################## 缠论强势板块 #################
class Pick_rank_sector(Create_stock_list):
    def __init__(self, params):
        Create_stock_list.__init__(self, params)
        self.strong_sector = params.get('strong_sector', False)
        self.sector_limit_pct = params.get('sector_limit_pct', 5)
        self.strength_threthold = params.get('strength_threthold', 4)
        self.isDaily = params.get('isDaily', False)
        self.useIntradayData = params.get('useIntradayData', False)
        self.useAvg = params.get('useAvg', True)
        self.avgPeriod = params.get('avgPeriod', 5)
        self.period_frequency = params.get('period_frequency', 'W')
        self.isWeighted = params.get('isWeighted', True)
        self.new_list = []
        
    def update_params(self, context, params):
        self.period_frequency = params.get('period_frequency', 'W')        
        self.isWeighted = params.get('isWeighted', True)
        
    def filter(self, context, data):
        return self.new_list
    
    def before_trading_start(self, context):
        # new_list = ['002714.XSHE', '603159.XSHG', '603703.XSHG','000001.XSHE','000002.XSHE','600309.XSHG','002230.XSHE','600392.XSHG','600291.XSHG']
        if self.g.isFirstNTradingDayOfPeriod(context, num_of_day=1, period=self.period_frequency) or not self.new_list or self.isDaily:
            self.log.info("选取前 %s%% 板块" % str(self.sector_limit_pct))
            ss = SectorSelection(limit_pct=self.sector_limit_pct, 
                    isStrong=self.strong_sector, 
                    min_max_strength=self.strength_threthold, 
                    useIntradayData=self.useIntradayData,
                    useAvg=self.useAvg,
                    avgPeriod=self.avgPeriod,
                    isWeighted=self.isWeighted,
                    effective_date=context.previous_date)
            self.new_list = ss.processAllSectorStocks()
            self.g.filtered_sectors = ss.processAllSectors()
        return self.new_list
    
    def after_trading_end(self, context):
        pass
    
    def __str__(self):
        if self.strong_sector:
            return '强势板块股票 %s%% 阈值 %s' % (self.sector_limit_pct, self.strength_threthold)
        else:
            return '弱势板块股票 %s%% 阈值 %s' % (self.sector_limit_pct, self.strength_threthold)


class Pick_Rank_Factor(Create_stock_list):
    def __init__(self, params):
        self.stock_num = params.get('stock_num', 20)
        self.index_scope = params.get('index_scope', '000985.XSHG')
        self.use_enhanced = params.get('use_enhanced', False)
        self.factor_category = params.get('factor_category', None)
        self.is_debug = params.get('is_debug', False)
        self.regress_profit = params.get('regress_profit', False)
        self.period = params.get('period', 'month_3')
        self.trainlength = params.get('train_length', 55)
        self.use_np = params.get("use_np", False)
        pass
    
    def update_params(self, context, params):
        self.period = params.get('period', 'month_3')
        self.trainlength = params.get('train_length', 55)
        self.use_np = params.get("use_np", False)
    
    def before_trading_start(self, context):
        from ml_factor_rank import ML_Dynamic_Factor_Rank, ML_Factor_Rank
        if self.use_enhanced:
            mdfr = ML_Dynamic_Factor_Rank({'stock_num':self.stock_num, 
                                  'index_scope':self.index_scope,
                                  'period':self.period,
                                  'is_debug':self.is_debug, 
                                  'use_dynamic_factors': True, 
                                  'context': context, 
                                  'regress_profit': self.regress_profit,
                                  'factor_category':self.factor_category, 
                                  'trainlength': self.trainlength})
            if self.use_np:
                new_list = mdfr.gaugeStocks_byfactors_np(context)
            else:
                new_list = mdfr.gaugeStocks_byfactors(context)

        else:
            mfr = ML_Factor_Rank({'stock_num':self.stock_num, 
                                  'index_scope':self.index_scope})
#             new_list = mfr.gaugeStocks_new(context)
            new_list = mfr.gaugeStocks(context)
        return new_list

    def __str__(self):
        return "多因子回归公式选股"
    

class Pick_Dynamic_Rank_Factor(Create_stock_list):
    def __init__(self, params):
        self.stock_num = params.get('stock_num', 5)
        self.index_scope = params.get('index_scope', 'hs300')
        self.period = params.get('period', 'month_3')
        self.model = params.get('model', 'long_only')
        self.category = params.get('category', ['basics', 'emotion', 'growth', 'momentum', 'pershare', 'quality', 'risk', 'style', 'technical'])
        self.factor_gauge = params.get('factor_gauge', 'ir')
        self.factor_num = params.get('factor_num', 10)
        self.factor_date_count = params.get('factor_date_count', 1)
        self.factor_method = params.get('factor_method', 'factor_intersection') # ranking_score
        self.ic_mean_threthold = params.get('ic_mean_threthold', 0.02)
        self.is_debug = params.get('is_debug', False)
        self.factor_analyzer_result_path = params.get('factor_analyzer_result_path', None)
        pass  

    def update_params(self, context, params):
        self.ic_mean_threthold = params.get('ic_mean_threthold', 0.02)
        self.is_debug = params.get('is_debug', False)
        self.factor_analyzer_result_path = params.get('factor_analyzer_result_path', None)

    def before_trading_start(self, context):
        from dynamic_factor_based_stock_ranking import Dynamic_factor_based_stock_ranking
        dfbsr = Dynamic_factor_based_stock_ranking({'stock_num':self.stock_num, 
                                                    'index_scope':self.index_scope,
                                                    'period':self.period,
                                                    'model':self.model,
                                                    'category':self.category,
                                                    'factor_num':self.factor_num,
                                                    'factor_gauge':self.factor_gauge,
                                                    'factor_date_count':self.factor_date_count,
                                                    'factor_method':self.factor_method,
                                                    'ic_mean_threthold':self.ic_mean_threthold,
                                                    'is_debug':self.is_debug})
        new_list = dfbsr.gaugeStocks(context, self.factor_analyzer_result_path)
        return new_list

    def __str__(self):
        return "动态多因子有效选股"
    
    
    
class Pick_ETF(Create_stock_list):
    def __init__(self, params):
        self.etf_index = params.get('etf_index', g.etf_index)
        pass
    
    def before_trading_start(self, context):
        return self.etf_index

    def __str__(self):
        return "ETF选股"
    
class Pick_fundamental_factor_rank(Create_stock_list):
    def __init__(self, params):
        self.stock_num = params.get('stock_num', 20)
        pass

    def before_trading_start(self, context):    
        q = query(
            valuation.code
        )
        for fd_param in self._params.get('factors', []):
            if not isinstance(fd_param, FD_Factor):
                continue
            if fd_param.min is None and fd_param.max is None:
                continue
            factor = eval(fd_param.factor)
            q = q.add_column(factor)            
            if fd_param.min is not None:
                q = q.filter(
                    factor > fd_param.min
                )
            if fd_param.max is not None:
                q = q.filter(
                    factor < fd_param.max
                )

        order_by = eval(self._params.get('order_by', None))
        sort_type = self._params.get('sort', SortType.asc)
        if order_by is not None:
            if sort_type == SortType.asc:
                q = q.order_by(order_by.asc())
            else:
                q = q.order_by(order_by.desc())

        df = get_fundamentals(q)
        df = df.set_index('code')
        #获取综合得分
        df['point'] = df.rank().T.apply(sum)        
        #按得分进行排序，取指定数量的股票
        df = df.sort_values('point')[:self.stock_num]
        return list(df.index.values)
    
    def before_trading_start_backup(self, context):
            #获取股票池
        df = get_fundamentals(query(valuation.code,valuation.pb_ratio,indicator.roe))
        #进行pb,roe大于0筛选
        df = df[(df['roe']>0) & (df['pb_ratio']>0)].sort('pb_ratio')
        #以股票名词作为index
#         df.index = df['code'].values
        df = df.set_index('code')
        #取roe倒数
        df['1/roe'] = 1/df['roe']
        #获取综合得分
        df['point'] = df[['pb_ratio','1/roe']].rank().T.apply(sum)
        #按得分进行排序，取指定数量的股票
        df = df.sort_values('point')[:self.stock_num]
        return df.index
        
    def __str__(self):
        return "多因子综合评分选股"

class Pick_Pair_Trading(Create_stock_list):
    def __init__(self, params):
        Create_stock_list.__init__(self, params)
        self.pair_period = params.get('pair_period', 250)
        self.init_index_list = params.get('init_index_list', ['801010', '801780', '801790'])
        self.isIndex = params.get('isIndex', False)
        self.input_as_list = params.get('input_as_list', False)
        self.get_pair = params.get('get_pair', False)
        self.return_pair = params.get('return_pair', 1)
        self.period_frequency = params.get('period_frequency', 'M')
        self.new_pair = []
    
    def update_params(self, context, params):
        self.period_frequency = params.get('period_frequency', 'M')
        
    
    def before_trading_start(self, context):
        if self.input_as_list:
            return list(set(self.init_index_list))
        
        initial_list = []
        for index in self.init_index_list:
            initial_list += get_index_stocks(index) if self.isIndex else get_industry_stocks(index) 
        initial_list = list(set(initial_list))
        
        if self.get_pair and (self.g.isFirstNTradingDayOfPeriod(context, num_of_day=1, period=self.period_frequency) or not self.new_pair):    
            data_frame = history(self.pair_period, '1d', 'close', security_list=initial_list, df=True)
            pto = PairTradingOls({'return_pair': self.return_pair})
            self.new_pair = pto.get_top_pair(data_frame)
            if not self.new_pair:
                return []
            self.g.pair_zscore = pto.get_regression_ratio(data_frame, self.new_pair)
            initial_list = np.array(self.new_pair).flatten().tolist()
        return initial_list

    def __str__(self):
        return "配对交易选对股"
    

class Pick_stock_list_from_file(Filter_stock_list):
    '''
    This class simple pick list of stocks from a file 
    and feed them to the next stage. 
    It's only used when the platform can't facilitate the initial
    stock selection process
    '''
    def __init__(self, params):
        Filter_stock_list.__init__(self, params)
        self.filename = params.get('filename', None)        

    def filter(self, context, data, stock_list):
        file_stock_list = read_file(self.filename)
        self.log.info("stocks {0} read from file {1}".format(file_stock_list, self.filename))
        return file_stock_list
        
    def __str__(self):
        return "从文件中读取已经写好的股票列表"
    
class Pick_stock_from_file_chan(Create_stock_list):
    '''
    take data from preprocessed file based on chan rule
    '''
    def __init__(self, params):
        Create_stock_list.__init__(self, params)
        self.filename = params.get('filename', None)
        self.current_chan_types = params.get('current_chan_types', [Chan_Type.I, Chan_Type.III, Chan_Type.INVALID])
        self.top_chan_types = params.get('top_chan_types', [Chan_Type.I, Chan_Type.INVALID])
        self.enable_on_demand = params.get('on_demand', False)
        self.isdebug = params.get('isdebug', False)
        self.min_stock_num = params.get('min_stock_num', 0)
        
    def before_trading_start(self, context):
        chan_stock_list = []
        if self.filename: # model prediction happened outside
            today_date = context.current_dt.date()
            yesterday = context.previous_date
            chan_dict = json.loads(read_file(self.filename))
            
                
            if str(today_date) not in chan_dict:
                if self.enable_on_demand:
                    print("{0} not in chan file, get stocks on demand".format(today_date))
                    check_stocks = filter_high_level_by_index(
                                                            direction=TopBotType.top2bot,
                                                            stock_index=['000985.XSHG'],
                                                            end_dt=yesterday,
                                                            df=False,
                                                            periods = ['1M'],
                                                            chan_types=self.top_chan_types)
                    check_stocks = filter_high_level_by_stocks(
                                                        direction=TopBotType.top2bot, 
                                                        stock_list=check_stocks,  
                                                        df=False,
                                                        end_dt= yesterday, 
                                                        periods = ['1w'],
                                                        chan_types=self.current_chan_types)
                    return check_stocks
                else:
                    print("{0} not in chan file".format(today_date))
                    return []
            
            chan_list = chan_dict[str(today_date)]
            if self.isdebug:
                self.log.info("data read from file: {0} stocks info".format(len(chan_list)))
            for stock, top_type_value, c_type_value, top_period, cur_period, c_direc_value, c_price, c_slope, c_force, z_time, s_time in chan_list:
                if stock in context.portfolio.positions.keys():
                    if self.isdebug:
                        self.log.info("{0} already in position".format(stock))
                    chan_stock_list.append(stock)
                    continue
                if self.current_chan_types and (Chan_Type.value2type(c_type_value) not in self.current_chan_types):
                    if self.isdebug:
                        self.log.info("{0} has invalid current chan type".format(stock))
                    continue
                if self.top_chan_types and (Chan_Type.value2type(top_type_value) not in self.top_chan_types):
                    if self.isdebug:
                        self.log.info("{0} has invalid top chan type".format(stock))
                    continue
                
                if z_time is None:
                    continue
                
                chan_stock_list.append(stock)
                if stock not in g.stock_chan_type:
                    g.stock_chan_type[stock] = [(Chan_Type.value2type(top_type_value), 
                                                      TopBotType.top2bot,
                                                      0, 
                                                      0,
                                                      0,
                                                      None,
                                                      None),
                                                      (Chan_Type.value2type(c_type_value),
                                                       TopBotType.value2type(c_direc_value),
                                                       c_price,
                                                       0,
                                                       0,
                                                       datetime.datetime.strptime(z_time, "%Y-%m-%d %H:%M:%S"), 
                                                       datetime.datetime.strptime(s_time, "%Y-%m-%d %H:%M:%S"), 
                                                       )]
            self.log.info("filtered data read from file: {0} stocks info. cache info: {1}".format(len(chan_stock_list), 
                                                                                                  g.stock_chan_type.keys()))
        return chan_stock_list if len(chan_stock_list) >= self.min_stock_num else []
    
    def __str__(self):
        return "从文件中读取根据缠论已经写好的股票列表以及数据"
    
    
class Read_stock_from_file_chan(Filter_stock_list):
    '''
    take data from preprocessed file based on chan rule
    '''
    def __init__(self, params):
        Filter_stock_list.__init__(self, params)
        self.filename = params.get('filename', None)
        self.current_chan_types = params.get('current_chan_types', [Chan_Type.I, Chan_Type.III, Chan_Type.INVALID])
        self.top_chan_types = params.get('top_chan_types', [Chan_Type.I, Chan_Type.INVALID])
        self.enable_on_demand = params.get('on_demand', False)
        self.isdebug = params.get('isdebug', False)
        self.min_stock_num = params.get('min_stock_num', 0)
        
    def filter(self, context, data, stock_list):
        chan_stock_list = []
        if self.filename: # model prediction happened outside
            today_date = context.current_dt.date()
            yesterday = context.previous_date
            chan_dict = json.loads(read_file(self.filename))
            
                
            if str(today_date) not in chan_dict:
                if self.enable_on_demand:
                    print("{0} not in chan file, get stocks on demand".format(today_date))
                    check_stocks = filter_high_level_by_index(
                                                            direction=TopBotType.top2bot,
                                                            stock_index=['000985.XSHG'],
                                                            end_dt=yesterday,
                                                            df=False,
                                                            periods = ['1M'],
                                                            chan_types=self.top_chan_types)
                    check_stocks = filter_high_level_by_stocks(
                                                        direction=TopBotType.top2bot, 
                                                        stock_list=check_stocks,  
                                                        df=False,
                                                        end_dt= yesterday, 
                                                        periods = ['1w'],
                                                        chan_types=self.current_chan_types)
                    return check_stocks
                else:
                    print("{0} not in chan file".format(today_date))
                    return []
            
            chan_list = chan_dict[str(today_date)]
            if self.isdebug:
                self.log.info("data read from file: {0} stocks info".format(len(chan_list)))
            for stock, top_type_value, c_type_value, top_period, cur_period, c_direc_value, c_price, c_slope, c_force, z_time, s_time in chan_list:
                if stock in context.portfolio.positions.keys():
                    if self.isdebug:
                        self.log.info("{0} already in position".format(stock))
                    chan_stock_list.append(stock)
                    continue
                if self.current_chan_types and (Chan_Type.value2type(c_type_value) not in self.current_chan_types):
                    if self.isdebug:
                        self.log.info("{0} has invalid current chan type".format(stock))
                    continue
                if self.top_chan_types and (Chan_Type.value2type(top_type_value) not in self.top_chan_types):
                    if self.isdebug:
                        self.log.info("{0} has invalid top chan type".format(stock))
                    continue
                
                if z_time is None:
                    continue
                
                chan_stock_list.append(stock)
                if stock not in g.stock_chan_type:
                    g.stock_chan_type[stock] = [(Chan_Type.value2type(top_type_value), 
                                                      TopBotType.top2bot,
                                                      0, 
                                                      0,
                                                      0,
                                                      None,
                                                      None),
                                                      (Chan_Type.value2type(c_type_value),
                                                       TopBotType.value2type(c_direc_value),
                                                       c_price,
                                                       0,
                                                       0,
                                                       datetime.datetime.strptime(z_time, "%Y-%m-%d %H:%M:%S"), 
                                                       datetime.datetime.strptime(s_time, "%Y-%m-%d %H:%M:%S"), 
                                                       )]
            self.log.info("filtered data read from file: {0} stocks info. cache info: {1}".format(len(chan_stock_list), 
                                                                                                  g.stock_chan_type.keys()))
        return chan_stock_list if len(chan_stock_list) >= self.min_stock_num else []
    
    def __str__(self):
        return "DEBUG从文件中读取根据缠论已经写好的股票列表以及数据"

        
class Filter_Chan_Stocks(Filter_stock_list):
    def __init__(self, params):
        Filter_stock_list.__init__(self, params)
        self.isdebug = params.get('isdebug', False)
        self.isDescription= params.get('isDescription', False)
        self.long_stock_num = params.get('long_stock_num', 0)
        self.sup_chan_type = params.get('sup_chan_type', [Chan_Type.I, Chan_Type.INVALID])
        self.current_chan_type = params.get('current_chan_type', [Chan_Type.I])
        self.sub_chan_type = params.get('sub_chan_type', [Chan_Type.INVALID, Chan_Type.I])
        self.periods = params.get('periods', ['5m', '1m'])
        self.num_of_data = params.get('num_of_data', 2500)
        self.sub_force_zhongshu = params.get('sub_force_zhongshu', True)
        self.bi_level_precision = params.get('bi_level_precision', True)
        self.long_hour_start = params.get('long_hour_start', 13)
        self.long_min_start = params.get('long_min_start', 30)
        self.use_sub_split = params.get('sub_split', True)
        self.ignore_xd = params.get('ignore_xd', False)
        self.use_stage_III = params.get('use_stage_III', False)
        self.stage_III_timing = params.get('stage_III_timing', [14, 50])
        self.long_candidate_num = params.get('long_candidate_num', self.long_stock_num)
        self.use_stage_A = params.get('use_stage_A', False)
        
        self.force_chan_type = params.get('force_chan_type', [
                                                              [Chan_Type.I, self.current_chan_type[0]],
                                                              [Chan_Type.I_weak, self.current_chan_type[0]],
                                                              [Chan_Type.INVALID, self.current_chan_type[0]]
                                                              ])
        self.tentative_chan_type = params.get('tentative_chan_type', [
                                    [Chan_Type.I, self.current_chan_type[0]],
                                    [Chan_Type.I_weak, self.current_chan_type[0]],
                                    [Chan_Type.INVALID, self.current_chan_type[0]]
                                    ])
        self.tentative_stage_I = set() # list to hold stocks waiting to be operated
        self.tentative_stage_II = set()
        self.tentative_stage_III = set()
        self.tentative_stage_A = set()
        self.tentative_stage_B = set()
        self.halt_check_when_enough = params.get('halt_check_when_enough', True)
        self.stage_A_pos_return_types = params.get('stage_A_pos_return_types', [Chan_Type.III, Chan_Type.III_strong, Chan_Type.III_weak, Chan_Type.INVALID])
        self.stage_A_neg_return_types = params.get('stage_A_neg_return_types', [Chan_Type.I, Chan_Type.I_weak])
        self.stage_A_types = params.get('stage_A_types', [Chan_Type.III, Chan_Type.III_strong, Chan_Type.III_weak])
        self.use_all_stocks_4_A = params.get('use_all_stocks_4_A', False)
        self.price_revert_range = params.get('price_revert_range', 0.055)
    
    def check_guide_price_reached(self, stock, context):
        current_profile = g.stock_chan_type[stock][1]
        current_chan_t = current_profile[0]
        current_chan_p = current_profile[2]
        current_start_time = current_profile[5]
        current_effective_time = current_profile[6]
        stock_data = get_price(stock,
                               start_date=current_start_time, 
                               end_date=context.current_dt, 
                               frequency=self.periods[0], 
                               fields=('high', 'low', 'close', 'money'), 
                               skip_paused=False)
        if current_chan_t == Chan_Type.I or current_chan_t == Chan_Type.I_weak:
            max_price_after_long = stock_data.loc[current_effective_time:, 'high'].max()
            if float_more_equal(max_price_after_long, current_chan_p):
                self.log.info("{0} reached target price:{1}, max: {2}".format(stock, 
                                                                              current_chan_p, 
                                                                              max_price_after_long))
                return True

#             min_time = stock_data.loc[current_effective_time:, 'low'].idxmin()
#             min_price = stock_data.loc[min_time,'low']
#             max_price = stock_data.loc[min_time:, 'high'].max()
#             if float_more_equal(max_price / min_price - 1, self.price_revert_range):
#                 self.log.info("{0} price reverted:{1}, max: {2}".format(stock, 
#                                                                       min_price, 
#                                                                       max_price))
#                 return True

        elif current_chan_t == Chan_Type.III or current_chan_t == Chan_Type.III_strong:
            min_price_after_long = stock_data.loc[current_effective_time:, 'low'].min()
            if float_less_equal(min_price_after_long, current_chan_p):
                return True
        return False
    
    def check_tentative_stocks(self, context):
        
        stocks_to_long = set()
        stocks_to_remove_I = set()
        stage_B_long = set()
        
        self.tentative_stage_I = self.tentative_stage_I.difference(set(context.portfolio.positions.keys()))
        
        for stock in self.tentative_stage_I:
            if stock not in g.stock_chan_type:
                print("{0} not in stock_chan_type cache, we ignore it".format(stock))
                stocks_to_remove_I.add(stock)
            
            if len(g.stock_chan_type[stock]) > 1: # we have check it before
                if self.check_guide_price_reached(stock, context):
                    stocks_to_remove_I.add(stock)
                    if self.use_all_stocks_4_A and self.use_stage_A:
                        self.tentative_stage_A.add(stock) # skip first phase
                    continue
            
            check_result, zhongshu_changed = self.check_stage_I(stock, context)
            if zhongshu_changed:
                stocks_to_remove_I.add(stock)
            elif check_result:
                stocks_to_long.add(stock)
        
        self.tentative_stage_I = self.tentative_stage_I.difference(stocks_to_remove_I)
        self.log.info("stocks removed from stage I: {0}".format(stocks_to_remove_I))
        
        stocks_to_remove_II = set()
        self.tentative_stage_II = stocks_to_long.union(self.tentative_stage_II)
        stocks_to_long = set()
        self.tentative_stage_I = self.tentative_stage_I.difference(self.tentative_stage_II)
        self.tentative_stage_II = self.tentative_stage_II.difference(set(context.portfolio.positions.keys()))
                
        for stock in self.tentative_stage_II:
            check_result = self.check_stage_II(stock, context)
            if check_result:
                top_profile = g.stock_chan_type[stock][0]
                cur_profile = g.stock_chan_type[stock][1]
                sub_profile = g.stock_chan_type[stock][2]
                
                top_chan_t = top_profile[0]
                cur_chan_t = cur_profile[0]
                sub_chan_t = sub_profile[0]
                
                chan_type_list = [top_chan_t, cur_chan_t, sub_chan_t]
                if self.force_chan_type and (chan_type_list not in self.force_chan_type):
                    stocks_to_remove_II.add(stock)
                    continue
                stocks_to_long.add(stock)
                
        self.tentative_stage_II = self.tentative_stage_II.difference(stocks_to_remove_II)
        self.log.info("stocks removed from stage II: {0}".format(stocks_to_remove_II))
        self.tentative_stage_II = self.tentative_stage_II.difference(stocks_to_long)
        
        self.tentative_stage_III = self.tentative_stage_III.union(stocks_to_long)
        stocks_to_remove_III = set()
        stocks_to_long = set()
        for stock in self.tentative_stage_III:
            check_result, checked, in_region = self.check_stage_III(stock, context)
            if not in_region:
                stocks_to_remove_III.add(stock)
            elif check_result and checked:
                stocks_to_long.add(stock)
                
        self.tentative_stage_III = self.tentative_stage_III.difference(stocks_to_remove_III)
        self.log.info("stocks removed from stage III: {0}".format(stocks_to_remove_III))
        self.tentative_stage_III = self.tentative_stage_III.difference(stocks_to_long)
        
        if self.use_stage_III and self.use_stage_A:
            # check stage A
            stage_A_long = set()
            stocks_to_remove_A = set()
            for stock in self.tentative_stage_A:
                if stock not in context.portfolio.positions.keys():
                    ready = self.check_stage_A(stock, context)
#                     if zhongshu_changed:
#                         stocks_to_remove_A.add(stock)
                    if ready:
                        stage_A_long.add(stock)
                    
            self.tentative_stage_A = self.tentative_stage_A.difference(stocks_to_remove_A)
            self.log.info("stocks removed from stage A: {0}".format(stocks_to_remove_A))
            
            # for stocks to be long we wait after initial stage A check ########
            self.tentative_stage_A = self.tentative_stage_A.union(stocks_to_long)
            ######################################################################
            self.tentative_stage_A = self.tentative_stage_A.difference(stage_A_long)
            
            self.tentative_stage_B = self.tentative_stage_B.union(stage_A_long)
            stocks_to_remove_B = set()
            for stock in self.tentative_stage_B:
                check_result, price_checked, in_region = self.check_stage_B(stock, context)
                if check_result and price_checked and stock in self.g.all_neg_return_stocks:
                    stage_B_long.add(stock)
                elif check_result and stock in self.g.all_pos_return_stocks:
                    stage_B_long.add(stock)
                elif check_result:
                    stocks_to_remove_B.add(stock)
                    
            self.tentative_stage_B = self.tentative_stage_B.difference(stage_B_long)
            self.tentative_stage_B = self.tentative_stage_B.difference(stocks_to_remove_B)
            self.log.info("stocks removed from stage B: {0}".format(stocks_to_remove_B))
            
#             self.tentative_stage_A = self.tentative_stage_A.union(stage_B_long)
                
        return stocks_to_long, stage_B_long
    
    def check_vol_money_cur_structure(self, stock, context, after_stage_III=False):
        result = False
        zhongshu_changed = False
        vol_result = self.check_vol_money(stock, context) if after_stage_III else self.check_internal_vol_money(stock, context)
            
        if vol_result:
            # check current level here
            cur_result, cur_xd_result, cur_profile = check_chan_by_type_exhaustion(stock,
                                                                          end_time=context.current_dt, 
                                                                          periods=[self.periods[0]], 
                                                                          count=self.num_of_data, 
                                                                          direction=TopBotType.top2bot,
                                                                          chan_type=self.stage_A_types if after_stage_III else self.current_chan_type, 
                                                                          isdebug=self.isdebug, 
                                                                          is_description=False,
                                                                          check_structure=True,
                                                                          check_full_zoushi=False,
                                                                          slope_only=False)
            result = cur_result and (cur_xd_result or self.ignore_xd)
            if result or after_stage_III:
                if len(g.stock_chan_type[stock]) > 1:
                    old_current_profile = g.stock_chan_type[stock][1]
                    if old_current_profile[0] in self.stage_A_types:
                        old_current_p = old_current_profile[2][0] if type(old_current_profile[2]) is list else old_current_profile[2]
                        current_p = cur_profile[0][2][0] if type(cur_profile[0][2]) is list else cur_profile[0][2]
                        zhongshu_changed = current_p != old_current_p
        
                g.stock_chan_type[stock] = [g.stock_chan_type[stock][0]] + cur_profile
                
                
        
        return result, zhongshu_changed
    
    def check_internal_vol_money(self, stock, context):
        
        current_profile = g.stock_chan_type[stock][1]
        current_zoushi_start_time = current_profile[5]
        cur_chan_type = current_profile[0]

        stock_data = get_bars(stock, 
                            count=2000, # 5d
                            unit=self.periods[0],
                            fields=['date','money'],
                            include_now=True, 
                            end_dt=context.current_dt, 
                            fq_ref_date=context.current_dt.date(), 
                            df=False)
        
        cutting_loc = np.where(stock_data['date']>=current_zoushi_start_time)[0][0]
        cutting_offset = stock_data.size - cutting_loc

        cur_internal_latest_money = sum(stock_data['money'][cutting_loc:][-int(cutting_offset/2):])
        cur_internal_past_money = sum(stock_data['money'][cutting_loc:][:-int(cutting_offset/2)])
        cur_internal_ratio = cur_internal_latest_money / cur_internal_past_money
        
        cur_latest_money = sum(stock_data['money'][cutting_loc:])
        cur_past_money = sum(stock_data['money'][:cutting_loc][-cutting_offset:])
        
        cur_ratio = cur_latest_money / cur_past_money
        
#         self.log.debug("candidate stock {0} cur: {1} cur_intern: {2}".format(stock, cur_ratio, cur_internal_ratio))
        if cur_chan_type == Chan_Type.I or cur_chan_type == Chan_Type.I_weak:
            if float_less_equal(cur_ratio, 0.809) or\
                (float_more_equal(cur_ratio, 1.191) and float_less_equal(cur_internal_ratio, 0.809)):
                return True
        elif cur_chan_type == Chan_Type.III or cur_chan_type == Chan_Type.III_strong:
            if float_less_equal(cur_ratio, 0.618) or\
                float_less_equal(cur_internal_ratio, 0.618):
                return True
        elif cur_chan_type == Chan_Type.INVALID:
            if float_less_equal(cur_ratio, 0.809) or\
                float_less_equal(cur_internal_ratio, 0.809):
                result = True
        return False
    
    def check_daily_vol_money(self, stock, context):
        # three days vol must decrease!
        stock_data = get_price(security=stock, 
                      end_date=context.current_dt, 
                      count = 4,
                      frequency='120m', 
                      skip_paused=True, 
                      panel=False, 
                      fields=['money'])
        
        cur_ratio = sum(stock_data['money'][-2:]) / sum(stock_data['money'][-4:-2])
        if float_less_equal(cur_ratio, 0.618):
            return True
        if float_more_equal(cur_ratio, 1.382):
            return True
        return False
    
    def check_vol_money(self, stock, context):
        sub_profile = g.stock_chan_type[stock][2]
        sub_effective_time = sub_profile[6]

        stock_data = get_bars(stock, 
                            count=4800, # 5d
                            unit=self.periods[0],
                            fields=['date','money', 'high'],
                            include_now=True, 
                            end_dt=context.current_dt, 
                            fq_ref_date=context.current_dt.date(), 
                            df=False)
        
#         if not stock_changed_record[stock]: # Zhongshu unchanged
        sub_loc = np.where(stock_data['date']>=sub_effective_time)[0][0]
        cut_stock_data = stock_data[sub_loc:]
        
        cutting_idx = np.where(cut_stock_data['high'] == np.amax(cut_stock_data['high']))[0][-1]
        cutting_date = cut_stock_data['date'][cutting_idx]
        
        real_cutting_idx = np.where(stock_data['date'] == cutting_date)[0][0]
        cutting_offset = stock_data.size - real_cutting_idx
        
        cur_latest_money = sum(stock_data['money'][real_cutting_idx:])
        cur_past_money = sum(stock_data['money'][:real_cutting_idx][-cutting_offset:])
# 
#         # current zslx money split by mid term
        sub_latest_money = sum(stock_data['money'][-int(cutting_offset/2):])
        sub_past_money = sum(stock_data['money'][real_cutting_idx:][:int(cutting_offset/2)])

        cur_ratio = cur_latest_money/cur_past_money
        sub_ratio = sub_latest_money/sub_past_money

#         self.log.debug("candidate stock {0} cur: {1}, sub: {2}".format(stock, 
#                                                                     cur_ratio, 
#                                                                     sub_ratio))
        if float_more_equal(cur_ratio, 1.191) or\
            float_more_equal(sub_ratio, 1.191):
            return True
        if float_less_equal(cur_ratio, 0.809) or\
            float_less_equal(sub_ratio, 0.809):
            return True

        return False
    
    def check_bot_shape(self, stock, context, from_local_max=False, ignore_bot_shape=True):
        current_profile = g.stock_chan_type[stock][1]
        current_start_time = current_profile[5]
        current_effective_time = current_profile[6]
        
        data_start_time = str(current_start_time.date()) + " {0}:{1}:00".format(self.stage_III_timing[0], 
                                                                                self.stage_III_timing[1]+1) # +1 fix data format bug
        stock_data = get_price(security=stock, 
                      end_date=context.current_dt, 
                      start_date=data_start_time, 
#                       count = 20,
                      frequency='240m', 
                      skip_paused=True, 
                      panel=False, 
                      fields=['high', 'low', 'close', 'open'])

        if from_local_max:
            max_time = stock_data.loc[current_effective_time:,'high'].idxmax()
            stock_data = stock_data.loc[max_time:,]
        
        stock_data['date'] = stock_data.index
        working_data_np = stock_data.to_records()
        kb_chan = KBarChan(working_data_np, isdebug=False)
        
        result, check = kb_chan.formed_tb(tb=TopBotType.bot)
        
        ###### DOUBLE CHECK #########
#         stock_data2 = get_bars_new(stock, 
#                             start_dt=current_start_time,
#                             unit='1d',
#                             fields=['date','high', 'low', 'close', 'open'],
#                             include_now=True, 
#                             end_dt=context.current_dt, 
#                             fq_ref_date=context.current_dt.date(), 
#                             df=False)
#         kb_chan2 = KBarChan(stock_data2, isdebug=False)
#         
#         result2, check2 = kb_chan2.formed_tb(tb=TopBotType.bot)
        
        return result and\
            (ignore_bot_shape or\
            not self.is_big_negative_stick(stock_data['open'][-1], 
                                           stock_data['close'][-1], 
                                           stock_data['high'][-1], 
                                           stock_data['low'][-1])), check
                                        
    def is_big_positive_stick(self, open, close, high, low):
        return float_more(close, open) and float_more_equal((close-open)/(high-low), 0.618)
        
    def is_big_negative_stick(self, open, close, high, low):
        return float_less(close, open) and float_more_equal((open-close)/(high-low), 0.618)
        
    def check_stage_II(self, stock, context):
#         result, _ = self.check_structure_sub_only(stock, context)
#         return result or self.check_daily_vol_money(stock, context)
        return True
    
    def check_stage_III(self, stock, context):
        if self.stage_III_timing and\
            (context.current_dt.hour != self.stage_III_timing[0] or\
            context.current_dt.minute != self.stage_III_timing[1]):
            return False, False, True
        
        bot_result, checked = self.check_bot_shape(stock, context, from_local_max=False, ignore_bot_shape=True)
        boll_result, in_region = self.check_daily_boll_lower(stock, context)
#         print("{0} {1}, {2}, {3}, {4}".format(stock, bot_result, checked, boll_result, in_region))
        return bot_result and boll_result, checked, in_region
    
    def check_stage_B(self, stock, context):
        if self.stage_III_timing and\
            (context.current_dt.hour != self.stage_III_timing[0] or\
            context.current_dt.minute != self.stage_III_timing[1]):
            return False, False, True
        
        bot_result, checked = self.check_bot_shape(stock, context, from_local_max=False, ignore_bot_shape=False)
        boll_result, in_region = self.check_daily_boll_lower(stock, context)
        return bot_result, checked, in_region
    
    def check_stage_A(self, stock, context):
        return self.check_stage_A_boll(stock, context) and self.check_stage_A_vol(stock, context)
    
    def check_stage_A_boll(self, stock, context):
        stock_data = get_bars(stock,
                               count=50,
                               end_dt=context.current_dt, 
                               unit='1d', # use super level
                               include_now=True, 
                               fields=('close', 'low', 'high'), 
                               fq_ref_date=context.current_dt.date(),
                               df=False)
        upper, middle, lower = talib.BBANDS(stock_data['close'], timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
        return float_less(stock_data['low'][-1],middle[-1])
    
    def check_stage_A_sub(self, stock, context):
        result, xd_result, s_profile, sub_zhongshu_formed = check_stock_sub(stock,
                                              end_time=context.current_dt,
                                              periods=[self.periods[1]],
                                              count=self.num_of_data,
                                              direction=TopBotType.top2bot,
                                              chan_types=self.stage_A_types,
                                              isdebug=self.isdebug,
                                              is_description=self.isDescription,
                                              is_anal=False,
                                              split_time=None,
                                              check_bi=False,
                                              allow_simple_zslx=False,
                                              force_zhongshu=False,
                                              check_full_zoushi=False,
                                              ignore_sub_xd=False)
        exhaustion_result = result and (xd_result or self.ignore_xd)
        
        g.stock_chan_type[stock] = [g.stock_chan_type[stock][0], g.stock_chan_type[stock][1]] +\
                                                                s_profile
        return exhaustion_result
    
    def check_stage_A_vol(self, stock, context):
        return self.check_daily_vol_money(stock, context)
    
    def check_stage_A_cur(self, stock, context):
        result = False
        zhongshu_changed = False
        
        result, xd_result, c_profile, sub_zhongshu_formed = check_stock_sub(stock,
                                              end_time=context.current_dt,
                                              periods=[self.periods[0]],
                                              count=self.num_of_data,
                                              direction=TopBotType.top2bot,
                                              chan_types=self.stage_A_types,
                                              isdebug=self.isdebug,
                                              is_description=self.isDescription,
                                              is_anal=False,
                                              split_time=None,
                                              check_bi=False,
                                              allow_simple_zslx=False,
                                              force_zhongshu=False,
                                              check_full_zoushi=False,
                                              ignore_sub_xd=False)
        exhaustion_result = result and (xd_result or self.ignore_xd)
        
        old_current_profile = g.stock_chan_type[stock][1]
        if len(g.stock_chan_type[stock]) > 1 and\
            old_current_profile[0] in self.stage_A_types:
            old_current_p = old_current_profile[2][0] if type(old_current_profile[2]) is list else old_current_profile[2]
            current_p = c_profile[0][2][0] if type(c_profile[0][2]) is list else c_profile[0][2]
            zhongshu_changed = current_p != old_current_p

        if c_profile[0][0] in self.stage_A_types and stock not in context.portfolio.positions.keys():
            g.stock_chan_type[stock] = [g.stock_chan_type[stock][0]] +\
                                                                    c_profile +\
                                            [(Chan_Type.INVALID,
                                               TopBotType.top2bot,
                                               0,
                                               0,
                                               0,
                                               None,
                                               context.current_dt, 
                                               )]# fit the results
        return exhaustion_result, zhongshu_changed
            

    def check_stage_A_full(self, stock, context):
        result = False
        zhongshu_changed = False
        
        exhaustion_result, profile, _ = check_stock_full(stock,
                                             end_time=context.current_dt,
                                             periods=self.periods,
                                             count=self.num_of_data,
                                             direction=TopBotType.top2bot, 
                                             current_chan_type=self.stage_A_types,
                                             sub_chan_type=[Chan_Type.I, 
                                                            Chan_Type.I_weak, 
                                                            Chan_Type.INVALID, 
                                                            Chan_Type.III_strong, 
                                                            Chan_Type.III_weak,
                                                            Chan_Type.III],
                                             isdebug=self.isdebug,
                                             is_description=self.isDescription,
                                             sub_force_zhongshu=self.sub_force_zhongshu, 
                                             sub_check_bi=self.bi_level_precision,
                                             use_sub_split=False,
                                             ignore_cur_xd=self.ignore_xd,
                                             ignore_sub_xd=self.bi_level_precision,
                                             enable_ac_opposite_direction=True)
        
        old_current_profile = g.stock_chan_type[stock][1]
        if len(g.stock_chan_type[stock]) > 1 and\
            old_current_profile[0] in self.stage_A_types:
            old_current_p = old_current_profile[2][0] if type(old_current_profile[2]) is list else old_current_profile[2]
            current_p = profile[0][2][0] if type(profile[0][2]) is list else profile[0][2]
            zhongshu_changed = current_p != old_current_p

        # only update cache when we don't hold it in pos
        if profile[0][0] in self.stage_A_types and stock not in context.portfolio.positions.keys():
            g.stock_chan_type[stock] = [g.stock_chan_type[stock][0]] + profile if len(profile) > 1 else\
                                            [g.stock_chan_type[stock][0]] + profile +\
                                                [(Chan_Type.INVALID,
                                               TopBotType.top2bot,
                                               0,
                                               0,
                                               0,
                                               None,
                                               context.current_dt, 
                                               )]
        
#         result = exhaustion_result and self.check_internal_vol_money(stock, context)
        
        return exhaustion_result, zhongshu_changed
            
    def check_structure_sub_only(self, stock, context):
        zhongshu_changed = False

        old_current_profile = g.stock_chan_type[stock][1]
        old_chan_type = old_current_profile[0]
        enable_ac_op_direction = old_chan_type == Chan_Type.III or old_chan_type == Chan_Type.III_strong

        splitTime = old_current_profile[5] if self.use_sub_split else None

        sub_exhausted, sub_xd_exhausted, sub_profile, zhongshu_completed = check_stock_sub(stock=stock, 
                                                                                end_time=context.current_dt, 
                                                                                periods=[self.periods[1]], 
                                                                                count=self.num_of_data, 
                                                                                direction=TopBotType.top2bot, 
                                                                                chan_types=self.sub_chan_type, 
                                                                                isdebug=self.isdebug, 
                                                                                is_description=self.isDescription,
                                                                                split_time=splitTime,
                                                                                check_bi=self.bi_level_precision,
                                                                                allow_simple_zslx=True,
                                                                                force_zhongshu=self.sub_force_zhongshu,
                                                                                force_bi_zhongshu=True,
                                                                                ignore_sub_xd=self.ignore_xd,
                                                                                check_full_zoushi=False, 
                                                                                enable_ac_opposite_direction=enable_ac_op_direction)
        
        if sub_profile:
            g.stock_chan_type[stock] = [g.stock_chan_type[stock][0], g.stock_chan_type[stock][1]] + sub_profile
        else:
            g.stock_chan_type[stock] = [g.stock_chan_type[stock][0], g.stock_chan_type[stock][1]] +\
                                            [(Chan_Type.INVALID,
                                               TopBotType.top2bot,
                                               0,
                                               0,
                                               0,
                                               None,
                                               context.current_dt, 
                                               )]

        return sub_exhausted and sub_xd_exhausted, zhongshu_changed
    
    def check_daily_boll_lower(self, stock, context):
        stock_data = get_bars(stock,
                               count=50,
                               end_dt=context.current_dt, 
                               unit='1d', # use super level
                               include_now=True, 
                               fields=('close', 'low', 'high'), 
                               fq_ref_date=context.current_dt.date(),
                               df=False)
        upper, middle, lower = talib.BBANDS(stock_data['close'], timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
#         print("stock: {0} \nupper {1}, \nmiddle {2}, \nlow {3}, \nhigh{4}".format(stock, 
#                                                                        upper[-2:], 
#                                                                        middle[-2:], 
#                                                                        lower[-2:],
#                                                                        stock_data['high'][-2:]))
        # consecutive below lower bounds or upper/lower shrink
#         return float_less(round(upper[-1]-middle[-1], 2), round(upper[-2]-middle[-2], 2)) or\
#                 (float_equal(round(upper[-1]-middle[-1], 2), round(upper[-2]-middle[-2], 2)) and\
#                  float_less(upper[-1], upper[-2])),\
#                  float_less(stock_data['close'][-1], middle[-1])
        return float_less(upper[-1], upper[-2]), float_less(stock_data['close'][-1], middle[-1])
    
    
    def check_stage_I(self, stock, context):
        result, zhongshu_changed = self.check_structure_sub_full(stock, context)
        return result, zhongshu_changed

    def check_structure_cur(self, stock, context, after_stage_III=False):
        zhongshu_changed=False
        cur_result, cur_xd_result, cur_profile = check_chan_by_type_exhaustion(stock,
                                                                      end_time=context.current_dt, 
                                                                      periods=[self.periods[0]], 
                                                                      count=self.num_of_data, 
                                                                      direction=TopBotType.top2bot,
                                                                      chan_type=self.stage_A_types if after_stage_III else self.current_chan_type, 
                                                                      isdebug=self.isdebug, 
                                                                      is_description=False,
                                                                      check_structure=True,
                                                                      check_full_zoushi=False,
                                                                      slope_only=False)
        result = cur_result and (cur_xd_result or self.ignore_xd)
        if result or after_stage_III:
            if len(g.stock_chan_type[stock]) > 1:
                old_current_profile = g.stock_chan_type[stock][1]
                if old_current_profile[0] in self.stage_A_types:
                    old_current_p = old_current_profile[2][0] if type(old_current_profile[2]) is list else old_current_profile[2]
                    current_p = cur_profile[0][2][0] if type(cur_profile[0][2]) is list else cur_profile[0][2]
                    zhongshu_changed = current_p != old_current_p
    
            g.stock_chan_type[stock] = [g.stock_chan_type[stock][0]] + cur_profile
            
        return result, zhongshu_changed

    def check_structure_sub_full(self, stock, context):
        zhongshu_changed = False

        old_current_profile = g.stock_chan_type[stock][1]
        old_chan_type = old_current_profile[0]
        enable_ac_op_direction = old_chan_type == Chan_Type.III or old_chan_type == Chan_Type.III_strong

        result, profile, _ = check_stock_full(stock,
                                             end_time=context.current_dt,
                                             periods=self.periods,
                                             count=self.num_of_data,
                                             direction=TopBotType.top2bot, 
                                             current_chan_type=self.current_chan_type,
                                             sub_chan_type=self.sub_chan_type,
                                             isdebug=self.isdebug,
                                             is_description=self.isDescription,
                                             sub_force_zhongshu=self.sub_force_zhongshu, 
                                             sub_check_bi=self.bi_level_precision,
                                             use_sub_split=self.use_sub_split,
                                             ignore_cur_xd=self.ignore_xd,
                                             ignore_sub_xd=self.bi_level_precision,
                                             enable_ac_opposite_direction=enable_ac_op_direction)
        
        old_price = old_current_profile[2][0] if type(old_current_profile[2]) is list else old_current_profile[2]
        new_price = profile[0][2][0] if type(profile[0][2]) is list else profile[0][2]
#             self.log.debug("stock {0}, zhongshu changed: {1} <-> {2}".format(stock, old_current_profile[2], profile[0][2]))
        zhongshu_changed = old_price != new_price
        

        if len(profile) > 1:
            g.stock_chan_type[stock] = [g.stock_chan_type[stock][0]] + profile
        else:
            g.stock_chan_type[stock] = [g.stock_chan_type[stock][0], g.stock_chan_type[stock][1]] +\
                                            [(Chan_Type.INVALID,
                                               TopBotType.top2bot,
                                               0,
                                               0,
                                               0,
                                               None,
                                               context.current_dt, 
                                               )]
        return result, zhongshu_changed
    
    def filter(self, context, data, stock_list):
        within_processing_time = True
        if context.current_dt.hour < self.long_hour_start:
            within_processing_time = False
        elif context.current_dt.hour == self.long_hour_start and context.current_dt.minute < self.long_min_start: # we should only try to long in the afternoon
            within_processing_time = False
        
        filter_stock_list = []
        if within_processing_time:
            stocks_in_place = set(context.portfolio.positions.keys()).union(self.tentative_stage_I).union(self.tentative_stage_II).union(self.tentative_stage_III).union(self.tentative_stage_A).union(self.tentative_stage_B)
            stock_list = [stock for stock in stock_list if stock not in stocks_in_place]
            stock_list = self.sort_by_sector_order(stock_list)
            
            for stock in stock_list:
                if self.halt_check_when_enough and (self.long_candidate_num <= len(self.tentative_stage_I)):
                    break

                if self.initial_stock_check(context, stock):
                    filter_stock_list.append(stock)
        
        self.log.info("newly qualified stocks: {0}".format(filter_stock_list))
        
        self.tentative_stage_I = self.tentative_stage_I.union(filter_stock_list)
        
        # other stages also follows time constrains
        # deal with all tentative stocks
        beichi_list, enhanced_list = self.check_tentative_stocks(context)
        self.g.enchanced_long_stocks = self.g.enchanced_long_stocks.union(enhanced_list)
        
        beichi_list, enhanced_list = list(beichi_list), list(enhanced_list)
        
        # sort by sectors again
        beichi_list = self.sort_by_sector_order(beichi_list) 
        
#         if not self.use_all_stocks_4_A:
            # relate to existing position profit result
#             enhanced_list = [stock for stock in enhanced_list if stock in self.g.all_return_stocks]
#             enhanced_list = self.filter_enhanced_stock_by_return(enhanced_list)
                
        self.g.all_pos_return_stocks = self.g.all_pos_return_stocks.difference(enhanced_list)
        self.g.all_neg_return_stocks = self.g.all_neg_return_stocks.difference(enhanced_list)
        
        
        self.log.info("\nStocks ready: Bei Chi: {0}, stage B: {1},\ntentative I: {2},\ntentative II: {3},\ntentative III:{4}, \ntentative A:{5} \ntentative B:{6}".format(
                                                                      beichi_list, 
                                                                      enhanced_list,
                                                                      self.tentative_stage_I,
                                                                      self.tentative_stage_II,
                                                                      self.tentative_stage_III,
                                                                      self.tentative_stage_A, 
                                                                      self.tentative_stage_B,))
        # prioritize old stocks
        return enhanced_list+beichi_list
    
    def initial_stock_check(self, context, stock):
        return self.check_internal_vol_money(stock, context)
    
    def filter_enhanced_stock_by_return(self, stocks):
        qualified_stocks = set()
        for stock in stocks:
            stock_chan_cur_type = g.stock_chan_type[stock][1][0]
            if stock in self.g.all_pos_return_stocks and stock_chan_cur_type in self.stage_A_pos_return_types:
                qualified_stocks.add(stock)
            if stock in self.g.all_neg_return_stocks and stock_chan_cur_type in self.stage_A_neg_return_types:
                qualified_stocks.add(stock)
        
        return list(qualified_stocks)

    def sort_by_sector_order(self, stock_list):
        # sort resulting stocks
        stock_industry_pair = [(stock, get_industry(stock)[stock]['sw_l2']['industry_code']) for stock in stock_list]
        
#         self.log.debug("before: {0}".format(stock_industry_pair))
        stock_industry_pair.sort(key=lambda tup: sort_by_sector_try(self.g.industry_sector_list, tup[1]))
#         self.log.debug("after: {0}".format(stock_industry_pair))
        
        return [pair[0] for pair in stock_industry_pair]

    def __str__(self):
        return "Chan Filter Params: {0} \n{1}".format(self.long_stock_num, self.sub_chan_type)

    def after_trading_end(self, context):
        holding_pos = context.portfolio.positions.keys()
        
        stored_stocks = list(g.stock_chan_type.keys())
        to_be_removed = [stock for stock in stored_stocks if (stock not in holding_pos and\
                                                              stock not in self.tentative_stage_I and\
                                                              stock not in self.tentative_stage_II and\
                                                              stock not in self.tentative_stage_III and\
                                                              stock not in self.tentative_stage_A and\
                                                              stock not in self.tentative_stage_B)]
        [g.stock_chan_type.pop(stock, None) for stock in to_be_removed]
        self.g.enchanced_long_stocks = self.g.enchanced_long_stocks.intersection(set(holding_pos))
        
        self.log.info("position chan info: {0}".format(g.stock_chan_type.keys()))

class Filter_Pair_Trading(Filter_stock_list):
    def __init__(self, params):
        Filter_stock_list.__init__(self, params)
        self.pair_period = params.get('pair_period', 250)
        self.pair_num_limit = params.get('pair_num_limit', 10)
        self.return_pair = params.get('return_pair', 1)
        self.period_frequency = params.get('period_frequency', 'M')    
        self.new_pair = []
        
    def update_params(self, context, params):
        self.period_frequency = params.get('period_frequency', 'M')        
        
    def filter(self, context, data, stock_list):
        self.log.info('配对筛股:\n' + join_list(["[%s]" % (show_stock(x)) for x in stock_list[-10:]], ' ', 10))
        self.log.info('总数: {0}'.format(len(stock_list)))
        if len(stock_list) < self.pair_num_limit:
            return []
        pto = PairTradingOls({'return_pair': self.return_pair})
        if self.g.isFirstNTradingDayOfPeriod(context, num_of_day=1, period=self.period_frequency) or not self.new_pair:    
            data_frame = history(self.pair_period, '1d', 'close', security_list=stock_list, df=True)
            self.new_pair = pto.get_top_pair(data_frame)
            if not self.new_pair:
                return []
            self.g.pair_zscore = pto.get_regression_ratio(data_frame, self.new_pair)
            self.log.info("pair stocks:{0}, pair_zscore: {1}".format(self.new_pair, self.g.pair_zscore))
        else:
            data_frame = history(self.pair_period, '1d', 'close', security_list=np.array(self.new_pair).flatten().tolist(), df=True)
            self.g.pair_zscore = pto.get_regression_ratio(data_frame, self.new_pair)
            self.log.info("pair stocks:{0}, pair_zscore: {1}".format(self.new_pair, self.g.pair_zscore))
        return np.array(self.new_pair).flatten().tolist()
        
    def __str__(self):
        return "配对交易选对股"    
    
class Filter_Rank_Sector(Early_Filter_stock_list):
    def __init__(self, params):
        Early_Filter_stock_list.__init__(self, params)
        self.strong_sector = params.get('strong_sector', False)
        self.sector_limit_pct = params.get('sector_limit_pct', 5)
        self.strength_threthold = params.get('strength_threthold', 4)
        self.isDaily = params.get('isDaily', False)
        self.useIntradayData = params.get('useIntradayData', False)
        self.useAvg = params.get('useAvg', True)
        self.avgPeriod = params.get('avgPeriod', 5)
        self.period_frequency = params.get('period_frequency', 'W')
        self.isWeighted = params.get('isWeighted', True)
        self.new_list = []
    
    def update_params(self, context, params):
        self.period_frequency = params.get('period_frequency', 'W')
        self.isWeighted = params.get('isWeighted', True)
    
    def filter(self, context, stock_list):
        return [stock for stock in stock_list if stock in self.new_list]

    def before_trading_start(self, context):
        if self.g.isFirstNTradingDayOfPeriod(context, num_of_day=1, period=self.period_frequency) or not self.new_list or self.isDaily:
            self.log.info("选取前 %s%% 板块" % str(self.sector_limit_pct))
            ss = SectorSelection(limit_pct=self.sector_limit_pct, 
                    isStrong=self.strong_sector, 
                    min_max_strength=self.strength_threthold, 
                    useIntradayData=self.useIntradayData,
                    useAvg=self.useAvg,
                    avgPeriod=self.avgPeriod,
                    isWeighted=self.isWeighted,
                    effective_date=context.previous_date)
            self.new_list = ss.processAllSectorStocks()
            
    def __str__(self):
        if self.strong_sector:
            return '强势板块股票 %s%% 阈值 %s' % (self.sector_limit_pct, self.strength_threthold)
        else:
            return '弱势板块股票 %s%% 阈值 %s' % (self.sector_limit_pct, self.strength_threthold)
    
class Filter_Industry_Sector(Early_Filter_stock_list):
    def __init__(self, params):
        Early_Filter_stock_list.__init__(self, params)
        self.strong_sector = params.get('strong_sector', False)
        self.sector_limit_pct = params.get('sector_limit_pct', 5)
        self.strength_threthold = params.get('strength_threthold', 4)
        self.isDaily = params.get('isDaily', False)
        self.useIntradayData = params.get('useIntradayData', False)
        self.useAvg = params.get('useAvg', True)
        self.avgPeriod = params.get('avgPeriod', 5)
        self.period_frequency = params.get('period_frequency', 'W')
        self.isWeighted = params.get('isWeighted', True)
        self.new_list = []
    
    def update_params(self, context, params):
        pass
    
    def filter(self, context, stock_list):
        # keep sector strength order
        return [stock for stock in self.new_list if stock in stock_list]

    def before_trading_start(self, context):
        if self.g.isFirstNTradingDayOfPeriod(context, num_of_day=1, period=self.period_frequency) or not self.new_list or self.isDaily:
            self.log.info("选取前 %s%% 板块" % str(self.sector_limit_pct))
            ss = SectorSelection(limit_pct=self.sector_limit_pct, 
                    isStrong=self.strong_sector, 
                    min_max_strength=self.strength_threthold, 
                    useIntradayData=self.useIntradayData,
                    useAvg=self.useAvg,
                    avgPeriod=self.avgPeriod,
                    isWeighted=self.isWeighted,
                    effective_date=context.previous_date)
            self.new_list = ss.processAllIndustrySectorStocks(isDisplay=False)
            self.g.industry_sector_list = ss.processAllIndustrySectors() # save sector order for later use
            self.log.info("saved industry list: {0}... (top TEN)".format(self.g.industry_sector_list[:10]))
            
    def __str__(self):
        if self.strong_sector:
            return '强势板块股票 %s%% 阈值 %s' % (self.sector_limit_pct, self.strength_threthold)
        else:
            return '弱势板块股票 %s%% 阈值 %s' % (self.sector_limit_pct, self.strength_threthold)

class Filter_Week_Day_Long_Pivot_Stocks(Filter_stock_list):
    def __init__(self, params):
        Filter_stock_list.__init__(self, params)
        self.monitor_levels = params.get('monitor_levels', ['5d','1d','60m'])
        self.enable_filter = params.get('enable_filter', True)
        self.period_frequency = params.get('period_frequency', 'W')
        
    def update_params(self, context, params):
        Filter_stock_list.update_params(self, context, params)
        self.enable_filter = params.get('enable_filter', True)
        self.period_frequency = params.get('period_frequency', 'W')
        
    def filter(self, context, data, stock_list):
        # 新选出票 + 过去一周选出票 + 过去一周强势票
        combined_list = list(set(stock_list + self.g.monitor_buy_list)) if self.enable_filter else stock_list
        # combined_list = ['002045.XSHE']
        # combined_list = list(set(stock_list))
        
        # update only on the first trading day of the week for 5d status
        if self.g.isFirstNTradingDayOfPeriod(context, num_of_day=1, period=self.period_frequency):
            self.log.info("本周第一个交易日, 更新周信息")
            if self.g.monitor_long_cm:
                self.g.monitor_long_cm = ChanMatrix(combined_list, isAnal=False)
                self.g.monitor_long_cm.gaugeStockList([self.monitor_levels[0]]) # 5d
            if self.g.monitor_short_cm:
                self.g.monitor_short_cm.gaugeStockList([self.monitor_levels[0]]) # 5d
        
        if not self.g.monitor_long_cm:
            self.g.monitor_long_cm = ChanMatrix(combined_list, isAnal=False)
            self.g.monitor_long_cm.gaugeStockList([self.monitor_levels[0]])
        if not self.g.monitor_short_cm: # only update if we have stocks in position
            self.g.monitor_short_cm = ChanMatrix(list(context.portfolio.positions.keys()), isAnal=False)
            self.g.monitor_short_cm.gaugeStockList([self.monitor_levels[0]])
    
        # update daily status
        self.g.monitor_short_cm.gaugeStockList([self.monitor_levels[1]]) # 1d
        self.g.monitor_long_cm.gaugeStockList([self.monitor_levels[1]])
        
        if not self.enable_filter:
            return combined_list
        
        monitor_list = self.matchStockForMonitor()
        monitor_list = self.removeStockForMonitor(monitor_list) # remove unqulified stocks
        monitor_list = list(set(monitor_list + self.g.head_stocks)) # add head stocks
        return monitor_list 

    def matchStockForMonitor(self):
        monitor_list = self.g.monitor_long_cm.filterDownTrendUpTrend(level_list=['5d','1d'], update_df=False)
        monitor_list += self.g.monitor_long_cm.filterUpNodeUpTrend(level_list=['5d','1d'], update_df=False)
        monitor_list += self.g.monitor_long_cm.filterDownNodeUpTrend(level_list=['5d','1d'], update_df=False)
        
        monitor_list += self.g.monitor_long_cm.filterDownNodeDownNode(level_list=['5d','1d'], update_df=False)
        monitor_list += self.g.monitor_long_cm.filterUpTrendDownNode(level_list=['5d','1d'], update_df=False)
        
        if g.port_pos_control == 1.0:
            monitor_list += self.g.monitor_long_cm.filterUpTrendUpTrend(level_list=['5d','1d'], update_df=False)
        monitor_list = list(set(monitor_list))
        return monitor_list
    
    def removeStockForMonitor(self, stockList): # remove any stocks turned (-1, 1) or  (1, 0) on 5d
        to_be_removed_from_monitor = self.g.monitor_long_cm.filterUpTrendDownTrend(stock_list=stockList, level_list=['5d','1d'], update_df=False)
        to_be_removed_from_monitor += self.g.monitor_long_cm.filterUpNodeDownTrend(level_list=['5d','1d'], update_df=False)
        to_be_removed_from_monitor += self.g.monitor_long_cm.filterDownNodeDownTrend(level_list=['5d','1d'], update_df=False)     
        to_be_removed_from_monitor += self.g.monitor_long_cm.filterDownTrendDownTrend(stock_list=stockList, level_list=['5d','1d'], update_df=False)
        
        # to_be_removed_from_monitor += self.g.monitor_long_cm.filterDownTrendUpNode(stock_list=stockList, level_list=['5d','1d'], update_df=False)
        to_be_removed_from_monitor += self.g.monitor_long_cm.filterUpNodeUpNode(stock_list=stockList, level_list=['5d','1d'], update_df=False)
        return [stock for stock in stockList if stock not in to_be_removed_from_monitor]

    def __str__(self):
        return '周线日线级别买点位置过滤'

#######################################################
class Filter_Herd_head_stocks(Filter_stock_list):
    def __init__(self, params):
        Filter_stock_list.__init__(self, params)
        self.gainThre = params.get('gainThre', 0.05)
        self.count = params.get('count', 20)
        self.intraday = params.get('useIntraday', False)
        self.intraday_period = params.get('intraday_period', '230m')
        self.filter_out = params.get('filter_out', True) # 0 for filter out

    def filter(self, context, data, stock_list):
        head_stocks = []
        industry, concept = self.g.filtered_sectors
        hh = HerdHead({'gainThre':self.gainThre, 'count':self.count, 'useIntraday':self.intraday, 'intraday_period':self.intraday_period})
        for gn in concept:
            stockList = hh.findLeadStock(index=gn, isConcept=True, method=2)
            if stockList:
                head_stocks += stockList
        for ind in industry:
            stockList = hh.findLeadStock(index=ind, isConcept=False, method=2)
            if stockList:
                head_stocks += stockList
        self.g.head_stocks = list(set([stock for stock in head_stocks if stock in stock_list]))
        self.log.info('强势票:'+','.join([get_security_info(stock).display_name for stock in self.g.head_stocks]))
        if self.filter_out:
            stock_list = [stock for stock in stock_list if stock not in self.g.head_stocks]
            self.log.info('强势票排除:{0}'.format(self.filter_out))
        return stock_list
    
    def after_trading_end(self, context):
        self.g.head_stocks = []
        
    def __str__(self):
        return '强势股票筛选特例加入每日待选'
#######################################################

# '''------------------创业板过滤器-----------------'''
class Filter_gem(Early_Filter_stock_list):
    def filter(self, context, stock_list):
        self.log.info("过滤创业板股票")
        return [stock for stock in stock_list if stock[0:3] != '300']

    def __str__(self):
        return '过滤创业板股票'


class Filter_common(Filter_stock_list):
    def __init__(self, params):
        self.filters = params.get('filters', ['st', 'high_limit', 'low_limit', 'pause','ban'])

    def set_feasible_stocks(self, initial_stocks, current_data):
        # 判断初始股票池的股票是否停牌，返回list
        paused_info = []
        
        for i in initial_stocks:
            paused_info.append(current_data[i].paused)
        df_paused_info = pd.DataFrame({'paused_info':paused_info},index = initial_stocks)
        unsuspened_stocks =list(df_paused_info.index[df_paused_info.paused_info == False])
        return unsuspened_stocks

    def filter(self, context, data, stock_list):
#         print("before filter list: {0}".format(stock_list))
        current_data = get_current_data()
        
        # filter out paused stocks
        stock_list = self.set_feasible_stocks(stock_list, current_data)
        
        if 'st' in self.filters:
            stock_list = [stock for stock in stock_list
                          if not current_data[stock].is_st
                          and 'ST' not in current_data[stock].name
                          and '*' not in current_data[stock].name
                          and '退' not in current_data[stock].name]
        try:
            if 'high_limit' in self.filters:
                stock_list = [stock for stock in stock_list if stock in context.portfolio.positions.keys()
                              or current_data[stock].last_price < current_data[stock].high_limit]
            if 'low_limit' in self.filters:
                stock_list = [stock for stock in stock_list if stock in context.portfolio.positions.keys()
                              or current_data[stock].last_price > current_data[stock].low_limit]
        except Exception as e:
            self.log.error(str(e))
            
        if 'pause' in self.filters:
            stock_list = [stock for stock in stock_list if not current_data[stock].paused]
            
        try:
            if 'ban' in self.filters:
                ban_shares = self.get_ban_shares(context)
                stock_list = [stock for stock in stock_list if stock[:6] not in ban_shares]
        except Exception as e:
            self.log.error(str(e))
        
        self.log.info("选股过滤（显示前五）:\n{0}, total: {1}".format(join_list(["[%s]" % (show_stock(x)) for x in stock_list[:5]], ' ', 10), len(stock_list)))
        return stock_list

    #获取解禁股列表
    def get_ban_shares(self, context):
        curr_year = context.current_dt.year
        curr_month = context.current_dt.month
        jj_range = [((curr_year*12+curr_month+i-1)/12,curr_year*12+curr_month+i-(curr_year*12+curr_month+i-1)/12*12) for i in range(-1,1)] #range 可指定解禁股的时间范围，单位为月
        df_jj = reduce(lambda x,y:pd.concat([x,y],axis=0), [ts.xsg_data(year=y, month=m) for (y,m) in jj_range])
        return df_jj.code.values

    def update_params(self, context, params):
        self.filters = params.get('filters', ['st', 'high_limit', 'low_limit', 'pause']) # ,'ban'

    def __str__(self):
        return '一般性股票过滤器:%s' % (str(self.filters))
