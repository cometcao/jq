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
from ml_factor_rank import *
from dynamic_factor_based_stock_ranking import *
from pair_trading_ols import *
from value_factor_lib import *
from quant_lib import *
from functools import reduce
from chan_common_include import Chan_Type, float_less_equal, float_more_equal
from biaoLiStatus import TopBotType
from chan_kbar_filter import *
from equilibrium import *


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
        self.add_etf = params.get('add_etf', True)

    def update_params(self, context, params):
        self.file_path = params.get('write_to_file', None)
        self.add_etf = params.get('add_etf', True)

    def handle_data(self, context, data):
        try:
            to_run_one = self._params.get('day_only_run_one', False)
        except:
            to_run_one = False
        if to_run_one and self.has_run:
            # self.log.info('设置一天只选一次，跳过选股。')
            return

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


class Filter_FX_data(Early_Filter_stock_list):
    def __init__(self, params):
        self.limit = params.get('limit', 100)
        self.quantlib = quantlib()
        self.value_factor = value_factor_lib()
    
    def filter(self, context, stock_list):
#         import datetime as dt
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
                self.g.stock_chan_type[stock] = chan_profile
        if self.is_debug:
            print(str(self.g.stock_chan_type))
        return list(self.g.stock_chan_type.keys())
    
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
        self.factor_category = params.get('factor_category', ['basics'])
        self.is_debug = params.get('is_debug', False)
        self.regress_profit = params.get('regress_profit', False)
        pass
    
    def update_params(self, context, params):
        self.use_enhanced = params.get('use_enhanced', False)      
        self.factor_category = params.get('factor_category', ['basics'])
        self.is_debug = params.get('is_debug', False)
        self.regress_profit = params.get('regress_profit', False)
    
    def before_trading_start(self, context):
        if self.use_enhanced:
            mdfr = ML_Dynamic_Factor_Rank({'stock_num':self.stock_num, 
                                  'index_scope':self.index_scope,
                                  'period':'month_3',
                                  'is_debug':self.is_debug, 
                                  'use_dynamic_factors': True, 
                                  'context': context, 
                                  'regress_profit': self.regress_profit,
                                  'factor_category':self.factor_category})
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
    
class Pick_stock_from_file_chan(Pick_Chan_Stocks):
    '''
    take data from preprocessed file based on chan rule
    '''
    def __init__(self, params):
        Pick_Chan_Stocks.__init__(self, params)
        self.filename = params.get('filename', None)
        self.current_chan_types = params.get('current_chan_types', [Chan_Type.I, Chan_Type.III, Chan_Type.INVALID])
        self.top_chan_types = params.get('top_chan_types', [Chan_Type.I, Chan_Type.INVALID])
        self.enable_on_demand = params.get('on_demand', False)
        self.isdebug = params.get('isdebug', False)
        
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
                
                chan_stock_list.append(stock)
                if stock not in self.g.stock_chan_type:
                    self.g.stock_chan_type[stock] = [(Chan_Type.value2type(top_type_value), 
                                                      TopBotType.top2bot,
                                                      0, 
                                                      0,
                                                      0,
                                                      None,
                                                      None)]
            self.log.info("filtered data read from file: {0} stocks info".format(len(chan_stock_list)))
        return chan_stock_list
    
    def __str__(self):
        return "从文件中读取根据缠论已经写好的股票列表以及数据"

        
class Filter_Chan_Stocks(Filter_stock_list):
    def __init__(self, params):
        Filter_stock_list.__init__(self, params)
        self.isdebug = params.get('isdebug', False)
        self.isDescription= params.get('isDescription', False)
        self.long_stock_num = params.get('long_stock_num', 0)
        self.sup_chan_type = params.get('sup_chan_type', [Chan_Type.I, Chan_Type.INVALID])
        self.curent_chan_type = params.get('current_chan_type', [Chan_Type.I])
        self.sub_chan_type = params.get('sub_chan_type', [Chan_Type.INVALID, Chan_Type.I])
        self.periods = params.get('periods', ['5m', '1m'])
        self.num_of_data = params.get('num_of_data', 2500)
        self.sub_force_zhongshu = params.get('sub_force_zhongshu', True)
        self.bi_level_precision = params.get('bi_level_precision', True)
        self.long_hour_start = params.get('long_hour_start', 13)
        self.long_min_start = params.get('long_min_start', 30)
        self.use_sub_split = params.get('sub_split', True)
        self.ignore_xd = params.get('ignore_xd', False)
        self.use_stage_II = params.get('use_stage_II', False)
        
        self.force_chan_type = params.get('force_chan_type', [
                                                              [Chan_Type.I, self.curent_chan_type[0], Chan_Type.I],
                                                              [Chan_Type.I_weak, self.curent_chan_type[0], Chan_Type.I],
                                                              [Chan_Type.INVALID, self.curent_chan_type[0], Chan_Type.I]
                                                              ])
        self.tentative_chan_type = params.get('tentative_chan_type', [
                                    [Chan_Type.I, self.curent_chan_type[0], Chan_Type.I],
                                    [Chan_Type.I_weak, self.curent_chan_type[0], Chan_Type.I],
                                    [Chan_Type.INVALID, self.curent_chan_type[0], Chan_Type.I]
                                    ])
        self.tentative_stage_I = set() # list to hold stocks waiting to be operated
        self.tentative_stage_II = set()
        self.halt_check_when_enough = params.get('halt_check_when_enough', True)
        
    def check_tentative_stocks(self, context):
        stocks_to_long = set()
#         stock_changed_record = {}
        stocks_to_remove = set()
        
        self.tentative_stage_I = self.tentative_stage_I.difference(set(context.portfolio.positions.keys()))
        
        for stock in self.tentative_stage_I:
            result, xd_result, c_profile = check_chan_by_type_exhaustion(stock,
                                                                  end_time=context.current_dt,
                                                                  periods=[self.periods[0]],
                                                                  count=4800,
                                                                  direction=TopBotType.top2bot,
                                                                  chan_type=self.curent_chan_type,
                                                                  isdebug=False,
                                                                  is_description =False,
                                                                  is_anal=False,
                                                                  check_structure=True,
                                                                  check_full_zoushi=False,
                                                                  slope_only=False) # synch with selection
            if not result:
                self.log.info("Bei Chi long point broken for stock: {0}".format(stock))
                stocks_to_remove.add(stock)
            elif not sanity_check(stock, c_profile, context.current_dt, self.periods[0], TopBotType.top2bot):
                self.log.info("Sanity check failed for stock: {0}".format(stock))
                stocks_to_remove.add(stock)
            else:
                old_current_profile = self.g.stock_chan_type[stock][1]
#                 stock_changed_record[stock] = old_current_profile[2] != c_profile[0][2]
#                 self.log.debug("stock {0}, zhongshu changed: {1}".format(stock, old_current_profile[2] != c_profile[0][2]))
                self.g.stock_chan_type[stock] = [(Chan_Type.I, 
                                                  TopBotType.top2bot,
                                                  0, 
                                                  0,
                                                  0,
                                                  None,
                                                  None)] +\
                                                c_profile +\
                                                [(Chan_Type.I, 
                                                  TopBotType.top2bot,
                                                  0, 
                                                  0,
                                                  0,
                                                  None,
                                                  context.current_dt)]
        self.tentative_stage_I = self.tentative_stage_I.difference(stocks_to_remove)
        
        # check volume/money
        for stock in self.tentative_stage_I:
            if self.check_vol_money(stock, context):
                stocks_to_long.add(stock)
        
        if self.use_stage_II:
            self.tentative_stage_II = stocks_to_long
            stocks_to_long = set()
            self.tentative_stage_I = self.tentative_stage_I.difference(self.tentative_stage_II)
        
            # check type III
            self.tentative_stage_II = self.tentative_stage_II.difference(set(context.portfolio.positions.keys()))
                    
            for stock in self.tentative_stage_II:
                if self.check_type_III_sub(stock, context):
                    stocks_to_long.add(stock)
                    
            self.tentative_stage_II = self.tentative_stage_II.difference(stocks_to_long)
                
        return stocks_to_long
        
    def check_vol_money(self, stock, context):
        current_profile = self.g.stock_chan_type[stock][1]
        current_zoushi_start_time = current_profile[5]

        stock_data = get_bars(stock, 
                            count=2000, # 5d
                            unit=self.periods[0],
                            fields=['date','money'],
                            include_now=True, 
                            end_dt=context.current_dt, 
                            fq_ref_date=context.current_dt.date(), 
                            df=False)
        
#         if not stock_changed_record[stock]: # Zhongshu unchanged
        cutting_loc = np.where(stock_data['date']>=current_zoushi_start_time)[0][0]
        cutting_offset = stock_data.size - cutting_loc
#             
#     #         # current zslx money compare to zs money
        cur_latest_money = sum(stock_data['money'][cutting_loc:])
        cur_past_money = sum(stock_data['money'][:cutting_loc][-cutting_offset:])
# 
#         # current zslx money split by mid term
        sub_latest_money = sum(stock_data['money'][cutting_loc:][-int(cutting_offset/2):])
        sub_past_money = sum(stock_data['money'][cutting_loc:][:int(cutting_offset/2)])
        
#         cur_latest_money = sum(stock_data['money'][-120:])
#         cur_past_money = sum(stock_data['money'][-240:][:120])
#         cur_latest_money = sum(stock_data['money'][-48:])
#         cur_past_money = sum(stock_data['money'][:48])

#         self.log.debug("candiate stock {0} cur: {1} -> {2}, sub: {3} -> {4}".format(stock, 
#                                                                            cur_past_money, 
#                                                                            cur_latest_money,
#                                                                            sub_past_money, 
#                                                                            sub_latest_money))

        if float_less_equal(cur_latest_money / cur_past_money, 0.809) and\
            float_less_equal(sub_latest_money / sub_past_money, 0.809):
            self.log.info("candiate stock {0} cur money active: {1} -> {2}, sub money active: {3} -> {4}".format(stock, 
                                                                               cur_past_money, 
                                                                               cur_latest_money,
                                                                               sub_past_money, 
                                                                               sub_latest_money))
            return True
        elif float_more_equal(cur_latest_money / cur_past_money, 1.809) and\
            float_less_equal(sub_latest_money / sub_past_money, 0.809):
            self.log.info("candiate stock {0} cur money active: {1} -> {2}, sub money active: {3} -> {4}".format(stock, 
                                                                               cur_past_money, 
                                                                               cur_latest_money,
                                                                               sub_past_money, 
                                                                               sub_latest_money))        
            return True
        return False
    
    def check_type_III_sub(self, stock, context):
        if context.current_dt.hour != 14 or context.current_dt.minute != 30:
            return False
#         exhausted, _, _, _ = check_stock_sub(stock, 
#                                         end_time=context.current_dt,
#                                         periods=[self.periods[1]], 
#                                         count=1000, 
#                                         direction=TopBotType.top2bot, 
#                                         chan_types=[Chan_Type.III, Chan_Type.III_weak, Chan_Type.III_strong], 
#                                         isdebug=self.isdebug, 
#                                         is_anal=False, 
#                                         split_time=None,
#                                         check_bi=False,
#                                         force_zhongshu=False,
#                                         force_bi_zhongshu=False,
#                                         check_full_zoushi=False
#                                         )
#         return exhausted
        check_num = 10
        stock_data = get_bars(stock, 
                            count=check_num, # 5d
                            unit='1d',
                            fields=['date','close', 'high', 'low', 'open'],
                            include_now=True, 
                            end_dt=context.current_dt, 
                            fq_ref_date=context.current_dt.date(), 
                            df=False)
        
        min_loc = stock_data['low'].argmin()
        if min_loc < check_num-2 and min_loc > 0:
            pre = stock_data[min_loc-1]
            first = stock_data[min_loc]
            second = stock_data[min_loc+1]
            last = stock_data[-1]
            
            pre_oc_high = max(pre['open'], pre['close'])
            first_oc_high = max(first['open'], first['close'])
            second_oc_high = max(second['open'], second['close'])
            min_bar = min(pre_oc_high, first_oc_high, second_oc_high)
            
            if last['close'] > min_bar: 
                return True
        return False
        
    
    def filter(self, context, data, stock_list):
        within_processing_time = True
        if context.current_dt.hour < self.long_hour_start:
            within_processing_time = False
        elif context.current_dt.hour == self.long_hour_start and context.current_dt.minute < self.long_min_start: # we should only try to long in the afternoon
            within_processing_time = False
        
        filter_stock_list = []
        if within_processing_time:
            if len(context.portfolio.positions) == self.long_stock_num != 0:
                return filter_stock_list
            stock_list = [stock for stock in stock_list if stock not in context.portfolio.positions.keys()]
            stock_list = self.sort_by_sector_order(stock_list)
            for stock in stock_list:
                if self.halt_check_when_enough and self.long_stock_num <= len(filter_stock_list):
                    # we don't need to look further, we have enough candidates for long position + 1 backup
                    break
                result, profile, _ = check_stock_full(stock,
                                                     end_time=context.current_dt,
                                                     periods=self.periods,
                                                     count=self.num_of_data,
                                                     direction=TopBotType.top2bot, 
                                                     current_chan_type=self.curent_chan_type,
                                                     sub_chan_type=self.sub_chan_type,
                                                     isdebug=self.isdebug,
                                                     is_description=self.isDescription,
                                                     sub_force_zhongshu=self.sub_force_zhongshu, 
                                                     sub_check_bi=self.bi_level_precision,
                                                     use_sub_split=self.use_sub_split,
                                                     ignore_cur_xd=self.ignore_xd,
                                                     ignore_sub_xd=self.bi_level_precision)
                
                if result:
                    filter_stock_list.append(stock)
                    self.g.stock_chan_type[stock] = self.g.stock_chan_type[stock] + profile
            
            
            self.log.info("Qualified stocks: {0}".format(filter_stock_list))
            to_ignore = set()
            
            # deal with tentative stocks
            for stock in filter_stock_list:
                top_profile = self.g.stock_chan_type[stock][0]
                current_profile = self.g.stock_chan_type[stock][1]
                sub_profile = self.g.stock_chan_type[stock][2]
                
                top_chan_t = top_profile[0]
                cur_chan_t = current_profile[0]
                sub_chan_t = sub_profile[0]
                
                chan_type_list = [top_chan_t, cur_chan_t, sub_chan_t]
                if self.force_chan_type and (chan_type_list not in self.force_chan_type):
    #                 self.log.debug("{0} chan type: {1} ignored".format(stock, chan_type_list))
                    to_ignore.add(stock)
                    continue
                
                if self.tentative_chan_type and (chan_type_list in self.tentative_chan_type):
    #                 self.log.info("stock {0} saved in tentative!".format(stock))
                    self.tentative_stage_I.add(stock)
            
            self.log.info("Stocks {0} ignored".format(to_ignore))
            filter_stock_list = [stock for stock in filter_stock_list if stock not in to_ignore]
            filter_stock_list = [stock for stock in filter_stock_list if stock not in self.tentative_stage_I and stock not in self.tentative_stage_II]
        
        # deal with all tentative stocks
        filter_stock_list = list(self.check_tentative_stocks(context)) + filter_stock_list
        
        # sort by sectors again
        filter_stock_list = self.sort_by_sector_order(filter_stock_list)
                
        self.log.info("Stocks ready: {0}, tentative: {1}, {2}".format(filter_stock_list, 
                                                                      self.tentative_stage_I,
                                                                      self.tentative_stage_II))
        return filter_stock_list

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
        stored_stocks = list(self.g.stock_chan_type.keys())
        to_be_removed = [stock for stock in stored_stocks if (stock not in holding_pos and stock not in self.tentative_stage_I and stock not in self.tentative_stage_II)]
        [self.g.stock_chan_type.pop(stock, None) for stock in to_be_removed]
        self.log.info("position chan info: {0}".format(self.g.stock_chan_type))

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
            self.new_list = ss.processAllIndustrySectorStocks()
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
