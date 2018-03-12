import numpy as np
import pandas as pd
import talib
from prettytable import PrettyTable
import types
from common_include import *
from oop_strategy_frame import *
from oop_adjust_pos import *
from oop_stop_loss import *
from oop_select_stock import *
from oop_sort_stock import *
from oop_record_stats import *
from oop_trading_sync import *


# 不同步的白名单，主要用于实盘易同步持仓时，不同步中的新股，需把新股代码添加到这里。https://www.joinquant.com/algorithm/index/edit?algorithmId=23c589f4594f827184d4f6f01a11b2f2
# 可把white_list另外放到研究的一个py文件里
def white_list():
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
    g.evs_limit = 5
    g.eve_limit = 5
    index2 = '000016.XSHG'  # 大盘指数
    index8 = '399333.XSHE'  # 小盘指数
    g.money_fund = ['511880.XSHG','511010.XSHG','511220.XSHG']
    
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
        [False, '', '多指数技术分析止损器', Mul_index_stop_loss_ta, {
            'indexs': [index2, index8],
            'ta_type': TaType.TRIX_PURE,
            'period':'5d'
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
                        'useAvg':False,
                        'avgPeriod':5}],
        [False, '', '基本面数据筛选', Filter_financial_data, {'factor':'valuation.pe_ratio', 'min':0, 'max':80}],
        [True, '', '基本面数据筛选', Filter_financial_data2, {
            'factors': [
                        FD_Factor('valuation.ps_ratio', min=0, max=g.ps_limit),
                        FD_Factor('valuation.pe_ratio', min=0, max=g.pe_limit),
                        # FD_Factor('valuation.pcf_ratio', min=0, max=100),
                        FD_Factor('valuation.pb_ratio', min=0, max=g.pb_limit),
                        # FD_Factor(eve_query_string
                        #         , min=0
                        #         , max=5
                        #         , isComplex=True),
                        # FD_Factor(evs_query_string
                        #         , min=0
                        #         , max=5
                        #         , isComplex=True),
                        ],
            'order_by': 'valuation.market_cap',
            'sort': SortType.asc,
            'by_sector': False,
            'limit':50}],
        [False, '', '小佛雪选股', Filter_FX_data, {'limit':50}],
        # 测试的多因子选股,所选因子只作为示例。
        # 选用的财务数据参考 https://www.joinquant.com/data/dict/fundamentals
        # 传入参数的财务因子需为字符串，原因是直接传入如 indicator.eps 会存在序列化问题。
        # FD_Factor 第一个参数为因子，min=为最小值 max为最大值，=None则不限，默认都为None。min,max都写则为区间
        [False, '', '多因子选股票池', Pick_financial_data, {
            'factors': [
                # FD_Factor('valuation.circulating_market_cap', min=0, max=1000)  # 流通市值0~1000
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
        [False, '', '强势股筛选', Filter_Herd_head_stocks,{'gainThre':0.05, 'count':20, 'useIntraday':True, 'filter_out':True}],
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
                [True, 'Sort_std_data', '波动率排序', Sort_std_data, {
                    'sort': SortType.asc
                    , 'period': 60
                    , 'weight': 100}],
                [False, 'cash_flow_rank', '庄股脉冲排序', Sort_cash_flow_rank, {
                    'sort': SortType.desc
                    , 'weight': 100}],
                [False, '', '市值排序', Sort_financial_data, {
                    'factor': 'valuation.market_cap',
                    'sort': SortType.asc
                    , 'weight': 100}],
                [False, '', 'EVS排序', Sort_financial_data, {
                    'factor': evs_query_string,
                    'sort': SortType.asc
                    , 'weight': 100}],
                [False, '', '流通市值排序', Sort_financial_data, {
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
                [False, '5growth', '5日涨幅排序', Sort_growth_rate, {
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
                [False, 'cash_flow_rank', '庄股脉冲排序', Sort_cash_flow_rank, {
                    'sort': SortType.desc
                    , 'weight': 100}],
                [False, '', '按换手率排序', Sort_turnover_ratio, {
                    'sort': SortType.desc
                    , 'weight': 50}],
            ]}
        ],
        [True, '', '获取最终选股数', Filter_buy_count, {
            'buy_count': 20  # 最终入选股票数
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
        [False, '', '买入股票日内表里', Buy_stocks_chan, {
            'buy_count': g.buy_count,
            'monitor_levels': g.monitor_levels, 
            'pos_control':g.port_pos_control}],
        [True,'','VaR方式买入股票', Buy_stocks_var, {
            'buy_count': g.buy_count,
            'monitor_levels': g.monitor_levels, 
            'pos_control':g.port_pos_control,
            'money_fund':g.money_fund,
            'adjust_pos':True,
            'equal_pos':True,
            }],
        [True, '_Show_postion_adjust_', '显示买卖的股票', Show_postion_adjust, {}],
        [g.is_sim_trade,'trade_Xq','Xue Qiu Webtrader',XueQiu_order,{'version':3}],
        # 实盘易同步持仓，把虚拟盘同步到实盘
        # [g.is_sim_trade, '_Shipane_manager_', '实盘易操作', Shipane_manager, {
        #     'host':'111.111.111.111',   # 实盘易IP
        #     'port':8888,    # 实盘易端口
        #     'key':'',   # 实盘易Key
        #     'client':'title:guangfa', # 实盘易client
        #     'strong_op':False,   # 强力同步模式，开启会强行同步两次。
        #     'col_names':col_names, # 指定实盘易返回的持仓字段映射
        #     'cost':context.portfolio.starting_cash, # 实盘的初始资金
        #     'get_white_list_func':white_list, # 不同步的白名单
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
        [True, '', '统计执行器', Stat, {'trade_stats':True}],
        [True, '', '自动调参器', Update_Params_Auto, {
            'ps_threthold':0.618,
            'pb_threthold':0.618,
            'pe_threthold':0.809,
            'buy_threthold':0.809,
            'evs_threthold':0.618,
            'eve_threthold':0.618,
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
        g.main.after_code_changed(context)
        g.main.log.info(g.main.show_strategy())
    except Exception as e:
        log.error('更新代码失败:' + str(e))
        # initialize(context)
        pass



