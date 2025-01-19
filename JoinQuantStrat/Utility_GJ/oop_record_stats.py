# -*- encoding: utf8 -*-
'''
Created on 4 Dec 2017

@author: MetalInvest
'''
from oop_strategy_frame import *
from strategy_stats import *
from prettytable import PrettyTable
import numpy as np


# '''------------------股票买卖操作记录-----------------'''
class Op_stocks_record(Adjust_expand):
    def __init__(self, params):
        Adjust_expand.__init__(self, params)
        self.op_buy_stocks = []
        self.op_sell_stocks = []
        self.position_has_change = False

    def on_buy_stock(self, stock, order, new_pindex=0,context=None):
        self.position_has_change = True
        self.op_buy_stocks.append([stock, order.filled])

    def on_sell_stock(self, position, order, is_normal, new_pindex=0,context=None):
        self.position_has_change = True
        self.op_sell_stocks.append([position.security, -order.filled])

    def after_adjust_end(self, context, data):
        self.op_buy_stocks = self.merge_op_list(self.op_buy_stocks)
        self.op_sell_stocks = self.merge_op_list(self.op_sell_stocks)

    def after_trading_end(self, context):
        self.op_buy_stocks = []
        self.op_sell_stocks = []
        self.position_has_change = False

    # 对同一只股票的多次操作，进行amount合并计算。
    def merge_op_list(self, op_list):
        s_list = list(set([x[0] for x in op_list]))
        return [[s, sum([x[1] for x in op_list if x[0] == s])] for s in s_list]


# '''------------------股票操作显示器-----------------'''
class Show_postion_adjust(Op_stocks_record):
    def after_adjust_end(self, context, data):
        # 调用父类方法
        Op_stocks_record.after_adjust_end(self, context, data)
        # if len(self.g.buy_stocks) > 0:
        #     if len(self.g.buy_stocks) > 5:
        #         tl = self.g.buy_stocks[0:5]
        #     else:
        #         tl = self.g.buy_stocks[:]
        #     self.log.info('选股:\n' + join_list(["[%s]" % (show_stock(x)) for x in tl], ' ', 10))
        # 显示买卖日志
        if len(self.op_sell_stocks) > 0:
            self.log.info(
                '\n' + join_list(["卖出 %s : %d" % (show_stock(x[0]), x[1]) for x in self.op_sell_stocks], '\n', 1))
        if len(self.op_buy_stocks) > 0:
            self.log.info(
                '\n' + join_list(["买入 %s : %d" % (show_stock(x[0]), x[1]) for x in self.op_buy_stocks], '\n', 1))
        # 显示完就清除
        self.op_buy_stocks = []
        self.op_sell_stocks = []

    def __str__(self):
        return '显示调仓时买卖的股票'

# ''' ----------------------统计类----------------------------'''
class Stat(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        # 加载统计模块
        self.trade_total_count = 0
        self.trade_success_count = 0
        self.statis = {'win': [], 'loss': []}
        self.strategy_stats = StrategyStats()

    def after_trading_end(self, context):
        if self._params.get('trade_stats', True):
            self.strategy_stats.processOrder(self.makeOrderRecords(get_orders()), context)
            if self.g.isFirstTradingDayOfMonth(context):
                self.strategy_stats.displayRecords()
            self.g.long_record = {}
            self.g.short_record = {}
        self.report(context)
    
    def makeOrderRecords(self, orders):
        order_record = []
        for order_id, order_obj in orders.items():
            stock = order_obj.security
            if stock in g.money_fund:
                continue
            if order_obj.action == 'open' and order_obj.side == 'long':
                if stock in self.g.long_record:
                    order_record.append((order_obj, self.g.long_record[stock]))
                else:
                    continue
            elif order_obj.action == 'close' and order_obj.side == 'long':
                if stock in self.g.short_record:
                    order_record.append((order_obj, self.g.short_record[stock]))
                else: # clear pos case
                    order_record.append((order_obj, ([(np.nan,np.nan),(np.nan,np.nan),(np.nan,np.nan)], None, None)))
        return order_record

    def on_sell_stock(self, position, order, is_normal, pindex=0,context=None):
        if order.filled > 0:
            # 只要有成交，无论全部成交还是部分成交，则统计盈亏
            self.watch(position.security, order.filled, position.avg_cost, position.price)

    def on_buy_stock(self,stock,order,pindex=0,context=None):
        pass

    def reset(self):
        self.trade_total_count = 0
        self.trade_success_count = 0
        self.statis = {'win': [], 'loss': []}

    # 记录交易次数便于统计胜率
    # 卖出成功后针对卖出的量进行盈亏统计
    def watch(self, stock, sold_amount, avg_cost, cur_price):
        self.trade_total_count += 1
        current_value = sold_amount * cur_price
        cost = sold_amount * avg_cost

        percent = round((current_value - cost) / cost * 100, 2)
        if current_value > cost:
            self.trade_success_count += 1
            win = [stock, percent]
            self.statis['win'].append(win)
        else:
            loss = [stock, percent]
            self.statis['loss'].append(loss)

    def report(self, context):
        cash = context.portfolio.cash
        totol_value = context.portfolio.portfolio_value
        position = 1 - cash / totol_value
        self.log.info("收盘后持仓概况:%s" % str(list(context.portfolio.positions)))
        self.log.info("仓位概况:%.2f" % position)
        self.print_win_rate(context.current_dt.strftime("%Y-%m-%d"), context.current_dt.strftime("%Y-%m-%d"), context)

    def print_win_rate_v2(self):
        pass

    # 打印胜率
    def print_win_rate(self, current_date, print_date, context):
        if str(current_date) == str(print_date):
            win_rate = 0
            if 0 < self.trade_total_count and 0 < self.trade_success_count:
                win_rate = round(self.trade_success_count / float(self.trade_total_count), 3)

            most_win = self.statis_most_win_percent()
            most_loss = self.statis_most_loss_percent()
            starting_cash = context.portfolio.starting_cash
            total_profit = self.statis_total_profit(context)
            if len(most_win) == 0 or len(most_loss) == 0:
                return
            
            s = '\n----------------------------绩效报表----------------------------'
            s += '\n交易次数: {0}, 盈利次数: {1}, 胜率: {2}'.format(self.trade_total_count, self.trade_success_count,
                                                          str(win_rate * 100) + str('%'))
            s += '\n单次盈利最高: {0}, 盈利比例: {1}%'.format(most_win['stock'], most_win['value'])
            s += '\n单次亏损最高: {0}, 亏损比例: {1}%'.format(most_loss['stock'], most_loss['value'])
            s += '\n总资产: {0}, 本金: {1}, 盈利: {2}, 盈亏比率：{3}%'.format(starting_cash + total_profit, starting_cash,
                                                                  total_profit, total_profit / starting_cash * 100)
            s += '\n---------------------------------------------------------------'
            self.log.info(s)

    def help_status_stats(self, stats, status_stats):
        for _, long_sta, short_sta in stats:
            if (long_sta, short_sta) not in status_stats:
                status_stats[(long_sta, short_sta)]=1
            else:
                status_stats[(long_sta, short_sta)]+=1
                
    def help_status_stats_concise(self, stats, status_stats):
         for _, long_sta, short_sta in stats:
            if long_sta not in status_stats:
                status_stats[long_sta]=1
            else:
                status_stats[long_sta]+=1  
            if short_sta not in status_stats:
                status_stats[short_sta]=1
            else:
                status_stats[short_sta]+=1  

    # 统计单次盈利最高的股票
    def statis_most_win_percent(self):
        result = {}
        for statis in self.statis['win']:
            if {} == result:
                result['stock'] = statis[0]
                result['value'] = statis[1]
            else:
                if statis[1] > result['value']:
                    result['stock'] = statis[0]
                    result['value'] = statis[1]

        return result

    # 统计单次亏损最高的股票
    def statis_most_loss_percent(self):
        result = {}
        for statis in self.statis['loss']:
            if {} == result:
                result['stock'] = statis[0]
                result['value'] = statis[1]
            else:
                if statis[1] < result['value']:
                    result['stock'] = statis[0]
                    result['value'] = statis[1]

        return result

    # 统计总盈利金额
    def statis_total_profit(self, context):
        return context.portfolio.portfolio_value - context.portfolio.starting_cash

    def __str__(self):
        return '策略绩效统计'
