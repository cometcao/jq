import numpy as np
import pandas as pd
import talib
from prettytable import PrettyTable
import types
import urllib2
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from trading_module import *
from sector_selection import *
from kBarProcessor import *
from chanMatrix import *
from macd_divergence import *
from herd_head import *
import datetime

try:
    import shipane_sdk
    import trader_sync
except:
    log.error("加载 shipane_sdk和trader_sync失败")
    pass


# 不同步的白名单，主要用于实盘易同步持仓时，不同步中的新股，需把新股代码添加到这里。https://www.joinquant.com/algorithm/index/edit?algorithmId=23c589f4594f827184d4f6f01a11b2f2
# 可把while_list另外放到研究的一个py文件里
def while_list():
    return ['000001.XSHE']


# ==================================策略配置==============================================
def select_strategy(context):
    g.strategy_memo = '混合策略'
    # **** 这里定义log输出的类类型,重要，一定要写。假如有需要自定义log，可更改这个变量
    g.log_type = Rule_loger
    # 判断是运行回测还是运行模拟
    g.is_sim_trade = context.run_params.type == 'sim_trade'
    g.port_pos_control = 1.0 # 组合仓位控制参数
    g.monitor_levels = ['5d','1d','60m']
    g.buy_count = 3
    g.pb_limit = 5
    g.ps_limit = 2.5
    g.pe_limit = 200
    index2 = '000016.XSHG'  # 大盘指数
    index8 = '399333.XSHE'  # 小盘指数

    ''' ---------------------配置 调仓条件判断规则-----------------------'''
    # 调仓条件判断
    adjust_condition_config = [
        [True, '_time_c_', '调仓时间', Time_condition, {
            # 'times': [[10,0],[10, 30], [11,00], [13,00], [13,30], [14,00],[14, 30]],  # 调仓时间列表，二维数组，可指定多个时间点
            'times': [[10, 30], [11,20], [13,30], [14, 50]],  # 调仓时间列表，二维数组，可指定多个时间点
        }],
        [False, '_Stop_loss_by_price_', '指数最高低价比值止损器', Stop_loss_by_price, {
            'index': '000001.XSHG',  # 使用的指数,默认 '000001.XSHG'
            'day_count': 160,  # 可选 取day_count天内的最高价，最低价。默认160
            'multiple': 2.2  # 可选 最高价为最低价的multiple倍时，触 发清仓
        }],
        [False,'_Stop_loss_by_3_black_crows_','指数三乌鸦止损', Stop_loss_by_3_black_crows,{
            'index':'000001.XSHG',  # 使用的指数,默认 '000001.XSHG'
             'dst_drop_minute_count':60,  # 可选，在三乌鸦触发情况下，一天之内有多少分钟涨幅<0,则触发止损，默认60分钟
            }],
        [False,'Stop_loss_stocks','个股止损',Stop_gain_loss_stocks,{
            'period':20,  # 调仓频率，日
            'stop_loss':0.0,
            'enable_stop_loss':True,
            'stop_gain':0.2,
            'enable_stop_gain':False
            },],
        # [True,'_Stop_loss_by_growth_rate_','当日指数涨幅止损器',Stop_loss_by_growth_rate,{
        #     'index':'000001.XSHG',  # 使用的指数,默认 '000001.XSHG'
        #      'stop_loss_growth_rate':-0.05,
        #     }],
        # [False,'_Stop_loss_by_28_index_','28实时止损',Stop_loss_by_28_index,{
        #             'index2' : '000016.XSHG',       # 大盘指数
        #             'index8' : '399333.XSHE',       # 小盘指数
        #             'index_growth_rate': 0.01,      # 判定调仓的二八指数20日增幅
        #             'dst_minute_count_28index_drop': 120 # 符合条件连续多少分钟则清仓
        #         }],
        [False, '_equity_curve_protect_', '资金曲线止损', equity_curve_protect, {
            'day_count': 20,  # 
            'percent': 0.01,  # 可选 当日总资产小于选定日前资产的固定百分数，触 发清仓
            'use_avg': False,
            'market_index':'000300.XSHG'
        }],
        [False, '', '多指数20日涨幅止损器', Mul_index_stop_loss, {
            'indexs': [index2, index8],
            'min_rate': 0.005
        }],
        [True, '', '调仓日计数器', Period_condition, {
            'period': 1,  # 调仓频率,日
        }],
    ]
    adjust_condition_config = [
        [True, '_adjust_condition_', '调仓执行条件的判断规则组合', Group_rules, {
            'config': adjust_condition_config
        }]
    ]

    ''' --------------------------配置 选股规则----------------- '''
    pick_config = [
        [True, '', '缠论强弱势板块', Pick_rank_sector,{
                        'strong_sector':True, 
                        'sector_limit_pct': 13,
                        'strength_threthold': 0, 
                        'isDaily': False, 
                        'useIntradayData':False,
                        'useAvg':True,
                        'avgPeriod':5}],
        [False, '', '基本面数据筛选', Filter_financial_data, {'factor':'valuation.pe_ratio', 'min':0, 'max':80}],
        [True, '', '基本面数据筛选', Filter_financial_data2, {
            'factors': [FD_Factor('valuation.ps_ratio', min=0, max=g.ps_limit),
                        FD_Factor('valuation.pe_ratio', min=0, max=g.pe_limit),
                        # FD_Factor('valuation.pcf_ratio', min=0, max=100),
                        FD_Factor('valuation.pb_ratio', min=0, max=g.pb_limit),
                        ],
            'order_by': 'valuation.market_cap',
            'sort': SortType.asc,
            'limit':300}],
        # 测试的多因子选股,所选因子只作为示例。
        # 选用的财务数据参考 https://www.joinquant.com/data/dict/fundamentals
        # 传入参数的财务因子需为字符串，原因是直接传入如 indicator.eps 会存在序列化问题。
        # FD_Factor 第一个参数为因子，min=为最小值 max为最大值，=None则不限，默认都为None。min,max都写则为区间
        [False, '', '多因子选股票池', Pick_financial_data, {
            'factors': [
                # FD_Factor('valuation.circulating_market_cap', min=0, max=1000)  # 流通市值0~100亿
                FD_Factor('valuation.market_cap', min=0, max=20000)  # 市值0~20000亿
                , FD_Factor('valuation.pe_ratio', min=0, max=80)  # 0 < pe < 200 
                , FD_Factor('valuation.pb_ratio', min=0, max=5)  # 0 < pb < 2
                , FD_Factor('valuation.ps_ratio', min=0, max=2.5)  # 0 < ps < 2
                # , FD_Factor('indicator.eps', min=0)  # eps > 0
                # , FD_Factor('indicator.operating_profit', min=0) # operating_profit > 0
                # , FD_Factor('valuation.pe_ratio/indicator.inc_revenue_year_on_year', min=0, max=1)
                # , FD_Factor('valuation.pe_ratio/indicator.inc_net_profit_to_shareholders_year_on_year', min=0, max=1)
                # , FD_Factor('balance.total_current_assets / balance.total_current_liability', min=0, max=2) # 0 < current_ratio < 2
                # , FD_Factor('(balance.total_current_assets - balance.inventories) / balance.total_current_liability', min= 0, max=1) # 0 < quick_ratio < 1
                # , FD_Factor('indicator.roe',min=0,max=50) # roe
                # , FD_Factor('indicator.inc_net_profit_annual',min=0,max=10000)
                # , FD_Factor('valuation.capitalization',min=0,max=8000)
                # , FD_Factor('indicator.gross_profit_margin',min=0,max=10000)
                # , FD_Factor('indicator.net_profit_margin',min=0,max=10000)
            ],
            'order_by': 'valuation.pb_ratio',  # 按流通市值排序
            'sort': SortType.asc,  # 从小到大排序 # SortType.desc
            'limit': 500  # 只取前200只
        }],
        [True, '', '过滤创业板', Filter_gem, {}],
        [True, '', '过滤ST,停牌,涨跌停股票', Filter_common, {}],
        [False, '', '强势股筛选', Filter_Herd_head_stocks,{'gainThre':0.05, 'count':20, 'useIntraday':True}],
        [False, '', '技术分析筛选-AND', checkTAIndicator_AND, { 
            'TA_Indicators':[
                            # (TaType.BOLL,'5d',233),
                            (TaType.TRIX_STATUS, '5d', 100),
                            # (TaType.MACD_ZERO, '5d', 100),
                            (TaType.MA, '1d', 20),
                            # (TaType.MA, '1d', 60),
                            ],
            'isLong':True}], # 确保大周期安全
        [False, '', '技术分析筛选-OR', checkTAIndicator_OR, { 
            'TA_Indicators':[
                            # (TaType.BOLL,'5d',233),
                            (TaType.TRIX_STATUS, '5d', 100),
                            # (TaType.MACD_STATUS, '5d', 100),
                            # (TaType.MA, '1d', 20),
                            # (TaType.MA, '1d', 60),
                            ],
            'isLong':True}], # 确保大周期安全
        [True, '', '日线周线级别表里买点筛选', Filter_Week_Day_Long_Pivot_Stocks, {'monitor_levels':g.monitor_levels}],
        [True, '', '过滤ST,停牌,涨跌停股票', Filter_common, {}],
        [True, '', '权重排序', SortRules, {
            'config': [
                [False, '', '市值排序', Sort_financial_data, {
                    'factor': 'valuation.market_cap',
                    'sort': SortType.asc
                    , 'weight': 100}],
                [True, '', '流通市值排序', Sort_financial_data, {
                    'factor': 'valuation.circulating_market_cap',
                    'sort': SortType.asc
                    , 'weight': 100}],
                [False, '', 'P/S排序', Sort_financial_data, {
                    'factor': 'valuation.ps_ratio',
                    'sort': SortType.asc
                    , 'weight': 100}],
                [False, '', 'GP排序', Sort_financial_data, {
                    'factor': 'income.total_profit/balance.total_assets',
                    'sort': SortType.desc
                    , 'weight': 100}],
                [False, '', '按当前价排序', Sort_price, {
                    'sort': SortType.asc
                    , 'weight': 20}],
                [True, '5growth', '5日涨幅排序', Sort_growth_rate, {
                    'sort': SortType.asc
                    , 'weight': 100
                    , 'day': 5}],
                [False, '20growth', '20日涨幅排序', Sort_growth_rate, {
                    'sort': SortType.asc
                    , 'weight': 100
                    , 'day': 20}],
                [False, '60growth', '60日涨幅排序', Sort_growth_rate, {
                    'sort': SortType.asc
                    , 'weight': 10
                    , 'day': 60}],
                [False, '', '按换手率排序', Sort_turnover_ratio, {
                    'sort': SortType.desc
                    , 'weight': 50}],
            ]}
        ],
        [True, '', '获取最终选股数', Filter_buy_count, {
            'buy_count': 50  # 最终入选股票数
        }],
    ]
    pick_new = [
        [True, '_pick_stocks_', '选股', Pick_stocks2, {
            'config': pick_config,
            'day_only_run_one': True
        }]
    ]

    ''' --------------------------配置 4 调仓规则------------------ '''
    # # 通达信持仓字段不同名校正
    col_names = {'可用': u'可用', '市值': u'参考市值', '证券名称': u'证券名称', '资产': u'资产'
        , '证券代码': u'证券代码', '证券数量': u'证券数量', '可卖数量': u'可卖数量', '当前价': u'当前价', '成本价': u'成本价'
                 }
    adjust_position_config = [
        [False, '', '卖出股票', Sell_stocks, {}],
        [False, '', '买入股票', Buy_stocks, {
            'buy_count': g.buy_count  # 最终买入股票数
        }],
        [True, '', '卖出股票日内表里', Sell_stocks_chan, {'monitor_levels': g.monitor_levels}],
        [True, '', '买入股票日内表里', Buy_stocks_chan, {'buy_count': g.buy_count,'monitor_levels': g.monitor_levels, 'pos_control':g.port_pos_control}],
        [False,'','VaR方式买入股票', Buy_stocks_var, {'buy_count': g.buy_count}],
        [True, '_Show_postion_adjust_', '显示买卖的股票', Show_postion_adjust, {}],
        # [g.is_sim_trade,'trade_Xq','Xue Qiu Webtrader',XueQiu_order,{'version':0}],
        # 实盘易同步持仓，把虚拟盘同步到实盘
        # [g.is_sim_trade, '_Shipane_manager_', '实盘易操作', Shipane_manager, {
        #     'host':'111.111.111.111',   # 实盘易IP
        #     'port':8888,    # 实盘易端口
        #     'key':'',   # 实盘易Key
        #     'client':'title:guangfa', # 实盘易client
        #     'strong_op':False,   # 强力同步模式，开启会强行同步两次。
        #     'col_names':col_names, # 指定实盘易返回的持仓字段映射
        #     'cost':context.portfolio.starting_cash, # 实盘的初始资金
        #     'get_white_list_func':while_list, # 不同步的白名单
        #     'sync_scale': 1,  # 实盘资金/模拟盘资金比例，建议1为好
        #     'log_level': ['debug', 'waring', 'error'],  # 实盘易日志输出级别
        #     'sync_with_change': True,  # 是否指定只有发生了股票操作时才进行同步 , 这里重要，避免无效同步！！！！
        # }],
        # # 模拟盘调仓邮件通知，暂时只试过QQ邮箱，其它邮箱不知道是否支持
        # [g.is_sim_trade, '_new_Email_notice_', '调仓邮件通知执行器', Email_notice, {
        #     'user': '123456@qq.com',    # QQmail
        #     'password': '123459486',    # QQmail密码
        #     'tos': ["接收者1<123456@qq.com>"], # 接收人Email地址，可多个
        #     'sender': '聚宽模拟盘',  # 发送人名称
        #     'strategy_name': g.strategy_memo, # 策略名称
        #     'send_with_change': False,   # 持仓有变化时才发送
        # }],
    ]
    adjust_position_config = [
        [True, '_Adjust_position_', '调仓执行规则组合', Adjust_position, {
            'config': adjust_position_config
        }]
    ]

    ''' --------------------------配置 辅助规则------------------ '''
    # 优先辅助规则，每分钟优先执行handle_data
    common_config_list = [
        [True, '', '设置系统参数', Set_sys_params, {
            'benchmark': '000300.XSHG'  # 指定基准为次新股指
        }],
        [True, '', '手续费设置器', Set_slip_fee, {}],
        [True, '', '持仓信息打印器', Show_position, {}],
        [True, '', '统计执行器', Stat, {}],
        [True, '', '自动调参器', Update_Params_Auto, {
            'ps_threthold':0.618,
            'pb_threthold':0.618,
            'pe_threthold':0.809,
            'buy_threthold':0.809,
            'pos_control_value': 1.0
        }],
        # [g.is_sim_trade, '_Purchase_new_stocks_', '实盘易申购新股', Purchase_new_stocks, {
        #     'times': [[11, 24]],
        #     'host':'111.111.111.111',   # 实盘易IP
        #     'port':8888,    # 实盘易端口
        #     'key':'',   # 实盘易Key
        #     'clients': ['title:zhaoshang', 'title:guolian'] # 实盘易client列表,即一个规则支持同一个实盘易下的多个帐号同时打新
        # }],
    ]
    common_config = [
        [True, '_other_pre_', '预先处理的辅助规则', Group_rules, {
            'config': common_config_list
        }]
    ]
    # 组合成一个总的策略
    g.main_config = (common_config
                     + adjust_condition_config
                     + pick_new
                     + adjust_position_config)


# ===================================聚宽调用==============================================
def initialize(context):
    # 策略配置
    select_strategy(context)
    # 创建策略组合
    g.main = Strategy_Group({'config': g.main_config
                                , 'g_class': Global_variable
                                , 'memo': g.strategy_memo
                                , 'name': '_main_'})
    g.main.initialize(context)

    # 打印规则参数
    g.main.log.info(g.main.show_strategy())


# 按分钟回测
def handle_data(context, data):
    # 保存context到全局变量量，主要是为了方便规则器在一些没有context的参数的函数里使用。
    g.main.g.context = context
    # 执行策略
    g.main.handle_data(context, data)


# 开盘
def before_trading_start(context):
    log.info("==========================================================================")
    g.main.g.context = context
    g.main.before_trading_start(context)


# 收盘
def after_trading_end(context):
    g.main.g.context = context
    g.main.after_trading_end(context)
    g.main.g.context = None


# 进程启动(一天一次)
def process_initialize(context):
    try:
        g.main.g.context = context
        g.main.process_initialize(context)
    except:
        pass


# 这里示例进行模拟更改回测时，如何调整策略,基本通用代码。
def after_code_changed(context):
    try:
        g.main
        pass
    except:
        print '更新代码->原先不是OO策略，重新调用initialize(context)。'
        initialize(context)
        return

    try:
        print '=> 更新代码'
        select_strategy(context)
        g.main.g.context = context
        g.main.update_params(context, {'config': g.main_config})
        # g.main.after_code_changed(context)
        g.main.log.info(g.main.show_strategy())
    except Exception as e:
        # log.error('更新代码失败:' + str(e) + '\n重新创建策略')
        # initialize(context)
        pass


'''=================================基础类======================================='''


# '''----------------------------共同参数类-----------------------------------
# 1.考虑到规则的信息互通，完全分离也会增加很大的通讯量。适当的约定好的全局变量，可以增加灵活性。
# 2.因共同约定，也不影响代码重用性。
# 3.假如需要更多的共同参数。可以从全局变量类中继承一个新类并添加新的变量，并赋于所有的规则类。
#     如此达到代码重用与策略差异的解决方案。
# '''
class Rule_loger(object):
    def __init__(self, msg_header):
        try:
            self._owner_msg = msg_header + ':'
        except:
            self._owner_msg = '未知规则:'

    def debug(self, msg, *args, **kwargs):
        log.debug(self._owner_msg + msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        log.info(self._owner_msg + msg, *args, **kwargs)

    def warn(self, msg, *args, **kwargs):
        log.warn(self._owner_msg + msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        log.error(self._owner_msg + msg, *args, **kwargs)


class Global_variable(object):
    context = None
    _owner = None
    stock_pindexs = [0]  # 指示是属于股票性质的子仓列表
    op_pindexs = [0]  # 提示当前操作的股票子仓Id
    buy_stocks = []  # 选股列表
    sell_stocks = []  # 卖出的股票列表
    # 以下参数需配置  Run_Status_Recorder 规则进行记录。
    is_empty_position = True  # True表示为空仓,False表示为持仓。
    run_day = 0  # 运行天数，持仓天数为正，空仓天数为负
    position_record = [False]  # 持仓空仓记录表。True表示持仓，False表示空仓。一天一个。
    curve_protect = False # 持仓资金曲线保护flag 
    monitor_buy_list = [] # 当日通过板块选股 外加周 日表里关系 选出的股票
    monitor_long_cm = None # 表里关系计算的可能买入的
    monitor_short_cm = None  # 表里关系计算可能卖出的
    long_record = {} # 记录买入技术指标
    short_record = {} # 记录卖出技术指标
    filtered_sectors = None # 记录筛选出的强势板块
    head_stocks = [] # 记录强势票 每日轮换

    def __init__(self, owner):
        self._owner = owner

    ''' ==============================持仓操作函数，共用================================'''

    # 开仓，买入指定价值的证券
    # 报单成功并成交（包括全部成交或部分成交，此时成交量大于0），返回True
    # 报单失败或者报单成功但被取消（此时成交量等于0），返回False
    # 报单成功，触发所有规则的when_buy_stock函数
    def open_position(self, sender, security, value, pindex=0):
        cur_price = get_close_price(security, 1, '1m')
        if math.isnan(cur_price):
            return False
        # 通过当前价，四乘五入的计算要买的股票数。
        amount = int(round(value / cur_price / 100) * 100)
        new_value = amount * cur_price

        order = order_target_value(security, new_value, pindex=pindex)
        if order != None and order.filled > 0:
            # 订单成功，则调用规则的买股事件 。（注：这里只适合市价，挂价单不适合这样处理）
            self._owner.on_buy_stock(security, order, pindex,self.context)
            return True
        return False

    # 按指定股数下单
    def order(self, sender, security, amount, pindex=0):
        cur_price = get_close_price(security, 1, '1m')
        if math.isnan(cur_price):
            return False
        position = self.context.subportfolios[pindex].long_positions[security] if self.context is not None else None
        _order = order(security, amount, pindex=pindex)
        if _order != None and _order.filled > 0:
            # 订单成功，则调用规则的买股事件 。（注：这里只适合市价，挂价单不适合这样处理）
            if amount > 0:
                self._owner.on_buy_stock(security, _order, pindex,self.context)
            elif position is not None:
                self._owner.on_sell_stock(position, _order, pindex,self.context)
            return _order
        return _order

    # 平仓，卖出指定持仓
    # 平仓成功并全部成交，返回True
    # 报单失败或者报单成功但被取消（此时成交量等于0），或者报单非全部成交，返回False
    # 报单成功，触发所有规则的when_sell_stock函数
    def close_position(self, sender, position, is_normal=True, pindex=0):
        security = position.security
        order = order_target_value(security, 0, pindex=pindex)  # 可能会因停牌失败
        if order != None:
            if order.filled > 0:
                self._owner.on_sell_stock(position, order, is_normal, pindex,self.context)
                if security not in self.sell_stocks:
                    self.sell_stocks.append(security)
                return True
            else:
                print("卖出%s失败, 尝试跌停价挂单" % (security))
                current_data = get_current_data()
                lo = LimitOrderStyle(current_data[security].low_limit)
                order_target_value(security, 0, style=lo, pindex=pindex) # 尝试跌停卖出
        return False

    # 清空卖出所有持仓
    # 清仓时，调用所有规则的 when_clear_position
    def clear_position(self, sender, context, pindexs=[0]):
        pindexs = self._owner.before_clear_position(context, pindexs)
        # 对传入的子仓集合进行遍历清仓
        for pindex in pindexs:
            if context.subportfolios[pindex].long_positions:
                sender.log.info(("[%d]==> 清仓，卖出所有股票") % (pindex))
                for stock in context.subportfolios[pindex].long_positions.keys():
                    position = context.subportfolios[pindex].long_positions[stock]
                    self.close_position(sender, position, False, pindex)
        # 调用规则器的清仓事件
        self._owner.on_clear_position(context, pindexs)

    # 通过对象名 获取对象
    def get_obj_by_name(self, name):
        return self._owner.get_obj_by_name(name)

    # 调用外部的on_log额外扩展事件
    def on_log(sender, msg, msg_type):
        pass

    # 获取当前运行持续天数，持仓返回正，空仓返回负，ignore_count为是否忽略持仓过程中突然空仓的天数也认为是持仓。或者空仓时相反。
    def get_run_day_count(self, ignore_count=1):
        if ignore_count == 0:
            return self.run_day

        prs = self.position_record
        false_count = 0
        init = prs[-1]
        count = 1
        for i in range(2, len(prs)):
            if prs[-i] != init:
                false_count += 1  # 失败个数+1
                if false_count > ignore_count:  # 连续不对超过 忽略噪音数。
                    if count < ignore_count:  # 如果统计的个数不足ignore_count不符，则应进行统计True或False反转
                        init = not init  # 反转
                        count += false_count  # 把统计失败的认为正常的加进去
                        false_count = 0  # 失败计数清0
                    else:
                        break
            else:
                count += 1  # 正常计数+1
                if false_count > 0:  # 存在被忽略的噪音数则累回来，认为是正常的
                    count += false_count
                    false_count = 0
        return count if init else -count  # 统计结束，返回结果。init为True返回正数，为False返回负数。
    
    def isFirstTradingDayOfWeek(self, context):
        trading_days = get_trade_days(end_date=context.current_dt.date(), count=2)
        today = trading_days[-1]
        last_trading_day = trading_days[-2]
        return (today.isocalendar()[1] != last_trading_day.isocalendar()[1])
    
    def getFundamentalThrethold(self, factor, threthold = 0.95):
        eval_factor = eval(factor)
        queryDf = get_fundamentals(query(
            eval_factor, valuation.code
            ).order_by(
                eval_factor.asc()
            ))
        total_num = queryDf.shape[0]
        threthold_index = int(total_num * threthold)
        return queryDf[factor.split('.')[1]][threthold_index]  

# ''' ==============================规则基类================================'''
class Rule(object):
    g = None  # 所属的策略全局变量
    name = ''  # obj名，可以通过该名字查找到
    memo = ''  # 默认描述
    log = None
    # 执行是否需要退出执行序列动作，用于Group_Rule默认来判断中扯执行。
    is_to_return = False

    def __init__(self, params):
        self._params = params.copy()
        pass

    # 更改参数
    def update_params(self, context, params):
        self._params = params.copy()
        pass

    def initialize(self, context):
        pass

    def handle_data(self, context, data):
        pass

    def before_trading_start(self, context):
        self.is_to_return = False
        pass

    def after_trading_end(self, context):
        self.is_to_return = False
        pass

    def process_initialize(self, context):
        pass

    def after_code_changed(self, context):
        pass

    @property
    def to_return(self):
        return self.is_to_return

    # 卖出股票时调用的函数
    # price为当前价，amount为发生的股票数,is_normail正常规则卖出为True，止损卖出为False
    def on_sell_stock(self, position, order, is_normal, pindex=0, context=None):
        pass

    # 买入股票时调用的函数
    # price为当前价，amount为发生的股票数
    def on_buy_stock(self, stock, order, pindex=0, context=None):
        pass

    # 清仓前调用。
    def before_clear_position(self, context, pindexs=[0]):
        return pindexs

    # 清仓时调用的函数
    def on_clear_position(self, context, pindexs=[0]):
        pass

    # handle_data没有执行完 退出时。
    def on_handle_data_exit(self, context, data):
        pass

    # record副曲线
    def record(self, **kwargs):
        if self._params.get('record', False):
            record(**kwargs)

    def set_g(self, g):
        self.g = g

    def __str__(self):
        return self.memo


# ''' ==============================策略组合器================================'''
# 通过此类或此类的子类，来规整集合其它规则。可嵌套，实现规则树，实现多策略组合。
class Group_rules(Rule):
    rules = []
    # 规则配置list下标描述变量。提高可读性与未来添加更多规则配置。
    cs_enabled, cs_name, cs_memo, cs_class_type, cs_param = range(5)

    def __init__(self, params):
        Rule.__init__(self, params)
        self.config = params.get('config', [])
        pass

    def update_params(self, context, params):
        Rule.update_params(self, context, params)
        self.config = params.get('config', self.config)

    def initialize(self, context):
        # 创建规则
        self.rules = self.create_rules(self.config)
        for rule in self.rules:
            rule.initialize(context)
        pass

    def handle_data(self, context, data):
        for rule in self.rules:
            rule.handle_data(context, data)
            if rule.to_return:
                self.is_to_return = True
                return
        self.is_to_return = False
        pass

    def before_trading_start(self, context):
        Rule.before_trading_start(self, context)
        for rule in self.rules:
            rule.before_trading_start(context)
        pass

    def after_trading_end(self, context):
        Rule.after_code_changed(self, context)
        for rule in self.rules:
            rule.after_trading_end(context)
        pass

    def process_initialize(self, context):
        Rule.process_initialize(self, context)
        for rule in self.rules:
            rule.process_initialize(context)
        pass

    def after_code_changed(self, context):
        # 重整所有规则
        # print self.config
        self.rules = self.check_chang(context, self.rules, self.config)
        # for rule in self.rules:
        #     rule.after_code_changed(context)

        pass

    # 检测新旧规则配置之间的变化。
    def check_chang(self, context, rules, config):
        nl = []
        for c in config:
            # 按顺序循环处理新规则
            if not c[self.cs_enabled]:  # 不使用则跳过
                continue
            # print c[self.cs_memo]
            # 查找旧规则是否存在
            find_old = None
            for old_r in rules:
                if old_r.__class__ == c[self.cs_class_type] and old_r.name == c[self.cs_name]:
                    find_old = old_r
                    break
            if find_old is not None:
                # 旧规则存在则添加到新列表中,并调用规则的更新函数，更新参数。
                nl.append(find_old)
                find_old.memo = c[self.cs_memo]
                find_old.log = g.log_type(c[self.cs_memo])
                find_old.update_params(context, c[self.cs_param])
                find_old.after_code_changed(context)
            else:
                # 旧规则不存在，则创建并添加
                new_r = self.create_rule(c[self.cs_class_type], c[self.cs_param], c[self.cs_name], c[self.cs_memo])
                nl.append(new_r)
                # 调用初始化时该执行的函数
                new_r.initialize(context)
        return nl

    def on_sell_stock(self, position, order, is_normal, new_pindex=0,context=None):
        for rule in self.rules:
            rule.on_sell_stock(position, order, is_normal, new_pindex,context)

    # 清仓前调用。
    def before_clear_position(self, context, pindexs=[0]):
        for rule in self.rules:
            pindexs = rule.before_clear_position(context, pindexs)
        return pindexs

    def on_buy_stock(self, stock, order, pindex=0,context=None):
        for rule in self.rules:
            rule.on_buy_stock(stock, order, pindex,context)

    def on_clear_position(self, context, pindexs=[0]):
        for rule in self.rules:
            rule.on_clear_position(context, pindexs)

    def before_adjust_start(self, context, data):
        for rule in self.rules:
            rule.before_adjust_start(context, data)

    def after_adjust_end(self, context, data):
        for rule in self.rules:
            rule.after_adjust_end(context, data)

    # 创建一个规则执行器，并初始化一些通用事件
    def create_rule(self, class_type, params, name, memo):
        obj = class_type(params)
        # obj.g = self.g
        obj.set_g(self.g)
        obj.name = name
        obj.memo = memo
        obj.log = g.log_type(obj.memo)
        # print g.log_type,obj.memo
        return obj

    # 根据规则配置创建规则执行器
    def create_rules(self, config):
        # config里 0.是否启用，1.描述，2.规则实现类名，3.规则传递参数(dict)]
        return [self.create_rule(c[self.cs_class_type], c[self.cs_param], c[self.cs_name], c[self.cs_memo]) for c in
                config if c[self.cs_enabled]]

    # 显示规则组合，嵌套规则组合递归显示
    def show_strategy(self, level_str=''):
        s = '\n' + level_str + str(self)
        level_str = '    ' + level_str
        for i, r in enumerate(self.rules):
            if isinstance(r, Group_rules):
                s += r.show_strategy('%s%d.' % (level_str, i + 1))
            else:
                s += '\n' + '%s%d. %s' % (level_str, i + 1, str(r))
        return s

    # 通过name查找obj实现
    def get_obj_by_name(self, name):
        if name == self.name:
            return self

        f = None
        for rule in self.rules:
            if isinstance(rule, Group_rules):
                f = rule.get_obj_by_name(name)
                if f != None:
                    return f
            elif rule.name == name:
                return rule
        return f

    def __str__(self):
        return self.memo  # 返回默认的描述


# 策略组合器
class Strategy_Group(Group_rules):
    def initialize(self, context):
        self.g = self._params.get('g_class', Global_variable)(self)
        self.memo = self._params.get('memo', self.memo)
        self.name = self._params.get('name', self.name)
        self.log = g.log_type(self.memo)
        self.g.context = context
        Group_rules.initialize(self, context)

    def handle_data(self, context, data):
        for rule in self.rules:
            rule.handle_data(context, data)
            if rule.to_return and not isinstance(rule, Strategy_Group):  # 这里新增控制，假如是其它策略组合器要求退出的话，不退出。
                self.is_to_return = True
                return
        self.is_to_return = False
        pass

    # 重载 set_g函数,self.g不再被外部修改
    def set_g(self, g):
        if self.g is None:
            self.g = g


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
        self.day_count = 0
        self.mark_today = {}

    def update_params(self, context, params):
        Weight_Base.update_params(self, context, params)
        self.period = params.get('period', self.period)
        self.mark_today = {}

    def handle_data(self, context, data):
        self.is_to_return = self.day_count % self.period != 0 or (self.mark_today[context.current_dt.date()] if context.current_dt.date() in self.mark_today else False)
        
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
        # if self.g.curve_protect:
        #     self.day_count = self.period-2
        #     self.g.curve_protect = False
        pass

    def __str__(self):
        return '调仓日计数器:[调仓频率: %d日] [调仓日计数 %d]' % (
            self.period, self.day_count)


class Stop_loss_by_price(Rule):
    def __init__(self, params):
        self.index = params.get('index', '000001.XSHG')
        self.day_count = params.get('day_count', 160)
        self.multiple = params.get('multiple', 2.2)
        self.is_day_stop_loss_by_price = False

    def update_params(self, context, params):
        self.index = params.get('index', self.index)
        self.day_count = params.get('day_count', self.day_count)
        self.multiple = params.get('multiple', self.multiple)

    def handle_data(self, context, data):
        # 大盘指数前130日内最高价超过最低价2倍，则清仓止损
        # 基于历史数据判定，因此若状态满足，则当天都不会变化
        # 增加此止损，回撤降低，收益降低

        if not self.is_day_stop_loss_by_price:
            h = attribute_history(self.index, self.day_count, unit='1d', fields=('close', 'high', 'low'),
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
            self.index, self.day_count, self.multiple, self.is_day_stop_loss_by_price)

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
                
            profit_threshold = self.__get_stop_profit_threshold(stock,self.period) if self.stop_gain == 0.0 else self.stop_gain
            if self.enable_stop_gain and cur_price > position.avg_cost * (1 + profit_threshold):
                self.log.info("==> 个股止盈, stock: %s, cur_price: %f, avg_cost: %f, threshold: %f"
                    % (stock,cur_price,self.last_high[stock],profit_threshold))
                position = context.portfolio.positions[stock]
                self.g.close_position(self, position, True, 0)      
    
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
        if not isnan(bstd):
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

# 资金曲线保护  
class equity_curve_protect(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        self.day_count = params.get('day_count', 20)
        self.percent = params.get('percent', 0.01)
        self.use_avg = params.get('use_avg', False)
        self.market_index = params.get('market_index', None)
        self.is_day_curve_protect = False
        self.port_value_record = []
    
    def update_params(self, context, params):
        self.percent = params.get('percent', self.percent)
        self.day_count = params.get('day_count', self.day_count)
        self.use_avg = params.get('use_avg', self.use_avg)

    def handle_data(self, context, data):
        if not self.is_day_curve_protect :
            cur_value = context.portfolio.total_value
            if len(self.port_value_record) >= self.day_count:
                market_growth_rate = get_growth_rate(self.market_index) if self.market_index else 0
                last_value = self.port_value_record[-self.day_count]
                if self.use_avg:
                    avg_value = sum(self.port_value_record[-self.day_count:]) / self.day_count
                    if cur_value < avg_value:
                        self.log.info("==> 启动资金曲线保护, %s日平均资产: %f, 当前资产: %f" %(self.day_count, avg_value, cur_value))
                        self.is_day_curve_protect = True           
                elif self.market_index:
                    if cur_value/last_value-1 >= 0: #持仓
                        pass
                    elif market_growth_rate < 0 and cur_value/last_value-1 < -self.percent: #清仓 今日不再买入
                        self.log.info("==> 启动资金曲线保护清仓, %s日资产增长: %f, 大盘增长: %f" %(self.day_count, cur_value/last_value-1, market_growth_rate))
                        self.is_day_curve_protect = True
                        self.is_to_return=True
                    elif market_growth_rate > 0 and cur_value/last_value-1 < -self.percent: # 换股
                        self.log.info("==> 启动资金曲线保护换股, %s日资产增长: %f, 大盘增长: %f" %(self.day_count, cur_value/last_value-1, market_growth_rate))
                        self.is_day_curve_protect = True
                else:
                    if cur_value <= last_value*(1-self.percent): 
                        self.log.info("==> 启动资金曲线保护, %s日前资产: %f, 当前资产: %f" %(self.day_count, last_value, cur_value))
                        self.is_day_curve_protect = True
        if self.is_day_curve_protect:
            # self.g.curve_protect = True
            self.g.clear_position(self, context, self.g.op_pindexs)
            self.port_value_record = []
            self.is_day_curve_protect = False

    def on_clear_position(self, context, pindexs=[0]):
        pass

    def after_trading_end(self, context):
        self.port_value_record.append(context.portfolio.total_value)
        if len(self.port_value_record) > self.day_count:
            self.port_value_record.pop(0)
        self.is_to_return=False
        # self.g.curve_protect = False

    def __str__(self):
        return '大盘资金比例止损器:[参数: %s日前资产] [保护百分数: %s]' % (
            self.day_count, self.percent)

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


'''=========================选股规则相关==================================='''

class Create_stock_list(Rule):
    def filter(self, context, data):
        return None

class Gauge_stock_list(Rule):
    def filter(self, context, data, stock_list):
        return None

# '''==============================选股 query过滤器基类=============================='''
class Filter_query(Rule):
    def filter(self, context, data, q):
        return None


# '''==============================选股 stock_list过滤器基类=============================='''
class Filter_stock_list(Rule):
    def filter(self, context, data, stock_list):
        return None


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
    
        for rule in self.rules:
            if isinstance(rule, Gauge_stock_list):
                stock_list = rule.filter(context, data, stock_list)
        self.g.monitor_buy_list = stock_list
        # self.g.buy_stocks = stock_list
        # if len(self.g.buy_stocks) > 5:
        #     tl = self.g.buy_stocks[0:5]
        # else:
        #     tl = self.g.buy_stocks[:]
        self.log.info('今日选股:\n' + join_list(["[%s]" % (show_stock(x)) for x in stock_list], ' ', 10))
        self.has_run = True

    def before_trading_start(self, context):
        self.has_run = False

    def __str__(self):
        return self.memo

# 选取财务数据的参数
# 使用示例 FD_param('valuation.market_cap',None,100) #先取市值小于100亿的股票
# 注：传入类型为 'valuation.market_cap'字符串而非 valuation.market_cap 是因 valuation.market_cap等存在序列化问题！！
# 具体传入field 参考  https://www.joinquant.com/data/dict/fundamentals
class FD_Factor(object):
    def __init__(self, factor, **kwargs):
        self.factor = factor
        self.min = kwargs.get('min', None)
        self.max = kwargs.get('max', None)


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
    def filter(self, context, data, stock_list):
        q = query(valuation).filter(
            valuation.code.in_(stock_list)
        )
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
        # print get_fundamentals(q)
        stock_list = list(get_fundamentals(q)['code'])
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
            # self.sector_limit_pct = 8 #if g.port_pos_control == 1.0 else 3
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


class Filter_Week_Day_Long_Pivot_Stocks(Gauge_stock_list):
    def __init__(self, params):
        Gauge_stock_list.__init__(self, params)
        self.monitor_levels = params.get('monitor_levels', ['5d','1d','60m'])
        
    def filter(self, context, data, stock_list):
        # 新选出票 + 过去一周选出票 + 过去一周强势票
        combined_list = list(set(stock_list + self.g.monitor_buy_list))
        # combined_list = list(set(self.g.head_stocks+self.g.monitor_buy_list))
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
        
        monitor_list = self.matchStockForMonitor()
        # self.g.monitor_buy_list = self.g.monitor_long_cm.stockList
        monitor_list = self.removeStockForMonitor(monitor_list) # remove unqulified stocks
        monitor_list = list(set(monitor_list + self.g.head_stocks)) # add head stocks
        return monitor_list # monitor saved in g.monitor_buy_list updated per day

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
        
        to_be_removed_from_monitor += self.g.monitor_long_cm.filterDownTrendUpNode(stock_list=stockList, level_list=['5d','1d'], update_df=False)
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
        return stock_list
    
    def after_trading_end(self, context):
        self.g.head_stocks = []
        
    def __str__(self):
        return '强势股票筛选特例加入每日待选'
#######################################################
class TA_Factor(Rule):
    def __init__(self, params):
        super(TA_Factor, self).__init__(params)
        self.period = params.get('period', '1d')
        self.ta_type = params.get('ta_type', None)
        self.count = params.get('count', 100)
        self.isLong = params.get('isLong', True)
        self.method = None
        
    def filter(self, stock_list):
        result = [stock for stock in stock_list if self.method(stock)]
        if result:
            print("通过技术指标 %s 参数 %s %s:" % (str(self.ta_type), self.period, "买点" if self.isLong else "卖点") + join_list([show_stock(stock) for stock in result[:10]], ' ', 10))
        return result
        
    def getlatest_df(self, stock, count, fields, dataframe_flag = True):
        df_data = attribute_history(stock, count, '1d', fields, df=dataframe_flag)
        latest_stock_data = attribute_history(stock, 1, '230m', fields, skip_paused=True, df=dataframe_flag) # 14:50
        if dataframe_flag:
            current_date = latest_stock_data.index[-1].date()
            latest_stock_data = latest_stock_data.reset_index(drop=False)
            latest_stock_data.ix[0, 'index'] = pd.DatetimeIndex([current_date])[0]
            latest_stock_data = latest_stock_data.set_index('index')
            df_data = df_data.reset_index().drop_duplicates(subset='index').set_index('index')
            df_data = df_data.append(latest_stock_data, verify_integrity=True) # True
        else:
            final_fields = []
            if isinstance(fields, basestring):
                final_fields.append(fields)
            else:
                final_fields = list(fields)
            for field in final_fields:
                df_data[field] = np.append(df_data[field], latest_stock_data[field][-1])
        return df_data

class TA_Factor_Short(TA_Factor):
    def __init__(self, params):
        super(TA_Factor_Short, self).__init__(params)
        if self.ta_type == TaType.MA:
            self.method = self.check_MA_list
        elif self.ta_type == TaType.MACD_STATUS:
            self.method = self.check_MACD_STATUS_list
        elif self.ta_type == TaType.RSI:
            self.method = self.check_RSI_list
        elif self.ta_type == TaType.TRIX:
            self.method = self.check_TRIX_list
        elif self.ta_type == TaType.MACD:
            self.method = self.check_MACD_list
        elif self.ta_type == TaType.BOLL:
            self.method = self.check_BOLL_list
        elif self.ta_type == TaType.BOLL_UPPER:
            self.method = self.check_BOLL_UPPER_list
        elif self.ta_type == TaType.TRIX_STATUS:
            self.method = self.check_TRIX_STATUS_list
        elif self.ta_type == TaType.TRIX_PURE:
            self.method = self.check_TRIX_PURE_list
        elif self.ta_type == TaType.MACD_CROSS:
            self.method = self.check_MACD_CROSS_list
    
    def check_MACD_CROSS_list(self, stock):
        fastperiod=12
        slowperiod=26
        signalperiod=9
        hData = attribute_history(stock, self.count, self.period, ('close'), skip_paused=True,df=False)
        close = hData['close']
        _dif, _dea, _macd = talib.MACD(close, fastperiod, slowperiod, signalperiod)
        return _macd[-1] < 0 and _macd[-2] > 0      
        
    def check_BOLL_UPPER_list(self, stock):
        hData = attribute_history(stock, self.count, self.period, ('close', 'high', 'volume','open'), skip_paused=True,df=False) if self.period!='1d' else self.getlatest_df(stock, self.count, ('close','high', 'volume','open'), dataframe_flag=False)
        close = hData['close']
        hopen = hData['open']
        high = hData['high']
        volume = hData['volume']
        # use BOLL to mitigate risk
        upper, _, lower = talib.BBANDS(close, timeperiod=21, nbdevup=2, nbdevdn=2, matype=0)
        vol_ma = talib.SMA(volume, 20)
        return high[-1] > upper[-1] and close[-1] < upper[-1] and close[-1] < hopen[-1] \
                and (volume[-1] > (vol_ma[-1] * 1.618) or volume[-2] > (vol_ma[-2] * 1.618)) 
    
    def check_BOLL_list(self, stock):
        # for high rise stocks dropping below Boll top band, sell
        hData = attribute_history(stock, self.count, self.period, ('close', 'high','open'), skip_paused=True,df=False) if self.period!='1d' else self.getlatest_df(stock, self.count, ('close','high','open'), dataframe_flag=False)
        close = hData['close']
        hopen = hData['open']
        high = hData['high']
        upper, middle, lower = talib.BBANDS(close, timeperiod=21, nbdevup=2, nbdevdn=2, matype=0)
        return (close[-1] < upper[-1] and high[-2] > upper[-2] and high[-3] > upper[-3]) and close[-1] < hopen[-1] \
                and ((upper[-1] - lower[-1]) / (upper[-2] - lower[-2]) < (upper[-2] - lower[-2]) / (upper[-3] - lower[-3]))
    
    def check_MACD_list(self, stock):
        df = attribute_history(stock, self.count, self.period, ('high', 'low', 'open', 'close', 'volume'), df=True) # 233
        if (np.isnan(df['high'][-1])) or (np.isnan(df['low'][-1])) or (np.isnan(df['close'][-1])):
            return False
        
        df.loc[:,'macd_raw'], _, df.loc[:,'macd'] = talib.MACD(df['close'].values, 12, 26, 9)
        df.loc[:,'vol_ma'] = talib.SMA(df['volume'].values, 5)
        df = df.dropna()

        md = macd_divergence()
        df2 = attribute_history(stock, self.count, self.period, ('high', 'low', 'open', 'close', 'volume'), df=False)
        return md.checkAtTopDoubleCross_v3(df2)# or md.checkAtTopDoubleCross_chan(df, False)
        
    def check_TRIX_list(self, stock, trix_span=12, trix_ma_span=9):
        hData = attribute_history(stock, self.count, self.period, ('close','volume'), skip_paused=True,df=False)
        close = hData['close']
        volume = hData['volume']
        trix = talib.TRIX(close, trix_span)
        if np.isnan(close[-1]) or np.isnan(trix[-1]):
            return False
        ma_trix = talib.SMA(trix, trix_ma_span)
        # macd_raw,_,macd = talib.MACD(close, 12, 26, 9)
        obv = talib.OBV(close, volume)
        ma_obv = talib.SMA(obv, 30)
        return trix[-1] < ma_trix[-1] and obv[-1] > ma_obv[-1]#and macd_raw[-1] > 0
    
    def check_TRIX_STATUS_list(self, stock, trix_span=12, trix_ma_span=9):
        hData = attribute_history(stock, self.count, self.period, ('close'), skip_paused=True,df=False)
        close = hData['close']
        trix = talib.TRIX(close, trix_span)
        if np.isnan(trix[-1]):
            return False
        ma_trix = talib.SMA(trix, trix_ma_span)
        return trix[-1] < trix[-2] and ((trix[-1] < ma_trix[-1] and (ma_trix[-1]-trix[-1]) > (ma_trix[-2]-trix[-2])) or \
                (trix[-1] >= ma_trix[-1] and (trix[-1] - ma_trix[-1]) < (trix[-2] - ma_trix[-2]) and (trix[-1] - ma_trix[-1]) < (trix[-3] - ma_trix[-3])))
    
    def check_TRIX_PURE_list(self, stock, trix_span=12, trix_ma_span=9):
        hData = attribute_history(stock, self.count, self.period, ('close'), skip_paused=True,df=False)
        close = hData['close']
        trix = talib.TRIX(close, trix_span)
        ma_trix = talib.SMA(trix, trix_ma_span)
        return trix[-1] < ma_trix[-1]      
    
    def check_RSI_list(self, stock):
        pass        
    
    def check_MACD_STATUS_list(self, stock):
        fastperiod=12
        slowperiod=26
        signalperiod=9
        hData = attribute_history(stock, self.count, self.period, ('close'), skip_paused=True,df=False)
        close = hData['close']
        _dif, _dea, _macd = talib.MACD(close, fastperiod, slowperiod, signalperiod)
        return _macd[-1] < _macd[-2] and _macd[-1] < _macd[-3]
    
    def check_MACD_ZERO_list(self, stock):
        fastperiod=12
        slowperiod=26
        signalperiod=9
        hData = attribute_history(stock, self.count, self.period, ('close'), skip_paused=True,df=False)
        close = hData['close']
        _dif, _dea, _macd = talib.MACD(close, fastperiod, slowperiod, signalperiod)
        return _dif[-1] >= 0 or _dea[-1] >=0
    
    def check_MA_list(self, stock):
        hData = attribute_history(stock, self.count, self.period, ('close'), skip_paused=True,df=False)
        close = hData['close']
        ma = sum(close)/len(close)
        return close[-1] < ma
        
class TA_Factor_Long(TA_Factor):
    def __init__(self, params):
        super(TA_Factor_Long, self).__init__(params)
        if self.ta_type == TaType.RSI:
            self.method = self.check_rsi_list_v2
        elif self.ta_type == TaType.MACD:
            self.method = self.check_macd_list
        elif self.ta_type == TaType.MA:
            self.method = self.check_ma_list
        elif self.ta_type == TaType.TRIX:
            self.method = self.check_trix_list
        elif self.ta_type == TaType.TRIX_PURE:
            self.method = self.check_trix_pure_list
        elif self.ta_type == TaType.TRIX_STATUS:    
            self.method = self.check_trix_status_list
        elif self.ta_type == TaType.BOLL_MACD:
            self.method = self.check_boll_macd_list
        elif self.ta_type == TaType.BOLL_UPPER:
            self.method = self.check_boll_upper_list
        elif self.ta_type == TaType.MACD_STATUS:
            self.method = self.check_macd_status_list
        elif self.ta_type == TaType.MACD_ZERO:
            self.method = self.check_macd_zero_list
        elif self.ta_type == TaType.MACD_CROSS:
            self.method = self.check_macd_cross_list
        elif self.ta_type == TaType.KDJ_CROSS:
            self.method = self.check_kdj_cross_list
    
    def check_kdj_cross_list(self, stock):
        macd_cross = self.check_macd_cross_list(stock)# and self.check_macd_zero_list(stock)
        hData = attribute_history(stock, self.count, self.period, ('close', 'high', 'low'), skip_paused=True,df=False) if self.period!='1d' else self.getlatest_df(stock, self.count, ('close','high', 'low'), dataframe_flag=False)
        slowk, slowd = talib.STOCH(hData['high'],
                                   hData['low'],
                                   hData['close'],
                                   fastk_period=9,
                                   slowk_period=3,
                                   slowk_matype=0,
                                   slowd_period=3,
                                   slowd_matype=0)
        slowj = 3 * slowk - 2 * slowd
        kdj_cross = False
        for i in range(1, 6):
            kdj_cross = kdj_cross or (slowk[-i] > slowd[-i] and slowk[-i-1] < slowd[-i-1])
            if kdj_cross:
                break
        return macd_cross and kdj_cross

    def check_macd_cross_list(self, stock):
        fastperiod=12
        slowperiod=26
        signalperiod=9
        hData = attribute_history(stock, self.count, self.period, ('close'), skip_paused=True,df=False) if self.period!='1d' else self.getlatest_df(stock, self.count, ('close'), dataframe_flag=False)
        close = hData['close']
        _dif, _dea, _macd = talib.MACD(close, fastperiod, slowperiod, signalperiod)
        return _macd[-1] > 0 and _macd[-2] < 0

    def check_boll_upper_list(self, stock):
        hData = attribute_history(stock, self.count, self.period, ('close', 'high'), skip_paused=True,df=False) if self.period!='1d' else self.getlatest_df(stock, self.count, ('close','high'), dataframe_flag=False)
        close = hData['close']
        high = hData['high']
        # use BOLL to mitigate risk
        upper, _, _ = talib.BBANDS(close, timeperiod=21, nbdevup=2, nbdevdn=2, matype=0)
        return high[-1] < upper[-1] or (high[-1] > upper[-1] and close[-1] < upper[-1])
    
    def check_macd_zero_list(self, stock):
        fastperiod=12
        slowperiod=26
        signalperiod=9
        hData = attribute_history(stock, self.count, self.period, ('close'), skip_paused=True,df=False) if self.period!='1d' else self.getlatest_df(stock, self.count, ('close'), dataframe_flag=False)
        close = hData['close']
        _dif, _dea, _macd = talib.MACD(close, fastperiod, slowperiod, signalperiod)
        return _dif[-1] <= 0 or _dea[-1] <=0  

    def check_macd_status_list(self, stock):
        fastperiod=12
        slowperiod=26
        signalperiod=9
        hData = attribute_history(stock, self.count, self.period, ('close'), skip_paused=True,df=False)
        close = hData['close']
        _dif, _dea, _macd = talib.MACD(close, fastperiod, slowperiod, signalperiod)
        return _macd[-1] > _macd[-2] and _macd[-1] > _macd[-3]
    
    def check_boll_macd_list(self, stock):
        # macd chan combine with boll lower band
        df = attribute_history(stock, self.count, self.period, ('high', 'low', 'open', 'close', 'volume'), df=True) # 233
        if (np.isnan(df['high'][-1])) or (np.isnan(df['low'][-1])) or (np.isnan(df['close'][-1])):
            return False
        
        df.loc[:,'macd_raw'], _, df.loc[:,'macd'] = talib.MACD(df['close'].values, 12, 26, 9)
        df.loc[:,'vol_ma'] = talib.SMA(df['volume'].values, 5)
        df = df.dropna()

        md = macd_divergence()
        if md.checkAtBottomDoubleCross_chan(df, False): 
            hData = attribute_history(stock, 233, self.period, ('close', 'low'), skip_paused=True,df=False) if self.period!='1d' else self.getlatest_df(stock, self.count, ('close', 'low'), dataframe_flag=False)
            close = hData['close']
            low = hData['low']
            _, _, lower = talib.BBANDS(close, timeperiod=21, nbdevup=2, nbdevdn=2, matype=0)
            min_index = np.argmin(low[-5:]) # hack for simple coding
            return low[-5:][min_index] <= lower[-5:][min_index]
        return False

    def check_trix_list(self, stock, trix_span=12, trix_ma_span=9):
        # special treatment for the long case
        hData = attribute_history(stock, self.count, self.period, ('close','volume'), skip_paused=True,df=False) if self.period!='1d' else self.getlatest_df(stock, self.count, ('close','volume'), dataframe_flag=False)
        close = hData['close']
        volume = hData['volume']
        trix = talib.TRIX(close, trix_span)
        if np.isnan(trix[-1]) or np.isnan(close[-1]):
            return False
        ma_trix = talib.SMA(trix, trix_ma_span)
        obv = talib.OBV(close, volume)
        ma_obv = talib.SMA(obv, 30)
        return trix[-1] > ma_trix[-1] and trix[-2] < ma_trix[-2] and obv[-1] < ma_obv[-1]
        
    def check_trix_pure_list(self, stock, trix_span=12, trix_ma_span=9):
        hData = attribute_history(stock, self.count, self.period, ('close'), skip_paused=True,df=False)
        close = hData['close']
        trix = talib.TRIX(close, trix_span)
        if np.isnan(close[-1]) or np.isnan(trix[-1]):
            return False
        ma_trix = talib.SMA(trix, trix_ma_span)
        return trix[-1] > ma_trix[-1]   

    def check_trix_status_list(self, stock, trix_span=12, trix_ma_span=9):
        hData = attribute_history(stock, self.count, self.period, ('close'), skip_paused=True,df=False)
        close = hData['close']
        trix = talib.TRIX(close, trix_span)
        if np.isnan(trix[-1]):
            return False
        ma_trix = talib.SMA(trix, trix_ma_span)
        return trix[-1] >= trix[-2] and ((trix[-1] < ma_trix[-1] and (ma_trix[-1]-trix[-1]) < (ma_trix[-2]-trix[-2]) and (ma_trix[-1]-trix[-1]) < (ma_trix[-3]-trix[-3])) or \
                (trix[-1] >= ma_trix[-1] and (trix[-1] - ma_trix[-1]) > (trix[-2] - ma_trix[-2])))


    def check_ma_list(self, stock):
        hData = attribute_history(stock, self.count, self.period, ('close'), skip_paused=True,df=False)
        close = hData['close']
        ma = sum(close)/len(close)
        return close[-1] > ma

    def check_rsi_list(self, stock):
        hData = attribute_history(stock, self.count, self.period, ('close'), skip_paused=True,df=False)
        close = hData['close']
        is_suddenly_rise = False
        n=10
        rsi6_day,rsi12_day,rsi24_day = self.get_rsi(close)
        for i in range(-n,-3): #i==-5,-4,-3,-2
            if (rsi6_day[i] <rsi12_day[i]) and (rsi6_day[i]< rsi24_day[i]) and(rsi6_day[i-1] <rsi12_day[i-1]) and (rsi6_day[i-1]< rsi24_day[i-1]):
                for a in range(i+1,-2):
                    if (rsi6_day[a] > rsi12_day[a]) and (rsi6_day[a]>rsi24_day[a]):
                        for b in range(a+1,-1):
                            if rsi12_day[b] >= rsi6_day[b]:
                                for c in range(b+1,0):
                                    if (rsi12_day[c] <=rsi6_day[c]) and (rsi6_day[-1]>rsi6_day[-2]):
                                        is_suddenly_rise = True
        return  is_suddenly_rise 
        
    def check_rsi_list_v2(self, stock):
        hData = attribute_history(stock, self.count, self.period, ('close'), skip_paused=True,df=False) if self.period!='1d' else self.getlatest_df(stock, self.count, ('close'), dataframe_flag=False)
        close = hData['close']
        is_ticked = False
        n=10
        rsi6_day,rsi12_day,rsi24_day = self.get_rsi(close)
        if rsi6_day[-1] > rsi12_day[-1] > rsi24_day[-1]: #最新多头排列
            current6 = rsi6_day[-1]
            for gap1 in range(1, 4): # 3
                if rsi6_day[-1-gap1] < rsi12_day[-1-gap1] < rsi24_day[-1-gap1]: 
                    for gap2 in range(1, 4): # 3
                        if rsi6_day[-1-gap1-gap2] > rsi12_day[-1-gap1-gap2] and rsi6_day[-1-gap1-gap2] > rsi24_day[-1-gap1-gap2]:
                            # is_ticked=True
                            prevous6 = rsi6_day[-1-gap1-gap2]
                            if current6 >= prevous6: # 勾型形态
                                is_ticked=True
        return is_ticked #and self.check_macd_zero_list(stock) #and self.check_trix_pure_list(stock)
        
    def check_macd_list(self, stock):
        df = attribute_history(stock, self.count, self.period, ('high', 'low', 'open', 'close', 'volume'), df=True) # 233
        if (np.isnan(df['high'][-1])) or (np.isnan(df['low'][-1])) or (np.isnan(df['close'][-1])):
            return False
        
        df.loc[:,'macd_raw'], _, df.loc[:,'macd'] = talib.MACD(df['close'].values, 12, 26, 9)
        df.loc[:,'vol_ma'] = talib.SMA(df['volume'].values, 5)
        df = df.dropna()

        md = macd_divergence()
        # df2 = attribute_history(stock, self.count, self.period, ('high', 'low', 'open', 'close', 'volume'), df=False)
        return md.checkAtBottomDoubleCross_v2(df) #or md.checkAtBottomDoubleCross_v3(df2) #or md.checkAtBottomDoubleCross_chan(df, False)
    
    def get_rsi(self, cData):
        rsi6  = talib.RSI(cData, timeperiod=6)
        rsi12  = talib.RSI(cData, timeperiod=12)
        rsi24  = talib.RSI(cData, timeperiod=24)
        return rsi6, rsi12, rsi24

class checkTAIndicator(Filter_stock_list):
    def __init__(self, params):
        Filter_stock_list.__init__(self, params)
    
class checkTAIndicator_OR(checkTAIndicator):
    def __init__(self, params):
        checkTAIndicator.__init__(self, params)
        self.filters = params.get('TA_Indicators', None)
        self.isLong = params.get('isLong', True)
    def filter(self, context, data, stock_list):
        result_list = []
        for fil,period,count in self.filters:
            ta = TA_Factor_Long({'ta_type':fil, 'period':period, 'count':count, 'isLong':self.isLong}) if self.isLong else TA_Factor_Short({'ta_type':fil, 'period':period, 'count':count, 'isLong':self.isLong})
            result_list += ta.filter(stock_list)
        return [stock for stock in stock_list if stock in result_list]

    def __str__(self):
        return '按照技术指标过滤-OR'

class checkTAIndicator_AND(checkTAIndicator):
    def __init__(self, params):
        checkTAIndicator.__init__(self, params)
        self.filters = params.get('TA_Indicators', None)
        self.isLong = params.get('isLong', True)
    def filter(self, context, data, stock_list):
        result_list = stock_list
        for fil,period,count in self.filters:
            ta = TA_Factor_Long({'ta_type':fil, 'period':period, 'count':count, 'isLong':self.isLong}) if self.isLong else TA_Factor_Short({'ta_type':fil, 'period':period, 'count':count, 'isLong':self.isLong})
            filtered_list = ta.filter(stock_list)
            result_list = [stock for stock in result_list if stock in filtered_list]
            if not result_list:
                return []
        return result_list

    def __str__(self):
        return '按照技术指标过滤-AND'


# '''------------------创业板过滤器-----------------'''
class Filter_gem(Filter_stock_list):
    def filter(self, context, data, stock_list):
        self.log.info("过滤创业板股票")
        return [stock for stock in stock_list if stock[0:3] != '300']

    def __str__(self):
        return '过滤创业板股票'


class Filter_common(Filter_stock_list):
    def __init__(self, params):
        self.filters = params.get('filters', ['st', 'high_limit', 'low_limit', 'pause'])

    def filter(self, context, data, stock_list):
        current_data = get_current_data()
        if 'st' in self.filters:
            stock_list = [stock for stock in stock_list
                          if not current_data[stock].is_st
                          and 'ST' not in current_data[stock].name
                          and '*' not in current_data[stock].name
                          and '退' not in current_data[stock].name]
        if 'high_limit' in self.filters:
            stock_list = [stock for stock in stock_list if stock in context.portfolio.positions.keys()
                          or data[stock].close < data[stock].high_limit]
        if 'low_limit' in self.filters:
            stock_list = [stock for stock in stock_list if stock in context.portfolio.positions.keys()
                          or data[stock].close > data[stock].low_limit]
        if 'pause' in self.filters:
            stock_list = [stock for stock in stock_list if not current_data[stock].paused]
        return stock_list

    def __str__(self):
        return '一般性股票过滤器:%s' % (str(self.filters))


import enum

class TaType(enum.Enum):
    MACD = 0,
    RSI = 1,
    BOLL = 2,
    MA = 3, 
    MACD_STATUS = 4,
    TRIX = 5,
    BOLL_UPPER = 6,
    TRIX_STATUS = 7,
    TRIX_PURE = 8,
    MACD_ZERO = 9,
    MACD_CROSS = 10,
    KDJ_CROSS = 11,
    BOLL_MACD = 12


# 因子排序类型
class SortType(enum.Enum):
    asc = 0  # 从小到大排序
    desc = 1  # 从大到小排序


# 价格因子排序选用的价格类型
class PriceType(enum.Enum):
    now = 0  # 当前价
    today_open = 1  # 开盘价
    pre_day_open = 2  # 昨日开盘价
    pre_day_close = 3  # 收盘价
    ma = 4  # N日均价


# 排序基本类 共用指定参数为 weight
class SortBase(Rule):
    @property
    def weight(self):
        return self._params.get('weight', 1)

    @property
    def is_asc(self):
        return self._params.get('sort', SortType.asc) == SortType.asc

    def _sort_type_str(self):
        return '从小到大' if self.is_asc else '从大到小'

    def sort(self, context, data, stock_list):
        return stock_list


# '''--多因子计算：每个规则产生一个排名，并根据排名和权重进行因子计算--'''
class SortRules(Group_rules, Filter_stock_list):
    def filter(self, context, data, stock_list):
        self.log.info(join_list([show_stock(stock) for stock in stock_list[:10]], ' ', 10))
        sorted_stocks = []
        total_weight = 0  # 总权重。
        for rule in self.rules:
            if isinstance(rule, SortBase):
                total_weight += rule.weight
        for rule in self.rules:
            if not isinstance(rule, SortBase):
                continue
            if rule.weight == 0:
                continue  # 过滤权重为0的排序规则，为以后批量自动调整权重作意外准备
            stocks = stock_list[:]  # 为防排序规则搞乱list，每次都重新复制一份
            # 获取规则排序
            tmp_stocks = rule.sort(context, data, stocks)
            rule.log.info(join_list([show_stock(stock) for stock in tmp_stocks[:10]], ' ', 10))

            for stock in stock_list:
                # 如果被评分器删除，则不增加到总评分里
                if stock not in tmp_stocks:
                    stock_list.remove(stock)

            sd = {}
            rule_weight = rule.weight * 1.0 / total_weight
            for i, stock in enumerate(tmp_stocks):
                sd[stock] = (i + 1) * rule_weight
            sorted_stocks.append(sd)
        result = []

        for stock in stock_list:
            total_score = 0
            for sd in sorted_stocks:
                score = sd.get(stock, 0)
                if score == 0:  # 如果评分为0 则直接不再统计其它的
                    total_score = 0
                    break
                else:
                    total_score += score
            if total_score != 0:
                result.append([stock, total_score])
        result = sorted(result, key=lambda x: x[1])
        # 仅返回股票列表 。
        return [stock for stock, score in result]

    def __str__(self):
        return '多因子权重排序器'


# 按N日增长率排序
# day 指定按几日增长率计算,默认为20
class Sort_growth_rate(SortBase):
    def sort(self, context, data, stock_list):
        day = self._params.get('day', 20)
        r = []
        for stock in stock_list:
            rate = get_growth_rate(stock, day)
            if rate != 0:
                r.append([stock, rate])
        r = sorted(r, key=lambda x: x[1], reverse=not self.is_asc)
        return [stock for stock, rate in r]

    def __str__(self):
        return '[权重: %s ] [排序: %s ] 按 %d 日涨幅排序' % (self.weight, self._sort_type_str(), self._params.get('day', 20))


class Sort_price(SortBase):
    def sort(self, context, data, stock_list):
        r = []
        price_type = self._params.get('price_type', PriceType.now)
        if price_type == PriceType.now:
            for stock in stock_list:
                close = data[stock].close
                r.append([stock, close])
        elif price_type == PriceType.today_open:
            curr_data = get_current_data()
            for stock in stock_list:
                r.append([stock, curr_data[stock].day_open])
        elif price_type == PriceType.pre_day_open:
            stock_data = history(count=1, unit='1d', field='open', security_list=stock_list, df=False, skip_paused=True)
            for stock in stock_data:
                r.append([stock, stock_data[stock][0]])
        elif price_type == PriceType.pre_day_close:
            stock_data = history(count=1, unit='1d', field='close', security_list=stock_list, df=False,
                                 skip_paused=True)
            for stock in stock_data:
                r.append([stock, stock_data[stock][0]])
        elif price_type == PriceType.ma:
            n = self._params.get('period', 20)
            stock_data = history(count=n, unit='1d', field='close', security_list=stock_list, df=False,
                                 skip_paused=True)
            for stock in stock_data:
                r.append([stock, stock_data[stock].mean()])

        r = sorted(r, key=lambda x: x[1], reverse=not self.is_asc)
        return [stock for stock, close in r]

    def __str__(self):
        s = '[权重: %s ] [排序: %s ] 按当 %s 价格排序' % (
            self.weight, self._sort_type_str(), str(self._params.get('price_type', PriceType.now)))
        if self._params.get('price_type', PriceType.now) == PriceType.ma:
            s += ' [%d 日均价]' % (self._params.get('period', 20))
        return s


# --- 按换手率排序 ---
class Sort_turnover_ratio(SortBase):
    def sort(self, context, data, stock_list):
        q = query(valuation.code, valuation.turnover_ratio).filter(
            valuation.code.in_(stock_list)
        )
        if self.is_asc:
            q = q.order_by(valuation.turnover_ratio.asc())
        else:
            q = q.order_by(valuation.turnover_ratio.desc())
        stock_list = list(get_fundamentals(q)['code'])
        return stock_list

    def __str__(self):
        return '[权重: %s ] [排序: %s ] 按换手率排序 ' % (self.weight, self._sort_type_str())


# --- 按财务数据排序 ---
class Sort_financial_data(SortBase):
    def sort(self, context, data, stock_list):
        factor = eval(self._params.get('factor', None))
        if factor is None:
            return stock_list
        q = query(valuation).filter(
            valuation.code.in_(stock_list)
        )
        if self.is_asc:
            q = q.order_by(factor.asc())
        else:
            q = q.order_by(factor.desc())
        stock_list = list(get_fundamentals(q)['code'])
        return stock_list

    def __str__(self):
        return '[权重: %s ] [排序: %s ] %s' % (self.weight, self._sort_type_str(), self.memo)


# '''------------------截取欲购股票数-----------------'''
class Filter_buy_count(Filter_stock_list):
    def __init__(self, params):
        self.buy_count = params.get('buy_count', 3)

    def update_params(self, context, params):
        self.buy_count = params.get('buy_count', self.buy_count)

    def filter(self, context, data, stock_list):
        if len(stock_list) > self.buy_count:
            return stock_list[:self.buy_count]
        else:
            return stock_list

    def __str__(self):
        return '获取最终待购买股票数:[ %d ]' % (self.buy_count)


'''===================================调仓相关============================'''


# '''------------------------调仓规则组合器------------------------'''
# 主要是判断规则集合有没有 before_adjust_start 和 after_adjust_end 方法
class Adjust_position(Group_rules):
    # 重载，实现调用 before_adjust_start 和 after_adjust_end 方法
    def handle_data(self, context, data):
        for rule in self.rules:
            if isinstance(rule, Adjust_expand):
                rule.before_adjust_start(context, data)

        Group_rules.handle_data(self, context, data)
        for rule in self.rules:
            if isinstance(rule, Adjust_expand):
                rule.after_adjust_end(context, data)
        if self.is_to_return:
            return


# '''==============================调仓规则器基类=============================='''
# 需要 before_adjust_start和after_adjust_end的子类可继承
class Adjust_expand(Rule):
    def before_adjust_start(self, context, data):
        pass

    def after_adjust_end(self, context, data):
        pass

class Sell_stocks_chan(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        self.monitor_levels = params.get('monitor_levels', ['5d','1d','60m'])
    def handle_data(self, context, data):
        # 日线级别卖点
        cti = None
        to_sell = to_sell_biaoli = []
        self.g.monitor_short_cm.updateGaugeStockList(newStockList=context.portfolio.positions.keys(), levels=[self.monitor_levels[-1]]) # gauge 30m level status
        if context.current_dt.hour < 11: # 10点之前
            # to_sell_biaoli += self.g.monitor_short_cm.filterUpTrendDownTrend(level_list=self.monitor_levels[:2], update_df=False)
            # to_sell_biaoli += self.g.monitor_short_cm.filterDownTrendDownTrend(level_list=self.monitor_levels[:2], update_df=False)
        
            # to_sell_biaoli += self.g.monitor_short_cm.filterDownTrendUpNode(level_list=self.monitor_levels[:2], update_df=False)
            # to_sell_biaoli += self.g.monitor_short_cm.filterUpNodeUpNode(level_list=self.monitor_levels[:2], update_df=False)
            # to_sell_biaoli += self.g.monitor_short_cm.filterDownNodeUpNode(level_list=self.monitor_levels[:2], update_df=False)
            # to_sell_biaoli += self.g.monitor_short_cm.filterDownNodeDownTrend(level_list=self.monitor_levels[:2], update_df=False)
            # to_sell_biaoli += self.g.monitor_short_cm.filterUpNodeDownTrend(level_list=self.monitor_levels[:2], update_df=False)
            cti = checkTAIndicator_OR({
                'TA_Indicators':[
                                (TaType.MACD,'1d',233),
                                (TaType.MACD,'120m',233),
                                (TaType.MACD,'60m',233),
                                (TaType.BOLL,'1d',100),
                                (TaType.BOLL_UPPER, '5d',100),
                                (TaType.TRIX_STATUS, '1d', 100),
                                ],
                'isLong':False}) #(TaType.BOLL, '240m',40),(TaType.MACD,'1d',233),
        elif context.current_dt.hour >= 14: # after 14:00
            cti = checkTAIndicator_OR({
                'TA_Indicators':[
                                (TaType.MACD,'240m',233),
                                (TaType.MACD,'120m',233),
                                (TaType.MACD,'60m',233),
                    ], 
                'isLong':False}) # (TaType.MACD,'240m',233),(TaType.BOLL,'1d',40)
        else:
            # return
            cti = checkTAIndicator_OR({
                'TA_Indicators':[(TaType.MACD,'60m',233),
                                (TaType.MACD,'120m',233),], 
                'isLong':False}) #(TaType.MACD_DEATH,'1d', 100) (TaType.MACD,'60m',233),
            # to_sell_biaoli += self.g.monitor_short_cm.filterDownTrendDownTrend(level_list=self.monitor_levels[1:], update_df=False)
            # to_sell_biaoli += self.g.monitor_short_cm.filterUpTrendDownTrend(level_list=self.monitor_levels[1:], update_df=False)
        to_sell = cti.filter(context, data, context.portfolio.positions.keys()) if cti else []
        
        to_sell = list(set(to_sell+to_sell_biaoli))
        if to_sell:
            self.log.info('准备卖出:\n' + join_list(["[%s]" % (show_stock(x)) for x in to_sell], ' ', 10))
            self.g.monitor_short_cm.displayMonitorMatrix(to_sell)
            self.adjust(context, data, to_sell)
            # remove stocks from short gauge
            sold_stocks = [stock for stock in to_sell if stock not in context.portfolio.positions.keys()] # make sure stock sold successfully
            self.g.monitor_short_cm.removeGaugeStockList(sold_stocks)
    
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

class Buy_stocks_chan(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
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
        if len(context.portfolio.positions)==self.buy_count:
            self.log.info("满仓等卖")
            return

        if context.current_dt.hour <= 10:
            self.daily_list = self.g.monitor_buy_list
            
        if not self.daily_list:
            self.log.info("现时无选股")
            return

        to_buy = self.daily_list
        self.g.monitor_long_cm.updateGaugeStockList(newStockList=self.daily_list, levels=[self.monitor_levels[-1]])
        # to_buy += self.g.monitor_long_cm.filterDownNodeDownNode(stock_list=self.daily_list, level_list=self.monitor_levels[1:], update_df=False)
        # to_buy += self.g.monitor_long_cm.filterDownNodeUpTrend(stock_list=self.daily_list, level_list=self.monitor_levels[1:], update_df=False) #*
        ## to_buy += self.g.monitor_long_cm.filterDownNodeUpNode(stock_list=self.daily_list, level_list=self.monitor_levels[1:], update_df=False)
        #### to_buy += self.g.monitor_long_cm.filterDownNodeDownTrend(stock_list=self.daily_list, level_list=self.monitor_levels[1:], update_df=False)

        # to_buy += self.g.monitor_long_cm.filterUpTrendDownNode(stock_list=self.daily_list, level_list=self.monitor_levels[1:], update_df=False)
        # * to_buy += self.g.monitor_long_cm.filterUpTrendDownTrend(stock_list=self.daily_list level_list=self.monitor_levels[1:], update_df=False)
        # * to_buy += self.g.monitor_long_cm.filterUpTrendUpNode(stock_list=self.daily_list, level_list=self.monitor_levels[1:], update_df=False)
        # to_buy += self.g.monitor_long_cm.filterUpTrendUpTrend(stock_list=self.daily_list, level_list=self.monitor_levels[1:], update_df=False)
        
        # to_buy += self.g.monitor_long_cm.filterUpNodeDownNode(stock_list=self.daily_list, level_list=self.monitor_levels[1:], update_df=False)
        #### to_buy += self.g.monitor_long_cm.filterUpNodeDownTrend(stock_list=self.daily_list, level_list=self.monitor_levels[1:], update_df=False)
        #### to_buy += self.g.monitor_long_cm.filterUpNodeUpNode(stock_list=self.daily_list, level_list=self.monitor_levels[1:], update_df=False)
        # to_buy += self.g.monitor_long_cm.filterUpNodeUpTrend(stock_list=self.daily_list, level_list=self.monitor_levels[1:], update_df=False)
        
        # to_buy += self.g.monitor_long_cm.filterDownTrendDownNode(stock_list=self.g.monitor_buy_list, level_list=self.monitor_levels[1:], update_df=False)
        #### to_buy += self.g.monitor_long_cm.filterDownTrendDownTrend(stock_list=self.g.monitor_buy_list, level_list=self.monitor_levels[1:], update_df=False)
        #### to_buy += self.g.monitor_long_cm.filterDownTrendUpNode(stock_list=self.g.monitor_buy_list, level_list=self.monitor_levels[1:], update_df=False)
        # to_buy += self.g.monitor_long_cm.filterDownTrendUpTrend(stock_list=self.daily_list, level_list=self.monitor_levels[1:], update_df=False)
        # 技术分析用于不买在卖点
        to_buy = list(set(to_buy))
        not_to_buy = []
        cti_short_check = checkTAIndicator_OR({
            'TA_Indicators':[(TaType.MACD,'240m',233),
                            (TaType.MACD,'60m',233),
                            (TaType.MACD,'120m',233),
                            (TaType.BOLL,'1d',40),
                            (TaType.BOLL_UPPER,'5d',40),
                            (TaType.TRIX_STATUS, '240m', 100), 
                            (TaType.TRIX_STATUS, '5d', 100)], 
            'isLong':False})
        not_to_buy = cti_short_check.filter(context, data, to_buy)
        
        not_to_buy += self.g.monitor_long_cm.filterUpTrendDownTrend(stock_list=to_buy, level_list=self.monitor_levels[1:], update_df=False)
        not_to_buy += self.g.monitor_long_cm.filterUpTrendUpNode(stock_list=to_buy, level_list=self.monitor_levels[1:], update_df=False)
        not_to_buy += self.g.monitor_long_cm.filterUpNodeDownTrend(stock_list=to_buy, level_list=self.monitor_levels[1:], update_df=False)
        not_to_buy += self.g.monitor_long_cm.filterUpNodeUpNode(stock_list=to_buy, level_list=self.monitor_levels[1:], update_df=False)
        not_to_buy = list(set(not_to_buy))
        
        self.daily_list = [stock for stock in self.daily_list if stock not in not_to_buy]

        to_buy = [stock for stock in to_buy if stock not in not_to_buy] 
        to_buy = [stock for stock in to_buy if stock not in context.portfolio.positions.keys()] 
        to_buy = [stock for stock in self.g.monitor_buy_list if stock in to_buy]
        
        if context.current_dt.hour >= 14:
            # 技术分析买点
            cta = checkTAIndicator_OR({
            'TA_Indicators':[
                            (TaType.MACD,'60m',233),
                            (TaType.MACD,'240m',233),
                            (TaType.BOLL_MACD, '60m', 233),
                            (TaType.BOLL_MACD, '240m', 233),
                            (TaType.RSI, '240m', 100),
                            (TaType.RSI, '60m', 100),
                            (TaType.KDJ_CROSS, '1d', 100),
                            (TaType.KDJ_CROSS, '60m', 100),
                            ],
            'isLong':True})
            to_buy = cta.filter(context, data, to_buy)
        else:
            cta = checkTAIndicator_OR({
            'TA_Indicators':[
                            (TaType.MACD,'60m',233),
                            (TaType.BOLL_MACD, '60m', 233),
                            # (TaType.RSI, '60m', 100),
                            (TaType.KDJ_CROSS, '60m', 100),
                            ],
            'isLong':True})
            to_buy = cta.filter(context, data, to_buy)            
        if to_buy:
            self.log.info('日内待买股:\n' + join_list(["[%s]" % (show_stock(x)) for x in to_buy], ' ', 10))
            self.g.monitor_long_cm.displayMonitorMatrix(to_buy)
            self.adjust(context, data, to_buy)
            bought_stocks = [stock for stock in context.portfolio.positions.keys() if stock in to_buy]
            #transfer long gauge to short gauge
            self.g.monitor_short_cm.appendStockList(self.g.monitor_long_cm.getGaugeStockList(bought_stocks))
    
    def adjust(self, context, data, buy_stocks):
        # 买入股票
        # 始终保持持仓数目为g.buy_stock_count
        # 根据股票数量分仓
        # 此处只根据可用金额平均分配购买，不能保证每个仓位平均分配
        for pindex in self.g.op_pindexs:
            position_count = len(context.subportfolios[pindex].long_positions)
            if self.buy_count > position_count:
                # value = context.subportfolios[pindex].available_cash * self.pos_control / (self.buy_count - position_count)
                value = context.subportfolios[pindex].total_value * self.pos_control / self.buy_count
                for stock in buy_stocks:
                    if stock in self.g.sell_stocks:
                        continue
                    if context.subportfolios[pindex].long_positions[stock].total_amount == 0:
                        if self.g.open_position(self, stock, value, pindex):
                            if len(context.subportfolios[pindex].long_positions) == self.buy_count:
                                break

    def after_trading_end(self, context):
        self.g.sell_stocks = []
        self.daily_list = []
        
    def __str__(self):
        return '股票调仓买入规则：买在对应级别买点'

# '''---------------卖出股票规则--------------'''
class Sell_stocks(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        self.use_short_filter = params.get('use_short_filter', False)
        
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
        self.g.buy_stocks = [stock for stock in self.g.buy_stocks if stock not in to_sell]
        self.adjust(context, data, self.g.buy_stocks)

    def adjust(self, context, data, buy_stocks):
        # 卖出不在待买股票列表中的股票
        # 对于因停牌等原因没有卖出的股票则继续持有
        for pindex in self.g.op_pindexs:
            for stock in context.subportfolios[pindex].long_positions.keys():
                if stock not in buy_stocks:
                    position = context.subportfolios[pindex].long_positions[stock]
                    self.g.close_position(self, position, True, pindex)

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

    def update_params(self, context, params):
        Rule.update_params(self, context, params)
        self.buy_count = params.get('buy_count', self.buy_count)

    def handle_data(self, context, data):
        if context.current_dt.hour < 11:
            self.to_buy = self.g.buy_stocks
        self.log.info("待选股票: "+join_list([show_stock(stock) for stock in self.to_buy], ' ', 10))
        if self.use_short_filter:
            self.to_buy = self.ta_short_filter(context, data, self.to_buy)
        if context.current_dt.hour >= 14:
            if self.use_long_filter:
                self.to_buy = self.ta_long_filter(context, data, self.to_buy) 
            self.adjust(context, data, self.to_buy)

    def ta_long_filter(self, context, data, to_buy):
        cta = checkTAIndicator_OR({
            'TA_Indicators':[
                            # (TaType.MACD_ZERO,'60m',233),
                            (TaType.TRIX_STATUS, '240m', 100),
                            # (TaType.MACD_STATUS, '240m', 100),
                            (TaType.RSI, '240m', 100)
                            ],
            'isLong':True})
        to_buy = cta.filter(context, data,to_buy)
        return to_buy

    def ta_short_filter(self, context, data, to_buy):
        cti = checkTAIndicator_OR({
            'TA_Indicators':[
                            (TaType.MACD,'240m',233),
                            (TaType.MACD,'60m',233),
                            (TaType.MACD,'120m',233),
                            (TaType.BOLL, '240m',100),
                            (TaType.BOLL_UPPER, '1d',100),
                            ],
            'isLong':False})
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
                    if context.subportfolios[pindex].long_positions[stock].total_amount == 0:
                        if self.g.open_position(self, stock, value, pindex):
                            if len(context.subportfolios[pindex].long_positions) == self.buy_count:
                                break
        pass

    def after_trading_end(self, context):
        self.g.sell_stocks = []
        self.to_buy = []

    def __str__(self):
        return '股票调仓买入规则：现金平分式买入股票达目标股票数'

def generate_portion(num):
    total_portion = num * (num+1) / 2
    start = num
    while num != 0:
        yield float(num) / float(total_portion)
        num -= 1

class Buy_stocks_portion(Rule):
    def __init__(self,params):
        Rule.__init__(self, params)
        self.buy_count = params.get('buy_count',3)
    def update_params(self,context,params):
        self.buy_count = params.get('buy_count',self.buy_count)
    def handle_data(self, context, data):
        self.adjust(context, data, self.g.buy_stocks)
    def adjust(self,context,data,buy_stocks):
        if self.is_to_return:
            self.log_warn('无法执行买入!! self.is_to_return 未开启')
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
                        buy_portion = portion_gen.next()
                        value = available_cash * buy_portion
                        if self.g.open_position(self, stock, value, pindex):
                            if len(context.subportfolios[pindex].long_positions) == self.buy_count:
                                break
        pass
    def after_trading_end(self, context):
        self.g.sell_stocks = []
    def __str__(self):
        return '股票调仓买入规则：现金比重式买入股票达目标股票数'  

class Buy_stocks_var(Rule):
    """使用 VaR 方法做调仓控制"""

    def __init__(self, params):
        Rule.__init__(self, params)
        self.buy_count = params.get('buy_count', 3)
        self.pc_var = None

    def update_params(self, context, params):
        self.buy_count = params.get('buy_count', self.buy_count)

    def handle_data(self, context, data):
        self.adjust(context, data, self.g.buy_stocks)

    def adjust(self, context, data, buy_stocks):
        if not self.pc_var:
            # 设置 VaR 仓位控制参数。风险敞口: 0.05,
            # 正态分布概率表，标准差倍数以及置信率: 0.96, 95%; 2.06, 96%; 2.18, 97%; 2.34, 98%; 2.58, 99%; 5, 99.9999%
            # 赋闲资金可以买卖银华日利做现金管理: ['511880.XSHG']
            self.pc_var = PositionControlVar(context, 0.12, 2.58, [])
        if self.is_to_return:
            self.log_warn('无法执行买入!! self.is_to_return 未开启')
            return
        # 买入股票或者进行调仓
        # 始终保持持仓数目为g.buy_stock_count
        for pindex in self.g.op_pindexs:
            position_count = len(context.subportfolios[pindex].positions)
            trade_ratio = {}
            if self.buy_count > position_count:
                buy_num = self.buy_count - position_count
                trade_ratio = self.pc_var.buy_the_stocks(context, buy_stocks[:buy_num])
            else:
                trade_ratio = self.pc_var.func_rebalance(context)
            # print trade_ratio
            for stock in trade_ratio:
                if stock in self.g.sell_stocks:
                    continue
                if context.subportfolios[pindex].long_positions[stock].total_amount == 0:
                    if self.g.open_position(self, stock, context.subportfolios[pindex].total_value*trade_ratio[stock],pindex):
                        if len(context.subportfolios[pindex].long_positions) == self.buy_count:
                            break
    def after_trading_end(self, context):
        self.g.sell_stocks = []
        
    def __str__(self):
        return '股票调仓买入规则：使用 VaR 方式买入或者调整股票达目标股票数'


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


'''==================================其它=============================='''


# '''---------------------------------系统参数一般性设置---------------------------------'''
class Set_sys_params(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        pd.options.mode.chained_assignment = None
        try:
            # 一律使用真实价格
            set_option('use_real_price', self._params.get('use_real_price', True))
        except:
            pass
        try:
            # 过滤log
            log.set_level(*(self._params.get('level', ['order', 'error'])))
        except:
            pass
        try:
            # 设置基准
            set_benchmark(self._params.get('benchmark', '000300.XSHG'))
        except:
            pass
            # set_benchmark('399006.XSHE')
            # set_slippage(FixedSlippage(0.04))

    def __str__(self):
        return '设置系统参数：[使用真实价格交易] [忽略order 的 log] [设置基准]'


# '''------------------设置手续费-----------------'''
# 根据不同的时间段设置滑点与手续费并且更新指数成分股
class Set_slip_fee(Rule):
    def before_trading_start(self, context):
        # 根据不同的时间段设置手续费
        dt = context.current_dt
        if dt > datetime.datetime(2013, 1, 1):
            set_commission(PerTrade(buy_cost=0.0003, sell_cost=0.0013, min_cost=5))

        elif dt > datetime.datetime(2011, 1, 1):
            set_commission(PerTrade(buy_cost=0.001, sell_cost=0.002, min_cost=5))

        elif dt > datetime.datetime(2009, 1, 1):
            set_commission(PerTrade(buy_cost=0.002, sell_cost=0.003, min_cost=5))
        else:
            set_commission(PerTrade(buy_cost=0.003, sell_cost=0.004, min_cost=5))

    def __str__(self):
        return '根据时间设置不同的交易费率'


# '''------------------持仓信息打印器-----------------'''
class Show_position(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        self.op_sell_stocks = []
        self.op_buy_stocks = []

    def after_trading_end(self, context):
        self.log.info(self.__get_portfolio_info_text(context, self.g.op_pindexs))
        self.op_buy_stocks = []
        self.op_buy_stocks = []

    def on_sell_stock(self, position, order, is_normal, new_pindex=0, context=None):
        self.op_sell_stocks.append([position.security, order.filled])
        pass

    def on_buy_stock(self, stock, order, new_pindex=0, context=None):
        self.op_buy_stocks.append([stock, order.filled])
        pass

    # # 调仓后调用用
    # def after_adjust_end(self,context,data):
    #     print self.__get_portfolio_info_text(context,self.g.op_pindexs)
    #     pass
    # ''' ------------------------------获取持仓信息，普通文本格式------------------------------------------'''
    def __get_portfolio_info_text(self, context, op_sfs=[0]):
        sub_str = ''
        table = PrettyTable(["仓号", "股票", "持仓", "当前价", "盈亏", "持仓比"])
        # table.padding_width = 1# One space between column edges and contents (default)
        for sf_id in self.g.stock_pindexs:
            cash = context.subportfolios[sf_id].cash
            p_value = context.subportfolios[sf_id].positions_value
            total_values = p_value + cash
            if sf_id in op_sfs:
                sf_id_str = str(sf_id) + ' *'
            else:
                sf_id_str = str(sf_id)
            new_stocks = [x[0] for x in self.op_buy_stocks]
            for stock in context.subportfolios[sf_id].long_positions.keys():
                position = context.subportfolios[sf_id].long_positions[stock]
                if sf_id in op_sfs and stock in new_stocks:
                    stock_str = show_stock(stock) + ' *'
                else:
                    stock_str = show_stock(stock)
                stock_raite = (position.total_amount * position.price) / total_values * 100
                table.add_row([sf_id_str,
                               stock_str,
                               position.total_amount,
                               position.price,
                               "%.2f%%" % ((position.price - position.avg_cost) / position.avg_cost * 100),
                               "%.2f%%" % (stock_raite)]
                              )
            if sf_id < len(self.g.stock_pindexs) - 1:
                table.add_row(['----', '---------------', '-----', '----', '-----', '-----'])
            sub_str += '[仓号: %d] [总值:%d] [持股数:%d] [仓位:%.2f%%] \n' % (sf_id,
                                                                     total_values,
                                                                     len(context.subportfolios[sf_id].long_positions)
                                                                     , p_value * 100 / (cash + p_value))
        if len(context.portfolio.positions) == 0:
            return '子仓详情:\n' + sub_str
        else:
            return '子仓详情:\n' + sub_str + str(table)

    def __str__(self):
        return '持仓信息打印'


# ''' ----------------------统计类----------------------------'''
class Stat(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        # 加载统计模块
        self.trade_total_count = 0
        self.trade_success_count = 0
        self.statis = {'win': [], 'loss': []}
        self.gauge_stats_buffer = {} # stock : long_status
        self.gauge_stats = {'win':[], 'loss':[]} # tuple (stock, long_status, short_status)

    def after_trading_end(self, context):
        self.g.long_record = {}
        self.g.short_record = {}
        # self.report(context)
        self.print_win_rate(context.current_dt.strftime("%Y-%m-%d"), context.current_dt.strftime("%Y-%m-%d"), context)

    def on_sell_stock(self, position, order, is_normal, pindex=0,context=None):
        if order.filled > 0:
            # 只要有成交，无论全部成交还是部分成交，则统计盈亏
            self.watch(position.security, order.filled, position.avg_cost, position.price)

    def on_buy_stock(self,stock,order,pindex=0,context=None):
        if order.filled > 0:
            self.gauge_stats_buffer[stock] = tuple(self.g.monitor_long_cm.getGaugeStockList(stock))

    def reset(self):
        self.trade_total_count = 0
        self.trade_success_count = 0
        self.statis = {'win': [], 'loss': []}
        self.gauge_stats_buffer = {} # stock : long_status
        self.gauge_stats = {'win':[], 'loss':[]} # tuple (stock, long_status, short_status)

    # 记录交易次数便于统计胜率
    # 卖出成功后针对卖出的量进行盈亏统计
    def watch(self, stock, sold_amount, avg_cost, cur_price):
        self.trade_total_count += 1
        current_value = sold_amount * cur_price
        cost = sold_amount * avg_cost

        percent = round((current_value - cost) / cost * 100, 2)
        stock_long_status = self.gauge_stats_buffer.pop(stock, None) # this shouldn't be None
        if current_value > cost:
            self.trade_success_count += 1
            win = [stock, percent]
            self.statis['win'].append(win)
            self.gauge_stats['win'].append((stock, stock_long_status, tuple(self.g.monitor_short_cm.getGaugeStockList(stock))))
        else:
            loss = [stock, percent]
            self.statis['loss'].append(loss)
            self.gauge_stats['loss'].append((stock, stock_long_status, tuple(self.g.monitor_short_cm.getGaugeStockList(stock))))

    def report(self, context):
        cash = context.portfolio.cash
        totol_value = context.portfolio.portfolio_value
        position = 1 - cash / totol_value
        self.log.info("收盘后持仓概况:%s" % str(list(context.portfolio.positions)))
        self.log.info("仓位概况:%.2f" % position)
        self.print_win_rate(context.current_dt.strftime("%Y-%m-%d"), context.current_dt.strftime("%Y-%m-%d"), context)

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
            
            # win_stats = self.gauge_stats['win']
            # loss_stats = self.gauge_stats['loss']
            # status_win_stats = {}
            # status_loss_stats = {}
            # self.help_status_stats(win_stats, status_win_stats)
            # self.help_status_stats(loss_stats, status_loss_stats)
            # s_msg = '\n----------------------------统计报表----------------------------'
            # for key, value in status_win_stats.items():
            #     s_msg += '\n成功买入: {0}, 成功卖出: {1}, 次数: {2}'.format(key[0], key[1], value)
            # for key, value in status_loss_stats.items():
            #     s_msg += '\n失败买入: {0}, 失败卖出: {1}, 次数: {2}'.format(key[0], key[1], value)
            # s += '\n---------------------------------------------------------------'
            # self.log.info(s_msg)
            
            # concise_win_stats = {}
            # concise_loss_stats = {}
            # self.help_status_stats_concise(win_stats, concise_win_stats)
            # self.help_status_stats_concise(loss_stats, concise_loss_stats)
            # s_concise_msg = '\n----------------------------统计报表----------------------------'
            # for key, value in concise_win_stats.items():
            #     s_concise_msg += '\n成功状态: {0}, 次数: {1}'.format(key, value)
            # for key, value in concise_loss_stats.items():
            #     s_concise_msg += '\n失败状态: {0}, 次数: {1}'.format(key, value)
            # s += '\n---------------------------------------------------------------'
            # self.log.info(s_concise_msg)

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

# ''' ----------------------参数自动调整----------------------------'''
class Update_Params_Auto(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        self.ps_threthold = params.get('ps_threthold',0.618)
        self.pb_threthold = params.get('pb_threthold',0.618)
        self.pe_threthold = params.get('pe_threthold',0.8)
        self.buy_threthold = params.get('buy_threthold', 0.9)
        self.pos_control_value = params.get('pos_control_value', 0.5)

    def before_trading_start(self, context):
        if self.g.isFirstTradingDayOfWeek(context):
            g.ps_limit = self.g.getFundamentalThrethold('valuation.ps_ratio', self.ps_threthold)
            g.pb_limit = self.g.getFundamentalThrethold('valuation.pb_ratio', self.pb_threthold)
            g.pe_limit = self.g.getFundamentalThrethold('valuation.pe_ratio', self.pe_threthold)
            
            stock_list = get_index_stocks('000300.XSHG')
            stock_list_df = history(1, unit='1d', field='avg', security_list=stock_list, df=True, skip_paused=False, fq='pre')
            stock_list_df = stock_list_df.transpose()
            stock_list_df = stock_list_df.sort(stock_list_df.columns.values[0], ascending=True, axis=0)
            threthold_price = stock_list_df.iloc[int(self.buy_threthold * 300),0] # 000300
            g.buy_count = int(context.portfolio.portfolio_value / (threthold_price * 1000)) # 10手
            self.log.info("每周修改全局参数: ps_limit: %s pb_limit: %s pe_limit: %s buy_count: %s" % (g.ps_limit, g.pb_limit, g.pe_limit, g.buy_count))
        
        self.doubleIndexControl('000016.XSHG', '399333.XSHE')
        self.log.info("每日修改全局参数: port_pos_control: %s" % (g.port_pos_control))
        self.updateRelaventRules(context)
    
    def doubleIndexControl(self, index1, index2, target=0, period=20):
        # 大盘周线弱势， 按照仓位比例操作
        # ta_trix = TA_Factor_Short({'ta_type':TaType.TRIX, 'period':'5d', 'count':100})
        # g.port_pos_control = self.pos_control_value if ta_trix.check_TRIX_list('000300.XSHG') else 1.0
        
        # ta_trix_long = TA_Factor_Long({'ta_type':TaType.TRIX_PURE, 'period':'5d', 'count':100, 'isLong':True})
        # long_list = ta_trix_long.filter(['000016.XSHG','399333.XSHE'])
        # if len(long_list) == 0:
        #     g.port_pos_control = self.pos_control_value / 2
        # elif len(long_list) == 1:
        #     g.port_pos_control = self.pos_control_value
        # else:
        #     g.port_pos_control = 1.0
        
        gr_index1 = get_growth_rate(index1, period)
        gr_index2 = get_growth_rate(index2, period)
        target = 0.01
        if gr_index1 < target and gr_index2 < target:
            g.port_pos_control = self.pos_control_value / 2
        elif gr_index1 >= target or gr_index2 >= target:
            g.port_pos_control = self.pos_control_value
        else:
            g.port_pos_control = 1.0  

    def updateRelaventRules(self, context):
        # print g.main.rules
        # update everything
        for rule in g.main.rules:
            if isinstance(rule, Pick_stocks2):
                for r2 in rule.rules:
                    if isinstance(r2, Filter_financial_data2):
                        r2.update_params(context, {
                            'factors': [FD_Factor('valuation.ps_ratio', min=0, max=g.ps_limit),
                                        FD_Factor('valuation.pe_ratio', min=0, max=g.pe_limit),
                                        FD_Factor('valuation.pb_ratio', min=0, max=g.pb_limit),
                                        ],
                            'order_by': 'valuation.circulating_market_cap',
                            'sort': SortType.asc,
                            'limit':50})
                        # print r2._params.get('factors', None)[0].max
            if isinstance(rule, Adjust_position):
                for r3 in rule.rules:
                    if isinstance(r3, Buy_stocks_chan):
                        r3.update_params(context, {'buy_count': g.buy_count, 'pos_control': g.port_pos_control})
                        # print r3.buy_count
                        # print r3.pos_control

    def __str__(self):
        return '参数自动调整'
'''===============================其它基础函数=================================='''


def get_growth_rate(security, n=20):
    '''
    获取股票n日以来涨幅，根据当前价(前1分钟的close）计算
    n 默认20日  
    :param security: 
    :param n: 
    :return: float
    '''
    lc = get_close_price(security, n)
    c = get_close_price(security, 1, '1m')

    if not isnan(lc) and not isnan(c) and lc != 0:
        return (c - lc) / lc
    else:
        log.error("数据非法, security: %s, %d日收盘价: %f, 当前价: %f" % (security, n, lc, c))
        return 0


def get_close_price(security, n, unit='1d'):
    '''
    获取前n个单位时间当时的收盘价
    为防止取不到收盘价，试3遍
    :param security: 
    :param n: 
    :param unit: '1d'/'1m'
    :return: float
    '''
    cur_price = np.nan
    for i in range(3):
        cur_price = attribute_history(security, n, unit, 'close', True)['close'][0]
        if not math.isnan(cur_price):
            break
    return cur_price


# 获取一个对象的类名
def get_obj_class_name(obj):
    cn = str(obj.__class__)
    cn = cn[cn.find('.') + 1:]
    return cn[:cn.find("'")]


def show_stock(stock):
    '''
    获取股票代码的显示信息    
    :param stock: 股票代码，例如: '603822.XSHG'
    :return: str，例如：'603822 嘉澳环保'
    '''
    return "%s %s" % (stock[:6], get_security_info(stock).display_name)


def join_list(pl, connector=' ', step=5):
    '''
    将list组合为str,按分隔符和步长换行显示(List的成员必须为字符型)
    例如：['1','2','3','4'],'~',2  => '1~2\n3~4'
    :param pl: List
    :param connector: 分隔符，默认空格 
    :param step: 步长，默认5
    :return: str
    '''
    result = ''
    for i in range(len(pl)):
        result += pl[i]
        if (i + 1) % step == 0:
            result += '\n'
        else:
            result += connector
    return result


'''-----------------根据XueQiuOrder下单------------------------'''
class XueQiu_order(Op_stocks_record):
    def __init__(self,params):
        self.version = params.get('version',1)
        self.xueqiu = XueQiuAction('xq', self.version)
        pass
        
    def update_params(self, context, params):
        self.__init__(params)
        
    def after_trading_end(self,context):
        self.xueqiu.reset()
        pass
        
        # 调仓后调用
    def after_adjust_end(self,context,data):
        self.xueqiu.adjustStock()
        self.xueqiu.reset()

    # 卖出股票时调用的函数
    def on_sell_stock(self,position,order,is_normal,pindex=0,context=None):
        try:
            if not order.is_buy:
                target_amount = 0 if order.action == 'close' else position.total_amount
                target_pct = target_amount * order.price / context.portfolio.total_value * 100
                self.log.info("xue qiu sell %s to target %s" % (position.security, target_pct))
                self.xueqiu.appendOrder(order.security[:6], target_pct, 0)
                pass
        except:
            self.log.error('雪球交易失败:' + str(order))
        pass
    
    # 买入股票时调用的函数
    def on_buy_stock(self,stock,order,pindex=0,context=None):
        try:
            if order.is_buy:
                target_amount = order.filled
                target_pct = target_amount * order.price / context.portfolio.total_value * 100
                self.log.info("xue qiu buy %s to target %s" % (stock, target_pct))
                self.xueqiu.appendOrder(order.security[:6], target_pct, 0)
            pass
        except:
            self.log.error('雪球交易失败:' + str(order))
        pass
    def __str__(self):
        return '雪球跟踪盘'




'''=================================实盘易相关================================='''


# '''-------------------实盘易对接 同步持仓-----------------------'''
class Shipane_manager(Op_stocks_record):
    def __init__(self, params):
        Op_stocks_record.__init__(self, params)
        try:
            log
            self._logger = shipane_sdk._Logger()
        except NameError:
            import logging
            self._logger = logging.getLogger()
        self.moni_trader = JoinQuantTrader()
        self.shipane_trader = ShipaneTrader(self._logger, **params)
        self.syncer = TraderSynchronizer(self._logger
                                         , self.moni_trader
                                         , self.shipane_trader
                                         , normalize_code=normalize_code
                                         , **params)
        self._cost = params.get('cost', 100000)
        self._source_trader_record = []
        self._dest_trader_record = []

    def update_params(self, context, params):
        Op_stocks_record.update_params(self, context, params)
        self._cost = params.get('cost', 100000)
        self.shipane_trader = ShipaneTrader(self._logger, **params)
        self.syncer = TraderSynchronizer(self._logger
                                         , self.moni_trader
                                         , self.shipane_trader
                                         , normalize_code=normalize_code
                                         , **params)

    def after_adjust_end(self, context, data):
        # 是否指定只在有发生调仓动作时进行调仓
        if self._params.get('sync_with_change', True):
            if self.position_has_change:
                self.syncer.execute(context, data)
        else:
            self.syncer.execute(context, data)
        self.position_has_change = False

    def on_clear_position(self, context, pindex=[0]):
        if self._params.get('sync_with_change', True):
            if self.position_has_change:
                self.syncer.execute(context, None)
        else:
            self.syncer.execute(context, None)
        self.position_has_change = False

    def after_trading_end(self, context):
        Op_stocks_record.after_trading_end(self, context)
        try:
            self.moni_trader.context = context
            self.shipane_trader.context = context
            # 记录模拟盘市值
            pf = self.moni_trader.portfolio
            self._source_trader_record.append([self.moni_trader.current_dt, pf.positions_value + pf.available_cash])
            # 记录实盘市值
            pf = self.shipane_trader.portfolio
            self._dest_trader_record.append([self.shipane_trader.current_dt, pf.positions_value + pf.available_cash])
            self._logger.info('[实盘管理器] 实盘涨幅统计:\n' + self.get_rate_str(self._dest_trader_record))
            self._logger.info('[实盘管理器] 实盘持仓统计:\n' + self._get_trader_portfolio_text(self.shipane_trader))
        except Exception as e:
            self._logger.error('[实盘管理器] 盘后数据处理错误!' + str(e))

    def get_rate_str(self, record):
        if len(record) > 1:
            if record[-2][1] == 0:
                return '穷鬼，你没钱，还统计啥'
            rate_total = (record[-1][1] - self._cost) / self._cost
            rate_today = (record[-1][1] - record[-2][1]) / record[-2][1]
            now = datetime.datetime.now()
            record_week = [x for x in record if (now - x[0]).days <= 7]
            rate_week = (record[-1][1] - record_week[0][1]) / record_week[0][1] if len(record_week) > 0 else 0
            record_mouth = [x for x in record if (now - x[0]).days <= 30]
            rate_mouth = (record[-1][1] - record_mouth[0][1]) / record_mouth[0][1] if len(record_mouth) > 0 else 0
            return '资产涨幅:[总:%.2f%%] [今日%.2f%%] [最近一周:%.2f%%] [最近30:%.2f%%]' % (
                rate_total * 100
                , rate_today * 100
                , rate_week * 100
                , rate_mouth * 100)
        else:
            return '数据不足'
        pass

    # 获取持仓信息，HTML格式
    def _get_trader_portfolio_html(self, trader):
        pf = trader.portfolio
        total_values = pf.positions_value + pf.available_cash
        position_str = "总资产: [ %d ]<br>市值: [ %d ]<br>现金   : [ %d ]<br>" % (
            total_values,
            pf.positions_value, pf.available_cash
        )
        position_str += "<table border=\"1\"><tr><th>股票代码</th><th>持仓</th><th>当前价</th><th>盈亏</th><th>持仓比</th></tr>"
        for position in pf.positions.values():
            stock = position.security
            if position.price - position.avg_cost > 0:
                tr_color = 'red'
            else:
                tr_color = 'green'
            stock_raite = (position.total_amount * position.price) / total_values * 100
            position_str += '<tr style="color:%s"><td> %s </td><td> %d </td><td> %.2f </td><td> %.2f%% </td><td> %.2f%%</td></tr>' % (
                tr_color,
                show_stock(normalize_code(stock)),
                position.total_amount, position.price,
                (position.price - position.avg_cost) / position.avg_cost * 100,
                stock_raite
            )

        return position_str + '</table>'

    # 获取持仓信息，普通文本格式
    def _get_trader_portfolio_text(self, trader):
        pf = trader.portfolio
        total_values = pf.positions_value + pf.available_cash
        position_str = "总资产 : [ %d ] 市值: [ %d ] 现金   : [ %d ]" % (
            total_values,
            pf.positions_value, pf.available_cash
        )

        table = PrettyTable(["股票", "持仓", "当前价", "盈亏", "持仓比"])
        for stock in pf.positions.keys():
            position = pf.positions[stock]
            if position.total_amount == 0:
                continue
            stock_str = show_stock(normalize_code(stock))
            stock_raite = (position.total_amount * position.price) / total_values * 100
            table.add_row([
                stock_str,
                position.total_amount,
                position.price,
                "%.2f%%" % ((position.price - position.avg_cost) / position.avg_cost * 100),
                "%.2f%%" % (stock_raite)]
            )
        return position_str + '\n' + str(table)

    def __str__(self):
        return '实盘管理类:[同步持仓] [实盘邮件] [实盘报表]'


# '''------------------------------通过实盘易申购新股----------------------'''
class Purchase_new_stocks(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        self.times = params.get('times', [[10, 00]])
        self.host = params.get('host', '')
        self.port = params.get('port', 8888)
        self.key = params.get('key', '')
        self.clients = params.get('clients', [])

    def update_params(self, context, params):
        Rule.update_params(self, context, params)
        self.times = params.get('times', [[10, 00]])
        self.host = params.get('host', '')
        self.port = params.get('port', 8888)
        self.key = params.get('key', '')
        self.clients = params.get('clients', [])

    def handle_data(self, context, data):
        hour = context.current_dt.hour
        minute = context.current_dt.minute
        if not [hour, minute] in self.times:
            return
        try:
            import shipane_sdk
        except:
            pass
        shipane = shipane_sdk.Client(g.log_type(self.memo), key=self.key, host=self.host, port=self.port,
                                     show_info=False)
        for client_param in self.clients:
            shipane.purchase_new_stocks(client_param)

    def __str__(self):
        return '实盘易申购新股[time: %s host: %s:%d  key: %s client:%s] ' % (
            self.times, self.host, self.port, self.key, self.clients)
            
# '''------------------邮件通知器-----------------'''
class Email_notice(Op_stocks_record):
    def __init__(self, params):
        Op_stocks_record.__init__(self, params)
        self.user = params.get('user', '')
        self.password = params.get('password', '')
        self.tos = params.get('tos', '')
        self.sender_name = params.get('sender', '发送者')
        self.strategy_name = params.get('strategy_name', '策略1')
        self.str_old_portfolio = ''

    def update_params(self, context, params):
        Op_stocks_record.update_params(self, context, params)
        self.user = params.get('user', '')
        self.password = params.get('password', '')
        self.tos = params.get('tos', '')
        self.sender_name = params.get('sender', '发送者')
        self.strategy_name = params.get('strategy_name', '策略1')
        self.str_old_portfolio = ''
        try:
            Op_stocks_record.update_params(self, context, params)
        except:
            pass

    def before_adjust_start(self, context, data):
        Op_stocks_record.before_trading_start(self, context)
        self.str_old_portfolio = self.__get_portfolio_info_html(context)
        pass

    def after_adjust_end(self, context, data):
        Op_stocks_record.after_adjust_end(self, context, data)
        try:
            send_time = self._params.get('send_time', [])
        except:
            send_time = []
        if self._params.get('send_with_change', True) and not self.position_has_change:
            return
        if len(send_time) == 0 or [context.current_dt.hour, context.current_dt.minute] in send_time:
            self.__send_email('%s:调仓结果' % (self.strategy_name)
                              , self.__get_mail_text_before_adjust(context
                                                                   , ''
                                                                   , self.str_old_portfolio
                                                                   , self.op_sell_stocks
                                                                   , self.op_buy_stocks))
            self.position_has_change = False  # 发送完邮件，重置标记

    def after_trading_end(self, context):
        Op_stocks_record.after_trading_end(self, context)
        self.str_old_portfolio = ''

    def on_clear_position(self, context, new_pindexs=[0]):
        # 清仓通知
        self.op_buy_stocks = self.merge_op_list(self.op_buy_stocks)
        self.op_sell_stocks = self.merge_op_list(self.op_sell_stocks)
        if len(self.op_buy_stocks) > 0 or len(self.op_sell_stocks) > 0:
            self.__send_email('%s:清仓' % (self.strategy_name), '已触发清仓')
            self.op_buy_stocks = []
            self.op_sell_stocks = []
        pass

    # 发送邮件 subject 为邮件主题,content为邮件正文(当前默认为文本邮件)
    def __send_email(self, subject, text):
        # # 发送邮件
        username = self.user  # 你的邮箱账号
        password = self.password  # 你的邮箱授权码。一个16位字符串

        sender = '%s<%s>' % (self.sender_name, self.user)

        msg = MIMEText("<pre>" + text + "</pre>", 'html', 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['to'] = ';'.join(self.tos)
        msg['from'] = sender  # 自己的邮件地址

        server = smtplib.SMTP_SSL('smtp.qq.com')
        try:
            # server.connect() # ssl无需这条
            server.login(username, password)  # 登陆
            server.sendmail(sender, self.tos, msg.as_string())  # 发送
            self.log.info('邮件发送成功:' + subject)
        except:
            self.log.info('邮件发送失败:' + subject)
        server.quit()  # 结束

    def __get_mail_text_before_adjust(self, context, op_info, str_old_portfolio,
                                      to_sell_stocks, to_buy_stocks):
        # 获取又买又卖的股票，实质为调仓
        mailtext = context.current_dt.strftime("%Y-%m-%d %H:%M:%S")
        if len(self.g.buy_stocks) >= 5:
            mailtext += '<br>选股前5:<br>' + ''.join(['%s<br>' % (show_stock(x)) for x in self.g.buy_stocks[:5]])
            mailtext += '--------------------------------<br>'
        # mailtext += '<br><font color="blue">'+op_info+'</font><br>'
        if len(to_sell_stocks) + len(to_buy_stocks) == 0:
            mailtext += '<br><font size="5" color="red">* 无需调仓! *</font><br>'
            mailtext += '<br>当前持仓:<br>'
        else:
            #             mailtext += '<br>==> 调仓前持仓:<br>'+str_old_portfolio+"<br>==> 执行调仓<br>--------------------------------<br>"
            mailtext += '卖出股票:<br><font color="blue">'
            mailtext += ''.join(['%s %d<br>' % (show_stock(x[0]), x[1]) for x in to_sell_stocks])
            mailtext += '</font>--------------------------------<br>'
            mailtext += '买入股票:<br><font color="red">'
            mailtext += ''.join(['%s %d<br>' % (show_stock(x[0]), x[1]) for x in to_buy_stocks])
            mailtext += '</font>'
            mailtext += '<br>==> 调仓后持仓:<br>'
        mailtext += self.__get_portfolio_info_html(context)
        return mailtext

    def __get_portfolio_info_html(self, context):
        total_values = context.portfolio.positions_value + context.portfolio.cash
        position_str = "--------------------------------<br>"
        position_str += "总市值 : [ %d ]<br>持仓市值: [ %d ]<br>现金   : [ %d ]<br>" % (
            total_values,
            context.portfolio.positions_value, context.portfolio.cash
        )
        position_str += "<table border=\"1\"><tr><th>股票代码</th><th>持仓</th><th>当前价</th><th>盈亏</th><th>持仓比</th></tr>"
        for stock in context.portfolio.positions.keys():
            position = context.portfolio.positions[stock]
            if position.price - position.avg_cost > 0:
                tr_color = 'red'
            else:
                tr_color = 'green'
            stock_raite = (position.total_amount * position.price) / total_values * 100
            position_str += '<tr style="color:%s"><td> %s </td><td> %d </td><td> %.2f </td><td> %.2f%% </td><td> %.2f%%</td></tr>' % (
                tr_color,
                show_stock(stock),
                position.total_amount, position.price,
                (position.price - position.avg_cost) / position.avg_cost * 100,
                stock_raite
            )

        return position_str + '</table>'

    def __str__(self):
        return '调仓结果邮件通知:[发送人:%s] [接收人:%s]' % (self.sender_name, str(self.tos))


# ===================== VaR仓位控制 ===============================================

class PositionControlVar(object):
    """基于风险价值法（VaR）的仓位控制"""

    def __init__(self, context, risk_money_ratio=0.05, confidencelevel=2.58, moneyfund=['511880.XSHG']):
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
        # ratio = 1.0 / len(stocks)       # equal 
        portion_gen = generate_portion(len(stocks))
        for stock in stocks:
            equity_ratio[stock] = portion_gen.next()
        trade_ratio = self.func_getequity_value(context, equity_ratio)
        # self.func_trade(context, trade_ratio)
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
            # self.func_trade(context, trade_ratio)
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
            hStocks = history(1, '1d', 'close', __equity_list, df=False)

            __curVaR = 0
            __portfolio_VaR = 0

            for stock in __equity_list:
                # 每股的 VaR，VaR = 上一日的价格 * 置信度换算得来的标准倍数 * 日收益率的标准差
                __curVaR = hStocks[stock] * __confidence_ratio * __func_getStd(stock, '1d', 120)
                # 一元会分配买多少股
                __curAmount = 1 * __equity_ratio[stock] / hStocks[stock]  # 1单位资金，分配时，该股票可以买多少股
                __portfolio_VaR += __curAmount * __curVaR  # 1单位资金时，该股票上的实际风险敞口
            
            if __portfolio_VaR:
                __equity_value = __risk_money / __portfolio_VaR
            else:
                __equity_value = 0

            if isnan(__equity_value):
                __equity_value = 0

            # print __equity_list
            # print __portfolio_VaR
            # print __equity_value

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
