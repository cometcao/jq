# -*- encoding: utf8 -*-

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


# ��ͬ���İ���������Ҫ����ʵ����ͬ���ֲ�ʱ����ͬ���е��¹ɣ�����¹ɴ�����ӵ����https://www.joinquant.com/algorithm/index/edit?algorithmId=23c589f4594f827184d4f6f01a11b2f2
# �ɰ�while_list����ŵ��о���һ��py�ļ���
def while_list():
    return ['000001.XSHE']

# ==================================��������==============================================
def select_strategy(context):
    g.strategy_memo = '��ϲ���'
    # **** ���ﶨ��log�����������,��Ҫ��һ��Ҫд����������Ҫ�Զ���log���ɸ����������
    g.log_type = Rule_loger
    # �ж������лز⻹������ģ��
    g.is_sim_trade = context.run_params.type == 'sim_trade'
    g.port_pos_control = 1.0 # ��ϲ�λ���Ʋ���
    g.monitor_levels = ['5d','1d','60m']
    g.buy_count = 3
    g.pb_limit = 5
    g.ps_limit = 2.5
    g.pe_limit = 200
    g.evs_limit = 5
    g.eve_limit = 5
    index2 = '000001.XSHG' #'000016.XSHG'  # ����ָ��
    index8 = '399001.XSHE' #'399333.XSHE'  # С��ָ��
    g.money_fund = ['511880.XSHG','511010.XSHG','511220.XSHG']
    
    ''' ---------------------���� ���������жϹ���-----------------------'''
    # ���������ж�
    adjust_condition_config = [
        [True, '_time_c_', '����ʱ��', Time_condition, {
            # 'times': [[10,0],[10, 30], [11,00], [13,00], [13,30], [14,00],[14, 30]],  # ����ʱ���б���ά���飬��ָ�����ʱ���
            'times': [[14, 50]],  # ����ʱ���б���ά���飬��ָ�����ʱ���
        }],
        [False, '_Stop_loss_by_price_', 'ָ����ߵͼ۱�ֵֹ����', Stop_loss_by_price, {
            'index': '000001.XSHG',  # ʹ�õ�ָ��,Ĭ�� '000001.XSHG'
            'day_count': 160,  # ��ѡ ȡday_count���ڵ���߼ۣ���ͼۡ�Ĭ��160
            'multiple': 2.2  # ��ѡ ��߼�Ϊ��ͼ۵�multiple��ʱ���� �����
        }],
        [False,'_Stop_loss_by_3_black_crows_','ָ������ѻֹ��', Stop_loss_by_3_black_crows,{
            'index':'000001.XSHG',  # ʹ�õ�ָ��,Ĭ�� '000001.XSHG'
             'dst_drop_minute_count':60,  # ��ѡ��������ѻ��������£�һ��֮���ж��ٷ����Ƿ�<0,�򴥷�ֹ��Ĭ��60����
            }],
        [False,'Stop_loss_stocks','����ֹ��',Stop_gain_loss_stocks,{
            'period':20,  # ����Ƶ�ʣ���
            'stop_loss':0.0,
            'enable_stop_loss':True,
            'stop_gain':0.2,
            'enable_stop_gain':False
            },],
        [True, '', '��ƱAI��ʱ', ML_Stock_Timing,{
            'ml_file_path':'training_result/multi_factor_trading_picked_stocks.txt',
            'only_take_long_stocks':True,
            'force_no_candidate':True
            }],
        [False, '', '��Ʊ��ʱ', Relative_Index_Timing, {
            'M':233,
            'N':21, #18
            'buy':0.7,
            'sell':-0.7,
            'correlation_period':233,
            'strict_long':False,
            'market_list':
                            # ['000059.XSHG','000060.XSHG', 
                            # '000063.XSHG', '000064.XSHG',
                            # '000832.XSHG', '000922.XSHG',
                            # '399370.XSHE', '399371.XSHE', '399372.XSHE', '399373.XSHE', '399374.XSHE', '399375.XSHE', '399376.XSHE', '399377.XSHE',]
                            ['399404.XSHE', '399405.XSHE', '399406.XSHE', '399407.XSHE', '399408.XSHE', '399409.XSHE',]
                            # [ '000985.XSHG',
                            # '000986.XSHG', '000987.XSHG', '000988.XSHG', '000989.XSHG', '000990.XSHG', '000991.XSHG', '000992.XSHG', '000993.XSHG', '000994.XSHG', '000995.XSHG', 
                            # ] # industry
                            # [ '000842.XSHG',
                            # '000070.XSHG','000071.XSHG','000072.XSHG','000073.XSHG','000074.XSHG','000075.XSHG','000076.XSHG','000077.XSHG','000078.XSHG', '000079.XSHG',
                            # ] # equal weights industry
                            # ['000016.XSHG', '399333.XSHE', '399006.XSHE'] # conventional '000300.XSHG','399984.XSHE', 
                            # ['000001.XSHG', '399001.XSHE', '399006.XSHE',]
            }],
        # [True,'_Stop_loss_by_growth_rate_','����ָ���Ƿ�ֹ����',Stop_loss_by_growth_rate,{
        #     'index':'000001.XSHG',  # ʹ�õ�ָ��,Ĭ�� '000001.XSHG'
        #      'stop_loss_growth_rate':-0.05,
        #     }],
        # [False,'_Stop_loss_by_28_index_','28ʵʱֹ��',Stop_loss_by_28_index,{
        #             'index2' : '000016.XSHG',       # ����ָ��
        #             'index8' : '399333.XSHE',       # С��ָ��
        #             'index_growth_rate': 0.01,      # �ж����ֵĶ���ָ��20������
        #             'dst_minute_count_28index_drop': 120 # ���������������ٷ��������
        #         }],
        [False, '_equity_curve_protect_', '�ʽ�����ֹ��', equity_curve_protect, {
            'day_count': 20,  # 
            'percent': 0.01,  # ��ѡ �������ʲ�С��ѡ����ǰ�ʲ��Ĺ̶��ٷ������� �����
            'use_avg': False,
            'market_index':'000300.XSHG'
        }],
        [False, '', '��ָ��20���Ƿ�ֹ����', Mul_index_stop_loss, {
            'indexs': [index2, index8],
            'min_rate': 0.005
        }],
        [False, '', '��ָ����������ֹ����', Mul_index_stop_loss_ta, {
            'indexs': [index2, index8],
            'ta_type': TaType.TRIX_PURE,
            'period':'5d'
        }],
        [False, '', '��ָ��ƽ��ֹ��', Mul_index_stop_loss_avg, {
            'indexs': [index2, index8],
            'n': 20
        }],
        [True, '', 'RSRS_timing', RSRS_timing, {
            'market_symbol': '000300.XSHG',
        }],
        [True, '', '�����ռ�����', Period_condition, {
            'period': 3,  # ����Ƶ��,��
            'clear_wait':0
        }],
    ]
    adjust_condition_config = [
        [True, '_adjust_condition_', '����ִ���������жϹ������', Group_rules, {
            'config': adjust_condition_config
        }]
    ]

    ''' --------------------------���� ѡ�ɹ���----------------- '''
    pick_config = [
        [False, '', '��Խ���ѡ�Թ�', Pick_Pair_Trading, {
                        'pair_period':250, 
                        'get_pair':False,
                        # 'init_index_list':['000300.XSHG', '000016.XSHG', '399333.XSHE', '399673.XSHE', '399330.XSHE'],
                        'init_index_list':['510050.XSHG', '510180.XSHG', '510300.XSHG', '512800.XSHG', '512000.XSHG', '510230.XSHG', '510310.XSHG', '510880.XSHG'],
                        'input_as_list':True,
                        'isIndex':True,
            }], 
        [True, '', '�����ӻع鹫ʽѡ��', Pick_Rank_Factor,{
                        'stock_num':34,
                        'index_scope':'000985.XSHG'
            }],
        [False, '', '����ǿ���ư��', Pick_rank_sector,{
                        'strong_sector':True, 
                        'sector_limit_pct': 8,
                        'strength_threthold': 0, 
                        'isDaily': False, 
                        'useIntradayData':False,
                        'useAvg':True,
                        'avgPeriod':21, 
                        'period_frequency':'M'}],
        [False, '', '������ѡ��Ʊ��', Pick_financial_data, {
            'factors': [
                # FD_Factor('valuation.circulating_market_cap', min=0, max=1000)  # ��ͨ��ֵ0~1000
                FD_Factor('valuation.market_cap', min=0, max=20000)  # ��ֵ0~20000��
                , FD_Factor('valuation.pe_ratio', min=0, max=200)  # 0 < pe < 200 
                # , FD_Factor('valuation.pb_ratio', min=0, max=5)  # 0 < pb < 2
                # , FD_Factor('valuation.ps_ratio', min=0, max=2.5)  # 0 < ps < 2
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
            'order_by': 'valuation.pb_ratio',  # ����ͨ��ֵ����
            'sort': SortType.asc,  # ��С�������� # SortType.desc
            'limit': 500  # ֻȡǰ200ֻ
        }],
        
        ################################### FILTER ##########################################
        [False, '', '����������ɸѡ', Filter_financial_data, {'factor':'valuation.pe_ratio', 'min':0, 'max':80}],
        [False, '', '����������ɸѡ', Filter_financial_data2, {
            'factors': [
                        # FD_Factor('valuation.ps_ratio', min=0, max=g.ps_limit),
                        FD_Factor('valuation.pe_ratio', min=0, max=300), #g.pe_limit
                        # FD_Factor('valuation.pcf_ratio', min=0, max=100),
                        # FD_Factor('valuation.pb_ratio', min=0, max=g.pb_limit),
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
        [False, '', 'С��ѩѡ��', Filter_FX_data, {'limit':144}],
        [True, '', '����ST,ͣ��,�ǵ�ͣ��Ʊ', Filter_common, {}],
        [False, '', '����ǿ���ư��', Filter_Rank_Sector,{
                        'strong_sector':True, 
                        'sector_limit_pct': 8,
                        'strength_threthold': 0, 
                        'isDaily': True, 
                        'useIntradayData':False,
                        'useAvg':False,
                        'avgPeriod':5,
                        'period_frequency':'W'}],
        [False, '', '���˴�ҵ��', Filter_gem, {}],
        [False, '', '��Խ���ɸѡ�Թ�', Filter_Pair_Trading, {
                        'pair_period':233,
                        'pair_num_limit':10,
                        'return_pair':1,
                        'period_frequency':'M'
            }],
        [False, '', 'ǿ�ƹ�ɸѡ', Filter_Herd_head_stocks,{'gainThre':0.05, 'count':20, 'useIntraday':True, 'filter_out':True}],
        [False, '', '��������ɸѡ-AND', checkTAIndicator_AND, { 
            'TA_Indicators':[
                            # (TaType.BOLL,'5d',233),
                            (TaType.TRIX_STATUS, '5d', 100),
                            # (TaType.MACD_ZERO, '5d', 100),
                            (TaType.MA, '1d', 20),
                            # (TaType.MA, '1d', 60),
                            ],
            'isLong':True}], # ȷ�������ڰ�ȫ
        [False, '', '��������ɸѡ-OR', checkTAIndicator_OR, { 
            'TA_Indicators':[
                            # (TaType.BOLL,'5d',233),
                            (TaType.TRIX_STATUS, '5d', 100),
                            # (TaType.MACD_STATUS, '5d', 100),
                            # (TaType.MA, '1d', 20),
                            # (TaType.MA, '1d', 60),
                            ],
            'isLong':True}], # ȷ�������ڰ�ȫ
        [False, '', '�������߼���������ɸѡ', Filter_Week_Day_Long_Pivot_Stocks, {
            'monitor_levels':g.monitor_levels,
            'enable_filter':False,
            }],
        [False, '', 'Ȩ������', SortRules, {
            'config': [
                [True, '', 'peg_re', Sort_financial_data, {
                    'factor': 'valuation.pe_ratio/indicator.inc_revenue_year_on_year',
                    'sort': SortType.asc
                    , 'weight': 100}], 
                [True, '', 'peg_pro', Sort_financial_data, {
                    'factor': 'valuation.pe_ratio/indicator.inc_net_profit_to_shareholders_year_on_year',
                    'sort': SortType.asc
                    , 'weight': 100}],  
                [False, 'Sort_std_data', '����������', Sort_std_data, {
                    'sort': SortType.asc
                    , 'period': 60
                    , 'weight': 100}],
                [False, 'cash_flow_rank', 'ׯ����������', Sort_cash_flow_rank, {
                    'sort': SortType.desc
                    , 'weight': 100}],
                [False, '', '��ֵ����', Sort_financial_data, {
                    'factor': 'valuation.market_cap',
                    'sort': SortType.asc
                    , 'weight': 100}],
                [False, '', 'EVS����', Sort_financial_data, {
                    'factor': evs_query_string,
                    'sort': SortType.asc
                    , 'weight': 100}],
                [False, '', '��ͨ��ֵ����', Sort_financial_data, {
                    'factor': 'valuation.circulating_market_cap',
                    'sort': SortType.asc
                    , 'weight': 100}],
                [False, '', 'P/S����', Sort_financial_data, {
                    'factor': 'valuation.ps_ratio',
                    'sort': SortType.asc
                    , 'weight': 100}],
                [False, '', 'GP����', Sort_financial_data, {
                    'factor': 'income.total_profit/balance.total_assets',
                    'sort': SortType.desc
                    , 'weight': 100}],
                [False, '', '����ǰ������', Sort_price, {
                    'sort': SortType.asc
                    , 'weight': 20}],
                [False, '5growth', '5���Ƿ�����', Sort_growth_rate, {
                    'sort': SortType.asc
                    , 'weight': 100
                    , 'day': 5}],
                [False, '20growth', '20���Ƿ�����', Sort_growth_rate, {
                    'sort': SortType.asc
                    , 'weight': 100
                    , 'day': 20}],
                [False, '60growth', '60���Ƿ�����', Sort_growth_rate, {
                    'sort': SortType.asc
                    , 'weight': 10
                    , 'day': 60}],
                [False, '', '������������', Sort_turnover_ratio, {
                    'sort': SortType.desc
                    , 'weight': 50}],
            ]}
        ],
        [True, '', '��ȡ����ѡ����', Filter_buy_count, {
            'buy_count': 20  # ������ѡ��Ʊ��
        }],
    ]
    pick_new = [
        [True, '_pick_stocks_', 'ѡ��', Pick_stocks2, {
            'config': pick_config,
            'day_only_run_one': True, 
            'write_to_file': 'multi_factor_trading_picked_stocks.txt'
        }]
    ]

    ''' --------------------------���� 4 ���ֹ���------------------ '''
    # # ͨ���ųֲ��ֶβ�ͬ��У��
    col_names = {'����': u'����', '��ֵ': u'�ο���ֵ', '֤ȯ����': u'֤ȯ����', '�ʲ�': u'�ʲ�'
        , '֤ȯ����': u'֤ȯ����', '֤ȯ����': u'֤ȯ����', '��������': u'��������', '��ǰ��': u'��ǰ��', '�ɱ���': u'�ɱ���'
                 }
    adjust_position_config = [
        [True, '', '������Ʊ', Sell_stocks, {}],
        [True, '', '�����Ʊ', Buy_stocks, {
            'use_short_filter':False,
            'buy_count': g.buy_count  # ���������Ʊ��
        }],
        [False, '', '������Թ�Ʊ', Sell_stocks_pair, {
            'buy_count':2
            }],
        [False, '', '������Թ�Ʊ', Buy_stocks_pair, {
            'buy_count':2,
            'money_fund':g.money_fund,
            'p_val': 2.58,
            'risk_var': 0.13,
            'adjust_pos':True,
            'equal_pos':True
            }],        
        [False, '', '������Ʊ���ڱ���', Sell_stocks_chan, {'monitor_levels': g.monitor_levels}],
        [False, '', '�����Ʊ���ڱ���', Buy_stocks_chan, {
            'buy_count': g.buy_count,
            'monitor_levels': g.monitor_levels, 
            'pos_control':g.port_pos_control}],
        [False,'','VaR��ʽ�����Ʊ', Buy_stocks_var, {
            'buy_count': g.buy_count,
            'money_fund':g.money_fund,
            'p_val': 2.58,
            'risk_var': 0.13,
            'adjust_pos':True,
            'equal_pos':True,
            }],
        [True, '_Show_postion_adjust_', '��ʾ�����Ĺ�Ʊ', Show_postion_adjust, {}],
        # [False,'trade_Xq','Xue Qiu Webtrader',XueQiu_order,{'version':3}],
        # ʵ����ͬ���ֲ֣���������ͬ����ʵ��
        # [g.is_sim_trade, '_Shipane_manager_', 'ʵ���ײ���', Shipane_manager, {
        #     'host':'111.111.111.111',   # ʵ����IP
        #     'port':8888,    # ʵ���׶˿�
        #     'key':'',   # ʵ����Key
        #     'client':'title:guangfa', # ʵ����client
        #     'strong_op':False,   # ǿ��ͬ��ģʽ��������ǿ��ͬ�����Ρ�
        #     'col_names':col_names, # ָ��ʵ���׷��صĳֲ��ֶ�ӳ��
        #     'cost':context.portfolio.starting_cash, # ʵ�̵ĳ�ʼ�ʽ�
        #     'get_white_list_func':while_list, # ��ͬ���İ�����
        #     'sync_scale': 1,  # ʵ���ʽ�/ģ�����ʽ����������1Ϊ��
        #     'log_level': ['debug', 'waring', 'error'],  # ʵ������־�������
        #     'sync_with_change': True,  # �Ƿ�ָ��ֻ�з����˹�Ʊ����ʱ�Ž���ͬ�� , ������Ҫ��������Чͬ����������
        # }],
        # # ģ���̵����ʼ�֪ͨ����ʱֻ�Թ�QQ���䣬�������䲻֪���Ƿ�֧��
        # [g.is_sim_trade, '_new_Email_notice_', '�����ʼ�ִ֪ͨ����', Email_notice, {
        #     'user': '123456@qq.com',    # QQmail
        #     'password': '123459486',    # QQmail����
        #     'tos': ["������1<123456@qq.com>"], # ������Email��ַ���ɶ��
        #     'sender': '�ۿ�ģ����',  # ����������
        #     'strategy_name': g.strategy_memo, # ��������
        #     'send_with_change': False,   # �ֲ��б仯ʱ�ŷ���
        # }],
    ]
    adjust_position_config = [
        [True, '_Adjust_position_', '����ִ�й������', Adjust_position, {
            'config': adjust_position_config
        }]
    ]

    ''' --------------------------���� ��������------------------ '''
    # ���ȸ�������ÿ��������ִ��handle_data
    common_config_list = [
        [True, '', '����ϵͳ����', Set_sys_params, {
            'benchmark': '000300.XSHG'  # ָ����׼Ϊ���¹�ָ
        }],
        [True, '', '������������', Set_slip_fee, {}],
        [True, '', '�ֲ���Ϣ��ӡ��', Show_position, {}],
        [True, '', 'ͳ��ִ����', Stat, {'trade_stats':False}],
        [False, '', '�Զ�������', Update_Params_Auto, {
            'ps_threthold':0.618,
            'pb_threthold':0.618,
            'pe_threthold':0.809,
            'buy_threthold':0.809,
            'evs_threthold':0.618,
            'eve_threthold':0.618,
            'pos_control_value': 1.0
        }],
        # [g.is_sim_trade, '_Purchase_new_stocks_', 'ʵ�����깺�¹�', Purchase_new_stocks, {
        #     'times': [[11, 24]],
        #     'host':'111.111.111.111',   # ʵ����IP
        #     'port':8888,    # ʵ���׶˿�
        #     'key':'',   # ʵ����Key
        #     'clients': ['title:zhaoshang', 'title:guolian'] # ʵ����client�б�,��һ������֧��ͬһ��ʵ�����µĶ���ʺ�ͬʱ����
        # }],
    ]
    common_config = [
        [True, '_other_pre_', 'Ԥ�ȴ���ĸ�������', Group_rules, {
            'config': common_config_list
        }]
    ]
    # ��ϳ�һ���ܵĲ���
    g.main_config = (common_config
                     + adjust_condition_config
                     + pick_new
                     + adjust_position_config)


# ===================================�ۿ����==============================================
def initialize(context):
    # ��������
    select_strategy(context)
    # �����������
    g.main = Strategy_Group({'config': g.main_config
                                , 'g_class': Global_variable
                                , 'memo': g.strategy_memo
                                , 'name': '_main_'})
    g.main.initialize(context)

    # ��ӡ�������
    g.main.log.info(g.main.show_strategy())


# �����ӻز�
def handle_data(context, data):
    # ����context��ȫ�ֱ���������Ҫ��Ϊ�˷����������һЩû��context�Ĳ����ĺ�����ʹ�á�
    g.main.g.context = context
    # ִ�в���
    g.main.handle_data(context, data)


# ����
def before_trading_start(context):
    log.info("==========================================================================")
    g.main.g.context = context
    g.main.before_trading_start(context)


# ����
def after_trading_end(context):
    g.main.g.context = context
    g.main.after_trading_end(context)
    g.main.g.context = None


# ��������(һ��һ��)
def process_initialize(context):
    try:
        g.main.g.context = context
        g.main.process_initialize(context)
    except:
        pass


# ����ʾ������ģ����Ļز�ʱ����ε�������,����ͨ�ô��롣
def after_code_changed(context):
    try:
        g.main
        pass
    except:
        print ('���´���->ԭ�Ȳ���OO���ԣ����µ���initialize(context)��')
        initialize(context)
        return

    try:
        print ('=> ���´���')
        select_strategy(context)
        g.main.g.context = context
        g.main.update_params(context, {'config': g.main_config})
        g.main.after_code_changed(context)
        g.main.log.info(g.main.show_strategy())
    except Exception as e:
        log.error('���´���ʧ��:' + str(e))
        # initialize(context)
        pass
    
    
# ''' ----------------------�����Զ�����----------------------------'''
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
            self.log.info("ÿ���޸�ȫ�ֲ���: ps_limit: %s pb_limit: %s pe_limit: %s buy_count: %s evs_limit: %s eve_limit: %s" % (g.ps_limit, g.pb_limit, g.pe_limit, g.buy_count, g.evs_limit, g.eve_limit))
        
        # self.doubleIndexControl('000016.XSHG', '399333.XSHE')
        # self.log.info("ÿ���޸�ȫ�ֲ���: port_pos_control: %s" % (g.port_pos_control))
        self.updateRelaventRules(context)
    
    def dynamicBuyCount(self, context):
        import math
        g.buy_count = int(math.ceil(math.log(context.portfolio.portfolio_value/10000)))
        # stock_list = get_index_stocks('000300.XSHG')
        # stock_list_df = history(1, unit='1d', field='avg', security_list=stock_list, df=True, skip_paused=False, fq='pre')
        # stock_list_df = stock_list_df.transpose()
        # stock_list_df = stock_list_df.sort(stock_list_df.columns.values[0], ascending=True, axis=0)
        # threthold_price = stock_list_df.iloc[int(self.buy_threthold * 300),0] # 000300
        # g.buy_count = int(context.portfolio.portfolio_value / (threthold_price * 1000)) # 10��
        
    def doubleIndexControl(self, index1, index2, target=0, period=20):
        # �����������ƣ� ���ղ�λ��������
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
        return '�����Զ�����'
    
