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
from ta_analysis import *
from oop_strategy_frame import *
from common_include import *
from sector_selection import *
import statsmodels.api as sm
from pandas import Series, DataFrame
# from ML_main import *
import os
import math
# import tensorflow as tf
# os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2' 

class Stop_loss_by_price(Rule):
    def __init__(self, params):
        self.index = params.get('index', '000001.XSHG')
        self.num_of_days = params.get('num_of_days', 160)
        self.multiple = params.get('multiple', 2.2)
        self.is_day_stop_loss_by_price = False

    def update_params(self, context, params):
        self.index = params.get('index', self.index)
        self.num_of_days = params.get('num_of_days', self.num_of_days)
        self.multiple = params.get('multiple', self.multiple)

    def handle_data(self, context, data):
        # 大盘指数前130日内最高价超过最低价2倍，则清仓止损
        # 基于历史数据判定，因此若状态满足，则当天都不会变化
        # 增加此止损，回撤降低，收益降低

        if not self.is_day_stop_loss_by_price:
            h = attribute_history(self.index, self.num_of_days, unit='1d', fields=('close', 'high', 'low'),
                                  skip_paused=True)
            low_price_130 = h.low.min()
            high_price_130 = h.high.max()
            if high_price_130 > self.multiple * low_price_130 and h['close'][-1] < h['close'][-4] * 1 and h['close'][
                -1] > h['close'][-100]:
                # 当日第一次输出日志
                self.log.info("==> 大盘止损，%s指数前130日内最高价超过最低价2倍, 最高价: %f, 最低价: %f" % (
                    get_security_info(self.index).display_name, high_price_130, low_price_130))
                self.is_day_stop_loss_by_price = True

        if self.is_day_stop_loss_by_price:
            self.g.clear_position(self, context, self.g.op_pindexs)
        self.is_to_return = self.is_day_stop_loss_by_price

    def before_trading_start(self, context):
        self.is_day_stop_loss_by_price = False
        pass

    def __str__(self):
        return '大盘高低价比例止损器:[指数: %s] [参数: %s日内最高最低价: %s倍] [当前状态: %s]' % (
            self.index, self.num_of_days, self.multiple, self.is_day_stop_loss_by_price)

''' ----------------------三乌鸦止损------------------------------'''
class Stop_loss_by_3_black_crows(Rule):
    def __init__(self,params):
        self.index = params.get('index','000001.XSHG')
        self.dst_drop_minute_count = params.get('dst_drop_minute_count',60)
        # 临时参数
        self.is_last_day_3_black_crows = False
        self.cur_drop_minute_count = 0
        
    def update_params(self,context,params):
        self.index = params.get('index',self.index)
        self.dst_drop_minute_count = params.get('dst_drop_minute_count',self.dst_drop_minute_count)

    def initialize(self,context):
        pass

    def handle_data(self,context,data):
        # 前日三黑鸦，累计当日每分钟涨幅<0的分钟计数
        # 如果分钟计数超过一定值，则开始进行三黑鸦止损
        # 避免无效三黑鸦乱止损
        if self.is_last_day_3_black_crows:
            if get_growth_rate(self.index,1) < 0:
                self.cur_drop_minute_count += 1

            if self.cur_drop_minute_count >= self.dst_drop_minute_count:
                if self.cur_drop_minute_count == self.dst_drop_minute_count:
                    self.log.info("==> 超过三黑鸦止损开始")

                self.g.clear_position(self, context, self.g.op_pindexs)
                self.is_to_return = True
        else:
            self.is_to_return = False
        pass

    def before_trading_start(self,context):
        self.is_last_day_3_black_crows = self.is_3_black_crows(self.index)
        if self.is_last_day_3_black_crows:
            self.log.info("==> 前4日已经构成三黑鸦形态")
        pass

    def after_trading_end(self,context):
        self.is_last_day_3_black_crows = False
        self.cur_drop_minute_count = 0
        pass

    def __str__(self):
        return '大盘三乌鸦止损器:[指数: %s] [跌计数分钟: %d] [当前状态: %s]' % (
            self.index,self.dst_drop_minute_count,self.is_last_day_3_black_crows)

    '''~~~~~~~~~~~~~~~~~~~~~~~~~~~基础函数~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'''
    def is_3_black_crows(self, stock):
        # talib.CDL3BLACKCROWS
    
        # 三只乌鸦说明来自百度百科
        # 1. 连续出现三根阴线，每天的收盘价均低于上一日的收盘
        # 2. 三根阴线前一天的市场趋势应该为上涨
        # 3. 三根阴线必须为长的黑色实体，且长度应该大致相等
        # 4. 收盘价接近每日的最低价位
        # 5. 每日的开盘价都在上根K线的实体部分之内；
        # 6. 第一根阴线的实体部分，最好低于上日的最高价位
        #
        # 算法
        # 有效三只乌鸦描述众说纷纭，这里放宽条件，只考虑1和2
        # 根据前4日数据判断
        # 3根阴线跌幅超过4.5%（此条件忽略）
    
        h = attribute_history(stock,4,'1d',('close','open'),skip_paused=True,df=False)
        h_close = list(h['close'])
        h_open = list(h['open'])
    
        if len(h_close) < 4 or len(h_open) < 4:
            return False
    
        # 一阳三阴
        if h_close[-4] > h_open[-4] \
            and (h_close[-1] < h_open[-1] and h_close[-2] < h_open[-2] and h_close[-3] < h_open[-3]):
            # and (h_close[-1] < h_close[-2] and h_close[-2] < h_close[-3]) \
            # and h_close[-1] / h_close[-4] - 1 < -0.045:
            return True
        return False

# machine learning timing check
class ML_Stock_Timing(Rule):
    def __init__(self, params):
        self.ml_predict_file_path = params.get('ml_file_path', None)
        self.only_take_long_stocks = params.get('only_take_long_stocks', False)
        self.clear_candidate_if_AI_failed = params.get('force_no_candidate', False)
        self.add_etf = params.get('add_etf', True)
        self.ml_categories = params.get('ml_categories', 4)
        self.use_day_only = params.get('use_day_only', False)
        self.use_week_only = params.get('use_week_only', False)
        self.use_strict_mode = params.get('use_strict_mode', False)
        
    def update_params(self, context, params):
        self.only_take_long_stocks = params.get('only_take_long_stocks', True)
        self.clear_candidate_if_AI_failed = params.get('force_no_candidate', True)
        self.add_etf = params.get('add_etf', True)
        self.ml_categories = params.get('ml_categories', 4)
        self.use_day_only = params.get('use_day_only', False)
        self.use_week_only = params.get('use_week_only', False)
        self.use_strict_mode = params.get('use_strict_mode', False)
    
    def ml_prediction(self, stock_list, context):
        from ML_main import ML_biaoli_check
        mbc_weekly = ML_biaoli_check({'rq':False, 
                               'ts':False,
                               'model_path':'training_model/cnn_lstm_model_base_weekly2.h5', 
                               'isAnal':False,
                               'extra_training':False,
                               'extra_training_period':90,
                               'save_new_model':False,
                               'long_threthold':0.9, 
                               'short_threthold':0.9, 
                               'isDebug':False,
                               'use_latest_pivot':True, 
                               'use_standardized_sub_df':True,
                               'use_cnn_lstm':True,
                               'use_cnn':False,
                               'check_level':['5d','1d'],
                               'sub_level_max_length':240
                              })
        
        mbc_day = ML_biaoli_check({'rq':False, 
                               'ts':False,
                               'model_path':'training_model/cnn_lstm_model_base2.h5', 
                               'isAnal':False,
                               'extra_training':False, 
                               'extra_training_period':250, # 1250
                               'save_new_model':False,
                               'long_threthold':0.9, 
                               'short_threthold':0.9, 
                               'isDebug':False, 
                               'use_latest_pivot':True, 
                               'use_standardized_sub_df':True,
                               'use_cnn_lstm':True,
                               'use_cnn':False,
                               'check_level':['1d','30m'],
                               'sub_level_max_length':400})
    
        stock_list.sort()
        weekly_gauge_results = mbc_weekly.gauge_stocks_analysis(stock_list, check_status=True, today_date=context.current_dt.date())
        daily_gauge_results = mbc_day.gauge_stocks_analysis(stock_list, check_status=True, today_date=context.current_dt.date())
        
        combined_results = zip(weekly_gauge_results, daily_gauge_results)
#         print("combined_result: {0}".format(combined_results))
        
        result = {}
        result[str(context.current_dt.date())]=[(stock, 1 if (long_week and long_day) else 0, 1 if (short_week or short_day) else 0) 
                                for (stock, (long_week, short_week)), (stock, (long_day, short_day)) in combined_results]

        return result
        
    def use_ml_data(self, context, trading_details):
        trade_dict = {}
        for trades in trading_details:
            stock, buy, sell = trades
            trade_dict[stock] = (buy, sell)
            
        # sell holding stocks if found # no need to do it
        hold_stocks_to_check = [stock for stock in context.portfolio.positions.keys() if stock not in g.money_fund]
        for stock in hold_stocks_to_check:
            if stock not in trade_dict:
                continue            
            (buy, sell) = trade_dict[stock]
            if sell == 1:
                self.g.sell_stocks.append(stock)
                if stock in context.portfolio.positions.keys():
                    print("stock {0} closed".format(stock))
                    self.g.close_position(self, context.portfolio.positions[stock], True, 0)
        
        # filter in long point stocks
        stocks_to_remove = []
        stocks_to_long = []
        check_list = self.g.buy_stocks + g.etf if self.add_etf else self.g.buy_stocks
        for stock in check_list:
            if stock not in trade_dict:
                continue
            (buy, sell) = trade_dict[stock]
            if sell == 1:
                self.g.sell_stocks.append(stock)
                stocks_to_remove.append(stock)
            if buy == 1:
                stocks_to_long.append(stock)
#             print("stocks to remove: {0}".format(stocks_to_remove))
        if self.only_take_long_stocks:
            self.g.buy_stocks = stocks_to_long
        else:
            self.g.buy_stocks = [stock for stock in self.g.buy_stocks if stock not in stocks_to_remove]
    
    def use_ml_data_4_day(self, context, trading_details):
        trade_dict = {}
        for trades in trading_details:
            stock, week_status, day_status = trades
            trade_dict[stock] = (week_status, day_status)

        # Dealing with potential long candidate
        stocks_to_remove = []
        stocks_to_long = []

        # Dearling with Holding stocks
        hold_stocks_to_check = [stock for stock in context.portfolio.positions.keys() if stock not in g.money_fund]
        for stock in hold_stocks_to_check:
            if stock not in trade_dict:
                continue
            (ws, ds) = trade_dict[stock]
            if math.isclose(ds,0.0) or math.isclose(ds, 1.0) or math.isclose(ds, -0.5): 
                self.g.sell_stocks.append(stock)
                stocks_to_remove.append(stock)
                if stock in context.portfolio.positions.keys():
                    print("stock {0} closed".format(stock))
                    self.g.close_position(self, context.portfolio.positions[stock], True, 0)
            else:
                stocks_to_long.append(stock)

        check_list = [stock for stock in (self.g.buy_stocks + g.etf if self.add_etf else self.g.buy_stocks) if stock not in hold_stocks_to_check]
        for stock in check_list:
            if stock not in trade_dict:
                continue
            (ws, ds) = trade_dict[stock]
            if math.isclose(ds,0.0) or math.isclose(ds,1.0) or math.isclose(ds,-0.5):
                self.g.sell_stocks.append(stock)
                stocks_to_remove.append(stock)
                
            if math.isclose(ds,-1) or math.isclose(ds,0.5):
                stocks_to_long.append(stock) 
        # combine the existing holdings and preserve the order
        if self.only_take_long_stocks:
            self.g.buy_stocks = stocks_to_long
        else:
            self.g.buy_stocks = [stock for stock in self.g.buy_stocks if stock not in stocks_to_remove]
            
    def use_ml_data_4_week(self, context, trading_details):
        trade_dict = {}
        for trades in trading_details:
            stock, week_status, day_status = trades
            trade_dict[stock] = (week_status, day_status)

        # Dealing with potential long candidate
        stocks_to_remove = []
        stocks_to_long = []

        # Dearling with Holding stocks
        hold_stocks_to_check = [stock for stock in context.portfolio.positions.keys() if stock not in g.money_fund]
        for stock in hold_stocks_to_check:
            if stock not in trade_dict:
                continue
            (ws, ds) = trade_dict[stock]
            if math.isclose(ws,0.0) or math.isclose(ws, 1.0) or math.isclose(ws): 
                self.g.sell_stocks.append(stock)
                stocks_to_remove.append(stock)
                if stock in context.portfolio.positions.keys():
                    print("stock {0} closed".format(stock))
                    self.g.close_position(self, context.portfolio.positions[stock], True, 0)
            else:
                stocks_to_long.append(stock)

        check_list = [stock for stock in (self.g.buy_stocks + g.etf if self.add_etf else self.g.buy_stocks) if stock not in hold_stocks_to_check]
        for stock in check_list:
            if stock not in trade_dict:
                continue
            (ws, ds) = trade_dict[stock]
            if math.isclose(ws,0.0) or math.isclose(ws,1.0) or math.isclose(ws,-0.5):
                self.g.sell_stocks.append(stock)
                stocks_to_remove.append(stock)
                
            if math.isclose(ws,-1) or math.isclose(ws,0.5):
                stocks_to_long.append(stock) 
        # combine the existing holdings and preserve the order
        if self.only_take_long_stocks:
            self.g.buy_stocks = stocks_to_long
        else:
            self.g.buy_stocks = [stock for stock in self.g.buy_stocks if stock not in stocks_to_remove]
    
    def use_ml_data_4(self, context, trading_details):    
        trade_dict = {}
        for trades in trading_details:
            stock, week_status, day_status = trades
            trade_dict[stock] = (week_status, day_status)

        # Dealing with potential long candidate
        stocks_to_remove = []
        stocks_to_long = []

        # Dearling with Holding stocks
        hold_stocks_to_check = [stock for stock in context.portfolio.positions.keys() if stock not in g.money_fund]
#         print(hold_stocks_to_check)
        for stock in hold_stocks_to_check:
            if stock not in trade_dict:
                continue
            (ws, ds) = trade_dict[stock]
            if (math.isclose(ds,0.0) or math.isclose(ds, 1.0) or math.isclose(ds,-0.5)):
                self.g.sell_stocks.append(stock)
                stocks_to_remove.append(stock)
                if stock in context.portfolio.positions.keys():
                    print("stock {0} closed".format(stock))
                    self.g.close_position(self, context.portfolio.positions[stock], True, 0)                
            elif ((math.isclose(ws, 0.0) or math.isclose(ws,1.0) or math.isclose(ws,-0.5)) and \
                  (math.isclose(ds,-1) or math.isclose(ds,0.5))):
                if self.use_strict_mode:
                    self.g.sell_stocks.append(stock)
                    stocks_to_remove.append(stock)
                    if stock in context.portfolio.positions.keys():
                        print("stock {0} closed".format(stock))
                        self.g.close_position(self, context.portfolio.positions[stock], True, 0)   
                    pass # do nothing for holding behaviour                   
                else:
                    self.g.position_proportion[stock] = 0.5
                    stocks_to_long.append(stock)
            else:
                self.g.position_proportion[stock] = 1.0
                stocks_to_long.append(stock)

        check_list = [stock for stock in (self.g.buy_stocks + g.etf if self.add_etf else self.g.buy_stocks) if stock not in hold_stocks_to_check]
#         print(check_list)
        for stock in check_list:
            if stock not in trade_dict:
                continue
            (ws, ds) = trade_dict[stock]
            if math.isclose(ds,0.0) or math.isclose(ds,1.0) or math.isclose(ds,-0.5):
                self.g.sell_stocks.append(stock)
                stocks_to_remove.append(stock)
                
            elif((math.isclose(ws, 0.0) or math.isclose(ws,1.0) or math.isclose(ws,-0.5)) and \
                  (math.isclose(ds,-1) or math.isclose(ds,0.5))):
                if self.use_strict_mode:
                    self.g.sell_stocks.append(stock)
                    stocks_to_remove.append(stock)   
                    pass # do nothing for other case           
                else:
                    stocks_to_long.append(stock)
                    self.g.position_proportion[stock] = 0.5  
            elif (math.isclose(ws,-1) or math.isclose(ws, 0.5)) and \
                (math.isclose(ds,-1) or math.isclose(ds, 0.5)):
                stocks_to_long.append(stock)
                self.g.position_proportion[stock] = 1.0  
#             print("stocks to long: {0}".format(stocks_to_long))
#             print("stocks to remove: {0}".format(stocks_to_remove))
        # combine the existing holdings and preserve the order
        if self.only_take_long_stocks:
            self.g.buy_stocks = stocks_to_long
        else:
            self.g.buy_stocks = [stock for stock in self.g.buy_stocks if stock not in stocks_to_remove]

    def handle_data(self, context, data):
        today_date = context.current_dt.date()
        try:
            if self.ml_predict_file_path: # model prediction happened outside
                trading_list = json.loads(read_file(self.ml_predict_file_path).decode())
            else:
                checking_list = list(set(self.g.buy_stocks+list(context.portfolio.positions.keys())))
                trading_list = self.ml_prediction(checking_list, context)
                
            trading_details = trading_list[str(today_date)]

            if self.ml_categories == 3:
                self.use_ml_data(context, trading_details)
            elif self.ml_categories == 4:
                if self.use_day_only:
                    self.use_ml_data_4_day(context, trading_details)
                elif self.use_week_only:
                    self.use_ml_data_4_week(context, trading_details)
                else:
                    self.use_ml_data_4(context, trading_details)

            self.log.info("ML择时结果: "+join_list([show_stock(stock) for stock in self.g.buy_stocks], ' ', 10))
            # make sure ML predict use check_status
        except Exception as e:
            print(str(e))
            self.log.warn("ML prediction data missing: {0} {1}".format(self.ml_predict_file_path, str(today_date)))
            if self.clear_candidate_if_AI_failed:
                self.g.buy_stocks = []
            return
            
        
    def after_trading_end(self, context):
        self.g.position_proportion = {}
        Rule.after_trading_end(self, context)
        
    def __str__(self):
        return '股票AI择时'


class Relative_Index_Timing(Rule):
    def __init__(self, params):
        self.market_list = params.get('market_list', ['000300.XSHG', '000016.XSHG', '399333.XSHE', '000905.XSHG', '399673.XSHE'])
        self.M = params.get('M', 600)
        self.N = params.get('N', 18)
        self.buy = params.get('buy', 0.7)
        self.sell = params.get('sell', -0.7)
        self.period = params.get('correlation_period', 250)
        self.strict_long = params.get('strict_long', False)
        self.default_index = self.market_list[0]
        self.rsrs_check = RSRS_Market_Timing({'market_list': self.market_list,
                                              'M':self.M,
                                              'N':self.N,
                                              'buy':self.buy,
                                              'sell':self.sell})
        self.isInitialized = False
        
    def update_params(self, context, params):
        self.period = params.get('correlation_period', 250)
        self.strict_long = params.get('strict_long', False)
        
    def before_trading_start(self, context):
        Rule.before_trading_start(self, context)
        if not self.isInitialized:
            self.rsrs_check.calculate_RSRS()
            self.isInitialized = True
        else:
            self.rsrs_check.add_new_RSRS()
            
        for market in self.market_list:
            self.g.market_timing_check[market]=self.rsrs_check.check_timing(market)
        self.log.info("Index timing check: {0}".format(self.g.market_timing_check))
        
    def after_trading_end(self, context):
        Rule.after_trading_end(self, context)
        self.g.stock_index_dict = {}
        self.g.market_timing_check = {}
        
    def build_stock_index_dict(self, context):
        # find the index for candidate stock by largest correlation
        stock_symbol_list = [stock for stock in list(set(context.portfolio.positions.keys() + self.g.monitor_buy_list)) if stock not in g.money_fund]
        for stock in stock_symbol_list:
            current_max_corr = 0
            stock_df = attribute_history(stock, self.period, '1d', 'close', df=False)
            for idx in self.market_list:
                index_df = attribute_history(idx, self.period, '1d', 'close', df=False)
                corr = np.corrcoef(stock_df['close'],index_df['close'])[0,1]
                if corr >= current_max_corr:
                    self.g.stock_index_dict[stock] = idx
                    current_max_corr = corr
            if stock not in self.g.stock_index_dict:
                self.g.stock_index_dict[stock] = self.default_index
                self.log.info("{0} set to default index {1}".format(stock, self.default_index))
        self.log.info("stock index correlation matrix: {0}".format(self.g.stock_index_dict))
        
    def handle_data(self, context, data):
        self.build_stock_index_dict(context)
        stocks_to_check = [stock for stock in list(set(context.portfolio.positions.keys() + self.g.monitor_buy_list)) if stock not in g.money_fund]
        for stock in stocks_to_check:
            market = self.g.stock_index_dict[stock]
            if self.g.market_timing_check[market] == -1:
                self.g.sell_stocks.append(stock)
                if stock in context.portfolio.positions.keys():
                    self.g.close_position(self, context.portfolio.positions[stock], True, 0)
                if stock in self.g.monitor_buy_list:
                    self.g.monitor_buy_list.remove(stock)
            if self.g.market_timing_check[market] != 1 and self.strict_long:
                if stock in self.g.monitor_buy_list:
                    self.g.monitor_buy_list.remove(stock)
        self.log.info("candidate stocks: {0} closed position: {1}".format(self.g.monitor_buy_list, self.g.sell_stocks))
    def __str__(self):
        return '股票精确择时'
    

# 个股止损止盈
class Stop_gain_loss_stocks(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        self.period = params.get('period', 3)
        self.stop_loss = params.get('stop_loss', 0.03)
        self.stop_gain = params.get('stop_gain', 0.2)
        self.enable_stop_loss = params.get('enable_stop_loss',False)
        self.enable_stop_gain = params.get('enable_stop_gain',False)
        self.last_high = {}
        self.pct_change = {}
    def update_params(self,context,params):
        self.period = params.get('period',self.period)    
        
    def handle_data(self,context,data):
        for stock in context.portfolio.positions.keys():
            position = context.portfolio.positions[stock]
            cur_price = data[stock].close
            loss_threthold = self.__get_stop_loss_threshold(stock,self.period) if self.stop_loss == 0.0 else self.stop_loss
            xi = attribute_history(stock,2,'1d','high',skip_paused=True)
            ma = xi['high'].max()
            if stock in self.last_high:
                if self.last_high[stock] < cur_price:
                    self.last_high[stock] = cur_price
            else:
                self.last_high[stock] = ma

            if self.enable_stop_loss and cur_price < self.last_high[stock] * (1 - loss_threthold):
                self.log.info("==> 个股止损, stock: %s, cur_price: %f, last_high: %f, threshold: %f"
                    % (stock,cur_price,self.last_high[stock],loss_threthold))
                position = context.portfolio.positions[stock]
                self.g.close_position(self, position, True, 0)
                self.g.sell_stocks.append(stock)
                
            profit_threshold = self.__get_stop_profit_threshold(stock,self.period) if self.stop_gain == 0.0 else self.stop_gain
            if self.enable_stop_gain and cur_price > position.avg_cost * (1 + profit_threshold):
                self.log.info("==> 个股止盈, stock: %s, cur_price: %f, avg_cost: %f, threshold: %f"
                    % (stock,cur_price,self.last_high[stock],profit_threshold))
                position = context.portfolio.positions[stock]
                self.g.close_position(self, position, True, 0) 
                self.g.sell_stocks.append(stock)     
    
    # 获取个股前n天的m日增幅值序列
    # 增加缓存避免当日多次获取数据
    def __get_pct_change(self,security,n,m):
        pct_change = None
        if security in self.pct_change.keys():
            pct_change = self.pct_change[security]
        else:
            h = attribute_history(security,n,unit='1d',fields=('close'),skip_paused=True)
            pct_change = h['close'].pct_change(m)  # 3日的百分比变比（即3日涨跌幅）
            self.pct_change[security] = pct_change
        return pct_change

    # 计算个股回撤止损阈值
    # 即个股在持仓n天内能承受的最大跌幅
    # 算法：(个股250天内最大的n日跌幅 + 个股250天内平均的n日跌幅)/2
    # 返回正值
    def __get_stop_loss_threshold(self,security,n=3):
        pct_change = self.__get_pct_change(security,250,n)
        # log.debug("pct of security [%s]: %s", pct)
        maxd = pct_change.min()
        # maxd = pct[pct<0].min()
        avgd = pct_change.mean()
        # avgd = pct[pct<0].mean()
        # maxd和avgd可能为正，表示这段时间内一直在增长，比如新股
        bstd = (maxd + avgd) / 2

        # 数据不足时，计算的bstd为nan
        if not np.isnan(bstd):
            if bstd != 0:
                return abs(bstd)
            else:
                # bstd = 0，则 maxd <= 0
                if maxd < 0:
                    # 此时取最大跌幅
                    return abs(maxd)
        return 0.099  # 默认配置回测止损阈值最大跌幅为-9.9%，阈值高貌似回撤降低    
    
    # 计算个股止盈阈值
    # 算法：个股250天内最大的n日涨幅
    # 返回正值
    def __get_stop_profit_threshold(self,security,n=3):
        pct_change = self.__get_pct_change(security,250,n)
        maxr = pct_change.max()

        # 数据不足时，计算的maxr为nan
        # 理论上maxr可能为负
        if (not isnan(maxr)) and maxr != 0:
            return abs(maxr)
        return 0.30  # 默认配置止盈阈值最大涨幅为30%    
    
    def after_trading_end(self,context):
        self.pct_change = {}
        pass

    def __str__(self):
        return '个股止损止盈器:[当前缓存价格数: %d ] 默认阈值止损%s [enabled:%s] 止盈%s [enabled:%s]' % (len(self.last_high), self.stop_loss, self.enable_stop_loss, self.stop_gain, self.enable_stop_gain)

class ATR_stoploss(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        self.stop = params.get('stop', 2)
        self.NATRstop = params.get('NATRstop', 6)
        self.ATR_period = params.get('ATR_period', 14)
        self.MaxLoss = params.get('MaxLoss', 0.1)
        self.HighPrice = {}

    def update_params(self,context,params):
        self.stop = params.get('stop', 2)
        self.NATRstop = params.get('NATRstop', 6)
        self.ATR_period = params.get('ATR_period', 14)
        self.MaxLoss = params.get('MaxLoss', 0.1)
        self.HighPrice = {}

    def handle_data(self,context,data): 
        for stock in context.portfolio.positions.keys():
            if context.portfolio.positions[stock].closeable_amount > 0:
                stock_price = context.portfolio.positions[stock].price
                if stock in self.HighPrice:
                    self.HighPrice[stock] = max(self.HighPrice[stock], stock_price)
                    if stock_price  < context.portfolio.positions[stock].avg_cost-self.stop*self.ATR(context,stock):
                        log.info('股票硬止损:\t' +  stock)
                        self.g.close_position(self, context.portfolio.positions[stock], True, 0) 
                        self.g.sell_stocks.append(stock)
                        del self.HighPrice[stock]
                    elif stock_price  < self.HighPrice[stock]  - self.NATRstop*self.ATR(context,stock):
                        log.info('股票追踪止损:\t' +  stock)
                        self.g.close_position(self, context.portfolio.positions[stock], True, 0) 
                        self.g.sell_stocks.append(stock)
                        del self.HighPrice[stock]
                else:
                    self.HighPrice[stock] = stock_price

    def ATR(self, context,stock):
        PriceArray= get_price(stock, '2005-01-05', context.previous_date, '1d', ['close','high','low'])
        close=PriceArray['close'].apply(lambda x: 0.00 if np.isnan(x) else x)#把NaN替换为0
        high=PriceArray['high'].apply(lambda x: 0.00 if np.isnan(x) else x)#把NaN替换为0
        low=PriceArray['low'].apply(lambda x: 0.00 if np.isnan(x) else x)#把NaN替换为0
        close = np.array(close)
        high = np.array(high)
        low = np.array(low)
        ATR = talib.ATR(high,low,close, self.ATR_period)[-1]
        return ATR

    def __str__(self):
        return 'ATR追踪止损:[参数: ATR硬止损倍数%s] [ATR追踪止损倍数: %s] [ATR计算周期: %s] [MaxLoss: %s] [各品种最高价字典: %s]' % (
            self.stop, self.NATRstop, self.ATR_period, self.MaxLoss, self.HighPrice)

# 资金曲线保护  
class equity_curve_protect(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        self.num_of_days = params.get('num_of_days', 20)
        self.percent = params.get('percent', 0.01)
        self.use_avg = params.get('use_avg', False)
        self.market_index = params.get('market_index', None)
        self.is_day_curve_protect = False
        self.port_value_record = []
        self.debug = params.get('debug', False)
        self.use_std = params.get('use_std', 35)
        self.use_zscore_left = params.get('use_zscore_left', -2.58) # left tail 99% -1.96 95%
        self.use_zscore_right = params.get('use_zscore_right', 2.807) # 99.5%
        self.use_pct = params.get('use_pct', True)
        self.use_log = params.get('use_log', True)
        self.clear_count = params.get('clear_count', 20)
    
    def update_params(self, context, params):
#         self.percent = params.get('percent', self.percent)
#         self.num_of_days = params.get('num_of_days', self.num_of_days)
#         self.use_avg = params.get('use_avg', self.use_avg)
        pass

    def portvalue_change_by_stats_toomuch(self, new_port_val):
        port_data_stats = []
        if self.use_pct:
            i = 0
            while i < len(self.port_value_record) - 1:
                port_data_stats.append((self.port_value_record[i+1] - self.port_value_record[i]) / self.port_value_record[i])
                i += 1
                
            port_data_stats = np.array(port_data_stats)
            new_change = (new_port_val - self.port_value_record[-1]) / self.port_value_record[-1]
        elif self.use_log:
            port_data_stats = np.log(self.port_value_record)
            new_change = np.log(new_port_val)
        else:
            port_data_stats = np.array(self.port_value_record)
            new_change = new_port_val
        
        ppc_std = np.std(port_data_stats)
        ppc_mean = np.mean(port_data_stats)
        nc_zscore = (new_change - ppc_mean) / ppc_std
        
        if self.debug:
            self.log.info("zscore:{0}".format(nc_zscore))        

        return (nc_zscore <= self.use_zscore_left or nc_zscore >= self.use_zscore_right) and\
            (self.port_value_record[-1] > self.port_value_record[0] if not self.use_pct else len([x for x in port_data_stats if x > 0]) > self.use_std * 2 // 3), nc_zscore
    
    def handle_data(self, context, data):
        if not self.is_day_curve_protect :
            cur_value = context.portfolio.total_value
            
            if self.use_std > 0 and len(self.port_value_record) >= self.use_std:
                changed_toomuch, zscore = self.portvalue_change_by_stats_toomuch(cur_value)
                if changed_toomuch:
                    self.log.info("==> 启动资金曲线保护, 当前资产: %f zscore: %f" %(cur_value, zscore))
                    self.is_day_curve_protect = True
                    self.is_to_return=True
            elif len(self.port_value_record) >= self.num_of_days:
                market_growth_rate = get_growth_rate(self.market_index) if self.market_index else 0
                last_value = self.port_value_record[-self.num_of_days]
                if self.debug:
                    self.g.log("current_value:{0}".format(cur_value))
                    self.g.log("last_value:{0}".format(last_value))
                    self.g.log("market_growth_rate:{0}".format(market_growth_rate))
                if self.use_avg:
                    avg_value = sum(self.port_value_record[-self.num_of_days:]) / self.num_of_days
                    if cur_value < avg_value:
                        self.log.info("==> 启动资金曲线保护, %s日平均资产: %f, 当前资产: %f" %(self.num_of_days, avg_value, cur_value))
                        self.is_day_curve_protect = True  
                        self.is_to_return=True
                elif self.market_index:
                    if cur_value/last_value-1 >= 0: #持仓
                        pass
                    elif market_growth_rate < 0 and cur_value/last_value-1 < -self.percent: #清仓 今日不再买入
                        self.log.info("==> 启动资金曲线保护清仓, %s日资产增长: %f, 大盘增长: %f" %(self.num_of_days, cur_value/last_value-1, market_growth_rate))
                        self.is_day_curve_protect = True
                        self.is_to_return=True
                    elif market_growth_rate > 0 and cur_value/last_value-1 < -self.percent: # 换股
                        self.log.info("==> 启动资金曲线保护换股, %s日资产增长: %f, 大盘增长: %f" %(self.num_of_days, cur_value/last_value-1, market_growth_rate))
                        self.is_day_curve_protect = True
                else:
                    if cur_value <= last_value*(1-self.percent): 
                        self.log.info("==> 启动资金曲线保护, %s日前资产: %f, 当前资产: %f" %(self.num_of_days, last_value, cur_value))
                        self.is_day_curve_protect = True
                        self.is_to_return=True
        if self.is_day_curve_protect:
            self.g.curve_protect = True
            self.g.clear_position(self, context, self.g.op_pindexs)
            self.port_value_record = self.port_value_record[self.clear_count:]
            self.is_day_curve_protect = False

    def on_clear_position(self, context, pindexs=[0]):
        pass

    def before_trading_start(self, context):
        if not self.is_to_return:
            self.port_value_record.append(context.portfolio.total_value)
        if len(self.port_value_record) > self.num_of_days:
            self.port_value_record.pop(0)
        self.is_to_return=False
        self.g.curve_protect = False

    def __str__(self):
        return '大盘资金比例止损器:[参数: %s日前资产] [保护百分数: %s]' % (
            self.num_of_days, self.percent)

''' ----------------------最高价最低价比例止损------------------------------'''
class Stop_loss_by_growth_rate(Rule):
    def __init__(self,params):
        self.index = params.get('index','000001.XSHG')
        self.stop_loss_growth_rate = params.get('stop_loss_growth_rate', -0.03)
    def update_params(self,context,params):
        self.index = params.get('index','000001.XSHG')
        self.stop_loss_growth_rate = params.get('stop_loss_growth_rate', -0.03)

    def handle_data(self,context,data):
        if self.is_to_return:
            return
        cur_growth_rate = get_growth_rate(self.index,1)
        if cur_growth_rate < self.stop_loss_growth_rate:
            self.log_warn('当日涨幅 [%s : %.2f%%] 低于阀值 %.2f%%,清仓止损!' % (self.index,
                cur_growth_rate * 100,self.stop_loss_growth_rate))
            self.is_to_return = True
            self.g.clear_position(context)
            return
        self.is_to_return = False

    def before_trading_start(self,context):
        self.is_to_return = False

    def __str__(self):
        return '指数当日涨幅限制止损器:[指数: %s] [最低涨幅: %.2f%%]' % (
                self.index,self.stop_loss_growth_rate * 100)


''' ----------------------28指数值实时进行止损------------------------------'''
class Stop_loss_by_28_index(Rule):
    def __init__(self,params):
        self.index2 = params.get('index2','')
        self.index8 = params.get('index8','')
        self.index_growth_rate = params.get('index_growth_rate',0.01)
        self.dst_minute_count_28index_drop = params.get('dst_minute_count_28index_drop',120)
        # 临时参数
        self.minute_count_28index_drop = 0
    def update_params(self,context,params):
        self.index2 = params.get('index2',self.index2)
        self.index8 = params.get('index8',self.index8)
        self.index_growth_rate = params.get('index_growth_rate',self.index_growth_rate)
        self.dst_minute_count_28index_drop = params.get('dst_minute_count_28index_drop',self.dst_minute_count_28index_drop)
    def initialize(self,context):
        pass

    def handle_data(self,context,data):
        # 回看指数前20天的涨幅
        gr_index2 = get_growth_rate(self.index2)
        gr_index8 = get_growth_rate(self.index8)

        if gr_index2 <= self.index_growth_rate and gr_index8 <= self.index_growth_rate:
            if (self.minute_count_28index_drop == 0):
                self.log_info("当前二八指数的20日涨幅同时低于[%.2f%%], %s指数: [%.2f%%], %s指数: [%.2f%%]" \
                    % (self.index_growth_rate * 100,
                    get_security_info(self.index2).display_name,
                    gr_index2 * 100,
                    get_security_info(self.index8).display_name,
                    gr_index8 * 100))

            self.minute_count_28index_drop += 1
        else:
            # 不连续状态归零
            if self.minute_count_28index_drop < self.dst_minute_count_28index_drop:
                self.minute_count_28index_drop = 0

        if self.minute_count_28index_drop >= self.dst_minute_count_28index_drop:
            if self.minute_count_28index_drop == self.dst_minute_count_28index_drop:
                self.log_info("==> 当日%s指数和%s指数的20日增幅低于[%.2f%%]已超过%d分钟，执行28指数止损" \
                    % (get_security_info(self.index2).display_name,get_security_info(self.index8).display_name,self.index_growth_rate * 100,self.dst_minute_count_28index_drop))

            self.clear_position(context)
            self.is_to_return = False
        else:
            self.is_to_return = True
        pass

    def after_trading_end(self,context):
        self.is_to_return = False
        self.minute_count_28index_drop = 0
        pass

    def __str__(self):
        return '28指数值实时进行止损:[大盘指数: %s %s] [小盘指数: %s %s] [判定调仓的二八指数20日增幅 %.2f%%] [连续 %d 分钟则清仓] ' % (
                self.index2,get_security_info(self.index2).display_name,
                self.index8,get_security_info(self.index8).display_name,
                self.index_growth_rate * 100,
                self.dst_minute_count_28index_drop)



# '''-------------多指数N日涨幅止损------------'''
class Mul_index_stop_loss(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        self._indexs = params.get('indexs', [])
        self._min_rate = params.get('min_rate', 0.01)
        self._n = params.get('n', 20)

    def update_params(self, context, params):
        Rule.__init__(self, params)
        self._indexs = params.get('indexs', [])
        self._min_rate = params.get('min_rate', 0.01)
        self._n = params.get('n', 20)

    def handle_data(self, context, data):
        self.is_to_return = False
        r = []
        for index in self._indexs:
            gr_index = get_growth_rate(index, self._n)
            self.log.info('%s %d日涨幅  %.2f%%' % (show_stock(index), self._n, gr_index * 100))
            r.append(gr_index > self._min_rate)
        if sum(r) == 0:
            self.log.warn('不符合持仓条件，清仓')
            self.g.clear_position(self, context, self.g.op_pindexs)
            self.is_to_return = True
            
    def on_clear_position(self, context, pindexs=[0]):
        self.g.buy_stocks = []

    def after_trading_end(self, context):
        Rule.after_trading_end(self, context)
        for index in self._indexs:
            gr_index = get_growth_rate(index, self._n - 1)
            self.log.info('%s %d日涨幅  %.2f%% ' % (show_stock(index), self._n - 1, gr_index * 100))

    def __str__(self):
        return '多指数20日涨幅损器[指数:%s] [涨幅:%.2f%%]' % (str(self._indexs), self._min_rate * 100)


# '''-------------多指数止损------------'''
class Mul_index_stop_loss_ta(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        self._indexs = params.get('indexs', [])
        self._ta = params.get('ta_type', TaType.TRIX_PURE)
        self._n = params.get('n', 100)
        self._period = params.get('period', '1d')
    
    def handle_data(self, context, data):
        self.is_to_return = False
        if self._ta == TaType.TRIX_PURE:
            ta_trix_long = TA_Factor_Long({'ta_type':TaType.TRIX_PURE, 'period':self._period, 'count':self._n, 'isLong':True})
            long_list = ta_trix_long.filter(self._indexs)
            print(long_list)
            if len(long_list) == 0:
                self.log.warn('不符合持仓条件，清仓')
                self.g.clear_position(self, context, self.g.op_pindexs)
                self.is_to_return = True
            
    def on_clear_position(self, context, pindexs=[0]):
        self.g.buy_stocks = []

    def after_trading_end(self, context):
        Rule.after_trading_end(self, context)

    def __str__(self):
        return '多指数技术分析止损器[指数:%s] [TA:%s]' % (str(self._indexs), self._ta)

# '''-------------多指数平均止损------------'''
class Mul_index_stop_loss_avg(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        self._indexs = params.get('indexs', ['000001.XSHG', '399001.XSHE'])
        self._n = params.get('n', 30)
        
    def handle_data(self, context, data):
        total_index_previous_price = 0.0
        total_index_avg_price = 0.0
        for index_a in self._indexs:
            close_data = attribute_history(index_a, self._n , '1d', ['close'])
            total_index_avg_price += close_data['close'].mean()
            total_index_previous_price += close_data['close'][-1]

        # 取得过n天的平均价格
        avg_price = total_index_avg_price/len(self._indexs)
        # 取得上一时间点价格
        current_price = total_index_previous_price/len(self._indexs)
        # 取得现有仓位中的所有股票
        if current_price < avg_price:
            self.log.warn('不符合持仓条件，清仓')
            self.g.clear_position(self, context, self.g.op_pindexs)
            self.is_to_return = True
        else:
            pass

    def after_trading_end(self, context):
        Rule.after_trading_end(self, context)        

    def __str__(self):
        return '多指数平均止损[指数:%s] [Number of days:%s]' % (str(self._indexs), self._n)

'''-------------缠论走势强弱--------------'''
class Chan_market_timing(Rule):
    def __init__(self, params):
        self.strong_sector = params.get('strong_sector', True)
        self.sector_limit_pct = params.get('sector_limit_pct', 80)
        self.strength_threthold = params.get('strength_threthold', 100)
        self.period_frequency = params.get('period_frequency', 'W')
        self.useAvg = params.get('useAvg', False)
        self.isDaily = params.get('isDaily', True)
        self.avgPeriod = params.get('avgPeriod', 10)
        self.overheat_value = params.get('overheat_value', 144)
    
    def handle_data(self, context, data):
        ss = SectorSelection(limit_pct=self.sector_limit_pct, 
                isStrong=self.strong_sector, 
                min_max_strength=self.strength_threthold, 
                useIntradayData=False,
                useAvg=self.useAvg,
                avgPeriod=self.avgPeriod,
                isWeighted=self.isWeighted,
                effective_date=context.previous_date)
        ind, _ = ss.get_market_avg_strength(display=False)
        if ind > self.overheat_value:
            self.log.warn('不符合持仓条件，清仓. value: {0}'.format(ind))
            self.g.clear_position(self, context, self.g.op_pindexs)
            self.is_to_return = True
    
    def on_clear_position(self, context, pindexs=[0]):
        self.g.monitor_buy_list = []

    def after_trading_end(self, context):
        Rule.after_trading_end(self, context)
        
    def __str__(self):
        return '缠论强弱择时'

# '''-------------RSRS------------'''
class RSRS_timing(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        # 设置买入和卖出阈值
        self.buy = params.get('buy', 0.7)
        self.sell = params.get('sell', -0.7)
        
        # 设置RSRS指标中N, M的值
        self.N = params.get('N', 18)
        self.M = params.get('M', 600)
                
        self.beta_list = []
        self.R2 = []
        
        self.market_symbol = params.get('market_symbol', '000300.XSHG')
        self.init = False
        

    def handle_data(self, context, data):
        if not self.init:
            self.calculate_RSRS(context)
            self.init=True
        else:
            self.add_new_RSRS()
        
        self.log.info("handle data updated RSRS info: \n{0}:".format(self.beta_list[-3:]))
        
        self.check_timing(context)


    def check_timing(self, context):
        section = self.beta_list[-self.M:]
        mu = np.mean(section)
        sigma = np.std(section)
        zscore = (section-mu)/sigma
        
        zscore_rightdev = zscore[-1] * self.beta_list[-1] * self.R2[-1]
        
#         self.log.info("zscore_rightdev:{0}".format(zscore_rightdev))
#         self.log.info("zscore_rightdev:{0}".format(self.beta_list[-10:]))
#         self.log.info("zscore_rightdev:{0}".format(self.R2[-10:]))
        
        # 获得前10日交易量
        trade_vol10 = attribute_history(self.market_symbol, 10, '1d', 'volume')
        
        if zscore_rightdev > self.buy: 
#             np.corrcoef(np.array([trade_vol10['volume'].values, (np.array(self.R2[-10:]) * np.array(zscore[-10:]))]))[0,1] > 0:
            self.log.info("RSRS右偏标准分大于买入阈值, 且修正标准分与前10日交易量相关系数为正")
            
        # 如果上一时间点的右偏RSRS标准分小于卖出阈值, （且修正标准分与前10日交易量相关系数为正）则空仓卖出
        elif zscore_rightdev < self.sell:
            self.log.info("RSRS右偏标准分小于卖出阈值, 且修正标准分与前10日交易量相关系数为正")
            self.g.clear_position(self, context, self.g.op_pindexs)
            self.is_to_return = True 
        


    def on_clear_position(self, context, pindexs=[0]):
        self.g.monitor_buy_list = []

    def after_trading_end(self, context):
        Rule.after_trading_end(self, context)

    def calculate_RSRS(self, context):
        ## on-demand method
#         prices = attribute_history(self.market_symbol, self.M+self.N, '1d', ['high', 'low'])
        prices = get_price(self.market_symbol, '2005-01-05', context.previous_date, '1d', ['high', 'low'])
        prices[np.isnan(prices)] = 0
        prices[np.isinf(prices)] = 0

        highs = prices.high
        lows = prices.low
        for i in range(len(highs))[self.N:]:
            data_high = highs.iloc[i-self.N+1:i+1]
            data_low = lows.iloc[i-self.N+1:i+1]
            X = sm.add_constant(data_low)
            model = sm.OLS(data_high,X).fit()
            beta = model.params[1]
            r2 = model.rsquared
            self.beta_list.append(beta)
            self.R2.append(r2)
    
    def add_new_RSRS(self):
        prices = attribute_history(self.market_symbol, self.N, '1d', ['high', 'low'])
        highs = prices.high
        lows = prices.low
        X = sm.add_constant(lows)
        model = sm.OLS(highs, X).fit()
        beta = model.params[1]
        r2 = model.rsquared
        self.beta_list.append(beta)
        self.R2.append(r2)

    def __str__(self):
        return 'RSRS_rightdev[指数:%s]' % (str(self.market_symbol))
    

