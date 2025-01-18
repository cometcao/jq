# -*- encoding: utf8 -*-
'''
Created on 4 Dec 2017

@author: MetalInvest
'''
from oop_strategy_frame import *
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

        stock_list = self.g.buy_stocks
        for rule in self.rules:
            if isinstance(rule, Filter_stock_list):
                stock_list = rule.filter(context, data, stock_list)

        # add the ETF index into list this is already done in oop_stop_loss,
        # dirty hack
        self.g.monitor_buy_list = stock_list
        self.log.info(
            '今日选股:\n' + join_list(["[%s]" % (show_stock(x)) for x in stock_list], ' ', 10))
        self.has_run = True

    def before_trading_start(self, context):
        self.has_run = False
        # clear the buy list this variable stores the initial list of
        # candidates for the day
        self.g.buy_stocks = []
        for rule in self.rules:
            if isinstance(rule, Create_stock_list):
                self.g.buy_stocks = self.g.buy_stocks + \
                    rule.before_trading_start(context)

        for rule in self.rules:
            if isinstance(rule, Early_Filter_stock_list):
                rule.before_trading_start(context)

        for rule in self.rules:
            if isinstance(rule, Early_Filter_stock_list):
                self.g.buy_stocks = rule.filter(context, self.g.buy_stocks)

        checking_stocks = [stock for stock in list(set(
            self.g.buy_stocks + list(context.portfolio.positions.keys()))) if stock not in g.money_fund]
        if self.add_etf:
            checking_stocks = checking_stocks + g.etf
        if self.file_path:
            if self.file_path == "daily":
                write_file(
                    "daily_stocks/{0}.txt".format(str(context.current_dt.date())), ",".join(checking_stocks))
            else:
                write_file(self.file_path, ",".join(checking_stocks))
                self.log.info('file written:{0}'.format(self.file_path))

    def __str__(self):
        return self.memo


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
        try:
            with open(NOTEBOOK_PATH+self.filename,'rb') as f:
                stock_list = json.load(f)
        #定义空的全局字典变量
        except:
            self.log.info(f"file {self.filename} read failed hold on current positions")
            stock_list = list(context.portfolio.positions.keys())
        self.log.info("stocks {0} read from file {1}".format(
            stock_list, self.filename))
        return stock_list

    def __str__(self):
        return "从文件中读取已经写好的股票列表"


class Pick_Rank_Factor(Create_stock_list):
    def __init__(self, params):
        self.stock_num = params.get('stock_num', 20)
        self.index_scope = params.get('index_scope', '000985.XSHG')
        self.factor_num = params.get('factor_num', 10)
        pass

    def update_params(self, context, params):
        self.factor_num = params.get('factor_num', 10)

    def before_trading_start(self, context):
        from ml_factor_rank import ML_Factor_Rank

        mfr = ML_Factor_Rank({'stock_num': self.stock_num,
                              'index_scope': self.index_scope})
        new_list = mfr.gaugeStocks(context)
        return new_list

    def __str__(self):
        return "多因子回归公式选股"

##########################################################
# '''------------------创业板过滤器-----------------'''


class Filter_gem(Early_Filter_stock_list):
    def filter(self, context, stock_list):
        self.log.info("过滤创业板股票")
        return [stock for stock in stock_list if stock[0:3] != '300']

    def __str__(self):
        return '过滤创业板股票'

##########################################################
# '''------------------科创板过滤器-----------------'''


class Filter_sti(Early_Filter_stock_list):
    def filter(self, context, stock_list):
        self.log.info("过滤科创板股票")
        return [stock for stock in stock_list if stock[0:3] != '688']

    def __str__(self):
        return '过滤科创板股票'


class Filter_common(Filter_stock_list):
    def __init__(self, params):
        self.filters = params.get(
            'filters', ['st', 'high_limit', 'low_limit', 'pause', 'ban'])

    def set_feasible_stocks(self, initial_stocks, current_data):
        # 判断初始股票池的股票是否停牌，返回list
        paused_info = []

        for i in initial_stocks:
            paused_info.append(current_data[i].paused)
        df_paused_info = pd.DataFrame(
            {'paused_info': paused_info}, index=initial_stocks)
        unsuspened_stocks = list(
            df_paused_info.index[df_paused_info.paused_info == False])
        return unsuspened_stocks

    def filter(self, context, data, stock_list):
        # print("before common filter list: {0}".format(stock_list))
        current_data = get_current_data()

        # filter out paused stocks
#         stock_list = self.set_feasible_stocks(stock_list, current_data)

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
            stock_list = [
                stock for stock in stock_list if not current_data[stock].paused]

        try:
            if 'ban' in self.filters:
                ban_shares = self.get_ban_shares(context)
                stock_list = [
                    stock for stock in stock_list if stock[:6] not in ban_shares]
        except Exception as e:
            self.log.error(str(e))

        self.log.info("选股过滤（显示前五）:\n{0}, total: {1}".format(join_list(
            ["[%s]" % (show_stock(x)) for x in stock_list[:5]], ' ', 10), len(stock_list)))
        return stock_list

    #获取解禁股列表
    def get_ban_shares(self, context):
        curr_year = context.current_dt.year
        curr_month = context.current_dt.month
        jj_range = [((curr_year * 12 + curr_month + i - 1) / 12, curr_year * 12 + curr_month + i -
                     (curr_year * 12 + curr_month + i - 1) / 12 * 12) for i in range(-1, 1)]  # range 可指定解禁股的时间范围，单位为月
        df_jj = reduce(lambda x, y: pd.concat([x, y], axis=0), [
                       ts.xsg_data(year=y, month=m) for (y, m) in jj_range])
        return df_jj.code.values

    def update_params(self, context, params):
        self.filters = params.get(
            'filters', ['st', 'high_limit', 'low_limit', 'pause'])  # ,'ban'

    def __str__(self):
        return '一般性股票过滤器:%s' % (str(self.filters))

#######################################################


class Filter_MA_CHAN_UP(Filter_stock_list):
    def __init__(self, params):
        # ZouShi_Type.Pan_Zheng_Composite, ZouShi_Type.Pan_Zheng
        self.expected_zoushi_up = params.get("expected_zoushi_up", [])
        self.expected_exhaustion_up = params.get(
            "expected_exhaustion_up", [])  # Chan_Type.PANBEI, Chan_Type.BEICHI
        # order small -> big
        self.check_level = params.get("check_level", ["5m", "30m"])
        self.onhold_days = params.get('onhold_days', 2)
        self.stock_remove_list = {}

    def get_count(self, period):
        if period == '1d':
            return 180
        elif period == '120m':
            return 237
        elif period == '90m':
            return 356
        elif period == '60m':
            return 712
        elif period == '30m':
            return 1200
        elif period == '15m':
            return 1500
        elif period == '5m':
            return 1800
        else:
            return 1800

    def filter(self, context, data, stock_list):
        # filter out any stock that are at sell point!

        stock_to_remove = []
        for stock in stock_list:
            fullfill_condition = ""
            for level in self.check_level:

                stock_data = get_bars(stock,
                                      count=self.get_count(level),
                                      end_dt=None,
                                      unit=level,
                                      fields=['date', 'high', 'low'],
                                      df=False,
                                      include_now=True)

                min_loc = int(
                    np.where(stock_data['low'] == min(stock_data['low']))[0][-1])
                bot_time = stock_data[min_loc]['date']
                bot_count = len(stock_data['low']) - min_loc
                if bot_count <= 0:
                    break
                result_zoushi_up, result_exhaustion_up = analyze_MA_zoushi_by_stock(stock=stock,
                                                                                    period=level,
                                                                                    count=bot_count,
                                                                                    end_dt=None,
                                                                                    df=False,
                                                                                    zoushi_types=self.expected_zoushi_up,
                                                                                    direction=TopBotType.bot2top)
                if result_zoushi_up in self.expected_zoushi_up and result_exhaustion_up in self.expected_exhaustion_up:
                    print("{0} zoushi: {1} exhaustion UP:{2} level:{3}".format(
                        stock, result_zoushi_up, result_exhaustion_up, level))
                    fullfill_condition = level
                else:
                    break

            if fullfill_condition:
                stock_to_remove.append(stock)
                self.stock_remove_list[stock] = self.onhold_days * \
                    self.get_count("") // self.get_count(level)
        self.log.info("stocks removed: {0}".format(stock_to_remove))
        return [stock for stock in stock_list if stock not in stock_to_remove and stock not in self.stock_remove_list]

    def after_trading_end(self, context):
        # auto increment and delete entries over the onhold days
        self.stock_remove_list = {
            a: (b - 1) for a, b in self.stock_remove_list.items() if b - 1 > 0}
        print(self.stock_remove_list)

    def __str__(self):
        return '缠论分析过滤UP: {0}'.format(self.check_level)


class Filter_MA_CHAN_DOWN(Filter_stock_list):
    def __init__(self, params):
        # ZouShi_Type.Pan_ZhengZouShi_Type.Qu_Shi_Down,
        self.expected_zoushi_down = params.get("expected_zoushi_down", [])
        self.expected_exhaustion_down = params.get(
            "expected_exhaustion_down", [])  # Chan_Type.PANBEI, Chan_Type.BEICHI
        self.check_level = params.get("check_level", ["5m", "30m"])
        self.onhold_days = params.get('onhold_days', 2)
        self.stock_remove_list = {}

    def get_count(self, period):
        if period == '1d':
            return 180
        elif period == '120m':
            return 237
        elif period == '90m':
            return 356
        elif period == '60m':
            return 712
        elif period == '30m':
            return 1200
        elif period == '15m':
            return 1500
        elif period == '5m':
            return 1800
        else:
            return 1800

    def filter(self, context, data, stock_list):
        # filter out any stock that are at sell point!

        stock_to_remove = []
        for stock in stock_list:
            fullfill_condition = True
            for level in self.check_level:

                stock_data = get_bars(stock,
                                      count=self.get_count(level),
                                      end_dt=None,
                                      unit=level,
                                      fields=['date', 'high', 'low'],
                                      df=False,
                                      include_now=True)

                max_loc = int(
                    np.where(stock_data['high'] == max(stock_data['high']))[0][-1])
                top_time = stock_data[max_loc]['date']
                top_count = len(stock_data['high']) - max_loc
                if top_count > 0:
                    result_zoushi_down, result_exhaustion_down = analyze_MA_zoushi_by_stock(stock=stock,
                                                                                            period=level,
                                                                                            count=top_count,
                                                                                            end_dt=None,
                                                                                            df=False,
                                                                                            zoushi_types=self.expected_zoushi_down,
                                                                                            direction=TopBotType.top2bot)
                    if result_zoushi_down in self.expected_zoushi_down and result_exhaustion_down in self.expected_exhaustion_down:
                        print("{0} zoushi: {1} exhaustion down:{2} level:{3}".format(
                            stock, result_zoushi_down, result_exhaustion_down, level))
                    else:
                        fullfill_condition = False
                        break
                else:
                    fullfill_condition = False
                    break
            if fullfill_condition:
                stock_to_remove.append(stock)
                self.stock_remove_list[stock] = self.onhold_days * \
                    self.get_count("") // self.get_count(self.check_level[-1])
        self.log.info("stocks removed: {0}".format(stock_to_remove))
        return [stock for stock in stock_list if stock not in stock_to_remove and stock not in self.stock_remove_list]

    def after_trading_end(self, context):
        # auto increment and delete entries over the onhold days
        self.stock_remove_list = {
            a: (b - 1) for a, b in self.stock_remove_list.items() if b - 1 > 0}
        print(self.stock_remove_list)

    def __str__(self):
        return '缠论分析过滤DOWN: {0}'.format(self.check_level)

#######################################################


class Filter_SD_CHAN(Filter_stock_list):
    def __init__(self, params):
        self.check_level = params.get("check_level", ["30m", "5m"])
        self.expected_current_types = params.get(
            'expected_current_types', [Chan_Type.I, Chan_Type.I_weak, Chan_Type.INVALID])
        self.onhold_days = params.get('onhold_days', 20)
        self.stock_remove_list = {}
        pass

    def filter(self, context, data, stock_list):
        stock_to_remove = []

        for stock in stock_list:
            if stock in self.stock_remove_list:
                print("{0} already in remove list {1} days left".format(
                    stock, self.stock_remove_list[stock]))
                continue
            m_result, xd_m_result, m_profile = check_chan_by_type_exhaustion(stock=stock,
                                                                             end_time=None,
                                                                             count=3000,
                                                                             periods=[
                                                                                 self.check_level[0]],
                                                                             direction=TopBotType.bot2top,
                                                                             chan_type=self.expected_current_types,
                                                                             isdebug=False,
                                                                             is_description=False,
                                                                             check_structure=True)

            if m_result and xd_m_result:
                c_result, xd_c_result, c_profile, current_zhongshu_formed = check_stock_sub(stock=stock,
                                                                                            end_time=None,
                                                                                            periods=[
                                                                                                self.check_level[1]],
                                                                                            count=4800,
                                                                                            direction=TopBotType.bot2top,
                                                                                            chan_types=self.expected_current_types,
                                                                                            isdebug=False,
                                                                                            is_anal=False,
                                                                                            is_description=False,
                                                                                            split_time=None,
                                                                                            check_bi=False,
                                                                                            force_zhongshu=True,
                                                                                            force_bi_zhongshu=True,
                                                                                            ignore_sub_xd=True)

                if c_profile and c_profile[0][0] in self.expected_current_types:
                    print("{0} zoushi: exhaustion on:{1} {2}".format(
                        stock, m_profile, c_profile))
                    self.stock_remove_list[stock] = self.onhold_days
                    stock_to_remove.append(stock)
        return [stock for stock in stock_list if stock not in stock_to_remove and stock not in self.stock_remove_list]

    def after_trading_end(self, context):
        # auto increment and delete entries over the onhold days
        self.stock_remove_list = {
            a: (b - 1) for a, b in self.stock_remove_list.items() if b - 1 > 0}
        print(self.stock_remove_list)

    def __str__(self):
        return '缠论标准分析过滤: {0}'.format(self.check_level)

##########################################################################
