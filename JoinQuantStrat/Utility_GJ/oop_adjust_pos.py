# -*- encoding: utf8 -*-
'''
Created on 4 Dec 2017

@author: MetalInvest
'''
from common_include import *
from ta_analysis import *
from oop_strategy_frame import *
from position_control_analysis import *
from rsrs_timing import *
from chan_common_include import Chan_Type, float_more_equal, GOLDEN_RATIO, float_less_equal, float_equal
from equilibrium import check_chan_indepth, check_stock_sub, check_chan_by_type_exhaustion, check_stock_full, sanity_check
from biaoLiStatus import TopBotType
from kBar_Chan import *
import json
import talib

'''==================================调仓条件相关规则========================================='''


# '''===========带权重的退出判断基类==========='''
class Weight_Base(Rule):
    @property
    def weight(self):
        return self._params.get('weight', 1)


# '''-------------------------调仓时间控制器-----------------------'''
class Time_condition(Weight_Base):
    def __init__(self, params):
        Weight_Base.__init__(self, params)
        # 配置调仓时间 times为二维数组，示例[[10,30],[14,30]] 表示 10:30和14：30分调仓
        self.times = params.get('times', [])

    def update_params(self, context, params):
        Weight_Base.update_params(self, context, params)
        self.times = params.get('times', self.times)
        pass

    def handle_data(self, context, data):
        hour = context.current_dt.hour
        minute = context.current_dt.minute
        self.is_to_return = not [hour, minute] in self.times
        pass

    def __str__(self):
        return '调仓时间控制器: [调仓时间: %s ]' % (
            str(['%d:%d' % (x[0], x[1]) for x in self.times]))


# '''-------------------------调仓日计数器-----------------------'''
class Period_condition(Weight_Base):
    def __init__(self, params):
        Weight_Base.__init__(self, params)
        # 调仓日计数器，单位：日
        self.period = params.get('period', 3)
        self.on_clear_wait_days = params.get('clear_wait', 2)
        self.day_count = 0
        self.mark_today = {}

    def update_params(self, context, params):
        Weight_Base.update_params(self, context, params)
#         self.on_clear_wait_days = params.get('clear_wait', 2)
#         self.mark_today = {}
        pass

    def handle_data(self, context, data):
        self.is_to_return = self.day_count < 0 or\
                            self.day_count % self.period != 0 or\
                            (self.mark_today[context.current_dt.date()] if context.current_dt.date() in self.mark_today else False)
        
        if context.current_dt.date() not in self.mark_today: # only increment once per day
            self.log.info("调仓日计数 [%d]" % (self.day_count))
            self.mark_today[context.current_dt.date()]=self.is_to_return
            self.day_count += 1
        pass

    def on_sell_stock(self, position, order, is_normal, pindex=0,context=None):
        if not is_normal:
            # 个股止损止盈时，即非正常卖股时，重置计数，原策略是这么写的
            self.day_count = 0
            self.mark_today = {}
        pass

    # 清仓时调用的函数
    def on_clear_position(self, context, new_pindexs=[0]):
        self.day_count = 0
        self.mark_today = {}
        if self.g.curve_protect or self.on_clear_wait_days > 0:
            self.day_count = -self.on_clear_wait_days
            self.g.curve_protect = False
        pass

    def __str__(self):
        return '调仓日计数器:[调仓频率: %d日] [调仓日计数 %d] [清仓等待: %d日]' % (self.period, self.day_count, self.on_clear_wait_days)


'''===================================调仓相关============================'''

# '''---------------卖出股票规则--------------'''
class Sell_stocks(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        
    def handle_data(self, context, data):
        to_sell = []
        self.g.monitor_buy_list = [stock for stock in self.g.monitor_buy_list if stock not in to_sell]        
        self.adjust(context, data, self.g.monitor_buy_list)

    def adjust(self, context, data, buy_stocks):
        # 卖出不在待买股票列表中的股票
        # 对于因停牌等原因没有卖出的股票则继续持有
        for stock in context.portfolio.positions.keys():
            if stock not in buy_stocks:
                position = context.portfolio.positions[stock]
                self.g.close_position(self, position, True)
                    
    def recordTrade(self, stock_list):
        pass

    def __str__(self):
        return '股票调仓卖出规则：卖出不在buy_stocks的股票'


# '''---------------买入股票规则--------------'''
class Buy_stocks(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        self.buy_count = params.get('buy_count', 3)
        self.to_buy = []

    def update_params(self, context, params):
        Rule.update_params(self, context, params)
        self.buy_count = params.get('buy_count', self.buy_count)

    def handle_data(self, context, data):
        if self.is_to_return:
            self.log_warn('无法执行买入!! self.is_to_return 未开启')
            return
        self.to_buy = self.g.monitor_buy_list
        self.log.info("待选股票: "+join_list([show_stock(stock) for stock in self.to_buy], ' ', 10))
        
        if self.buy_count > len(context.portfolio.positions):
            cash_value = context.portfolio.cash
            cash_avg = cash_value / (self.buy_count - len(context.portfolio.positions.keys()))
            value_avg = context.portfolio.portfolio_value / self.buy_count
            
            if cash_avg / value_avg - 1 > 0.191:
                self.log.info("rebalance positions")
                self.adjust_avg(context, data, self.to_buy)
            else:
                self.adjust(context, data, self.to_buy)
        
    def adjust(self, context, data, buy_stocks):
        # 买入股票
        # 始终保持持仓数目为g.buy_stock_count
        # 根据股票数量分仓
        # 此处只根据可用金额平均分配购买，不能保证每个仓位平均分配
        position_count = len(context.portfolio.positions)
        if self.buy_count > position_count:
            value = context.portfolio.cash / (self.buy_count - position_count)
            for stock in buy_stocks:
                if stock in self.g.sell_stocks:
                    continue
                if stock not in context.portfolio.positions.keys():
                    if self.g.open_position(self, stock, value):
                        if len(context.portfolio.positions) == self.buy_count:
                            break
    
    def adjust_avg(self, context, data, buy_stocks):
        position_count = len(context.portfolio.positions)
        if self.buy_count > position_count:
            buy_stocks = [stock for stock in buy_stocks if stock not in self.g.sell_stocks and stock not in context.portfolio.positions.keys()]
            buy_stocks = list(context.portfolio.positions.keys()) + buy_stocks
                
        avg_value = context.portfolio.portfolio_value / self.buy_count
        for stock in buy_stocks:
            if self.g.open_position(self, stock, avg_value, pindex):
                if len(context.portfolio.positions) == self.buy_count:
                    break
                    
    def after_trading_end(self, context):
        self.g.sell_stocks = []
        self.to_buy = []
        
    def recordTrade(self, stock_list):
        pass

    def __str__(self):
        return '股票调仓买入规则：现金平分式买入股票达目标股票数'


