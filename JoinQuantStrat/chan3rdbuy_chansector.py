# 导入函数库
from jqdata import *
from common_include import *
from oop_strategy_frame import *
from oop_adjust_pos import *
from oop_select_stock import *
from oop_sort_stock import *
from oop_record_stats import *
from ml_factor_rank import *
import pandas as pd
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

  
# 不同步的白名单，主要用于实盘易同步持仓时，不同步中的新股，需把新股代码添加到这里。https://www.joinquant.com/algorithm/index/edit?algorithmId=23c589f4594f827184d4f6f01a11b2f2
# 可把while_list另外放到研究的一个py文件里
def while_list():
    return []

# ==================================策略配置==============================================
def select_strategy(context):
    g.strategy_memo = '缠论强势板块5m三买'
    g.is_sim_trade = context.run_params.type == 'sim_trade'
    # **** 这里定义log输出的类类型,重要，一定要写。假如有需要自定义log，可更改这个变量
    g.log_type = Rule_loger
    g.port_pos_control = 1.0 # 组合仓位控制参数
    g.buy_count = 8
    g.money_fund = []

    ''' ---------------------配置 调仓条件判断规则-----------------------'''
    # 调仓条件判断
    adjust_condition_config = [
        [True, '_time_c_', '调仓时间', Time_condition, {
            # 'times': [[10,0],[10, 30], [11,00], [13,00], [13,30], [14,00],[14, 30]],  # 调仓时间列表，二维数组，可指定多个时间点
            'times': [[14, 35]],  # 调仓时间列表，二维数组，可指定多个时间点
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
        [True, '', '所有非次新股', Pick_non_new_stocks, {}],
        [True, '', '过滤ST,停牌,涨跌停股票', Filter_common_early, {}],
        # [False, '', '过滤创业板', Filter_gem, {}],
        [True, '', '过滤科创板', Filter_sti, {}],
        [True, '', '强势板块股票', Filter_sector_stocks,{
                        'strong_sector':True,
                        'sector_limit_pct':'2',
                        'strength_threthold':144,
                        'useAvg':False,
                        'period_frequency': 'D',
                        'isWeighted': True,
            }],
        [True, '', '缠论标准分析过滤', Filter_SD_CHAN,{
                        'check_level':["30m", "5m"],
                        'expected_current_types':[Chan_Type.I, Chan_Type.I_weak, Chan_Type.INVALID],
            }],
        [True, '', '权重排序', SortRules, {
            'config': [
                [True, '', '主力关注排序', Sort_main_money_inflow, {
                    'sort': SortType.desc
                    , 'weight': 100}],
            ]}
        ],
        [True, '', '获取最终选股数', Filter_buy_count, {
            'buy_count': 13  # 最终入选股票数
        }],
    ]
    pick_new = [
        [True, '_pick_stocks_', '选股', Pick_stocks2, {
            'config': pick_config,
            'day_only_run_one': True, 
            'write_to_file': '3rdBChan.json',
            'add_etf': False,
            'send_email': "email_sender_config.json"
        }]
    ]

    ''' --------------------------配置 4 调仓规则------------------ '''
    adjust_position_config = [
        [True, '', '卖出股票', Sell_stocks, {
            'buy_count': g.buy_count,
            'strict_mode': False,
        }],
        [True, '', '买入股票', Buy_stocks, {
            'use_short_filter':False,
            'buy_count': g.buy_count,  # 最终买入股票数
            'use_adjust_portion':False
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

