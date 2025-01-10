from common_include import *
from oop_strategy_frame import *
from oop_adjust_pos import *
from oop_stop_loss import *
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
    g.buy_count = 8
    g.pb_limit = 5
    g.ps_limit = 2.5
    g.pe_limit = 200
    g.evs_limit = 5
    g.eve_limit = 5
    index2 = '000971.XSHG'  # 大盘指数
    index8 = '000842.XSHG'  # 小盘指数
    g.money_fund = ['511880.XSHG','511010.XSHG','511220.XSHG']
    g.etf = ["510050.XSHG","510180.XSHG","510300.XSHG", "159915.XSHE"]#"512880.XSHG","512660.XSHG",  "518880.XSHG", "510900.XSHG", "159901.XSHE"
    
    ''' ---------------------配置 调仓条件判断规则-----------------------'''
    # 调仓条件判断
    adjust_condition_config = [
        [True, '_time_c_', '调仓时间', Time_condition, {
            # 'times': [[10,0],[10, 30], [11,00], [13,00], [13,30], [14,00],[14, 30]],  # 调仓时间列表，二维数组，可指定多个时间点
            'times': [[9, 35]],  # 调仓时间列表，二维数组，可指定多个时间点
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
        [True, '', '多因子回归公式选股', Pick_Rank_Factor,{
                        'stock_num':34,
                        # 'index_scope':['000016.XSHG','000300.XSHG', '000905.XSHG', '399673.XSHE','399005.XSHE'],
                        'index_scope':'all',
                        'use_np':False,
                        'use_enhanced':False,
                        'factor_num': 10,
                        # 'train_length': 55,
                        'is_debug':False,
                        'factor_category': ['basics','quality', 'pershare', 'growth', 'style']##['basics', 'emotion', 'growth', 'momentum', 'pershare', 'quality', 'risk', 'style', 'technical']##
            }],

        [True, '', '过滤ST,停牌,涨跌停股票', Filter_common, {}],
        # [False, '', '过滤创业板', Filter_gem, {}],
        [True, '', '过滤科创板', Filter_sti, {}],
        [True, '1', '缠论卖点过滤', Filter_MA_CHAN_UP, {
            'expected_zoushi_up':[ZouShi_Type.Qu_Shi_Up], #ZouShi_Type.Pan_Zheng
            'expected_exhaustion_up':[Chan_Type.BEICHI], #Chan_Type.PANBEI 
            'check_level':["1m", "5m", "30m", "60m", "1d"],
            'onhold_days': 2,
            }],
        # [False, '2', '缠论卖点过滤', Filter_MA_CHAN_UP, {
        #     'expected_zoushi_up':[ZouShi_Type.Qu_Shi_Up],
        #     'expected_exhaustion_up':[Chan_Type.BEICHI],
        #     'onhold_days': 2,
        #     'check_level':["5m", "30m"],
        #     }],
        [True, '2', '缠论卖点过滤', Filter_MA_CHAN_DOWN, {
            'expected_zoushi_down':[ZouShi_Type.Qu_Shi_Down, ZouShi_Type.Pan_Zheng], #ZouShi_Type.Qu_Shi_Down ZouShi_Type.Pan_Zheng
            'expected_exhaustion_down':[Chan_Type.INVIGORATE], #Chan_Type.PANBEI 
            'check_level':["1d"],
            'onhold_days': 1,
            }],
        # [True, '', '缠论卖点过滤', Filter_SD_CHAN, {
        #     'expected_current_types':[Chan_Type.I, Chan_Type.I_weak], 
        #     'check_level':["30m", "5m"],
        #     'onhold_days': 15
        #     }],

        [True, '', '获取最终选股数', Filter_buy_count, {
            'buy_count': 13  # 最终入选股票数
        }],
    ]
    pick_new = [
        [True, '_pick_stocks_', '选股', Pick_stocks2, {
            'config': pick_config,
            'day_only_run_one': True, 
            'write_to_file': 'low_valuation_regression.txt',
            'add_etf':False
        }]
    ]

    ''' --------------------------配置 4 调仓规则------------------ '''
    # # 通达信持仓字段不同名校正
    col_names = {'可用': u'可用', '市值': u'参考市值', '证券名称': u'证券名称', '资产': u'资产'
        , '证券代码': u'证券代码', '证券数量': u'证券数量', '可卖数量': u'可卖数量', '当前价': u'当前价', '成本价': u'成本价'
                 }
    adjust_position_config = [
        [True, '', '卖出股票', Sell_stocks, {}],
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
        [False, '', '自动调参器', Update_Params_Auto, {
            'ps_threthold':0.618,
            'pb_threthold':0.618,
            'pe_threthold':0.809,
            'buy_threthold':0.809,
            'evs_threthold':0.618,
            'eve_threthold':0.618,
            'pos_control_value': 1.0
        }],
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
    
    
# ''' ----------------------参数自动调整----------------------------'''
class Update_Params_Auto(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        self.ps_threthold = params.get('ps_threthold',0.8)
        self.pb_threthold = params.get('pb_threthold',0.618)
        self.pe_threthold = params.get('pe_threthold',0.8)
        self.evs_threthold = params.get('evs_threthold',0.618)
        self.eve_threthold = params.get('eve_threthold',0.618)
        self.buy_threthold = params.get('buy_threthold', 0.9)
        self.pos_control_value = params.get('pos_control_value', 0.5)

    def before_trading_start(self, context):
        if self.g.isFirstTradingDayOfWeek(context):
            g.ps_limit = self.g.getFundamentalThrethold('valuation.ps_ratio', self.ps_threthold)
            g.pb_limit = self.g.getFundamentalThrethold('valuation.pb_ratio', self.pb_threthold)
            g.pe_limit = self.g.getFundamentalThrethold('valuation.pe_ratio', self.pe_threthold)
            g.evs_limit = self.g.getFundamentalThrethold(evs_query_string, self.evs_threthold)
            g.eve_limit = self.g.getFundamentalThrethold(eve_query_string, self.eve_threthold)
            
            self.dynamicBuyCount(context)
            self.log.info("每周修改全局参数: ps_limit: %s pb_limit: %s pe_limit: %s buy_count: %s evs_limit: %s eve_limit: %s" % (g.ps_limit, g.pb_limit, g.pe_limit, g.buy_count, g.evs_limit, g.eve_limit))
        
        # self.log.info("每日修改全局参数: port_pos_control: %s" % (g.port_pos_control))
        #self.updateRelaventRules(context)
    
    def dynamicBuyCount(self, context):
        import math
        g.buy_count = int(math.ceil(math.log(context.portfolio.portfolio_value/10000)))
        # stock_list = get_index_stocks('000300.XSHG')
        # stock_list_df = history(1, unit='1d', field='avg', security_list=stock_list, df=True, skip_paused=False, fq='pre')
        # stock_list_df = stock_list_df.transpose()
        # stock_list_df = stock_list_df.sort(stock_list_df.columns.values[0], ascending=True, axis=0)
        # threthold_price = stock_list_df.iloc[int(self.buy_threthold * 300),0] # 000300
        # g.buy_count = int(context.portfolio.portfolio_value / (threthold_price * 1000)) # 10手
        

    def updateRelaventRules(self, context):
        # print g.main.rules
        # update everything
        for rule in g.main.rules:
            if isinstance(rule, Pick_stocks2):
                for r2 in rule.rules:
                    if isinstance(r2, Filter_financial_data2):
                        r2.update_params(context, {
                            'factors': [
                                        FD_Factor('valuation.ps_ratio', min=0, max=g.ps_limit),
                                        FD_Factor('valuation.pe_ratio', min=0, max=g.pe_limit),
                                        FD_Factor('valuation.pb_ratio', min=0, max=g.pb_limit),
                                        # FD_Factor(evs_query_string, min=0, max=g.evs_limit, isComplex=True),
                                        # FD_Factor(eve_query_string, min=0, max=g.eve_limit, isComplex=True),
                                        ],
                            'order_by': 'valuation.circulating_market_cap',
                            'sort': SortType.asc,
                            'by_sector':False,
                            'limit':50})
            if isinstance(rule, Adjust_position):
                for r3 in rule.rules:
                    if isinstance(r3, Buy_stocks_chan) or isinstance(r3, Buy_stocks_var):
                        r3.update_params(context, {'buy_count': g.buy_count, 'pos_control': g.port_pos_control})

    def __str__(self):
        return '参数自动调整'
