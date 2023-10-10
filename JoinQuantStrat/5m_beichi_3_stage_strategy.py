import types
from common_include import *
from oop_strategy_frame import *
from oop_adjust_pos import *
from oop_stop_loss import *
from oop_select_stock import *
from oop_sort_stock import *
from oop_record_stats import *
from chan_common_include import Chan_Type

import pandas as pd
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

# ==================================策略配置==============================================
def select_strategy(context):
    g.strategy_memo = '缠短线策略'
    # **** 这里定义log输出的类类型,重要，一定要写。假如有需要自定义log，可更改这个变量
    g.log_type = Rule_loger
    # 判断是运行回测还是运行模拟
    g.is_sim_trade = context.run_params.type == 'sim_trade'
    g.port_pos_control = 1.0 # 组合仓位控制参数
    g.monitor_levels = ['5m','1m']
    g.buy_count = 10
    g.stock_chan_type = {}
    g.money_fund = ['511880.XSHG']
    
    ''' ---------------------配置 调仓条件判断规则-----------------------'''
    # 调仓条件判断
    adjust_condition_config = [
        [True, '_time_c_', '调仓时间', Time_condition, {
            'times': [[10,0], [10, 30],[11, 0],[13,0], [13,30],[14,0], [14, 50]],  # 调仓时间列表，二维数组，可指定多个时间点
        }],
        [True, '', '调仓日计数器', Period_condition, {
            'period': 1,  # 调仓频率,日
            'clear_wait': 0
        }],
    ]
    adjust_condition_config = [
        [True, '_adjust_condition_', '调仓执行条件的判断规则组合', Group_rules, {
            'config': adjust_condition_config
        }]
    ]

    ''' --------------------------配置 选股规则----------------- '''
    pick_config = [
        # [False, '', '缠论有效选股', Pick_Chan_Stocks,{
        #                 'index': '000985.XSHG',
        #                 'periods':['1w'],
        #                 'chan_types':[Chan_Type.I],
        #                 'isdebug':False, 
        #                 'number_of_stock':13,
        #                 'number_of_data':4800
        #     }],
        [True, '', '缠论提前选股', Pick_stock_from_file_chan, {
                        'filename':'chan_stocks_initial_scan_daily.txt', #'chan_stocks_initial_scan_daily.txt',
                        'current_chan_types': [Chan_Type.I], # Chan_Type.I_weak
                        'top_chan_types': [Chan_Type.INVALID, Chan_Type.I, Chan_Type.I_weak],
                        'on_demand':False,
                        'min_stock_num':0
            }],
        # [True, '', 'DEBUG', Read_stock_from_file_chan, {
        #                 'filename':'chan_stocks_initial_scan_daily.txt',
        #                 'current_chan_types': [Chan_Type.I, Chan_Type.I_weak],
        #                 'top_chan_types': [Chan_Type.INVALID, Chan_Type.I, Chan_Type.I_weak],
        #                 'on_demand':False,
        #                 'min_stock_num':0
        #     }],
        # [True, '', '筛选可能暴雷公司', Filter_black_stocks, {}],
        [True, '', '缠论强弱势板块', Filter_Industry_Sector,{
                        'strong_sector':True, 
                        'sector_limit_pct': 80.2,
                        'strength_threthold': 0, 
                        'isDaily': True, 
                        'useIntradayData':False,
                        'useAvg':True,
                        'avgPeriod':55,
                        'period_frequency':'W',
                        'isWeighted':True
                        }],
        # [True, '', '基本面数据排序', Sort_By_Financial_Data, {
        #     'f_type': "evs",
        #     'isdebug':False,
        #     'force_positive': False,
        #     'limit':55}],
        [True, '', '过滤ST,停牌,涨跌停股票', Filter_common, {}],
        # [False, '', '过滤创业板', Filter_gem, {}],
        [True, '', '', Filter_Chan_Stocks, {
                        'isdebug':False,
                        'isDescription':False,
                        'sup_chan_type':[Chan_Type.INVALID, Chan_Type.I, Chan_Type.I_weak],
                        'current_chan_type':[Chan_Type.I, Chan_Type.I_weak],
                        'sub_chan_type':[Chan_Type.I, Chan_Type.INVALID, Chan_Type.I_weak],
                        'peroid':['5m','1m'], #['1m','bi']
                        'long_stock_num':g.buy_count,
                        'long_candidate_num':55,
                        'num_of_data':4800,
                        'sub_force_zhongshu':True,
                        'bi_level_precision':True, 
                        'long_hour_start':9,
                        'long_min_start':30,
                        'sub_split':False,
                        'ignore_xd':True,
                        'force_chan_type': [
                                          [Chan_Type.I, Chan_Type.I, Chan_Type.I],
                                          [Chan_Type.INVALID, Chan_Type.I, Chan_Type.I],
                                          [Chan_Type.I_weak, Chan_Type.I, Chan_Type.I],
                                          
                                          [Chan_Type.INVALID, Chan_Type.I, Chan_Type.I_weak],
                                          [Chan_Type.I, Chan_Type.I, Chan_Type.I_weak],
                                          [Chan_Type.I_weak, Chan_Type.I, Chan_Type.I_weak],
                                          
                                          [Chan_Type.INVALID, Chan_Type.I, Chan_Type.INVALID],
                                          
                                          [Chan_Type.I, Chan_Type.I, Chan_Type.INVALID],
                                          [Chan_Type.I_weak, Chan_Type.I, Chan_Type.INVALID],
                                          
                                          [Chan_Type.I, Chan_Type.I_weak, Chan_Type.I],
                                          [Chan_Type.INVALID, Chan_Type.I_weak, Chan_Type.I],
                                          [Chan_Type.I_weak, Chan_Type.I_weak, Chan_Type.I],
                                          
                                          [Chan_Type.INVALID, Chan_Type.I_weak, Chan_Type.I_weak],
                                          [Chan_Type.I, Chan_Type.I_weak, Chan_Type.I_weak],
                                          [Chan_Type.I_weak, Chan_Type.I_weak, Chan_Type.I_weak],
                                          
                                          [Chan_Type.INVALID, Chan_Type.I_weak, Chan_Type.INVALID],
                                          
                                          [Chan_Type.I, Chan_Type.I_weak, Chan_Type.INVALID],
                                          [Chan_Type.I_weak, Chan_Type.I_weak, Chan_Type.INVALID],
                                          
                                          ],
                        'halt_check_when_enough': True,
                        'use_stage_III': True,
                        'stage_III_timing': [14, 50],
                        'use_stage_A': True,
                        'stage_A_pos_return_types':[Chan_Type.III, 
                                            Chan_Type.III_strong, 
                                            Chan_Type.III_weak, 
                                            Chan_Type.INVALID, 
                                            Chan_Type.I, 
                                            Chan_Type.I_weak],
                        'stage_A_neg_return_types': [Chan_Type.I, 
                                            Chan_Type.I_weak],
                        'use_all_stocks_4_A': False,
                        'price_revert_range': 0.0618
        }],
        
        [True, '', '获取最终选股数', Filter_buy_count, {
            'buy_count': 34  # 最终入选股票数
        }],
    ]
    pick_new = [
        [True, '_pick_stocks_', '选股', Pick_stocks2, {
            'config': pick_config,
            'day_only_run_one': False, 
            'write_to_file': 'chan_BC_selection.txt',
            'add_etf':False
        }]
    ]

    ''' --------------------------配置 4 调仓规则------------------ '''
    # # 通达信持仓字段不同名校正
    col_names = {'可用': u'可用', '市值': u'参考市值', '证券名称': u'证券名称', '资产': u'资产'
        , '证券代码': u'证券代码', '证券数量': u'证券数量', '可卖数量': u'可卖数量', '当前价': u'当前价', '成本价': u'成本价'
                 }
    adjust_position_config = [
        [True, '', '卖出股票', Short_Chan, {
            'sub_period':'1m',
            'current_period':'5m',
            'sup_period':'30m',
            'stop_loss':0.055,
            'stop_profit':0.055,
            'use_ma13': False,
            'isdebug':False,
            'isDescription': False,
            'sub_split':False, 
            'short_stage_II_timing': [14,50],
            'use_check_top': True
        }],
        [True, '', '买入股票', Long_Chan, {
            'buy_count': g.buy_count,  # 最终买入股票数
            'force_price_check': False,
            'expected_profit': 0.034,
            'long_timing': [14, 50],
        }],
        [True, '_Show_postion_adjust_', '显示买卖的股票', Show_postion_adjust, {}],
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
        [True, '', '统计执行器', Stat, {'trade_stats':False}],
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
        print ('更新代码->原先不是OO策略，重新调用initialize(context)。')
        initialize(context)
        return

    try:
        print ('=> 更新代码')
        select_strategy(context)
        g.main.g.context = context
        g.main.update_params(context, {'config': g.main_config})
        g.main.after_code_changed(context)
        g.main.log.info(g.main.show_strategy())
    except Exception as e:
        log.error('更新代码失败:' + str(e))
        # initialize(context)
        pass