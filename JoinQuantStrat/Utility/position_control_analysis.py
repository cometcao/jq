# -*- encoding: utf8 -*-
'''
Created on 4 Dec 2017

@author: MetalInvest
'''
try:
    from kuanke.user_space_api import *
except:
    pass
import numpy as np
from jqdata import *
import datetime
from common_include import generate_portion

# ===================== VaR仓位控制 ===============================================

class PositionControlVar(object):
    """基于风险价值法（VaR）的仓位控制"""

    def __init__(self, context, risk_money_ratio=0.05, confidencelevel=2.58, moneyfund=['511880.XSHG'], equal_pos=False):
        """ 相关参数说明：
            1. 设置风险敞口
            risk_money_ratio = 0.05

            2. 正态分布概率表，标准差倍数以及置信率
                1.96, 95%; 2.06, 96%; 2.18, 97%; 2.34, 98%; 2.58, 99%; 5, 99.9999%
            confidencelevel = 2.58

            3. 使用赋闲资金做现金管理的基金(银华日利)
            moneyfund = ['511880.XSHG']
        """
        self.risk_money = context.portfolio.portfolio_value * risk_money_ratio
        self.confidencelevel = confidencelevel
        self.moneyfund = self.delete_new_moneyfund(context, moneyfund, 60)
        self.equal_pos = equal_pos

    def __str__(self):
        return 'VaR仓位控制'

    # 卖出股票
    def sell_the_stocks(self, context, stocks):
        equity_ratio = {}
        for stock in stocks:
            if stock in context.portfolio.positions.keys():
                # 这段代码不甚严谨，多产品轮动会有问题，本案例 OK
                if stock not in self.moneyfund:
                    equity_ratio[stock] = 0
        trade_ratio = self.func_getequity_value(context, equity_ratio)
        # self.func_trade(context, trade_ratio)
        return trade_ratio

    # 买入股票
    def buy_the_stocks(self, context, stocks):
        equity_ratio = {}
        portion_gen = generate_portion(len(stocks))
        for stock in stocks:
            equity_ratio[stock] = 1.0/len(stocks) if self.equal_pos else portion_gen.next() 
        trade_ratio = self.func_getequity_value(context, equity_ratio)
        return trade_ratio

    # 股票调仓
    def func_rebalance(self, context):
        myholdlist = list(context.portfolio.positions.keys())
        trade_ratio = {}
        if myholdlist:
            for stock in myholdlist:
                if stock not in self.moneyfund:
                    equity_ratio = {stock: 1.0}
                    trade_ratio = self.func_getequity_value(context, equity_ratio)
        return trade_ratio
            
    # 剔除上市时间较短的基金产品
    def delete_new_moneyfund(self, context, equity, deltaday):
        deltaDate = context.current_dt.date() - datetime.timedelta(deltaday)
    
        tmpList = []
        for stock in equity:
            if get_security_info(stock).start_date < deltaDate:
                tmpList.append(stock)
    
        return tmpList

    # 根据预设的 risk_money 和 confidencelevel 来计算，可以买入该多少权益类资产
    def func_getequity_value(self, context, equity_ratio):
        def __func_getdailyreturn(stock, freq, lag):
            hStocks = history(lag, freq, 'close', stock, df=True)
            dailyReturns = hStocks.resample('D', how='last').pct_change().fillna(value=0, method=None, axis=0).values
            return dailyReturns

        def __func_getStd(stock, freq, lag):
            dailyReturns = __func_getdailyreturn(stock, freq, lag)
            std = np.std(dailyReturns)
            return std

        def __func_getEquity_value(__equity_ratio, __risk_money, __confidence_ratio):
            __equity_list = list(__equity_ratio.keys())
            __curVaR = 0
            __portfolio_VaR = 0

            for stock in __equity_list:
                # # 每股的 VaR，VaR = 上一日的价格 * 置信度换算得来的标准倍数 * 日收益率的标准差
                __portfolio_VaR += __confidence_ratio * __func_getStd(stock, '1d', 120) * __equity_ratio[stock]
                
            if __portfolio_VaR:
                __equity_value = __risk_money / __portfolio_VaR
            else:
                __equity_value = 0

            if np.isnan(__equity_value):
                __equity_value = 0

            # print __equity_value
            # print __portfolio_VaR
                
            return __equity_value

        risk_money = self.risk_money
        equity_value, bonds_value = 0, 0

        equity_value = __func_getEquity_value(equity_ratio, risk_money, self.confidencelevel)
        portfolio_value = context.portfolio.portfolio_value
        if equity_value > portfolio_value:
            portfolio_value = equity_value  # TODO: 是否有误？equity_value = portfolio_value?
            bonds_value = 0
        else:
            bonds_value = portfolio_value - equity_value
        trade_ratio = {}
        equity_list = list(equity_ratio.keys())
        for stock in equity_list:
            if stock in trade_ratio:
                trade_ratio[stock] += round((equity_value * equity_ratio[stock] / portfolio_value), 3)
            else:
                trade_ratio[stock] = round((equity_value * equity_ratio[stock] / portfolio_value), 3)

        # 没有对 bonds 做配仓，因为只有一个
        if self.moneyfund:
            stock = self.moneyfund[0]
            if stock in trade_ratio:
                trade_ratio[stock] += round((bonds_value * 1.0 / portfolio_value), 3)
            else:
                trade_ratio[stock] = round((bonds_value * 1.0 / portfolio_value), 3)
        log.info('trade_ratio: %s' % trade_ratio)
        return trade_ratio

    # 交易函数
    def func_trade(self, context, trade_ratio):
        def __func_trade(context, stock, value):
            log.info(stock + " 调仓到 " + str(round(value, 2)) + "\n")
            order_target_value(stock, value)

        def __func_tradeBond(context, stock, Value):
            hStocks = history(1, '1d', 'close', stock, df=False)
            curPrice = hStocks[stock]
            curValue = float(context.portfolio.positions[stock].total_amount * curPrice)
            deltaValue = abs(Value - curValue)
            if deltaValue > (curPrice * 100):
                if Value > curValue:
                    cash = context.portfolio.cash
                    if cash > (curPrice * 100):
                        __func_trade(context, stock, Value)
                else:
                    # 如果是银华日利，多卖 100 股，避免个股买少了
                    if stock == self.moneyfund[0]:
                        Value -= curPrice * 100
                    __func_trade(context, stock, Value)

        def __func_tradeStock(context, stock, ratio):
            total_value = context.portfolio.portfolio_value
            if stock in self.moneyfund:
                __func_tradeBond(context, stock, total_value * ratio)
            else:
                curPrice = history(1, '1d', 'close', stock, df=False)[stock][-1]
                curValue = context.portfolio.positions[stock].total_amount * curPrice
                Quota = total_value * ratio
                if Quota:
                    if abs(Quota - curValue) / Quota >= 0.25:
                        if Quota > curValue:
                            cash = context.portfolio.cash
                            if cash >= Quota * 0.25:
                                __func_trade(context, stock, Quota)
                        else:
                            __func_trade(context, stock, Quota)
                else:
                    __func_trade(context, stock, Quota)

        trade_list = list(trade_ratio.keys())

        hStocks = history(1, '1d', 'close', trade_list, df=False)

        myholdstock = list(context.portfolio.positions.keys())
        total_value = context.portfolio.portfolio_value

        # 已有仓位
        holdDict = {}
        hholdstocks = history(1, '1d', 'close', myholdstock, df=False)
        for stock in myholdstock:
            tmpW = round((context.portfolio.positions[stock].total_amount * hholdstocks[stock]) / total_value, 2)
            holdDict[stock] = float(tmpW)

        # 对已有仓位做排序
        tmpDict = {}
        for stock in holdDict:
            if stock in trade_ratio:
                tmpDict[stock] = round((trade_ratio[stock] - holdDict[stock]), 2)
        tradeOrder = sorted(tmpDict.items(), key=lambda d: d[1], reverse=False)

        _tmplist = []
        for idx in tradeOrder:
            stock = idx[0]
            __func_tradeStock(context, stock, trade_ratio[stock])
            _tmplist.append(stock)

        # 交易其他股票
        for i in range(len(trade_list)):
            stock = trade_list[i]
            if len(_tmplist) != 0:
                if stock not in _tmplist:
                    __func_tradeStock(context, stock, trade_ratio[stock])
            else:
                __func_tradeStock(context, stock, trade_ratio[stock])
