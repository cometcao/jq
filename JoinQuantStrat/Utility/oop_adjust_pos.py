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
from centralRegion import Chan_Type
from equilibrium import check_chan_indepth
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
        self.equal_pos = params.get('equal_pos', False)
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
        self.period = params.get('period', '1m')
        self.isdebug = params.get('isdebug', False)
    
    def handle_data(self, context, data):
        to_check = context.portfolio.positions.keys()
        to_check = [stock for stock in to_check if context.portfolio.positions[stock].closeable_amount > 0]
        for stock in to_check:
            position_time = context.portfolio.positions[stock].transact_time
            chan_t, chan_d, chan_p = self.g.stock_chan_type[stock][0][0]
            if chan_t == Chan_Type.I: # for TYPE we can wait till target price
                stock_data = attribute_history(stock,240, unit='1m', fields=('high'), skip_paused=True, df=True)
                if stock_data.loc[position_time:, 'high'].max() > chan_p:
                    print("reached target price: {0}".format(chan_p))
                    self.g.close_position(self, context.portfolio.positions[stock], True, 0)
            else:
                result = check_chan_indepth(stock,
                                          end_time=context.current_dt, 
                                          period=self.period, 
                                          count=2000, 
                                          direction=TopBotType.bot2top,
                                          isdebug=self.isdebug, 
                                          is_anal=False,
                                          split_time=position_time)
                if result:
                    print("exhausted at {0} BI level".format(self.period))
                    self.g.close_position(self, context.portfolio.positions[stock], True, 0)

            
    def __str__(self):
        return '缠论调仓卖出规则'


class Long_Chan(Buy_stocks_portion):
    def __init__(self, params):
        Buy_stocks_portion.__init__(self, params)
        self.buy_count = params.get('buy_count', 3)
        self.to_buy = []
        
    def handle_data(self, context, data):
        if self.is_to_return:
            self.log_warn('无法执行买入!! self.is_to_return 未开启')
            return

        self.to_buy = self.g.monitor_buy_list
        type_I_stocks = []
        for stock in self.to_buy:
            # only check the top level in our case 5m level
            if Chan_Type.I in self.g.stock_chan_type[stock][0][0]:
                type_I_stocks.append(stock)
                self.to_buy.remove(stock)
        self.to_buy = type_I_stocks + self.to_buy
        self.adjust(context, data, self.to_buy)
        
    def __str__(self):
        return '缠论调仓买入规则'
  