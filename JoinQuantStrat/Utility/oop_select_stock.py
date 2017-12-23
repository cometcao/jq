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


'''=========================选股规则相关==================================='''

# '''-----------------选股组合器2-----------------------'''
class Pick_stocks2(Group_rules):
    def __init__(self, params):
        Group_rules.__init__(self, params)
        self.has_run = False

    def handle_data(self, context, data):
        try:
            to_run_one = self._params.get('day_only_run_one', False)
        except:
            to_run_one = False
        if to_run_one and self.has_run:
            # self.log.info('设置一天只选一次，跳过选股。')
            return

        # q = None
        # for rule in self.rules:
        #     if isinstance(rule, Filter_query):
        #         q = rule.filter(context, data, q)
        # stock_list = list(get_fundamentals(q)['code']) if q != None else []
        stock_list = []

        for rule in self.rules:
            if isinstance(rule, Create_stock_list):
                stock_list += rule.filter(context, data)
                
        if stock_list:
            self.g.buy_stocks = stock_list
        else:
            stock_list = self.g.buy_stocks

        for rule in self.rules:
            if isinstance(rule, Filter_stock_list):
                stock_list = rule.filter(context, data, stock_list)
    
        self.g.monitor_buy_list = stock_list

        self.log.info('今日选股:\n' + join_list(["[%s]" % (show_stock(x)) for x in stock_list], ' ', 10))
        self.has_run = True

    def before_trading_start(self, context):
        self.has_run = False

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

class Filter_financial_data2(Filter_stock_list):
    def normal_filter(self, context, data, stock_list):
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
        # print get_fundamentals(q)
        stock_list = list(get_fundamentals(q)['code'])
        return stock_list    
    
    def filter_by_sector(self, context, data):
        final_list = []
        threthold_limit = self._params.get('limit', None)
        industry_sectors, concept_sectors = self.g.filtered_sectors
        total_sector_num = len(industry_sectors) + len(concept_sectors)
        limit_num = threthold_limit/total_sector_num if threthold_limit is not None else 3
        for sector in industry_sectors:
            stock_list = get_industry_stocks(sector)
            stock_list = self.normal_filter(context, data, stock_list)
            final_list += stock_list[:limit_num]
        
        for con in concept_sectors:
            stock_list = get_concept_stocks(con)
            stock_list = self.normal_filter(context, data, stock_list)
            final_list += stock_list[:limit_num]
        return final_list
    
    def filter(self, context, data, stock_list):
        if self._params.get('by_sector', False):
            return self.filter_by_sector(context, data)
        else:
            return self.normal_filter(context, data, stock_list)

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


class Filter_FX_data(Filter_stock_list):
    def __init__(self, params):
        self.limit = params.get('limit', 100)
        self.quantlib = quantlib()
        self.value_factor = value_factor_lib()
    
    def filter(self, context, data, stock_list):
        import datetime as dt
        statsDate = context.current_dt.date() - dt.timedelta(1)
        #获取坏股票列表，将会剔除
        bad_stock_list = self.quantlib.fun_get_bad_stock_list(statsDate)
        # 低估值策略
        fx_stock_list = self.value_factor.fun_get_stock_list(context, self.limit, statsDate, bad_stock_list)
        return [stock for stock in fx_stock_list if stock in stock_list]
        
    def __str__(self):
        return '小佛雪选股 选取:%s' % self.limit

# 根据财务数据对Stock_list进行过滤。返回符合条件的stock_list
class Filter_financial_data(Filter_stock_list):
    def filter(self, context, data, stock_list):
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
        
    def filter(self, context, data):
        # new_list = ['002714.XSHE', '603159.XSHG', '603703.XSHG','000001.XSHE','000002.XSHE','600309.XSHG','002230.XSHE','600392.XSHG','600291.XSHG']
        new_list=[]
        if self.g.isFirstTradingDayOfWeek(context) or not self.g.buy_stocks or self.isDaily:
            self.log.info("选取前 %s%% 板块" % str(self.sector_limit_pct))
            ss = SectorSelection(limit_pct=self.sector_limit_pct, 
                    isStrong=self.strong_sector, 
                    min_max_strength=self.strength_threthold, 
                    useIntradayData=self.useIntradayData,
                    useAvg=self.useAvg,
                    avgPeriod=self.avgPeriod)
            new_list = ss.processAllSectorStocks()
            self.g.filtered_sectors = ss.processAllSectors()
        return new_list 
    
    def before_trading_start(context):
        pass
    
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
        
    def update_params(self, context, params):
        Filter_stock_list.update_params(self, context, params)
        self.enable_filter = params.get('enable_filter', True)
        
    def filter(self, context, data, stock_list):
        # 新选出票 + 过去一周选出票 + 过去一周强势票
        combined_list = list(set(stock_list + self.g.monitor_buy_list)) if self.enable_filter else stock_list
        # combined_list = ['002045.XSHE']
        # combined_list = list(set(stock_list))
        
        # update only on the first trading day of the week for 5d status
        if self.g.isFirstTradingDayOfWeek(context):
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
            self.g.monitor_short_cm = ChanMatrix(context.portfolio.positions.keys(), isAnal=False)
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
class Filter_gem(Filter_stock_list):
    def filter(self, context, data, stock_list):
        self.log.info("过滤创业板股票")
        return [stock for stock in stock_list if stock[0:3] != '300']

    def __str__(self):
        return '过滤创业板股票'


class Filter_common(Filter_stock_list):
    def __init__(self, params):
        self.filters = params.get('filters', ['st', 'high_limit', 'low_limit', 'pause','ban'])

    def filter(self, context, data, stock_list):
        current_data = get_current_data()
        if 'st' in self.filters:
            stock_list = [stock for stock in stock_list
                          if not current_data[stock].is_st
                          and 'ST' not in current_data[stock].name
                          and '*' not in current_data[stock].name
                          and '退' not in current_data[stock].name]
        try:
            if 'high_limit' in self.filters:
                stock_list = [stock for stock in stock_list if stock in context.portfolio.positions.keys()
                              or data[stock].close < data[stock].high_limit]
            if 'low_limit' in self.filters:
                stock_list = [stock for stock in stock_list if stock in context.portfolio.positions.keys()
                              or data[stock].close > data[stock].low_limit]
        except:
            pass
        if 'pause' in self.filters:
            stock_list = [stock for stock in stock_list if not current_data[stock].paused]
            
        if 'ban' in self.filters:
            ban_shares = self.get_ban_shares(context)
            stock_list = [stock for stock in stock_list if stock[:6] not in ban_shares]
        return stock_list

    #获取解禁股列表
    def get_ban_shares(self, context):
        curr_year = context.current_dt.year
        curr_month = context.current_dt.month
        jj_range = [((curr_year*12+curr_month+i-1)/12,curr_year*12+curr_month+i-(curr_year*12+curr_month+i-1)/12*12) for i in range(-1,1)] #range 可指定解禁股的时间范围，单位为月
        df_jj = reduce(lambda x,y:pd.concat([x,y],axis=0), [ts.xsg_data(year=y, month=m) for (y,m) in jj_range])
        return df_jj.code.values

    def update_params(self, context, params):
        self.filters = params.get('filters', ['st', 'high_limit', 'low_limit', 'pause','ban'])

    def __str__(self):
        return '一般性股票过滤器:%s' % (str(self.filters))
