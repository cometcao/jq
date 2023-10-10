import types
from common_include import *
from oop_strategy_frame import *
from oop_adjust_pos import *
from oop_stop_loss import *
from oop_select_stock import *
from oop_sort_stock import *
from oop_record_stats import *
# from oop_trading_sync import *
# from ML_kbar_prep import *
# from ML_model_prep import *
# from ML_main import *
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
    # g.etf_index = ["000010.XSHG", "000300.XSHG", "000016.XSHG", "000134.XSHG", "399437.XSHE", "000038.XSHG", "518880.XSHG"]
    # g.etf_list = {"000010.XSHG":"510180.XSHG", 
    #                 "000300.XSHG":"510300.XSHG", 
    #                 "000016.XSHG":"510050.XSHG", 
    #                 "000134.XSHG":"512800.XSHG", 
    #                 "399437.XSHE":"512000.XSHG", 
    #                 "000038.XSHG":"510230.XSHG", 
    #                 "518880.XSHG":"518880.XSHG"}
    g.etf = ["510050.XSHG","510180.XSHG","510300.XSHG", "159915.XSHE"]#"512880.XSHG","512660.XSHG",  "518880.XSHG", "510900.XSHG", "159901.XSHE"
    
    ''' ---------------------配置 调仓条件判断规则-----------------------'''
    # 调仓条件判断
    adjust_condition_config = [
        [True, '_time_c_', '调仓时间', Time_condition, {
            # 'times': [[10,0],[10, 30], [11,00], [13,00], [13,30], [14,00],[14, 30]],  # 调仓时间列表，二维数组，可指定多个时间点
            'times': [[9, 35]],  # 调仓时间列表，二维数组，可指定多个时间点
        }],
        # [False, '_Stop_loss_by_price_', '指数最高低价比值止损器', Stop_loss_by_price, {
        #     'index': '000001.XSHG',  # 使用的指数,默认 '000001.XSHG'
        #     'day_count': 160,  # 可选 取day_count天内的最高价，最低价。默认160
        #     'multiple': 2.2  # 可选 最高价为最低价的multiple倍时，触 发清仓
        # }],
        # [False,'_Stop_loss_by_3_black_crows_','指数三乌鸦止损', Stop_loss_by_3_black_crows,{
        #     'index':'000001.XSHG',  # 使用的指数,默认 '000001.XSHG'
        #      'dst_drop_minute_count':60,  # 可选，在三乌鸦触发情况下，一天之内有多少分钟涨幅<0,则触发止损，默认60分钟
        #     }],
        # [False,'Stop_loss_stocks','个股止损',Stop_gain_loss_stocks,{
        #     'period':20,  # 调仓频率，日
        #     'stop_loss':0.05,
        #     'enable_stop_loss':True,
        #     'stop_gain':0.2,
        #     'enable_stop_gain':False
        #     },],
        # [False,'ATR_stoploss','ATR个股止损',ATR_stoploss,{
        #     'stop':2,  # 调仓频率，日
        #     'NATRstop':6,
        #     'ATR_period':14,
        #     'MaxLoss':0.1,
        #     'HighPrice':{}
        #     },],
        # [False, '', '股票AI择时', ML_Stock_Timing,{
        #     'ml_file_path':'training_result/etf_testing_results_seq.txt', 
        #     'only_take_long_stocks':True, 
        #     'ml_categories': 4, 
        #     'use_day_only': False,
        #     'use_week_only':True,
        #     'use_strict_mode': True
        #     }],
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
        # [False, '_equity_curve_protect_', '资金曲线止损', equity_curve_protect, {
        #     'day_count': 20,  # 
        #     'percent': 0.01,  # 可选 当日总资产小于选定日前资产的固定百分数，触 发清仓
        #     'use_avg': True,
        #     'market_index':'000300.XSHG'
        # }],
        # [False, '', '多指数20日涨幅止损器', Mul_index_stop_loss, {
        #     'indexs': [index2, index8],
        #     'min_rate': 0.005
        # }],
        # [False, '', '多指数技术分析止损器', Mul_index_stop_loss_ta, {
        #     'indexs': [index2, index8],
        #     'ta_type': TaType.TRIX_PURE,
        #     'period':'5d'
        # }],
        # [False, '', 'RSRS_timing', RSRS_timing, {
        #     'market_symbol': '000905.XSHG',
        #     'M':1100,
        #     'N':18
        # }],
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
        # [False, '', '配对交易选对股', Pick_Pair_Trading, {
        #                 'pair_period':250, 
        #                 'get_pair':False,
        #                 # 'init_index_list':['000300.XSHG', '000016.XSHG', '399333.XSHE', '399673.XSHE', '399330.XSHE'],
        #                 'init_index_list':['510050.XSHG', '510180.XSHG', '510300.XSHG', '512800.XSHG', '512000.XSHG', '510230.XSHG', '510310.XSHG', '510880.XSHG'],
        #                 'input_as_list':True,
        #                 'isIndex':True,
        # }], 
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
        # [False, '', 'ETF选股', Pick_ETF,{
        #                 'etf_index':g.etf,
        #     }],        
        # [False, '', '基本面综合选股', Pick_fundamental_factor_rank,{
        #                 'stock_num':6,
        #                 'factors': [
        #                             FD_Factor('valuation.pb_ratio', min=0),
        #                             FD_Factor('1/indicator.roe',min=0) # roe
        #                             ],
        #                 'order_by': 'valuation.pb_ratio',
        #                 'sort': SortType.asc}], 
        # [False, '', '缠论强弱势板块', Pick_rank_sector,{
        #                 'strong_sector':True, 
        #                 'sector_limit_pct': 8,
        #                 'strength_threthold': 0, 
        #                 'isDaily': False, 
        #                 'useIntradayData':False,
        #                 'useAvg':True,
        #                 'avgPeriod':21, 
        #                 'period_frequency':'M'}],
        # [False, '', '基本面数据筛选', Filter_financial_data, {'factor':'valuation.pe_ratio', 'min':0, 'max':80}],
        # [False, '', '基本面数据筛选', Filter_financial_data2, {
        #     'factors': [
        #                 FD_Factor('valuation.ps_ratio', min=0, max=g.ps_limit),
        #                 FD_Factor('valuation.pe_ratio', min=0, max=g.pe_limit),
        #                 # FD_Factor('valuation.pcf_ratio', min=0, max=100),
        #                 FD_Factor('valuation.pb_ratio', min=0, max=g.pb_limit),
        #                 # FD_Factor(eve_query_string
        #                 #         , min=0
        #                 #         , max=5
        #                 #         , isComplex=True),
        #                 # FD_Factor(evs_query_string
        #                 #         , min=0
        #                 #         , max=5
        #                 #         , isComplex=True),
        #                 ],
        #     'order_by': 'valuation.market_cap',
        #     'sort': SortType.asc,
        #     'by_sector': False,
        #     'limit':50}],
        # [False, '', '小佛雪选股', Filter_FX_data, {'limit':144}],
        # [False, '', '多因子选股票池', Pick_financial_data, {
        #     'factors': [
        #         # FD_Factor('valuation.circulating_market_cap', min=0, max=1000)  # 流通市值0~1000
        #         FD_Factor('valuation.market_cap', min=0, max=20000)  # 市值0~20000亿
        #         , FD_Factor('valuation.pe_ratio', min=0, max=80)  # 0 < pe < 200 
        #         , FD_Factor('valuation.pb_ratio', min=0, max=5)  # 0 < pb < 2
        #         , FD_Factor('valuation.ps_ratio', min=0, max=2.5)  # 0 < ps < 2
        #         # , FD_Factor('indicator.eps', min=0)  # eps > 0
        #         # , FD_Factor('indicator.operating_profit', min=0) # operating_profit > 0
        #         # , FD_Factor('valuation.pe_ratio/indicator.inc_revenue_year_on_year', min=0, max=1)
        #         # , FD_Factor('valuation.pe_ratio/indicator.inc_net_profit_to_shareholders_year_on_year', min=0, max=1)
        #         # , FD_Factor('balance.total_current_assets / balance.total_current_liability', min=0, max=2) # 0 < current_ratio < 2
        #         # , FD_Factor('(balance.total_current_assets - balance.inventories) / balance.total_current_liability', min= 0, max=1) # 0 < quick_ratio < 1
        #         # , FD_Factor('indicator.roe',min=0,max=50) # roe
        #         # , FD_Factor('indicator.inc_net_profit_annual',min=0,max=10000)
        #         # , FD_Factor('valuation.capitalization',min=0,max=8000)
        #         # , FD_Factor('indicator.gross_profit_margin',min=0,max=10000)
        #         # , FD_Factor('indicator.net_profit_margin',min=0,max=10000)
        #     ],
        #     'order_by': 'valuation.pb_ratio',  # 按流通市值排序
        #     'sort': SortType.asc,  # 从小到大排序 # SortType.desc
        #     'limit': 500  # 只取前200只
        # }],
        [True, '', '过滤ST,停牌,涨跌停股票', Filter_common, {}],
        # [False, '', '缠论强弱势板块', Filter_Rank_Sector,{
        #                 'strong_sector':True, 
        #                 'sector_limit_pct': 8,
        #                 'strength_threthold': 0, 
        #                 'isDaily': True, 
        #                 'useIntradayData':False,
        #                 'useAvg':False,
        #                 'avgPeriod':5,
        #                 'period_frequency':'W'}],
        # [False, '', '过滤创业板', Filter_gem, {}],
        [True, '', '过滤科创板', Filter_sti, {}],
        # [False, '', '配对交易筛选对股', Filter_Pair_Trading, {
        #                 'pair_period':233,
        #                 'pair_num_limit':10,
        #                 'return_pair':1,
        #                 'period_frequency':'M'
        #     }],
        # [False, '', '强势股筛选', Filter_Herd_head_stocks,{'gainThre':0.05, 'count':20, 'useIntraday':True, 'filter_out':True}],
        # [False, '', '技术分析筛选-AND', checkTAIndicator_AND, { 
        #     'TA_Indicators':[
        #                     # (TaType.BOLL,'5d',233),
        #                     (TaType.TRIX_STATUS, '5d', 100),
        #                     # (TaType.MACD_ZERO, '5d', 100),
        #                     (TaType.MA, '1d', 20),
        #                     # (TaType.MA, '1d', 60),
        #                     ],
        #     'isLong':True}], # 确保大周期安全
        # [False, '', '技术分析筛选-OR', checkTAIndicator_OR, { 
        #     'TA_Indicators':[
        #                     # (TaType.BOLL,'5d',233),
        #                     (TaType.TRIX_STATUS, '5d', 100),
        #                     # (TaType.MACD_STATUS, '5d', 100),
        #                     # (TaType.MA, '1d', 20),
        #                     # (TaType.MA, '1d', 60),
        #                     ],
        #     'isLong':True}], # 确保大周期安全
        # [False, '', '日线周线级别表里买点筛选', Filter_Week_Day_Long_Pivot_Stocks, {
        #     'monitor_levels':g.monitor_levels,
        #     'enable_filter':False,
        #     }],
        
        # [True, '', '过滤主力净流入负数的股票', Filter_Money_Flow, {
        #         'start_time_range' : 5,
        #         'use_method': 2
        #     }],
        
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
        # [False, '', '权重排序', SortRules, {
        #     'config': [
        #         [False, 'Sort_std_data', '波动率排序', Sort_std_data, {
        #             'sort': SortType.asc
        #             , 'period': 60
        #             , 'weight': 100}],
        #         [False, 'cash_flow_rank', '庄股脉冲排序', Sort_cash_flow_rank, {
        #             'sort': SortType.desc
        #             , 'weight': 100}],
        #         [False, '', '市值排序', Sort_financial_data, {
        #             'factor': 'valuation.market_cap',
        #             'sort': SortType.asc
        #             , 'weight': 100}],
        #         [False, '', 'EVS排序', Sort_financial_data, {
        #             'factor': evs_query_string,
        #             'sort': SortType.asc
        #             , 'weight': 100}],
        #         [True, '', 'EVE排序', Sort_financial_data, {
        #             'factor': eve_query_string,
        #             'sort': SortType.asc
        #             , 'weight': 100}],
        #         [False, '', '流通市值排序', Sort_financial_data, {
        #             'factor': 'valuation.circulating_market_cap',
        #             'sort': SortType.asc
        #             , 'weight': 100}],
        #         [False, '', 'P/B排序', Sort_financial_data, {
        #             'factor': 'valuation.pb_ratio',
        #             'sort': SortType.asc
        #             , 'weight': 100}],
        #         [False, '', 'GP排序', Sort_financial_data, {
        #             'factor': 'income.total_profit/balance.total_assets',
        #             'sort': SortType.desc
        #             , 'weight': 100}],
        #         [False, '', '按当前价排序', Sort_price, {
        #             'sort': SortType.asc
        #             , 'weight': 20}],
        #         [False, '5growth', '5日涨幅排序', Sort_growth_rate, {
        #             'sort': SortType.asc
        #             , 'weight': 100
        #             , 'day': 5}],
        #         [False, '20growth', '20日涨幅排序', Sort_growth_rate, {
        #             'sort': SortType.asc
        #             , 'weight': 100
        #             , 'day': 20}],
        #         [False, '60growth', '60日涨幅排序', Sort_growth_rate, {
        #             'sort': SortType.asc
        #             , 'weight': 10
        #             , 'day': 60}],
        #         [False, '', '按换手率排序', Sort_turnover_ratio, {
        #             'sort': SortType.desc
        #             , 'weight': 50}],
            #     [True, '', '主力关注排序', Sort_main_money_inflow, {
            #         'sort': SortType.desc
            #         , 'weight': 100}],
            # ]}
        # ],
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
        # [False, '', '股票择时', Relative_Index_Timing, {
        #     'M':233,
        #     'N':21, #18
        #     'buy':0.7,
        #     'sell':-0.7,
        #     'correlation_period':233,
        #     'strict_long':False,
        #     'market_list':
        #                     # ['000059.XSHG','000060.XSHG', 
        #                     # '000063.XSHG', '000064.XSHG',
        #                     # '000832.XSHG', '000922.XSHG',
        #                     # '399370.XSHE', '399371.XSHE', '399372.XSHE', '399373.XSHE', '399374.XSHE', '399375.XSHE', '399376.XSHE', '399377.XSHE',]
        #                     ['399404.XSHE', '399405.XSHE', '399406.XSHE', '399407.XSHE', '399408.XSHE', '399409.XSHE',]
        #                     # [ '000985.XSHG',
        #                     # '000986.XSHG', '000987.XSHG', '000988.XSHG', '000989.XSHG', '000990.XSHG', '000991.XSHG', '000992.XSHG', '000993.XSHG', '000994.XSHG', '000995.XSHG', 
        #                     # ] # industry
        #                     # [ '000842.XSHG',
        #                     # '000070.XSHG','000071.XSHG','000072.XSHG','000073.XSHG','000074.XSHG','000075.XSHG','000076.XSHG','000077.XSHG','000078.XSHG', '000079.XSHG',
        #                     # ] # equal weights industry
        #                     # ['000016.XSHG', '399333.XSHE', '399006.XSHE'] # conventional '000300.XSHG','399984.XSHE', 
        #                     # ['000001.XSHG', '399001.XSHE', '399006.XSHE',]
        #     }],
        [True, '', '卖出股票', Sell_stocks, {}],
        [True, '', '买入股票', Buy_stocks, {
            'use_short_filter':False,
            'buy_count': g.buy_count,  # 最终买入股票数
            'use_adjust_portion':False
        }],
        # [False, '', '卖出配对股票', Sell_stocks_pair, {
        #     'buy_count':2
        #     }],
        # [False, '', '买入配对股票', Buy_stocks_pair, {
        #     'buy_count':2,
        #     'money_fund':g.money_fund,
        #     'p_val': 2.58,
        #     'risk_var': 0.13,
        #     'adjust_pos':True,
        #     'equal_pos':True
        #     }],        
        # [False, '', '卖出股票日内表里', Sell_stocks_chan, {'monitor_levels': g.monitor_levels}],
        # [False, '', '买入股票日内表里', Buy_stocks_chan, {
        #     'buy_count': g.buy_count,
        #     'monitor_levels': g.monitor_levels, 
        #     'pos_control':g.port_pos_control}],
        # [False,'','VaR方式买入股票', Buy_stocks_var, {
        #     'buy_count': g.buy_count,
        #     'money_fund':g.money_fund,
        #     'p_val': 2.58,
        #     'risk_var': 0.13,
        #     'adjust_pos':True,
        #     'equal_pos':True,
        #     }],
        [True, '_Show_postion_adjust_', '显示买卖的股票', Show_postion_adjust, {}],
        # [False,'trade_Xq','Xue Qiu Webtrader',XueQiu_order,{'version':3}],
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
        
        # self.doubleIndexControl('000016.XSHG', '399333.XSHE')
        # self.log.info("每日修改全局参数: port_pos_control: %s" % (g.port_pos_control))
        self.updateRelaventRules(context)
    
    def dynamicBuyCount(self, context):
        import math
        g.buy_count = int(math.ceil(math.log(context.portfolio.portfolio_value/10000)))
        # stock_list = get_index_stocks('000300.XSHG')
        # stock_list_df = history(1, unit='1d', field='avg', security_list=stock_list, df=True, skip_paused=False, fq='pre')
        # stock_list_df = stock_list_df.transpose()
        # stock_list_df = stock_list_df.sort(stock_list_df.columns.values[0], ascending=True, axis=0)
        # threthold_price = stock_list_df.iloc[int(self.buy_threthold * 300),0] # 000300
        # g.buy_count = int(context.portfolio.portfolio_value / (threthold_price * 1000)) # 10手
        
    def doubleIndexControl(self, index1, index2, target=0, period=20):
        # 大盘周线弱势， 按照仓位比例操作
        # ta_trix = TA_Factor_Short({'ta_type':TaType.TRIX, 'period':'1d', 'count':100})
        # g.port_pos_control = self.pos_control_value if ta_trix.check_TRIX_list('000300.XSHG') else 1.0
        
        # ta_trix_long = TA_Factor_Long({'ta_type':TaType.TRIX_PURE, 'period':'1d', 'count':100, 'isLong':True})
        # long_list = ta_trix_long.filter([index1,index2])
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
    
