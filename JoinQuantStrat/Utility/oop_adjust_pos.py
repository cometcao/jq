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
from common_include import *
from ta_analysis import *
from oop_strategy_frame import *
from position_control_analysis import *
from rsrs_timing import *
from chan_common_include import Chan_Type, float_more_equal, GOLDEN_RATIO
from equilibrium import check_chan_indepth, check_stock_sub, check_chan_by_type_exhaustion, check_stock_full
from biaoLiStatus import TopBotType
import json

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
        self.use_short_filter = params.get('use_short_filter', False)
        self.money_fund = params.get('money_fund', ['511880.XSHG'])
        
    def handle_data(self, context, data):
        to_sell = context.portfolio.positions.keys()
        if self.use_short_filter:
            cta = checkTAIndicator_OR({
                'TA_Indicators':[
                                (TaType.MACD,'240m',233),
                                (TaType.MACD,'120m',233),
                                (TaType.MACD,'60m',233),
                                (TaType.BOLL, '240m',100),
                                (TaType.BOLL_UPPER, '1d',100),
                                ],
                'isLong':False})
            to_sell = cta.filter(context, data,to_sell)
        else:
            to_sell = []
        self.g.monitor_buy_list = [stock for stock in self.g.monitor_buy_list if stock not in to_sell]        
        self.adjust(context, data, self.g.monitor_buy_list)

    def adjust(self, context, data, buy_stocks):
        # 卖出不在待买股票列表中的股票
        # 对于因停牌等原因没有卖出的股票则继续持有
        for pindex in self.g.op_pindexs:
            for stock in context.subportfolios[pindex].long_positions.keys():
                if stock not in buy_stocks and stock not in self.money_fund:
                    position = context.subportfolios[pindex].long_positions[stock]
                    self.g.close_position(self, position, True, pindex)
                    
    def recordTrade(self, stock_list):
        for stock in stock_list:
            biaoLiStatus = self.g.monitor_short_cm.getGaugeStockList(stock).values
            _, ta_type, period = self.g.short_record[stock] if stock in self.g.short_record else ([(nan, nan), (nan, nan), (nan, nan)], None, None)
            self.g.short_record[stock] = (biaoLiStatus, ta_type, period)

    def __str__(self):
        return '股票调仓卖出规则：卖出不在buy_stocks的股票'


# '''---------------买入股票规则--------------'''
class Buy_stocks(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        self.buy_count = params.get('buy_count', 3)
        self.use_long_filter = params.get('use_long_filter', False)
        self.use_short_filter = params.get('use_short_filter', False)
        self.to_buy = []
        self.use_adjust_portion = params.get('use_adjust_portion', False)

    def update_params(self, context, params):
        Rule.update_params(self, context, params)
        self.buy_count = params.get('buy_count', self.buy_count)

    def handle_data(self, context, data):
        if self.is_to_return:
            self.log_warn('无法执行买入!! self.is_to_return 未开启')
            return        

        self.to_buy = self.g.monitor_buy_list
        self.log.info("待选股票: "+join_list([show_stock(stock) for stock in self.to_buy], ' ', 10))
        if self.use_short_filter:
            self.to_buy = self.ta_short_filter(context, data, self.to_buy)
#         if context.current_dt.hour >= 14:
        if self.use_long_filter:
            self.to_buy = self.ta_long_filter(context, data, self.to_buy) 
        if self.use_adjust_portion:
            self.adjust_portion(context, data, self.to_buy)
        else:
            self.adjust(context, data, self.to_buy)

    def ta_long_filter(self, context, data, to_buy):
        cta = checkTAIndicator_OR({
            'TA_Indicators':[
                            # (TaType.MACD_ZERO,'60m',233),
                            (TaType.TRIX_STATUS, '240m', 100),
                            # (TaType.MACD_STATUS, '240m', 100),
                            (TaType.RSI, '240m', 100)
                            ],
            'isLong':True,
            'use_latest_data':True})
        to_buy = cta.filter(context, data,to_buy)
        return to_buy

    def ta_short_filter(self, context, data, to_buy):
        cti = checkTAIndicator_OR({
            'TA_Indicators':[
                            (TaType.MACD,'1d',233),
                            (TaType.BOLL, '1d',100),
                            (TaType.TRIX_STATUS, '1d', 100),
                            (TaType.BOLL_MACD,'1d',233),
                            (TaType.KDJ_CROSS, '1d', 100)
                            ],
            'isLong':False, 
            'use_latest_data':True})
        not_to_buy = cti.filter(context, data, to_buy)
        to_buy = [stock for stock in to_buy if stock not in not_to_buy]
        return to_buy
        
    def adjust(self, context, data, buy_stocks):
        # 买入股票
        # 始终保持持仓数目为g.buy_stock_count
        # 根据股票数量分仓
        # 此处只根据可用金额平均分配购买，不能保证每个仓位平均分配
        for pindex in self.g.op_pindexs:
            position_count = len(context.subportfolios[pindex].long_positions)
            if self.buy_count > position_count:
                value = context.subportfolios[pindex].available_cash / (self.buy_count - position_count)
                for stock in buy_stocks:
                    if stock in self.g.sell_stocks:
                        continue
                    if stock not in context.subportfolios[pindex].long_positions.keys():
                        if self.g.open_position(self, stock, value, pindex):
                            if len(context.subportfolios[pindex].long_positions) == self.buy_count:
                                break
        pass        
        
    def adjust_portion(self, context, data, buy_stocks):
        # 买入股票
        # 始终保持持仓数目为g.buy_stock_count
        # 根据股票数量分仓
        # 此处只根据可用金额平均分配购买，不能保证每个仓位平均分配
        for pindex in self.g.op_pindexs:
            value = context.subportfolios[pindex].total_value / self.buy_count
            for stock in context.subportfolios[pindex].long_positions.keys():
                sub_holding_value = value * (self.g.position_proportion[stock] if stock in self.g.position_proportion else 1.0)
                self.g.adjust_position(context, stock, sub_holding_value, pindex)            
            
            position_count = len(context.subportfolios[pindex].long_positions)
            if self.buy_count > position_count:
                for stock in buy_stocks:
                    if stock in self.g.sell_stocks:
                        continue
                    if stock not in context.subportfolios[pindex].long_positions.keys():
                        sub_value = value * (self.g.position_proportion[stock] if stock in self.g.position_proportion else 1.0)
                        if self.g.open_position(self, stock, sub_value, pindex):
                            if len(context.subportfolios[pindex].long_positions) == self.buy_count:
                                break
        pass
                    
    def after_trading_end(self, context):
        self.g.sell_stocks = []
        self.to_buy = []
        
    def recordTrade(self, stock_list):
        for stock in stock_list:
            biaoLiStatus = self.g.monitor_long_cm.getGaugeStockList(stock).values
            _, ta_type, period = self.g.long_record[stock] if stock in self.g.long_record else ([(nan, nan), (nan, nan), (nan, nan)], None, None)
            self.g.long_record[stock] = (biaoLiStatus, ta_type, period)

    def __str__(self):
        return '股票调仓买入规则：现金平分式买入股票达目标股票数'

class Buy_stocks_portion(Buy_stocks):
    def __init__(self,params):
        Rule.__init__(self, params)
        self.buy_count = params.get('buy_count',3)
    def update_params(self,context,params):
        self.buy_count = params.get('buy_count',self.buy_count)
    def handle_data(self, context, data):
        self.adjust(context, data, self.g.monitor_buy_list)
    def adjust(self,context,data,buy_stocks):
        if self.is_to_return:
            self.log_warn('无法执行买入!! self.is_to_return 未开启')
#             self.g.send_port_info(context)
            return
        for pindex in self.g.op_pindexs:
            position_count = len(context.subportfolios[pindex].positions)
            if self.buy_count > position_count:
                buy_num = self.buy_count - position_count
                portion_gen = generate_portion(buy_num)
                available_cash = context.subportfolios[pindex].available_cash
                for stock in buy_stocks:
                    if stock in self.g.sell_stocks:
                        continue
                    if context.subportfolios[pindex].long_positions[stock].total_amount == 0:
                        buy_portion = next(portion_gen)
#                         buy_portion = portion_gen.next()
                        value = available_cash * buy_portion
                        if self.g.open_position(self, stock, value, pindex):
                            if len(context.subportfolios[pindex].long_positions) == self.buy_count:
                                break
#         self.g.send_port_info(context)
        pass
    def after_trading_end(self, context):
        self.g.sell_stocks = []
    def __str__(self):
        return '股票调仓买入规则：现金比重式买入股票达目标股票数'  

class Buy_stocks_var(Buy_stocks):
    """使用 VaR 方法做调仓控制"""
    def __init__(self, params):
        Buy_stocks.__init__(self, params)
        self.money_fund = params.get('money_fund', ['511880.XSHG'])
        self.adjust_pos = params.get('adjust_pos', True)
        self.equal_pos = params.get('equal_pos', True)
        self.p_value = params.get('p_val', 2.58)
        self.risk_var = params.get('risk_var', 0.13)
        self.pc_var = None

    def adjust(self, context, data, buy_stocks):
#         buy_stocks = [g.etf_list[stock]  if stock in g.etf_list else stock for stock in buy_stocks]
        if not self.pc_var:
            # 设置 VaR 仓位控制参数。风险敞口: 0.05,
            # 正态分布概率表，标准差倍数以及置信率: 0.96, 95%; 2.06, 96%; 2.18, 97%; 2.34, 98%; 2.58, 99%; 5, 99.9999%
            # 赋闲资金可以买卖银华日利做现金管理: ['511880.XSHG']
            self.pc_var = PositionControlVar(context, self.risk_var, self.p_value, self.money_fund, self.equal_pos)
        if self.is_to_return:
            self.log_warn('无法执行买入!! self.is_to_return 未开启')
#             self.g.send_port_info(context)
            return
        
        if self.adjust_pos:
            self.adjust_all_pos(context, data, buy_stocks)
        else:
            self.adjust_new_pos(context, data, buy_stocks)
    
    def adjust_new_pos(self, context, data, buy_stocks):
        for pindex in self.g.op_pindexs:
            position_count = len([stock for stock in context.subportfolios[pindex].positions.keys() if stock not in self.money_fund and stock not in buy_stocks])
            extra_buy_stocks = [stock for stock in buy_stocks if stock not in context.subportfolios[pindex].positions.keys()]
            trade_ratio = {}
            if self.buy_count > position_count:
                buy_num = self.buy_count - position_count
                trade_ratio = self.pc_var.buy_the_stocks(context, extra_buy_stocks[:buy_num])
            else:
                trade_ratio = self.pc_var.func_rebalance(context)

            # sell money_fund if not in list
            for stock in context.subportfolios[pindex].long_positions.keys():
                position = context.subportfolios[pindex].long_positions[stock]
                if stock in self.money_fund: 
                    if (stock not in trade_ratio or trade_ratio[stock] == 0.0):
                        self.g.close_position(self, position, True, pindex)
                    else:
                        self.g.adjust_position(context, stock, context.subportfolios[pindex].total_value*trade_ratio[stock],pindex)
                        
            for stock in trade_ratio:
                if stock in self.g.sell_stocks and stock not in self.money_fund:
                    continue
                if context.subportfolios[pindex].long_positions[stock].total_amount == 0:
                    if self.g.adjust_position(context, stock, context.subportfolios[pindex].total_value*trade_ratio[stock],pindex):
                        if len(context.subportfolios[pindex].long_positions) == self.buy_count+1:
                            break        
        
    def adjust_all_pos(self, context, data, buy_stocks):
        # 买入股票或者进行调仓
        # 始终保持持仓数目为g.buy_count
        for pindex in self.g.op_pindexs:
            to_buy_num = len(buy_stocks)
            # exclude money_fund
            holding_positon_exclude_money_fund = [stock for stock in context.subportfolios[pindex].positions.keys() if stock not in self.money_fund]
            position_count = len(holding_positon_exclude_money_fund)
            extra_buy_stocks = [stock for stock in buy_stocks if stock not in context.subportfolios[pindex].positions.keys()]
            trade_ratio = {}
            if self.buy_count <= position_count+to_buy_num: # 满仓数
                buy_num = self.buy_count - position_count
                trade_ratio = self.pc_var.buy_the_stocks(context, holding_positon_exclude_money_fund+extra_buy_stocks[:buy_num])
            else: # 分仓数
                trade_ratio = self.pc_var.buy_the_stocks(context, holding_positon_exclude_money_fund+extra_buy_stocks)

            current_ratio = self.g.getCurrentPosRatio(context)
            order_stocks = self.getOrderByRatio(current_ratio, trade_ratio)
            for stock in order_stocks:
                if stock in self.g.sell_stocks:
                    continue
                if self.g.adjust_position(context, stock, context.subportfolios[pindex].total_value*trade_ratio[stock],pindex):
                    pass
    
    def getOrderByRatio(self, current_ratio, target_ratio):
        diff_ratio = [(stock, target_ratio[stock]-current_ratio[stock]) for stock in target_ratio if stock in current_ratio] \
                    + [(stock, target_ratio[stock]) for stock in target_ratio if stock not in current_ratio] \
                    + [(stock, 0.0) for stock in current_ratio if stock not in target_ratio]
        diff_ratio.sort(key=lambda x: x[1]) # asc
        return [stock for stock,_ in diff_ratio]
    
    def __str__(self):
        return '股票调仓买入规则：使用 VaR 方式买入或者调整股票达目标股票数'
    
# adjust stocks ###########

class Sell_stocks_chan(Sell_stocks):
    def __init__(self, params):
        Sell_stocks.__init__(self, params)
        self.monitor_levels = params.get('monitor_levels', ['5d','1d','60m'])
        self.money_fund = params.get('money_fund', ['511880.XSHG'])
    def handle_data(self, context, data):
        # 日线级别卖点
        cti = None
        TA_Factor.global_var = self.g
        self.g.monitor_short_cm.updateGaugeStockList(newStockList=context.portfolio.positions.keys(), levels=[self.monitor_levels[-1]]) # gauge 30m level status
        if context.current_dt.hour < 11: # 10点之前
            cti = checkTAIndicator_OR({
                'TA_Indicators':[
                                (TaType.BOLL_MACD,'1d',233),
                                # (TaType.BOLL_MACD,'60m',233),
                                # (TaType.MACD,'60m',233),
                                (TaType.MACD,'1d',233),
                                # (TaType.BOLL,'1d',100), 
                                ],
                'isLong':False}) 
        elif context.current_dt.hour >= 14: # after 14:00
            cti = checkTAIndicator_OR({
                'TA_Indicators':[
                                # (TaType.BOLL,'240m',100), 
                                (TaType.BOLL_MACD,'240m',233), # moved from morning check
                                # (TaType.BOLL_MACD,'60m',233),
                                # (TaType.MACD,'60m',233),
                                (TaType.MACD,'240m',233),
                                # (TaType.TRIX_STATUS, '240m', 100),
                                (TaType.KDJ_CROSS, '240m', 100)
                    ], 
                'isLong':False}) 
        else:
            cti = checkTAIndicator_OR({
                'TA_Indicators':[
                                # (TaType.BOLL_MACD,'60m',233),
                                # (TaType.MACD,'60m',233),
                                ], 
                'isLong':False}) 
        to_sell = cti.filter(context, data, context.portfolio.positions.keys())
        to_sell = [stock for stock in to_sell if stock not in self.money_fund] # money fund only adjusted by buy method
        to_sell_intraday = self.intradayShortFilter(context, data)
        # to_sell_intraday = []
        try:
            to_sell = [stock for stock in to_sell if data[stock].close < data[stock].high_limit] # 涨停不卖
        except:
            pass

        # ML check
        # mlb = ML_biaoli_check()
        # to_sell_biaoli = mlb.gauge_stocks(context.portfolio.positions.keys(), isLong=False)
        to_sell_biaoli = []
        
        to_sell = list(set(to_sell+to_sell_biaoli+to_sell_intraday))
        if to_sell:
            self.log.info('准备卖出:\n' + join_list(["[%s]" % (show_stock(x)) for x in to_sell], ' ', 10))
            self.adjust(context, data, to_sell)
            # remove stocks from short gauge
            sold_stocks = [stock for stock in to_sell if stock not in context.portfolio.positions.keys()] # make sure stock sold successfully
            self.g.monitor_short_cm.displayMonitorMatrix(to_sell)
            self.recordTrade(to_sell) # record all selling candidate
            self.g.monitor_short_cm.removeGaugeStockList(sold_stocks)
        self.g.intraday_long_stock = [stock for stock in self.g.intraday_long_stock if stock in context.portfolio.positions.keys()]

    def intradayShortFilter(self, context, data):
        cti_short_check = None
        if context.current_dt.hour < 11:
            cti_short_check = checkTAIndicator_OR({
                'TA_Indicators':[
                                # (TaType.BOLL,'60m',40),
                                (TaType.BOLL_MACD,'60m',233),
                                (TaType.MACD,'60m',233),
                                (TaType.TRIX_STATUS, '60m', 100),
                                ], 
                'isLong':False})
        elif context.current_dt.hour >= 14:
            cti_short_check = checkTAIndicator_OR({
                'TA_Indicators':[
                                (TaType.BOLL_MACD,'60m',233),
                                (TaType.MACD,'60m',233),
                                # (TaType.BOLL,'60m',40),
                                (TaType.TRIX_STATUS, '60m', 100),
                                ], 
                'isLong':False})            
        else:
            # pass
            cti_short_check = checkTAIndicator_OR({
                'TA_Indicators':[
                                (TaType.BOLL_MACD,'60m',233),
                                (TaType.MACD,'60m',233),
                                # (TaType.BOLL,'60m',40),
                                (TaType.TRIX_STATUS, '60m', 100),
                                ], 
                'isLong':False})
        intraday_short_check = [stock for stock in context.portfolio.positions.keys() if stock in self.g.intraday_long_stock]
        to_sell = cti_short_check.filter(context, data, intraday_short_check) if cti_short_check else []
        return to_sell

    def adjust(self, context, data, sell_stocks):
        # 卖出在待卖股票列表中的股票
        # 对于因停牌等原因没有卖出的股票则继续持有
        for pindex in self.g.op_pindexs:
            for stock in context.subportfolios[pindex].long_positions.keys():
                if stock in sell_stocks:
                    position = context.subportfolios[pindex].long_positions[stock]
                    self.g.close_position(self, position, True, pindex)

    def __str__(self):
        return '股票调仓卖出规则：卖出在对应级别卖点'

class Buy_stocks_chan(Buy_stocks_var):
    def __init__(self, params):
        Buy_stocks.__init__(self, params)
        self.buy_count = params.get('buy_count', 3)
        self.monitor_levels = params.get('monitor_levels', ['5d','1d','60m'])
        self.pos_control = params.get('pos_control', 1.0)
        self.daily_list = []
        
    def update_params(self, context, params):
        self.buy_count = params.get('buy_count', 3)
        self.pos_control = params.get('pos_control', 1.0)
        
    def handle_data(self, context, data):
        if self.is_to_return:
            self.log_warn('无法执行买入!! self.is_to_return 未开启')
            return
        if len([stock for stock in context.portfolio.positions if stock not in g.money_fund])==self.buy_count:
            self.log.info("满仓等卖")
            return

        if context.current_dt.hour <= 10:
            self.daily_list = self.g.monitor_buy_list
            
        if not self.daily_list:
            self.log.info("现时无选股")
            return

        to_buy = self.daily_list
        self.g.monitor_long_cm.updateGaugeStockList(newStockList=self.daily_list, levels=[self.monitor_levels[-1]])
        # 技术分析用于不买在卖点
        not_to_buy = self.dailyShortFilter(context, data, to_buy)
        
        self.daily_list = [stock for stock in self.daily_list if stock not in not_to_buy]

        to_buy = [stock for stock in to_buy if stock not in not_to_buy] 
        to_buy = [stock for stock in to_buy if stock not in context.portfolio.positions.keys()] 
        to_buy = [stock for stock in self.g.monitor_buy_list if stock in to_buy]
        try:
            to_buy = [stock for stock in to_buy if data[stock].close > data[stock].low_limit] # 跌停不买
        except:
            pass
        
        to_buy = self.dailyLongFilter(context, data, to_buy)
        
        if to_buy:
            buy_msg = '日内待买股:\n' + join_list(["[%s]" % (show_stock(x)) for x in to_buy], ' ', 10)
            self.log.info(buy_msg)
            self.adjust(context, data, to_buy)
            bought_stocks = [stock for stock in context.portfolio.positions.keys() if stock in to_buy]
            #transfer long gauge to short gauge
            self.g.monitor_short_cm.appendStockList(self.g.monitor_long_cm.getGaugeStockList(bought_stocks))
            self.g.monitor_long_cm.displayMonitorMatrix(to_buy)
            self.recordTrade(bought_stocks)
#             self.g.send_port_info(context)
        elif context.current_dt.hour >= 14:
            self.adjust(context, data, [])
#             self.g.send_port_info(context)

        self.g.intraday_long_stock = [stock for stock in self.g.intraday_long_stock if stock in context.portfolio.positions.keys()] # keep track of bought stocks
        if context.current_dt.hour >= 14:
            self.log.info('日内60m标准持仓:\n' + join_list(["[%s]" % (show_stock(x)) for x in self.g.intraday_long_stock], ' ', 10))
    
    def dailyLongFilter(self, context, data, to_buy):
        to_buy_list = []
        TA_Factor.global_var = self.g 
        
        cta = checkTAIndicator_OR({
        'TA_Indicators':[
                        (TaType.MACD,'60m',233),
                        (TaType.BOLL_MACD, '60m', 233),
                        ],
        'isLong':True})
        to_buy_intraday_list = cta.filter(context, data, to_buy)      

        # intraday short check
        intraday_not_to_buy = self.intradayShortFilter(context, data, to_buy_intraday_list+self.g.intraday_long_stock)
        to_buy_intraday_list = [stock for stock in to_buy_intraday_list if stock not in intraday_not_to_buy]
        
        # 日内待选股票中排除日内出卖点
        self.daily_list = [stock for stock in self.daily_list if stock not in intraday_not_to_buy] 
        # combine with existing intraday long stocks
        self.g.intraday_long_stock = list(set(self.g.intraday_long_stock + to_buy_intraday_list))

        if context.current_dt.hour >= 14:
            cta = checkTAIndicator_OR({
            'TA_Indicators':[
                            (TaType.RSI, '240m', 100),
                            ],
            'isLong':True})
            to_buy_special_list = cta.filter(context, data, to_buy)
            # combine with existing intraday long stocks
            self.g.intraday_long_stock = list(set(self.g.intraday_long_stock + to_buy_special_list))            
            
            cta = checkTAIndicator_OR({
            'TA_Indicators':[
                            (TaType.MACD,'240m',233),
                            (TaType.BOLL_MACD, '240m', 233),
#                             (TaType.RSI, '240m', 100),
                            (TaType.KDJ_CROSS, '240m', 100),
                            ],
            'isLong':True})
            to_buy_list = cta.filter(context, data, to_buy)
            
            # ML check
            # mlb = ML_biaoli_check()
            # to_buy_list = mlb.gauge_stocks(to_buy_list, isLong=True)
            
            # 之前的日内选股的票排除掉如果被更大级别买点覆盖
            self.g.intraday_long_stock = [stock for stock in self.g.intraday_long_stock if stock not in to_buy_list]        
    
        return to_buy_list + to_buy_intraday_list

    def intradayShortFilter(self, context, data, to_buy):
        cti_short_check = None
        if context.current_dt.hour < 11:
            cti_short_check = checkTAIndicator_OR({
                'TA_Indicators':[
                                (TaType.MACD,'60m',233),
                                (TaType.BOLL_MACD,'60m',233),
                                # (TaType.BOLL,'60m',40),
                                (TaType.TRIX_STATUS, '60m', 100)
                                ], 
                'isLong':False})
        elif context.current_dt.hour >= 14:
            cti_short_check = checkTAIndicator_OR({
                'TA_Indicators':[
                                (TaType.MACD,'60m',233),
                                (TaType.BOLL_MACD,'60m',233),
                                # (TaType.BOLL,'60m',40),
                                (TaType.TRIX_STATUS, '60m', 100)
                                ], 
                'isLong':False})  
        else:
            cti_short_check = checkTAIndicator_OR({
                'TA_Indicators':[
                                (TaType.MACD,'60m',233),
                                (TaType.BOLL_MACD,'60m',233),
                                # (TaType.BOLL,'60m',40),
                                (TaType.TRIX_STATUS, '60m', 100)
                                ], 
                'isLong':False})  

        not_to_buy = cti_short_check.filter(context, data, to_buy) if cti_short_check else []
        return not_to_buy


    def dailyShortFilter(self, context, data, to_buy):
        remove_from_candidate = []
        not_to_buy = []
        cti_short_check = checkTAIndicator_OR({
            'TA_Indicators':[
                            # (TaType.MACD,'60m',233),
                            # (TaType.BOLL_MACD,'60m',233),
                            ], 
            'isLong':False})
        not_to_buy += cti_short_check.filter(context, data, to_buy)       
    
        if context.current_dt.hour < 11:
            cti_short_check = checkTAIndicator_OR({
                'TA_Indicators':[
                                (TaType.MACD,'1d',233),
                                (TaType.BOLL_MACD,'1d',233),
                                (TaType.BOLL,'1d',40),
                                (TaType.TRIX_STATUS, '1d', 100)], 
                'isLong':False})
            remove_from_candidate = cti_short_check.filter(context, data, to_buy) 
            not_to_buy += remove_from_candidate
        
        elif context.current_dt.hour >= 14:
            cti_short_check = checkTAIndicator_OR({
                'TA_Indicators':[
                                (TaType.MACD,'240m',233),
                                (TaType.BOLL_MACD,'240m',233),
                                (TaType.BOLL,'240m',40),
                                (TaType.TRIX_STATUS, '240m', 100), 
                                ], 
                'isLong':False})
            remove_from_candidate = cti_short_check.filter(context, data, to_buy)
            not_to_buy += remove_from_candidate

        not_to_buy += self.g.monitor_long_cm.filterUpTrendDownTrend(stock_list=to_buy, level_list=self.monitor_levels[1:], update_df=False)
        not_to_buy += self.g.monitor_long_cm.filterUpTrendUpNode(stock_list=to_buy, level_list=self.monitor_levels[1:], update_df=False)
        not_to_buy += self.g.monitor_long_cm.filterUpNodeDownTrend(stock_list=to_buy, level_list=self.monitor_levels[1:], update_df=False)
        not_to_buy += self.g.monitor_long_cm.filterUpNodeUpNode(stock_list=to_buy, level_list=self.monitor_levels[1:], update_df=False)
        
        ## not_to_buy += self.g.monitor_long_cm.filterDownNodeUpNode(stock_list=to_buy, level_list=self.monitor_levels[1:], update_df=False)
        not_to_buy = list(set(not_to_buy))
        # 大级别卖点从待选股票中去掉
#         if remove_from_candidate:
#             self.g.monitor_long_cm.removeGaugeStockList(remove_from_candidate)
#             self.g.monitor_buy_list = [stock for stock in self.g.monitor_buy_list if stock not in remove_from_candidate]
        return not_to_buy

    def after_trading_end(self, context):
        self.g.sell_stocks = []
        self.daily_list = []
        
    def __str__(self):
        return '股票调仓买入规则：买在对应级别买点'
            
    
class Sell_stocks_pair(Sell_stocks):
    def __init__(self,params):
        Sell_stocks.__init__(self, params)
        self.buy_count = params.get('buy_count', 2)
        
    def handle_data(self, context, data):
        if self.g.pair_zscore and len(self.g.monitor_buy_list)>1:
            final_buy_list = []
            i = 0
            while i < len(self.g.monitor_buy_list) and i < self.buy_count:
                if self.g.pair_zscore[int(i/2)] > 1:
                    final_buy_list.append(self.g.monitor_buy_list[i])
                elif self.g.pair_zscore[int(i/2)] < -1:
                    final_buy_list.append(self.g.monitor_buy_list[i+1])
                else: 
#                     self.g.pair_zscore[int(i/2)] >= 0:
#                     final_buy_list.append(self.g.monitor_buy_list[i])
#                     final_buy_list.append(self.g.monitor_buy_list[i+1])
                    pass
                i += 2
                
            for stock in context.portfolio.positions.keys():
                if stock not in final_buy_list:
                    self.g.close_position(self, context.portfolio.positions[stock], True, 0)

    def __str__(self):
        return '股票调仓买入规则：配对交易卖出'

class Buy_stocks_pair(Buy_stocks_var):
    def __init__(self,params):
        Buy_stocks_var.__init__(self, params)
        self.buy_count = params.get('buy_count', 2)
        
    def handle_data(self, context, data):
        if self.g.pair_zscore and len(self.g.monitor_buy_list) > 1:
            final_buy_list = []
            i = 0
            while i < len(self.g.monitor_buy_list) and i < self.buy_count:            
                if self.g.pair_zscore[int(i/2)] > 1:
                    final_buy_list.append(self.g.monitor_buy_list[i])  
                elif self.g.pair_zscore[int(i/2)] < -1:
                    final_buy_list.append(self.g.monitor_buy_list[i+1])
                else:
                    
#                     if self.g.pair_zscore[int(i/2)] >= 0:
#                         final_buy_list = final_buy_list + self.g.monitor_buy_list
#                     else:
#                         final_buy_list = final_buy_list + self.g.monitor_buy_list
                    pass
                    
                i += 2
            self.adjust(context, data, final_buy_list)
        else:
            self.adjust(context, data, [])
            
#         self.g.send_port_info(context)
        

    def __str__(self):
        return '股票调仓买入规则：配对交易买入'



class Short_Chan(Sell_stocks):
    def __init__(self, params):
        Sell_stocks.__init__(self, params)
        self.sup_period = params.get('sup_period' ,'30m')
        self.current_period = params.get('current_period', '5m')
        self.sub_period = params.get('sub_period', '1m')
        self.isdebug = params.get('isdebug', False)
        self.isDescription = params.get('isDescription', True)
        self.stop_loss = params.get('stop_loss', 0.02)
        self.stop_profit = params.get('stop_profit', 0.03)
        self.use_ma13 = params.get('use_ma13', False)
        self.use_sub_split = params.get('sub_split', False)
    
    def check_stop_loss(self, stock, context):
        avg_cost = context.portfolio.positions[stock].avg_cost
        # short circuit
        if context.portfolio.positions[stock].avg_cost < context.portfolio.positions[stock].price:
            return False
        
        current_profile = self.g.stock_chan_type[stock][1]
        sub_profile = self.g.stock_chan_type[stock][2]
        current_chan_t = current_profile[0]
        current_chan_p = current_profile[2]
        current_chan_slope = current_profile[3]
        current_chan_force = current_profile[4]
        current_zoushi_start_time = current_profile[5]
        splitTime = current_profile[6]
        sub_chan_t = sub_profile[0]
        sub_chan_p = sub_profile[2]
        sub_chan_slope = sub_profile[3]
        sub_chan_force = sub_profile[4]
        sub_zoushi_start_time = sub_profile[5]
        effective_time = sub_profile[6]
        
        if current_chan_t == Chan_Type.I:
            # This is to make sure we have enough data for MACD and MA
            data_start_time = current_zoushi_start_time - pd.Timedelta(minutes=250)
            stock_data = get_price(stock,
                                   start_date=data_start_time, 
                                   end_date=context.current_dt, 
                                   frequency=self.current_period, 
                                   fields=('high', 'low', 'close', 'money'), 
                                   skip_paused=False)

            max_price = stock_data.loc[current_zoushi_start_time:, 'high'].max()
            min_price = stock_data.loc[current_zoushi_start_time:, 'low'].min()
            max_price_time = stock_data.loc[current_zoushi_start_time:, 'high'].idxmax()
            min_price_time = stock_data.loc[effective_time:, 'low'].idxmin()
            max_loc = stock_data.index.get_loc(max_price_time)
            min_loc = stock_data.index.get_loc(min_price_time)
            current_loc_diff = stock_data.loc[effective_time:,].shape[0]
            first_loc_diff = stock_data.loc[current_zoushi_start_time:,].shape[0] - current_loc_diff
            
#             if current_loc_diff > first_loc_diff/2:
#                 if (1 - stock_data.iloc[-1].close / avg_cost) >= 0:
#                     print("waited for equal period {0}:{1} never reached profit {2}".format(first_loc_diff, 
#                                                                                                   current_loc_diff, 
#                                                                                                   stock_data.iloc[-1].close))
#                     return True
            if current_loc_diff > first_loc_diff:
                if max_price < current_chan_p:
                    print("waited for equal period {0}:{1} never reached guiding price {2}".format(first_loc_diff, 
                                                                                                  current_loc_diff, 
                                                                                                  current_chan_p))
                    return True

            if (1 - stock_data.iloc[-1].close / avg_cost) >= self.stop_loss:
                # check if original long point still holds
                result, xd_result, _ = check_chan_by_type_exhaustion(stock,
                                                                      end_time=min_price_time,
                                                                      periods=[self.current_period],
                                                                      count=4800,
                                                                      direction=TopBotType.top2bot,
                                                                      chan_type=[current_chan_t],
                                                                      isdebug=self.isdebug,
                                                                      is_description =self.isDescription,
                                                                      is_anal=False,
                                                                      check_structure=True,
                                                                      check_full_zoushi=False,
                                                                      slope_only=False) # synch with selection
                if not result:
                    print("Bei Chi long point broken")
                    return True
            
#             if (1 - stock_data.iloc[-1].close / avg_cost) >= self.stop_loss * 2:
#                 print("HARDCORE stop loss")
#                 return True

#                 result, profile, _ = check_stock_full(stock,
#                                                      end_time=min_price_time,
#                                                      periods=[self.current_period, self.sub_period],
#                                                      count=6000, # needs more data!
#                                                      direction=TopBotType.top2bot, 
#                                                      current_chan_type=[current_chan_t],
#                                                      sub_chan_type=[sub_chan_t],
#                                                      isdebug=self.isdebug,
#                                                      is_description=self.isDescription,
#                                                      sub_force_zhongshu=True, 
#                                                      sub_check_bi=False,
#                                                      use_sub_split=self.use_sub_split, 
#                                                      ignore_sub_xd=False)
#                 if not result:
#                     print("BeiChi long point broken")
#                     return True

#             elif (1 - stock_data.iloc[-1].close / avg_cost) >= 0:
#                 # check slope
#                 latest_slope = (max_price-min_price)/(max_loc-min_loc)
#                 if latest_slope < 0 and abs(latest_slope) >= abs(current_chan_slope):
#                     print("slope gets deeper! STOPLOSS {0},{1}".format(current_chan_slope, latest_slope))
#                     return True
#                   
#                 # check force
#                 money_sum = stock_data.loc[current_zoushi_start_time:, 'money'].sum() / 1e8
#                 price_delta = (min_price - max_price) / max_price * 100
#                 time_delta = stock_data.loc[current_zoushi_start_time:,:].shape[0] / 1200 * 100
#                 latest_force = money_sum * price_delta / time_delta ** 2
#                 if current_chan_force != 0 and latest_force < 0 and abs(latest_force) > abs(current_chan_force):
#                     print("force gets deeper! STOPLOSS {0},{1}".format(current_chan_force, latest_force))
#                     return True
                
            return False
        elif current_chan_t == Chan_Type.III or current_chan_t == Chan_Type.INVALID:
            # This is to make sure we have enough data for MACD and MA
            data_start_time = sub_zoushi_start_time - pd.Timedelta(minutes=120)
            stock_data = get_price(stock,
                                   start_date=data_start_time, 
                                   end_date=context.current_dt, 
                                   frequency='1m', 
                                   fields=('high', 'low', 'close', 'money'), 
                                   skip_paused=False)
            # check slope
            max_price = stock_data.loc[sub_zoushi_start_time:, 'high'].max()
            min_price = stock_data.loc[sub_zoushi_start_time:, 'low'].min()
            max_price_time = stock_data.loc[sub_zoushi_start_time:, 'high'].idxmax()
            min_price_time = stock_data.loc[sub_zoushi_start_time:, 'low'].idxmin()
            max_loc = stock_data.index.get_loc(max_price_time)
            min_loc = stock_data.index.get_loc(min_price_time)

            if (1 - stock_data.iloc[-1].close / avg_cost) >= self.stop_loss: # reached stop loss mark
                exhausted, xd_exhausted, _, _ = check_stock_sub(stock,
                                                              end_time=min_price_time,
                                                              periods=['1m' if self.sub_period == 'bi' else self.sub_period],
                                                              count=2500,
                                                              direction=TopBotType.top2bot,
                                                              chan_types=[Chan_Type.I, Chan_Type.INVALID],
                                                              isdebug=self.isdebug,
                                                              is_description =self.isDescription,
                                                              is_anal=False,
                                                              split_time=splitTime,
                                                              check_bi=(self.sub_period=='bi'),
                                                              force_zhongshu=True,
                                                              check_full_zoushi=False) # synch with selection
                if not exhausted or not xd_exhausted:
                    print("sub long point broken")
                    return True
            elif (1 - stock_data.iloc[-1].close / avg_cost) >= 0: # negative return
                latest_slope = (max_price-min_price)/(max_loc-min_loc)
                if latest_slope < 0 and abs(latest_slope) >= abs(sub_chan_slope):
                    print("slope gets deeper! STOPLOSS {0},{1}".format(sub_chan_slope, latest_slope))
                    return True
                
                # use force instead
                money_sum = stock_data.loc[sub_zoushi_start_time:, 'money'].sum() / 1e8
                price_delta = (min_price - max_price) / max_price * 100
                time_delta = stock_data.loc[sub_zoushi_start_time:, :].shape[0] / 1200 * 100
                latest_force = money_sum * price_delta / time_delta ** 2
                if sub_chan_force != 0 and latest_force < 0 and abs(latest_force) > abs(sub_chan_force):
                    print("force gets deeper! STOPLOSS {0},{1}".format(sub_chan_force, latest_force))
                    return True

            if current_chan_t == Chan_Type.III and stock_data.loc[effective_time:,'low'].min() <= current_chan_p:
                print("TYPE III invalidated {0}, {1}".format(stock_data.loc[effective_time:,'low'].min(), current_chan_p))
                return True
            
            return False
    
    def check_stop_profit(self, stock, context):
        # short circuit
        if context.portfolio.positions[stock].avg_cost > context.portfolio.positions[stock].price:
            return False
        
        position_time = context.portfolio.positions[stock].transact_time
        current_profile = self.g.stock_chan_type[stock][1]
        sub_profile = self.g.stock_chan_type[stock][2]
        current_chan_t = current_profile[0]
        current_chan_p = current_profile[2]
        current_zoushi_start_time = current_profile[5]
        current_split_time = current_profile[6]
        sub_chan_t = sub_profile[0]
        sub_chan_p = sub_profile[2]
        sub_zoushi_start_time = sub_profile[5]
        effective_time = sub_profile[6]
        
        if current_chan_t == Chan_Type.I:
            data_start_time = current_zoushi_start_time - pd.Timedelta(minutes=200)
            stock_data = get_price(stock,
                                   start_date=data_start_time, 
                                   end_date=context.current_dt, 
                                   frequency=self.current_period, 
                                   fields=('high', 'low', 'close'), 
                                   skip_paused=False)
            min_time = stock_data.loc[current_split_time:, 'low'].idxmin()
            
            sup_exhausted, sup_xd_exhausted, _, sup_zhongshu_formed = check_stock_sub(stock,
                                                  end_time=context.current_dt,
                                                  periods=[self.sup_period],
                                                  count=2000,
                                                  direction=TopBotType.bot2top,
                                                  chan_types=[Chan_Type.I, Chan_Type.INVALID],
                                                  isdebug=self.isdebug,
                                                  is_description=self.isDescription,
                                                  is_anal=False,
                                                  split_time=min_time,
                                                  check_bi=False,
                                                  allow_simple_zslx=False,
                                                  force_zhongshu=False,
                                                  check_full_zoushi=False, 
                                                  ignore_sub_xd=False) # synch with selection
            
            if (sup_exhausted and sup_zhongshu_formed) or (not sup_zhongshu_formed and sup_exhausted and sup_xd_exhausted):
                print("STOP PROFIT {0} {1} exhausted: {2}, {3}, {4}".format(stock,
                                                                            self.sup_period,
                                                                            sup_exhausted,
                                                                            sup_xd_exhausted,
                                                                            sup_zhongshu_formed))
                return True
            
            current_exhausted, current_xd_exhausted, _, current_zhongshu_formed = check_stock_sub(stock,
                                                  end_time=context.current_dt,
                                                  periods=[self.current_period],
                                                  count=2000,
                                                  direction=TopBotType.bot2top,
                                                  chan_types=[Chan_Type.I, Chan_Type.INVALID],
                                                  isdebug=self.isdebug,
                                                  is_description=self.isDescription,
                                                  is_anal=False,
                                                  split_time=min_time,
                                                  check_bi=False,
                                                  allow_simple_zslx=False,
                                                  force_zhongshu=True,
                                                  check_full_zoushi=False, 
                                                  ignore_sub_xd=False)
            if current_exhausted and current_zhongshu_formed:
                print("STOP PROFIT {0} {1} exhausted: {2}, {3}, {4}".format(stock,
                                                                            self.current_period,
                                                                            current_exhausted,
                                                                            current_xd_exhausted,
                                                                            current_zhongshu_formed))
                return True
            
            sub_exhausted, sub_xd_exhausted, _, sub_zhongshu_formed = check_stock_sub(stock,
                                                  end_time=context.current_dt,
                                                  periods=['1m' if self.sub_period == 'bi' else self.sub_period],
                                                  count=2000,
                                                  direction=TopBotType.bot2top,
                                                  chan_types=[Chan_Type.I],
                                                  isdebug=self.isdebug,
                                                  is_description=self.isDescription,
                                                  is_anal=False,
                                                  split_time=min_time,
                                                  check_bi=False,
                                                  allow_simple_zslx=False,
                                                  force_zhongshu=False,
                                                  check_full_zoushi=False,
                                                  ignore_sub_xd=False)
            if sub_exhausted:
                print("STOP PROFIT {0} {1} exhausted: {2}, {3}, {4}".format(stock,
                                                                            self.sub_period,
                                                                            sub_exhausted,
                                                                            sub_xd_exhausted,
                                                                            sub_zhongshu_formed))
                return True
            
            sma13 = stock_data['close'].values[-13:].sum() / 13
            sma5 = stock_data['close'].values[-5:].sum() / 5
            if stock_data.loc[effective_time:, 'high'].max() >= current_chan_p:# reached target price
                print("STOP PROFIT {0} target price: {1}, now max: {2}".format(stock, current_chan_p, stock_data.loc[effective_time:, 'high'].max()))
                if context.portfolio.positions[stock].price < current_chan_p:
                    if self.use_ma13 and sma5 < sma13:
                        print("STOP PROFIT {0} below ma13: {1}".format(stock, sma13))
                        return True
            else:
                if current_zhongshu_formed: 
                    print("STOP PROFIT working level zhongshu {0}".format("formed" if current_zhongshu_formed else "not formed"))
                    if self.use_ma13 and sma5 < sma13:
                        print("STOP PROFIT {0} below ma13: {1}".format(stock, sma13))
                        return True
                
#                 sub_exhausted, sub_xd_exhausted, _, sub_zhongshu_formed = check_stock_sub(stock,
#                                                       end_time=context.current_dt,
#                                                       periods=['1m' if self.sub_period == 'bi' else self.sub_period],
#                                                       count=2000,
#                                                       direction=TopBotType.bot2top,
#                                                       chan_types=[Chan_Type.I, Chan_Type.INVALID],
#                                                       isdebug=self.isdebug,
#                                                       is_description=self.isDescription,
#                                                       is_anal=False,
#                                                       split_time=min_time,
#                                                       check_bi=True,
#                                                       allow_simple_zslx=False,
#                                                       force_zhongshu=True,
#                                                       check_full_zoushi=False,
#                                                       ignore_sub_xd=False)
#                 if sub_exhausted:
#                     print("STOP PROFIT {0} {1} exhausted: {2}, {3}, {4}".format(stock,
#                                                                                 self.sub_period,
#                                                                                 sub_exhausted,
#                                                                                 sub_xd_exhausted,
#                                                                                 sub_zhongshu_formed))
#                     return True

            
        elif current_chan_t == Chan_Type.III or current_chan_t == Chan_Type.INVALID:
            
            # extra data for SMA calculation
            data_start_time = sub_zoushi_start_time - pd.Timedelta(minutes=200)
            stock_data = get_price(stock,
                                   start_date=data_start_time, 
                                   end_date=context.current_dt, 
                                   frequency=self.current_period, 
                                   fields=('high', 'low', 'close'), 
                                   skip_paused=False)

            sma13 = stock_data['close'].values[-13:].sum() / 13
            sma5 = stock_data['close'].values[-5:].sum() / 5
#             if stock_data.loc[effective_time:, 'high'].max() >= (sub_chan_p[1] if type(sub_chan_p) is list else sub_chan_p): 
#                 print("Stock {0} reached upper ZhongShu/target price {1}".format(stock, (sub_chan_p[1] if type(sub_chan_p) is list else sub_chan_p)))
#                 if self.use_ma13 and stock_data.iloc[-1].close < sma13:
#                     print("STOP PROFIT MA13 {0} {1}".format(stock_data.iloc[-1].close, sma13))
#                     return True
#             print("STOP PROFIT reached return {0} {1}".format(context.portfolio.positions[stock].avg_cost, stock_data.loc[effective_time:, 'high'].max()))
#             max_time = stock_data.loc[effective_time:, 'high'].idxmax()
            min_time = stock_data.loc[sub_zoushi_start_time:, 'low'].idxmin()

            bi_exhausted, bi_check_exhaustion, _, bi_all_types = check_chan_indepth(stock, 
                                                                                   end_time=context.current_dt, 
                                                                                   period=('1m' if self.sub_period == 'bi' else self.sub_period), 
                                                                                   count=2000, 
                                                                                   direction=TopBotType.bot2top, 
                                                                                   isdebug=self.isdebug, 
                                                                                   is_anal=False, 
                                                                                   is_description=self.isDescription,
                                                                                   split_time=min_time)
            if bi_all_types and bi_all_types[0][0] == Chan_Type.I and bi_exhausted:
                print("STOP PROFIT {0} bi exhausted: {1}, {2}, {3}".format(stock,
                                                                           bi_exhausted,
                                                                           bi_check_exhaustion,
                                                                           bi_all_types))
                return True
                
            exhausted, xd_exhausted, _, sub_zhongshu_formed = check_stock_sub(stock,
                                                          end_time=context.current_dt,
                                                          periods=['1m' if self.sub_period == 'bi' else self.sub_period],
                                                          count=2000,
                                                          direction=TopBotType.bot2top,
                                                          chan_types=[Chan_Type.I, Chan_Type.INVALID],
                                                          isdebug=self.isdebug,
                                                          is_description=self.isDescription,
                                                          is_anal=False,
                                                          split_time=min_time,
                                                          force_zhongshu=False,
                                                          allow_simple_zslx=False,
                                                          check_bi=False,
                                                          force_bi_zhongshu=True, 
                                                          check_full_zoushi=False) # relax rule
            if bi_exhausted and ((exhausted and sub_zhongshu_formed) or (not sub_zhongshu_formed and exhausted and xd_exhausted)):
                print("STOP PROFIT {0} sub exhausted: {1}, {2} Zhongshu formed: {3}".format(stock,
                                                                                   exhausted,
                                                                                   xd_exhausted,
                                                                                   sub_zhongshu_formed))
                return True
            
            if sub_zhongshu_formed and (stock_data.loc[effective_time:, 'high'].max() / context.portfolio.positions[stock].avg_cost - 1) >= self.stop_profit:
                # for TYPE III of 5m, we don't want to hold a stock for too long
                top_result, top_xd_result,_, top_zhongshu_formed = check_stock_sub(stock,
                                                              end_time=context.current_dt,
                                                              periods=[self.current_period],
                                                              count=2000,
                                                              direction=TopBotType.bot2top,
                                                              chan_types=[Chan_Type.I, Chan_Type.INVALID],
                                                              isdebug=self.isdebug,
                                                              is_description=self.isDescription,
                                                              is_anal=False,
                                                              split_time=min_time,
                                                              check_bi=True,
                                                              allow_simple_zslx=True,
                                                              force_zhongshu=False,
                                                              force_bi_zhongshu=True) # relax rule
                if top_result and top_xd_result:
                    print("STOP PROFIT {0} top exhausted: {1}, {2} Zhongshu formed: {3}".format(stock,
                                                                                       top_result,
                                                                                       top_xd_result,
                                                                                       top_zhongshu_formed))
                    return True
                
                if top_zhongshu_formed and self.use_ma13 and sma5 < sma13:
                    print("STOP PROFIT MA13 {0} {1} after Zhongshu formed".format(stock_data.iloc[-1].close, sma13))
                    return True
                
            return False
        
    def handle_data(self, context, data):
        to_check = context.portfolio.positions.keys()
        to_check = [stock for stock in to_check if (context.portfolio.positions[stock].closeable_amount > 0 and stock not in self.money_fund)]
        to_sell = []
        for stock in to_check:
            if self.check_stop_loss(stock, context):
                to_sell.append(stock)
                continue
            
            if self.check_stop_profit(stock, context):
                to_sell.append(stock)
        self.adjust(context, data, to_sell)

    def adjust(self, context, data, sell_stocks):
        # 卖出在待卖股票列表中的股票
        # 对于因停牌等原因没有卖出的股票则继续持有
        for pindex in self.g.op_pindexs:
            for stock in context.subportfolios[pindex].long_positions.keys():
                if stock in sell_stocks:
                    position = context.subportfolios[pindex].long_positions[stock]
                    self.g.close_position(self, position, True, pindex)

    def __str__(self):
        return '缠论调仓卖出规则'


class Long_Chan(Buy_stocks):  # Buy_stocks_portion
    def __init__(self, params):
        Buy_stocks.__init__(self, params)
        self.buy_count = params.get('buy_count', 3)
        self.working_chan_type = params.get('working_chan_type', Chan_Type.I)
        self.working_period = params.get('working_period', '5m')
        self.money_check_period = params.get('money_check_period', '1d')
        self.force_chan_type = params.get('force_chan_type', [
                                                              [Chan_Type.INVALID, self.working_chan_type, Chan_Type.I],
                                                              [Chan_Type.INVALID, self.working_chan_type, Chan_Type.I_weak],
                                                              [Chan_Type.INVALID, self.working_chan_type, Chan_Type.INVALID]
                                                              ])
        self.force_price_check = params.get('force_price_check', True)
        self.expected_profit = params.get('expected_profit', 0.03)
        self.tentative_chan_type = params.get('tentative_chan_type', [
                                    [Chan_Type.I, self.working_chan_type, Chan_Type.I],
                                    [Chan_Type.I_weak, self.working_chan_type, Chan_Type.I],
                                    [Chan_Type.I, self.working_chan_type, Chan_Type.I_weak]
                                    ])
        self.tentative_to_buy = set() # list to hold stocks waiting to be operated
        self.to_buy = []
        
    def handle_data(self, context, data):
        if self.is_to_return:
            self.log_warn('无法执行买入!! self.is_to_return 未开启')
            return

        self.to_buy = [stock for stock in self.g.monitor_buy_list if stock not in self.tentative_to_buy]
        self.log.info("Candidate stocks: {0} tentative stocks: {1}".format(self.to_buy, self.tentative_to_buy))
        type_I_stocks = []
        to_ignore = []
        for stock in self.to_buy:
            top_profile = self.g.stock_chan_type[stock][0]
            current_profile = self.g.stock_chan_type[stock][1]
            sub_profile = self.g.stock_chan_type[stock][2]
            
            top_chan_t = top_profile[0]
            cur_chan_t = current_profile[0]
            cur_chan_p = current_profile[2]
            sub_chan_t = sub_profile[0]
            sub_chan_p = sub_profile[2]
            effective_time = sub_profile[6]
            
            chan_type_list = [top_chan_t, cur_chan_t, sub_chan_t]
            
            if self.tentative_chan_type and (chan_type_list in self.tentative_chan_type):
                self.log.info("stock {0} saved for later!".format(stock))
                self.tentative_to_buy.add(stock)
                continue
            
            if self.force_chan_type and (chan_type_list not in self.force_chan_type):
#                 self.log.info("stock {0} ignored due to force {1}".format(stock, [top_chan_t, cur_chan_t, sub_chan_t]))
                to_ignore.append(stock)
            
            latest_data = get_price(stock,
                                   start_date=effective_time, 
                                   end_date=context.current_dt, 
                                   frequency='1m', 
                                   fields=('high', 'low', 'close'), 
                                   skip_paused=True)
            latest_high_price = latest_data['high'].max()
            latest_min_price = latest_data['low'].min()
            latest_price = latest_data.iloc[-1].close
            # check current price of the stock ignore the ones not suitable
            # sort the stocks prioritize TYPE I stocks
            if Chan_Type.I == cur_chan_t:
                
                if self.force_price_check and (latest_high_price >= cur_chan_p or cur_chan_p/latest_price - 1 < self.expected_profit):
                    to_ignore.append(stock)
                    
            elif self.force_price_check:
                if cur_chan_t == Chan_Type.III:
                    if latest_min_price <= cur_chan_p:
                        # if TYPE III not valid anymore
                        to_ignore.append(stock)
                if cur_chan_t == Chan_Type.INVALID:
                    if type(cur_chan_p) is list:
                        if latest_high_price >= cur_chan_p[0] or cur_chan_p[0]/latest_price - 1 < self.expected_profit:
                            to_ignore.append(stock)
                    else: # can only be actual price here
                        if latest_high_price >= cur_chan_p or cur_chan_p/latest_price - 1 < self.expected_profit:
                            to_ignore.append(stock)

                if sub_chan_t == Chan_Type.INVALID:
                    if type(sub_chan_p) is list:
                        if latest_high_price >= sub_chan_p[0] or sub_chan_p[0]/latest_price - 1 < self.expected_profit:
                            to_ignore.append(stock)
                    else: # can only be actual price here
                        if latest_high_price >= sub_chan_p or sub_chan_p/latest_price - 1 < self.expected_profit:
                            to_ignore.append(stock)
        
        if to_ignore:
            self.log.info("stocks: {0} ignored due to conditions".format(to_ignore)) 
            self.to_buy = [stock for stock in self.to_buy if stock not in to_ignore]
        
        self.to_buy = [stock for stock in self.to_buy if stock not in self.tentative_to_buy]
        
        self.to_buy = self.check_tentative_stocks(context) + self.to_buy
        
        self.adjust(context, data, self.to_buy)
        
    def check_tentative_stocks(self, context):
        stocks_to_long = []
        stocks_to_remove = set()
        for stock in self.tentative_to_buy:
            result, xd_result, c_profile = check_chan_by_type_exhaustion(stock,
                                                                  end_time=context.current_dt,
                                                                  periods=[self.working_period],
                                                                  count=4800,
                                                                  direction=TopBotType.top2bot,
                                                                  chan_type=[self.working_chan_type],
                                                                  isdebug=False,
                                                                  is_description =False,
                                                                  is_anal=False,
                                                                  check_structure=True,
                                                                  check_full_zoushi=False,
                                                                  slope_only=False) # synch with selection
            if not result:
                self.log.info("Bei Chi long point broken for stock: {0}".format(stock))
                stocks_to_remove.add(stock)
            else:
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
        self.tentative_to_buy = self.tentative_to_buy.difference(stocks_to_remove)
        
        # check volume/money
        for stock in self.tentative_to_buy:
            if self.check_vol_money(stock, context):
                stocks_to_long.append(stock)
                
        stocks_to_long = [stock for stock in stocks_to_long if stock not in context.portfolio.positions.keys()]
        
        return stocks_to_long
        # check TYPE III at sub level??
        
    def check_vol_money(self, stock, context):
        current_profile = self.g.stock_chan_type[stock][1]
        current_zoushi_start_time = current_profile[5]

        stock_data = get_bars(stock, 
                            count=240, # 5d
                            unit=self.working_period,
                            fields=['date','money'],
                            include_now=True, 
                            end_dt=context.current_dt, 
                            fq_ref_date=context.current_dt.date(), 
                            df=False)
        
#         cutting_loc = np.where(stock_data['date']>=current_zoushi_start_time)[0][0]
#         cutting_offset = stock_data.size - cutting_loc
        
#         # current zslx money compare to zs money
#         latest_money = sum(stock_data['money'][cutting_loc:])
#         past_money = sum(stock_data['money'][:cutting_loc][-cutting_offset:])

        # current zslx money split by mid term
#         latest_money = sum(stock_data['money'][cutting_loc:][-int(cutting_offset/2):])
#         past_money = sum(stock_data['money'][cutting_loc:][:int(cutting_offset/2)])

        latest_money = sum(stock_data['money'][-120:])
        past_money = sum(stock_data['money'][:120])
        
        if float_more_equal(latest_money / past_money, 1+GOLDEN_RATIO):
            self.log.info("candiate stock {0} money active: {1} <-> {2}".format(stock, past_money, latest_money))
            return True
        return False
        
    def __str__(self):
        return '缠论调仓买入规则'
  