import copy
import pandas as pd
import requests
from requests import Request
from six.moves.urllib.parse import urlencode
import datetime

from seek_cash_flow import * 
from chip_migration_II import *
from scipy.signal import argrelextrema

try:
    # ʵ���ײ���SDK,�°�SDK�ѽ���ۿ����л����⡣
    import shipane_sdk
except:
    pass


'''
�汾����������ع� ������ʱС��ֵv2.0.7
���ڣ�2017.1.4
ԭ���ߣ�Morningstar
�޸��ߣ������С��
'''

'''
2017-02-23����:
    1. ����ͨ��ʵ�����Զ��깺�¹ɵĹ����� Purchase_new_stocks
    2. ���Ļص���ʵ���׹ٷ�SDK��shipane_sdk.py�ķ����������պ���¡�
    
2017-02-21����:
    1. ��ԭSDK��JoinQuantExecutor�����ϵ�Shipane_order�����
        ʹ��Rule�ļ���log����������ԭ�ȵ�_logger�������޷����л�����
    2. ��ԭSDK��Client����Ϊ�̳�Rule����ɾ��_logger��
        ʹ��Rule�ļ���log����������ԭ�ȵ�_logger�������޷����л�����
    3. Shipane_order �µ�ʱ��Try���Ա����µ�����ʱ����ģ�����쳣�˳���
        ����ֻ�Ǽ򵥴ֱ��Ĵ����µ�ʧ�ܣ���ʵ���Ը���һ������ʧ��(δ )��
        1) ������ʱ��ͨ����ȡ�ֲ���Ϣ�����ж��ж��ٿ����ģ��Ƿ�ﵽorderҪ��
        2) ����ʱ��ͨ����ȡ�ֲ���Ϣ�����ж��µ��������Ƿ�ﵽorderҪ���Ƿ���Ҫ��
            ����ɲο�Shipane_sync_p��һЩ����ʽ��
    
2017-02-16����:
    1. ����ģ���̸��´����Ǳ��BUG��ԭ���ƣ�����һ�����򴴽�����ʵ�����ͻ���¹�����ҡ�
    �������� [True,'_filter_gem_','���˴�ҵ��',Filter_gem,{}],�ڶ� ���ֶ�Ϊ����һ����������
    ���һ������ֻ����һ�Σ����Բ�д������ͬһ������ʹ�ö�Σ�����Ҫһ��Ҫд���֡�
    ���� ��������ʵ���׹���ȥ��������ͨ�����ʺš�
    2. ����Filter_rank ����Stock_listΪ��ʱ�쳣��Bug��
    3. Shipane_sync_p ��ִ������������sleepһ��ʱ�䣬�������̫�죬�ֲ���Ϣû����
2017-02-15����:
    1. ����ԭShipane����Ϊ Shipane_sync_p
    2. Shipane_sync_p�������ʱִ��ͬ���ֲ֡�
    3. �������ۿ��µ���order��ʵ���׸���ʵ���µ������� Shepane_order��
    
2017-02-14����:
    1.����ͨ��ʵ���׶Խ�ʵ�̵Ĵ��룬ʹ���Կ���ֱ��ʵ�� Shipane�ࡣ
        ʵ�̲����߼�˵����
        ����˼·��ʹʵ�ֲ̳־�����ģ���ֲֿ̳�£��
        ͨ��ʵ�ֲ̳���ģ���ֲֵ̳Ĳ�λ�Աȣ�ȡ���в��Ĺ�Ʊ������������ʵ���µ���
        �����Ǹ��ݲ��������µ�����ʵ���µ��ġ�
        (���谴�����µ�ȥʵ���µ���������ʵ���׹ٷ�SDK��Ĵ���)
        ����ʵ���׵������������Ĺ���:http://www.iguuu.com/e
        �÷�����ȱ�㣺
        �ŵ㣺ģ������ʵ�ֲֻ̳���ͬ��ӽ��������ڲ�����Ч�Լ��飬Ҳʹ�ز���������
        ȱ�㣺��ģ������ʵ���ʽ���Ƚϴ��ʱ���п��ܻᵼ��һЩ��Ʊ��Ƶ��С���ֵ�������
              ����취Ҳ�У�����ģ�����ʽ��ʵ�̶�ʱ�����ǰ�ѿ����ʽ��ȼ�ȥ�����ȥ�������������������ʱû���ⲿ��
        Shipane����Ĭ��δ���á�����Ҫ�����úò����ٿ���
        ע������δ���ϸ�ʵ�̲��ԣ�������ʹ�ã����� ͨ����ģ�⳴�ɲ��ԡ�
2017-1-11���£�
    1.�������ѡȡ������������� �� д��д�ַ�����Ϊֱ��д����
    2.Rule�������� on_get_obj_by_class_type��Ӻ�����ͨ����ʵ��һ������õ���һ�������ʵ��
        ����ĳЩ����¹�����໥���á����پ�����ֻ��handle_data˳����á�����������߼��򵥣�û��ʹ�á�
    3.ȥ�����ж����__name__���塣���´���ʱ��ֱ����������ͶԱȡ�
    4.ΪRule���memo���ԣ������memoֱ���Բ����������memo�ֶθ�ֵ����־��ֱ��
2017-1-5 ����
    1.������ʹ��Queryѡ�ɹ���ʱ�����BUG
    2.����28ʵʱֹ���� Stop_loss_by_28_index ��BUG
    3.Rule����log_info��log_warn������������ʾ�����ĸ��������������־��
    4.�� tradestatҲ�ع�Ϊ�����࣬���ɵ���������������ⲿ����tradestat.pyģ����
'''

'''ѡ�������ϳ�һ����������'''
def select_strategy(context):
    '''
    ����ѡ������˵��:
    ���������²��������ϣ���϶���:
    1.�ֲֹ�Ʊ�Ĵ������
    2.���������жϹ���
    3.Queryѡ�ɹ��� (��ѡ����Щ������ܲ���Ҫ���)
    4.��Ʊ�ع��˹��� (��ѡ����Щ������ܲ���Ҫ���)
    5.���ֹ���
    6.��������(��ͳ��)
    
    ÿ������Ĺ������Ϊһ����ά����
    һάָ����ʲô������ɣ�ע��˳�򣬳��򽫻ᰴ˳�򴴽�����˳��ִ�С�
    ��ͬ�Ĺ�����Ͽ��ܴ���һ����˳���ϵ��
    ��άָ������������ã��� [0.�Ƿ����ã�1.������2.����ʵ��������3.���򴫵ݲ���(dict)]] ��ɡ�
    ע�����й����඼����̳���Rule���Rule�������
    '''
    # ��������list�±�������������߿ɶ�����δ����Ӹ���������á�
    g.cs_enabled,g.cs_name,g.cs_memo,g.cs_class_name,g.cs_param = range(5)

    # 0.�Ƿ����ã�1.������2.����ʵ��������3.���򴫵ݲ���(dict)]
    period = 3  # ����Ƶ��
    # ���� 1.�ֲֹ�Ʊ�Ĵ������ (������Ҫ�����Ƿ���и���ֹ��ֹӯ)
    g.position_stock_config = [
        [False,'','����ֹ��',Stop_loss_stocks,{
            'period':period  # ����Ƶ�ʣ���
            },],
        [False,'','����ֹӯ',Stop_profit_stocks,
            {'period':period ,  # ����Ƶ�ʣ���
            }]
    ]

    # ���� 2.���������жϹ���
    g.adjust_condition_config = [
        [True,'','ָ����ߵͼ۱�ֵֹ��',Stop_loss_by_price,{
            'index':'000001.XSHG',  # ʹ�õ�ָ��,Ĭ�� '000001.XSHG'
             'day_count':160,  # ��ѡ ȡday_count���ڵ���߼ۣ���ͼۡ�Ĭ��160
             'multiple':2.2  # ��ѡ ��߼�Ϊ��ͼ۵�multiple��ʱ���� �����
            }],
        [True,'','ָ������ѻֹ��',Stop_loss_by_3_black_crows,{
            'index':'000001.XSHG',  # ʹ�õ�ָ��,Ĭ�� '000001.XSHG'
             'dst_drop_minute_count':60,  # ��ѡ��������ѻ��������£�һ��֮���ж��ٷ����Ƿ�<0,�򴥷�ֹ��Ĭ��60����
            }],
        [False,'','_Stop_loss_by_growth_rate_','����ָ���Ƿ�ֹ����',Stop_loss_by_growth_rate,{
            'index':'000001.XSHG',  # ʹ�õ�ָ��,Ĭ�� '000001.XSHG'
             'stop_loss_growth_rate':-0.05,
            }],
        [False,'','28ʵʱֹ��',Stop_loss_by_28_index,{
                    'index2' : '000016.XSHG',       # ����ָ��
                    'index8' : '399333.XSHE',       # С��ָ��
                    'index_growth_rate': 0.01,      # �ж����ֵĶ���ָ��20������
                    'dst_minute_count_28index_drop': 120 # ���������������ٷ��������
                }],
        [True,'','����ʱ��',Time_condition,{
            'sell_hour': 14,  # ����ʱ��,Сʱ
            'sell_minute': 50,  # ����ʱ�䣬����
            'buy_hour': 14,  # ����ʱ��,Сʱ
            'buy_minute': 50 # ����ʱ�䣬����
            }],
        [True,'','28������ʱ',Index28_condition,{  # �õ����������ܻ���������Ϊ
                'index2' : '000016.XSHG',  # ����ָ��
                'index8' : '399333.XSHE',  # С��ָ��
                'index_growth_rate': 0.01,  # �ж����ֵĶ���ָ��20������
            }],
        [True,'','�����ռ�����',Period_condition,{
                'period' : period ,  # ����Ƶ��,��
            }],
    ]

    # ���� 3.Queryѡ�ɹ���
    g.pick_stock_by_query_config = [
        [False,'','ѡȡС��ֵ',Pick_small_cap,{}],
        [True,'','ѡȡׯ��',Pick_by_market_cap,{'mcap_limit':300}],
        [False,'','ѡȡׯ�ɣ���ͨ��ֵ��',Pick_by_cir_market_cap,{'cir_mcap_limit':300}],
        # [False'',,'����PE',Filter_pe,{
        #     'pe_min':0                          # ��СPE
        #     ,'pe_max':200                       # ���PE
        #     }],
        [True,'','����EPS',Filter_eps,{
            'eps_min':0  # ��СEPS
            }],
        [True,'','��ѡ��Ʊ����',Filter_limite,{
            'pick_stock_count':100  # ��ѡ��Ʊ��Ŀ
            }]
    ]

    # ���� 4.��Ʊ�ع��˹���
    g.filter_stock_list_config = [
        [True,'_filter_gem_','���˴�ҵ��',Filter_gem,{}],
        [True,'','����ST',Filter_st,{}],
        [True,'','����ͣ��',Filter_paused_stock,{}],
        # [False,'','���˴��¹�',Filter_new_stock,{'day_count':130}],
        [True,'','������ͣ',Filter_limitup,{}],
        [True,'','���˵�ͣ',Filter_limitdown,{}],
        # [False,'','����n��������Ϊ���Ĺ�Ʊ',Filter_growth_is_down,{
        #     'day_count':20                      # �ж϶��������Ƿ�
        #     }],
        # [False,'','���˺�����',Filter_blacklist,{}],
        [False,'','ׯ������',Filter_cash_flow_rank,{'rank_stock_count':50}],
        [True,'','����ֲ�����',Filter_chip_density,{'rank_stock_count':50}],        
        [True,'','��Ʊ����',Filter_rank,{
            'rank_stock_count': 20  # ���ֹ���
            }],
        [True,'','��ȡ����ѡ����',Filter_buy_count,{
            'buy_count': 3  # ������ѡ��Ʊ��
            }],
    ]

    # ���� 5.���ֹ���
    g.adjust_position_config = [
        [True,'','������Ʊ',Sell_stocks,{}],
        [False,'','�����Ʊ',Buy_stocks,{
            'buy_count': 4  # ���������Ʊ��
            }],
        [False,'','�����������Ʊ',Buy_stocks_portion,{'buy_count':3}],
        [True,'','VaR��ʽ�����Ʊ', Buy_stocks_var, {'buy_count': 3}]
    ]

    # �ж��Ƿ���ģ��������
    g.is_sim_trade = context.run_params.type == 'sim_trade'

    # ���� 6.��������
    g.other_config = [
        
        # [False,'trade_Xq','Xue Qiu Webtrader',XueQiu_order,{}],
        # ע�⣺Shipane_order �� Shipane_sync_p ����һ�������ˡ�
        # ��������ȷ��ʵ����IP���˿ڣ�Key,client

        # ��ͨ�� g.is_sim_trade �����ƻز�ʱ�����ã�ģ���̲�����ʵ���ײ����ӿ�
        [False,'Shipane_order_moni','ʵ���׸�order�µ�',Shipane_order,{
            'host':'192.168.0.5',  # ʵ����IP
            'port':8888,  # �˿�
            'key':'',  # ʵ���� key
            'client' : 'title:moni',  # ���ò�����ȯ��,ֻ��һ������Ϊ''
            }],

        # [g.is_sim_trade,'_shipane_moni_','ʵ����-�Աȳֲ��µ�',Shipane_sync_p,{
        [False,'_shipane_moni_','ʵ����-�Աȳֲ��µ�',Shipane_sync_p,{
            'host':'192.168.0.5',  # ʵ����IP
            'port':8888,  # �˿�
            'key':'',  # ʵ���� key
            'client' : 'title:moni',  # ���ò�����ȯ��,ֻ��һ������Ϊ''
            'strong_op' : True,  # �����Ƿ�Ϊǿ������ģʽ,��ʮ�����Ͻ��鿪����С�ʽ�����ν���ر�Ч�ʸ�һ���
                }],

        # ͨ��ʵ�����Զ��깺�¹�
        [False,'_Purchase_new_stocks_','ʵ�����깺�¹�',Purchase_new_stocks,{
            'times':[[9,40]],  # ִ���깺�¹ɵ�ʱ��
            'host':'192.168.0.5',  # ʵ����IP
            'port':8888,  # �˿�
            'key':'',  # ʵ���� key
            'clients':['title:moni']  # ִ���깺�¹ɵ�ȯ�̱���list������д�����
                }],

        [True,'','ͳ��',Stat,{}]
    ]


# ����һ������ִ����������ʼ��һЩͨ���¼�
def create_rule(class_type,name,params,memo):
    obj = class_type(params)
    obj.name = name
    obj.on_open_position = open_position  # ���
    obj.on_close_position = close_position  # ����
    obj.on_clear_position = clear_position  # ���
    obj.on_get_obj_by_class_type = get_obj_by_class_type  # ͨ�������õ����ʵ��
    obj.memo = memo
    return obj

# ���ݹ������ô�������ִ����
def create_rules(config):
    # config�� 0.�Ƿ����ã�1.������2.����ʵ��������3.���򴫵ݲ���(dict)]
    return [create_rule(c[g.cs_class_name],c[g.cs_name],c[g.cs_param],c[g.cs_memo]) for c in config if c[g.cs_enabled]]



# 1 ���ò���
def set_params():
    # ���û�׼����
    set_benchmark('000300.XSHG')


# 2 �����м����
def set_variables(context):
    # ���� VaR ��λ���Ʋ��������ճ���: 0.05,
    # ��̬�ֲ����ʱ���׼����Լ�������: 0.96, 95%; 2.06, 96%; 2.18, 97%; 2.34, 98%; 2.58, 99%; 5, 99.9999%
    # �����ʽ�������������������ֽ����: ['511880.XSHG']
    set_slip_fee(context)
    context.pc_var = PositionControlVar(context, 0.07, 2.18, [])


# 3 ���ûز�����
def set_backtest():
    set_option('use_real_price', True)  # ����ʵ�۸���
    log.set_level('order', 'error')
    log.set_level('strategy', 'info')


def initialize(context):
    log.info("==> initialize @ %s" % (str(context.current_dt)))
    try:
        set_params()  # 1���ò��Բ���
        set_variables(context)  # 2�����м����
        set_backtest()  # 3���ûز�����
        # set_commission(PerTrade(buy_cost=0.0003,sell_cost=0.0013,min_cost=5))
        # set_benchmark('000300.XSHG')
        # set_option('use_real_price',True)
        # log.set_level('order','error')
    except:
        pass
    # �ж��Ƿ���ģ����״̬
    g.is_sim_trade = context.run_params.type == 'sim_trade'

    select_strategy(context)
    '''-----1.�ֲֹ�Ʊ�Ĵ������:-----'''
    g.position_stock_rules = create_rules(g.position_stock_config)

    '''-----2.���������жϹ���:-----'''
    g.adjust_condition_rules = create_rules(g.adjust_condition_config)

    '''-----3.Queryѡ�ɹ���:-----'''
    g.pick_stock_by_query_rules = create_rules(g.pick_stock_by_query_config)

    '''-----4.��Ʊ�ع��˹���:-----'''
    g.filter_stock_list_rules = create_rules(g.filter_stock_list_config)

    '''-----5.���ֹ���:��-----'''
    g.adjust_position_rules = create_rules(g.adjust_position_config)

    '''-----6.��������:-------'''
    g.other_rules = create_rules(g.other_config)

    # �����й���ϲ���������һ���ܵĹ�����¼�����Է��������ͬ���õ�
    g.all_rules = list(set(g.position_stock_rules
            + g.adjust_condition_rules
            + g.pick_stock_by_query_rules
            + g.filter_stock_list_rules
            + g.adjust_position_rules
            + g.other_rules
        ))

    for rule in g.all_rules:
        rule.initialize(context)

    # ��ӡ�������
    log_param()

# �����ӻز�
def handle_data(context,data):
    # ִ��������������
    for rule in g.other_rules:
        rule.handle_data(context,data)

    # �ֲֹ�Ʊ������ִ��,ĿǰΪ����ֹ��ֹӯ
    for rule in g.position_stock_rules:
        rule.handle_data(context,data)

    # ----------�ⲿ�ֵ�ǰ��������ʵ��û��ɶ�ã���չ��--------------
    # ����ִ��ѡ������������handle_data��Ҫ��Ϊ����չĳЩѡ�ɷ�ʽ������Ҫ��ǰ�������ݡ�
    # ��������̬��ȡ�����������Ե���ǰһ��ʱ����ִ�С�28С��ֵ�������ﶼ�ǿն�����
    for rule in g.pick_stock_by_query_rules:
        rule.handle_data(context,data)

    for rule in g.filter_stock_list_rules:
        rule.handle_data(context,data)

    # �������ķ��Ӵ���
    for rule in g.adjust_position_rules:
        rule.handle_data(context,data)
    # -----------------------------------------------------------

    # �ж��Ƿ�����������������й�����and �߼�ִ��
    for rule in g.adjust_condition_rules:
        rule.handle_data(context,data)
        if not rule.can_adjust:
            return
    # ---------------------����--------------------------
    log.info("handle_data: ==> �����������е���")
    # ����ǰԤ����
    for rule in g.all_rules:
        rule.before_adjust_start(context,data)

    # Query ѡ��
    q = None
    for rule in g.pick_stock_by_query_rules:
        q = rule.filter(context,data,q)

    # ���˹�Ʊ�б�
    stock_list = list(get_fundamentals(q)['code']) if q != None else []
    for rule in g.filter_stock_list_rules:
        stock_list = rule.filter(context,data,stock_list)

    log.info("handle_data: ѡ�ɺ�����Ʊ: %s" % (stock_list))

    # ִ�е���
    for rule in g.adjust_position_rules:
        rule.adjust(context,data,stock_list)

    # ���ֺ���
    for rule in g.all_rules:
        rule.after_adjust_end(context,data)
    # ----------------------------------------------------

# ����
def before_trading_start(context):
    log.info("==========================================================================")
    for rule in g.all_rules:
        rule.before_trading_start(context)

# ����
def after_trading_end(context):
    for rule in g.all_rules:
        rule.after_trading_end(context)

    # �õ���ǰδ��ɶ���
    orders = get_open_orders()
    for _order in orders.values():
        log.info("canceled uncompleted order: %s" % (_order.order_id))

# ��������(һ��һ��)
def process_initialize(context):
    # ����Tryһ�£���ֹ���´���ʱ����
    try:
        for rule in g.all_rules:
            rule.process_initialize(context)
    except:
        pass

# ����ʾ������ģ����Ļز�ʱ����ε�������,����ͨ�ô��롣
def after_code_changed(context):
    try:
        g.all_rules
    except:
        print 'ԭ�ȷ����������Դ��룬���³�ʼ��'
        initialize(context)
        return

    print '���´��룺'
    # ��������ͨ��ʵ������
    # ��ȡ�²���
    select_strategy(context)
    # ���²���˳�����������б��������֮ǰ���ڣ����Ƶ����б����������½���
    # ����֮ǰ�ɵĹ����б���ʲô˳��һ�ʰ����б���������
    def check_chang(rules,config):
        nl = []
        for c in config:
        # ��˳��ѭ�������¹���
            if not c[g.cs_enabled]:  # ��ʹ��������
                continue
            # ���Ҿɹ����Ƿ����
            find_old = None
            for old_r in rules:
                if old_r.__class__ == c[g.cs_class_name] and old_r.name == c[g.cs_name]:
                    find_old = old_r
                    break
            if find_old != None:
                # �ɹ����������ӵ����б���,�����ù���ĸ��º��������²�����
                nl.append(find_old)
                find_old.update_params(context,c[g.cs_param])
            else:
                # �ɹ��򲻴��ڣ��򴴽������
                new_r = create_rule(c[g.cs_class_name],c[g.cs_name],c[g.cs_param],c[g.cs_mome])
                nl.append(new_r)
                # ���ó�ʼ��ʱ��ִ�еĺ���
                rule.initialize(context)
        return nl

    # �������й���
    g.position_stock_rules = check_chang(g.position_stock_rules,g.position_stock_config)
    g.adjust_condition_rules = check_chang(g.adjust_condition_rules,g.adjust_condition_config)
    g.pick_stock_by_query_rules = check_chang(g.pick_stock_by_query_rules,g.pick_stock_by_query_config)
    g.filter_stock_list_rules = check_chang(g.filter_stock_list_rules,g.filter_stock_list_config)
    g.adjust_position_rules = check_chang(g.adjust_position_rules,g.adjust_position_config)
    g.other_rules = check_chang(g.other_rules,g.other_config)

    # �����������й����list
    g.all_rules = list(set(
            g.position_stock_rules
            + g.adjust_condition_rules
            + g.pick_stock_by_query_rules
            + g.filter_stock_list_rules
            + g.adjust_position_rules
            + g.other_rules
        ))
    log_param()

# ��ʾ�������
def log_param():
    def get_rules_str(rules):
        return '\n'.join(['   %d.%s ' % (i + 1,str(r)) for i,r in enumerate(rules)]) + '\n'
    s = '\n---------------------����һ����������������----------------------------\n'
    s += 'һ���ֲֹ�Ʊ�Ĵ������:\n' + get_rules_str(g.position_stock_rules)
    s += '�������������жϹ���:\n' + get_rules_str(g.adjust_condition_rules)
    s += '����Queryѡ�ɹ���:\n' + get_rules_str(g.pick_stock_by_query_rules)
    s += '�ġ���Ʊ�ع��˹���:\n' + get_rules_str(g.filter_stock_list_rules)
    s += '�塢���ֹ���:\n' + get_rules_str(g.adjust_position_rules)
    s += '������������:\n' + get_rules_str(g.other_rules)
    s += '--------------------------------------------------------------------------'
    print s

''' ==============================�ֲֲ�������������================================'''
# ���֣�����ָ����ֵ��֤ȯ
# �����ɹ����ɽ�������ȫ���ɽ��򲿷ֳɽ�����ʱ�ɽ�������0��������True
# ����ʧ�ܻ��߱����ɹ�����ȡ������ʱ�ɽ�������0��������False
# �����ɹ����������й����when_buy_stock����
def open_position(sender,security,value):
    order = order_target_value_(sender,security,value)
    if order != None and order.filled > 0:
        for rule in g.all_rules:
            rule.when_buy_stock(security,order)
        return True
    return False

# ƽ�֣�����ָ���ֲ�
# ƽ�ֳɹ���ȫ���ɽ�������True
# ����ʧ�ܻ��߱����ɹ�����ȡ������ʱ�ɽ�������0�������߱�����ȫ���ɽ�������False
# �����ɹ����������й����when_sell_stock����
def close_position(sender,position,is_normal=True):
    security = position.security
    order = order_target_value_(sender,security,0)  # ���ܻ���ͣ��ʧ��
    if order != None:
        if order.filled > 0:
            for rule in g.all_rules:
                rule.when_sell_stock(position,order,is_normal)
            return True
    return False

# ����������гֲ�
# ���ʱ���������й���� when_clear_position
def clear_position(sender,context):
    if context.portfolio.positions:
        sender.log_info("==> ��֣��������й�Ʊ")
        for stock in context.portfolio.positions.keys():
            position = context.portfolio.positions[stock]
            close_position(sender,position,False)
    for rule in g.all_rules:
        rule.when_clear_position(context)

# �Զ����µ�
# ����Joinquant�ĵ�����ǰ����������������ִ�У�������������order_target_value�����ؼ���ʾ�������
# �����ɹ����ر�����������һ����ɽ��������򷵻�None
def order_target_value_(sender,security,value):
    if value == 0:
        sender.log_debug("Selling out %s" % (security))
    else:
        sender.log_debug("Order %s to value %f" % (security,value))

    # �����Ʊͣ�ƣ�����������ʧ�ܣ�order_target_value ����None
    # �����Ʊ�ǵ�ͣ������������ɹ���order_target_value ����Order�����Ǳ�����ȡ��
    # ���ɲ����ı������ۿ�״̬���ѳ�����ʱ�ɽ���>0����ͨ���ɽ����ж��Ƿ��гɽ�
    return order_target_value(security,value)

# ͨ��������͵õ��Ѵ����Ķ���ʵ��
def get_obj_by_class_type(class_type):
    for rule in g.all_rules:
        if rule.__class__ == class_type:
            return rule
''' ==============================�������================================'''
class Rule(object):
    # �ֲֲ������¼�
    on_open_position = None  # ��ɵ����ⲿ����
    on_close_position = None  # ���ɵ����ⲿ����
    on_clear_position = None  # ��ֵ����ⲿ����
    on_get_obj_by_class_type = None  # ͨ��������Ͳ����Ѵ��������ʵ��
    memo = ''  # �����Ҫ˵��
    name = ''

    def __init__(self,params):
        pass
    def initialize(self,context):
        pass
    def handle_data(self,context,data):
        pass
    def before_trading_start(self,context):
        pass
    def after_trading_end(self,context):
        pass
    def process_initialize(self,context):
        pass
    def after_code_changed(self,context):
        pass
    # ������Ʊʱ���õĺ���
    # is_normail������������ΪTrue��ֹ������ΪFalse
    def when_sell_stock(self,position,order,is_normal):
        pass
    # �����Ʊʱ���õĺ���
    def when_buy_stock(self,stock,order):
        pass
    # ���ʱ���õĺ���
    def when_clear_position(self,context):
        pass
    # ����ǰ����
    def before_adjust_start(self,context,data):
        pass
    # ���ֺ������
    def after_adjust_end(slef,context,data):
        pass
    # ���Ĳ���
    def update_params(self,context,params):
        pass

    # �ֲֲ����¼��ļ��жϴ�������ʹ�á�
    def open_position(self,security,value):
        if self.on_open_position != None:
            return self.on_open_position(self,security,value)
    def close_position(self,position,is_normal=True):
        if self.on_close_position != None:
            return self.on_close_position(self,position,is_normal=True)
    def clear_position(self,context):
        if self.on_clear_position != None:
            self.on_clear_position(self,context)
    # ͨ��������ͻ�ȡ�Ѵ��������ʵ������
    # ʾ�� obj = get_obj_by_class_type(Index28_condition)
    def get_obj_by_class_type(self,class_type):
        if self.on_get_obj_by_class_type != None:
            return self.on_get_obj_by_class_type(class_type)
        else:
            return None
    # Ϊ��־��ʾ�������ĸ������������
    def log_info(self,msg):
        log.info('%s: %s' % (self.memo,msg))
    def log_warn(self,msg):
        log.warn('%s: %s' % (self.memo,msg))
    def log_debug(self,msg):
        log.debug('%s: %s' % (self.memo,msg))
    def log_error(self,msg):
        log.error('%s: %s' % (self.memo,msg))

'''==============================���������ж�������=============================='''
class Adjust_condition(Rule):
    # �����ܷ���е���
    @property
    def can_adjust(self):
        return True

'''==============================ѡ�� query����������=============================='''
class Filter_query(Rule):
    def filter(self,context,data,q):
        return None
'''==============================ѡ�� stock_list����������=============================='''
class Filter_stock_list(Rule):
    def filter(self,context,data,stock_list):
        return None
'''==============================���ֵĲ�������=============================='''
class Adjust_position(Rule):
    def adjust(self,context,data,buy_stocks):
        pass

'''-------------------------����ʱ�������-----------------------'''
# class Time_condition(Adjust_condition):
#     def __init__(self,params):
#         # ���õ���ʱ�䣨24Сʱ�����ƣ�
#         self.times = params.get('times',[])
#     def update_params(self,context,params):
#         self.times = params.get('times',self.times)
#         pass
#     @property
#     def can_adjust(self):
#         return self.t_can_adjust

#     def handle_data(self,context,data):
#         hour = context.current_dt.hour
#         minute = context.current_dt.minute
#         self.t_can_adjust = [hour,minute ] in self.times
#         pass

#     def __str__(self):
#         return '����ʱ�������: [����ʱ��: %s ]' % (
#                 str(['%d:%d' % (x[0],x[1]) for x in self.times]))
                
class Time_condition(Adjust_condition):
    """����ʱ�������"""

    def __init__(self, params):
        # ���õ���ʱ�䣨24Сʱ�����ƣ�
        self.sell_hour = params.get('sell_hour', 10)
        self.sell_minute = params.get('sell_minute', 15)
        self.buy_hour = params.get('buy_hour', 14)
        self.buy_minute = params.get('buy_minute', 50)

    def update_params(self, context, params):
        self.sell_hour = params.get('sell_hour', self.sell_hour)
        self.sell_minute = params.get('sell_minute', self.sell_minute)
        self.buy_hour = params.get('buy_hour', self.buy_hour)
        self.buy_minute = params.get('buy_minute', self.buy_minute)

    @property
    def can_adjust(self):
        return self.t_can_adjust

    def handle_data(self, context, data):
        hour = context.current_dt.hour
        minute = context.current_dt.minute
        self.t_can_adjust = False
        if (hour == self.sell_hour and minute == self.sell_minute):
            self.t_can_adjust = True
            context.flags_can_sell = True
        else:
            context.flags_can_sell = False
        if (hour == self.buy_hour and minute == self.buy_minute):
            self.t_can_adjust = True
            context.flags_can_buy = True
        else:
            context.flags_can_buy = False

    def __str__(self):
        return '����ʱ�������: [����ʱ��: %d:%d] [����ʱ��: %d:%d]' % (
            self.sell_hour, self.sell_minute, self.buy_hour, self.buy_minute)

'''-------------------------�����ռ�����-----------------------'''
class Period_condition(Adjust_condition):
    def __init__(self,params):
        # �����ռ���������λ����
        self.period = params.get('period',3)
        self.day_count = 0
        self.t_can_adjust = False

    def update_params(self,context,params):
        self.period = params.get('period',self.period)

    @property
    def can_adjust(self):
        return self.t_can_adjust

    def handle_data(self,context,data):
        self.log_info("�����ռ��� [%d]" % (self.day_count))
        self.t_can_adjust = self.day_count % self.period == 0
        self.day_count += 1
        pass

    def before_trading_start(self,context):
        self.t_can_adjust = False
        pass
    def when_sell_stock(self,position,order,is_normal):
        if not is_normal:
            # ����ֹ��ֹӯʱ��������������ʱ�����ü�����ԭ��������ôд��
            self.day_count = 0
        pass
    # ���ʱ���õĺ���
    def when_clear_position(self,context):
        self.day_count = 0
        pass

    def __str__(self):
        return '�����ռ�����:[����Ƶ��: %d��] [�����ռ��� %d]' % (
                self.period,self.day_count)
'''-------------------------28ָ���Ƿ������ж���----------------------'''
class Index28_condition(Adjust_condition):
    def __init__(self,params):
        self.index2 = params.get('index2','')
        self.index8 = params.get('index8','')
        self.index_growth_rate = params.get('index_growth_rate',0.01)
        self.t_can_adjust = False

    def update_params(self,context,params):
        self.index2 = params.get('index2',self.index2)
        self.index8 = params.get('index8',self.index8)
        self.index_growth_rate = params.get('index_growth_rate',self.index_growth_rate)

    @property
    def can_adjust(self):
        return self.t_can_adjust

    def handle_data(self,context,data):
        # �ؿ�ָ��ǰ20����Ƿ�
        gr_index2 = get_growth_rate(self.index2)
        gr_index8 = get_growth_rate(self.index8)
        self.log_info("��ǰ%sָ����20���Ƿ� [%.2f%%]" % (get_security_info(self.index2).display_name,gr_index2 * 100))
        self.log_info("��ǰ%sָ����20���Ƿ� [%.2f%%]" % (get_security_info(self.index8).display_name,gr_index8 * 100))
        if gr_index2 <= self.index_growth_rate and gr_index8 <= self.index_growth_rate:
            self.clear_position(context)
            self.t_can_adjust = False
        else:
            self.t_can_adjust = True
        pass

    def before_trading_start(self,context):
        pass

    def __str__(self):
        return '28ָ����ʱ:[����ָ��:%s %s] [С��ָ��:%s %s] [�ж����ֵĶ���ָ��20������ %.2f%%]' % (
                self.index2,get_security_info(self.index2).display_name,
                self.index8,get_security_info(self.index8).display_name,
                self.index_growth_rate * 100)

'''------------------С��ֵѡ����-----------------'''
class Pick_small_cap(Filter_query):
    def filter(self,context,data,q):
        return query(valuation).order_by(valuation.market_cap.asc())
    def __str__(self):
        return '����ֵ����ѡȡ��Ʊ'

class Pick_by_market_cap(Filter_query):
    def __init__(self,params):
        self.mcap_limit = params.get('mcap_limit',300)
    def filter(self, context, data,q):
        return query(valuation).filter(valuation.market_cap<=self.mcap_limit).order_by(valuation.market_cap.asc())
    def __str__(self):
        return '����ֵ������ѡȡ��Ʊ: [ market_cap < %d ]' % self.mcap_limit
        
class Pick_by_cir_market_cap(Filter_query):
    def __init__(self,params):
        self.cir_mcap_limit = params.get('cir_mcap_limit',200)
    def filter(self, context, data,q):
        return query(valuation).filter(valuation.circulating_market_cap<=self.cir_mcap_limit,
                                        valuation.circulating_market_cap>50).order_by(valuation.circulating_market_cap.asc())
    def __str__(self):
        return '����ͨ��ֵ������ѡȡ��Ʊ: [ cir_market_cap < %d ]' % self.cir_mcap_limit    

class Filter_pe(Filter_query):
    def __init__(self,params):
        self.pe_min = params.get('pe_min',0)
        self.pe_max = params.get('pe_max',200)

    def update_params(self,context,params):
        self.pe_min = params.get('pe_min',self.pe_min)
        self.pe_max = params.get('pe_max',self.pe_max)

    def filter(self,context,data,q):
        return q.filter(
            valuation.pe_ratio > self.pe_min,
            valuation.pe_ratio < self.pe_max
            )
    def __str__(self):
        return '����PE��Χѡȡ��Ʊ�� [ %d < pe < %d]' % (self.pe_min,self.pe_max)

class Filter_eps(Filter_query):
    def __init__(self,params):
        self.eps_min = params.get('eps_min',0)
    def update_params(self,context,params):
        self.eps_min = params.get('eps_min',self.eps_min)
    def filter(self,context,data,q):
        return q.filter(
            indicator.eps > self.eps_min,
            )
    def __str__(self):
        return '����EPS��Χѡȡ��Ʊ�� [ %d < eps ]' % (self.eps_min)

class Filter_limite(Filter_query):
    def __init__(self,params):
        self.pick_stock_count = params.get('pick_stock_count',0)
    def update_params(self,context,params):
        self.pick_stock_count = params.get('pick_stock_count',self.pick_stock_count)
    def filter(self,context,data,q):
        return q.limit(self.pick_stock_count)
    def __str__(self):
        return '��ѡ��Ʊ����: %d' % (self.pick_stock_count)

class Filter_gem(Filter_stock_list):
    def filter(self,context,data,stock_list):
        return [stock for stock in stock_list if stock[0:3] != '300']
    def __str__(self):
        return '���˴�ҵ���Ʊ'

class Filter_paused_stock(Filter_stock_list):
    def filter(self,context,data,stock_list):
        current_data = get_current_data()
        return [stock for stock in stock_list if not current_data[stock].paused]
    def __str__(self):
        return '����ͣ�ƹ�Ʊ'

class Filter_limitup(Filter_stock_list):
    def filter(self,context,data,stock_list):
        threshold = 1.00
        return [stock for stock in stock_list if stock in context.portfolio.positions.keys()
            or data[stock].close < data[stock].high_limit * threshold]
    def __str__(self):
        return '������ͣ��Ʊ'

class Filter_limitdown(Filter_stock_list):
    def filter(self,context,data,stock_list):
        threshold = 1.00
        return [stock for stock in stock_list if stock in context.portfolio.positions.keys()
            or data[stock].close > data[stock].low_limit * threshold]
    def __str__(self):
        return '���˵�ͣ��Ʊ'

class Filter_old_stock(Filter_stock_list):
    def __init__(self,params):
        self.day_count = params.get('day_count',365)
    def update_params(self,context,params):
        self.day_count = params.get('day_count',self.day_count)
    def filter(self,context,data,stock_list):
        tmpList = []
        for stock in stock_list :
            days_public = (context.current_dt.date() - get_security_info(stock).start_date).days
            # ����δ����1��
            if days_public < self.day_count:
                tmpList.append(stock)
        return tmpList
    def __str__(self):
        return '��������ʱ�䳬�� %d ��Ĺ�Ʊ' % (self.day_count)

class Filter_new_stock(Filter_stock_list):
    def __init__(self,params):
        self.day_count = params.get('day_count',365)
    def update_params(self,context,params):
        self.day_count = params.get('day_count',self.day_count)
    def filter(self,context,data,stock_list):
        tmpList = []
        for stock in stock_list :
            days_public = (context.current_dt.date() - get_security_info(stock).start_date).days
            if days_public > self.day_count:
                tmpList.append(stock)
        return tmpList
    def __str__(self):
        return '��������ʱ��δ���� %d ��Ĵ��¹�' % (self.day_count)

class Filter_st(Filter_stock_list):
    def filter(self,context,data,stock_list):
        current_data = get_current_data()
        return [stock for stock in stock_list
            if not current_data[stock].is_st
            and not current_data[stock].name.startswith('��')]
    def __str__(self):
        return '����ST��Ʊ'

class Filter_growth_is_down(Filter_stock_list):
    def __init__(self,params):
        self.day_count = params.get('day_count',20)
    def update_params(self,context,params):
        self.day_count = params.get('day_count',self.day_count)
    def filter(self,context,data,stock_list):
        return [stock for stock in stock_list if get_growth_rate(stock,self.day_count) > 0]
    def __str__(self):
        return '����n��������Ϊ���Ĺ�Ʊ'

class Filter_blacklist(Filter_stock_list):
    def __get_blacklist(self):
        # ������һ��������ʱ�� 2016.7.10 by ɳ��
        # �ƺ�ɷݡ�̫�հ�ҵ��һ��2016���������ֱ��������ͣ���з���
        blacklist = ["600656.XSHG","300372.XSHE","600403.XSHG","600421.XSHG","600733.XSHG","300399.XSHE",
                     "600145.XSHG","002679.XSHE","000020.XSHE","002330.XSHE","300117.XSHE","300135.XSHE",
                     "002566.XSHE","002119.XSHE","300208.XSHE","002237.XSHE","002608.XSHE","000691.XSHE",
                     "002694.XSHE","002715.XSHE","002211.XSHE","000788.XSHE","300380.XSHE","300028.XSHE",
                     "000668.XSHE","300033.XSHE","300126.XSHE","300340.XSHE","300344.XSHE","002473.XSHE"]
        return blacklist

    def filter(self,context,data,stock_list):
        blacklist = self.__get_blacklist()
        return [stock for stock in stock_list if stock not in blacklist]
    def __str__(self):
        return '���˺�������Ʊ'

class Filter_cash_flow_rank(Filter_stock_list):
    def __init__(self,params):
        self.rank_stock_count = params.get('rank_stock_count',300)
    def update_params(self,context,params):
        self.rank_stock_count = params.get('self.rank_stock_count',self.rank_stock_count)
    def __str__(self):
        return 'ׯ���������� [���ֹ���] %d' % self.rank_stock_count    
    def filter(self, context, data, stock_list):
        df = cow_stock_value(stock_list[:self.rank_stock_count], score_threthold=0)
        return df.index

class Filter_chip_density(Filter_stock_list):
    def __init__(self,params):
        self.rank_stock_count = params.get('rank_stock_chip_density',50)
    def update_params(self,context,params):
        self.rank_stock_count = params.get('self.rank_stock_count',self.rank_stock_count)
    def __str__(self):
        return '����ֲ��������� [���ֹ���] %d' % self.rank_stock_count  
    def filter(self, context, data, stock_list):
        results = chip_concentration(context, stock_list[:100])
        return [stock for stock, score in results]

class Filter_rank(Filter_stock_list):
    def __init__(self,params):
        self.rank_stock_count = params.get('rank_stock_count',20)
    def update_params(self,context,params):
        self.rank_stock_count = params.get('self.rank_stock_count',self.rank_stock_count)
    def filter(self,context,data,stock_list):
        if len(stock_list) == 0:
            return stock_list
        if len(stock_list) > self.rank_stock_count:
            stock_list = stock_list[:self.rank_stock_count]

        dst_stocks = {}
        for stock in stock_list:
            h = attribute_history(stock,130,unit='1d',fields=('close','high','low'),skip_paused=True)
            low_price_130 = h.low.min()
            high_price_130 = h.high.max()

            avg_15 = data[stock].mavg(15,field='close')
            cur_price = data[stock].close

            score = (cur_price - low_price_130) + (cur_price - high_price_130) + (cur_price - avg_15)
            dst_stocks[stock] = score

        df = pd.DataFrame(dst_stocks.values(),index=dst_stocks.keys())
        df.columns = ['score']
        df = df.sort(columns='score',ascending=True)
        return list(df.index)

    def __str__(self):
        return '��Ʊ�������� [���ֹ���: %d ]' % (self.rank_stock_count)

class Filter_buy_count(Filter_stock_list):
    def __init__(self,params):
        self.buy_count = params.get('buy_count',3)
    def update_params(self,context,params):
        self.buy_count = params.get('buy_count',self.buy_count)
    def filter(self,context,data,stock_list):
        if len(stock_list) > self.buy_count:
            return stock_list[:self.buy_count]
        else:
            return stock_list
    def __str__(self):
        return '��ȡ���մ������Ʊ��:[ %d ]' % (self.buy_count)

'''---------------������Ʊ����--------------'''
class Sell_stocks(Adjust_position):
    def adjust(self,context,data,buy_stocks):
        # �������ڴ����Ʊ�б��еĹ�Ʊ
        # ������ͣ�Ƶ�ԭ��û�������Ĺ�Ʊ���������
        for stock in context.portfolio.positions.keys():
            if stock not in buy_stocks:
                self.log_info("stock [%s] in position is not buyable" % (stock))
                position = context.portfolio.positions[stock]
                self.close_position(position)
            else:
                self.log_info("stock [%s] is already in position" % (stock))
    def __str__(self):
        return '��Ʊ��������������������buy_stocks�Ĺ�Ʊ'

'''---------------�����Ʊ����--------------'''
class Buy_stocks(Adjust_position):
    def __init__(self,params):
        self.buy_count = params.get('buy_count',3)
    def update_params(self,context,params):
        self.buy_count = params.get('buy_count',self.buy_count)
    def adjust(self,context,data,buy_stocks):
        # �����Ʊ
        # ʼ�ձ��ֲֳ���ĿΪg.buy_stock_count
        # ���ݹ�Ʊ�����ֲ�
        # �˴�ֻ���ݿ��ý��ƽ�����乺�򣬲��ܱ�֤ÿ����λƽ������
        position_count = len(context.portfolio.positions)
        if self.buy_count > position_count:
            value = context.portfolio.cash / (self.buy_count - position_count)
            for stock in buy_stocks:
                if context.portfolio.positions[stock].total_amount == 0:
                    if self.open_position(stock,value):
                        if len(context.portfolio.positions) == self.buy_count:
                            break
        pass
    def __str__(self):
        return '��Ʊ������������ֽ�ƽ��ʽ�����Ʊ��Ŀ���Ʊ��'

def generate_portion(num):
    total_portion = num * (num+1) / 2
    start = num
    while num != 0:
        yield float(num) / float(total_portion)
        num -= 1
        
class Buy_stocks_portion(Adjust_position):
    def __init__(self,params):
        self.buy_count = params.get('buy_count',3)
    def update_params(self,context,params):
        self.buy_count = params.get('buy_count',self.buy_count)
    def adjust(self,context,data,buy_stocks):
        # �����Ʊ
        # ʼ�ձ��ֲֳ���ĿΪg.buy_stock_count
        # ���ݹ�Ʊ�����ֲ�
        # �˴�ֻ���ݿ��ý��ƽ�����乺�򣬲��ܱ�֤ÿ����λƽ������
        position_count = len(context.portfolio.positions)
        if self.buy_count > position_count:
            buy_num = self.buy_count - position_count
            portion_gen = generate_portion(buy_num)
            available_cash = context.portfolio.cash
            for stock in buy_stocks:
                if context.portfolio.positions[stock].total_amount == 0:
                    buy_portion = portion_gen.next()
                    value = available_cash * buy_portion
                    if self.open_position(stock, value):
                        if len(context.portfolio.positions) == self.buy_count:
                            break
        pass
    def __str__(self):
        return '��Ʊ������������ֽ����ʽ�����Ʊ��Ŀ���Ʊ��'    

class Buy_stocks_weighted(Adjust_position):
    def __init__(self,params):
        self.buy_count = params.get('buy_count',3)
    def update_params(self,context,params):
        self.buy_count = params.get('buy_count',self.buy_count)
    def adjust(self, context, data, stock_weighted_list):
        position_count = len(context.portfolio.positions)
        if self.buy_count > position_count:       
            buy_num = self.buy_count - position_count
            available_cash = context.portfolio.cash
            total_weight = 0
            for weight, stock in stock_weighted_list:
                total_weight += weight
            for weight, stock in stock_weighted_list:
                buy_portion = weight / total_weight * available_cash
                if self.open_position(stock, value):
                    if len(context, portfolio.positions) == self.buy_count:
                        break

class Buy_stocks_var(Adjust_position):
    """ʹ�� VaR ���������ֿ���"""

    def __init__(self, params):
        self.buy_count = params.get('buy_count', 3)

    def update_params(self, context, params):
        self.buy_count = params.get('buy_count', self.buy_count)

    def adjust(self, context, data, buy_stocks):
        if not context.flags_can_buy:
            self.log_warn('�޷�ִ������!! context.flags_can_buy δ����')
            return
        # �����Ʊ���߽��е���
        # ʼ�ձ��ֲֳ���ĿΪg.buy_stock_count
        position_count = len(context.portfolio.positions)
        if self.buy_count > position_count:
            buy_num = self.buy_count - position_count
            context.pc_var.buy_the_stocks(context, buy_stocks[:buy_num])
        else:
            context.pc_var.func_rebalance(context)
        pass

    def __str__(self):
        return '��Ʊ�����������ʹ�� VaR ��ʽ������ߵ�����Ʊ��Ŀ���Ʊ��'

# �޳�����ʱ��϶̵Ļ����Ʒ
def delete_new_moneyfund(context, equity, deltaday):
    deltaDate = context.current_dt.date() - datetime.timedelta(deltaday)

    tmpList = []
    for stock in equity:
        if get_security_info(stock).start_date < deltaDate:
            tmpList.append(stock)

    return tmpList


'''---------------����ֹ��--------------'''
class Stop_loss_stocks(Rule):
    # get_period_func Ϊ��ȡperiod�ĺ���,�޴����������������Ϊperiod
    # on_close_position_func ������Ʊʱ�������¼����������Ϊ stock,�޷���
    def __init__(self,params):
        self.last_high = {}
        self.period = params.get('period',3)
        self.pct_change = {}
    def update_params(self,context,params):
        self.period = params.get('period',self.period)
    # ����ֹ��
    def handle_data(self,context,data):
        for stock in context.portfolio.positions.keys():
            cur_price = data[stock].close
            xi = attribute_history(stock,2,'1d','high',skip_paused=True)
            ma = xi.max()
            if self.last_high[stock] < cur_price:
                self.last_high[stock] = cur_price

            threshold = self.__get_stop_loss_threshold(stock,self.period)
            # log.debug("����ֹ����ֵ, stock: %s, threshold: %f" %(stock, threshold))
            if cur_price < self.last_high[stock] * (1 - threshold):
                self.log_info("==> ����ֹ��, stock: %s, cur_price: %f, last_high: %f, threshold: %f"
                    % (stock,cur_price,self.last_high[stock],threshold))

                position = context.portfolio.positions[stock]
                self.close_position(position,False)

    # ��ȡ����ǰn���m������ֵ����
    # ���ӻ�����⵱�ն�λ�ȡ����
    def __get_pct_change(self,security,n,m):
        pct_change = None
        if security in self.pct_change.keys():
            pct_change = self.pct_change[security]
        else:
            h = attribute_history(security,n,unit='1d',fields=('close'),skip_paused=True)
            pct_change = h['close'].pct_change(m)  # 3�յİٷֱȱ�ȣ���3���ǵ�����
            self.pct_change[security] = pct_change
        return pct_change

    # ������ɻس�ֹ����ֵ
    # �������ڳֲ�n�����ܳ��ܵ�������
    # �㷨��(����250��������n�յ��� + ����250����ƽ����n�յ���)/2
    # ������ֵ
    def __get_stop_loss_threshold(self,security,n=3):
        pct_change = self.__get_pct_change(security,250,n)
        # log.debug("pct of security [%s]: %s", pct)
        maxd = pct_change.min()
        # maxd = pct[pct<0].min()
        avgd = pct_change.mean()
        # avgd = pct[pct<0].mean()
        # maxd��avgd����Ϊ������ʾ���ʱ����һֱ�������������¹�
        bstd = (maxd + avgd) / 2

        # ���ݲ���ʱ�������bstdΪnan
        if not isnan(bstd):
            if bstd != 0:
                return abs(bstd)
            else:
                # bstd = 0���� maxd <= 0
                if maxd < 0:
                    # ��ʱȡ������
                    return abs(maxd)

        return 0.099  # Ĭ�����ûز�ֹ����ֵ������Ϊ-9.9%����ֵ��ò�ƻس�����

    def when_sell_stock(self,position,order,is_normal):
        if position.security in self.last_high:
            self.last_high.pop(position.security)
        pass

    def when_buy_stock(self,stock,order):
        if order.status == OrderStatus.held and order.filled == order.amount:
            # ȫ���ɽ���ɾ�����֤ȯ����߼ۻ���
            self.last_high[stock] = get_close_price(stock,1,'1m')
        pass

    def after_trading_end(self,context):
        self.pct_change = {}
        pass

    def __str__(self):
        return '����ֹ����:[��ǰ����۸���: %d ]' % (len(self.last_high))

''' ----------------------����ֹӯ------------------------------'''
class Stop_profit_stocks(Rule):
    def __init__(self,params):
        self.last_high = {}
        self.period = params.get('period',3)
        self.pct_change = {}
    def update_params(self,context,params):
        self.period = params.get('period',self.period)
    # ����ֹӯ
    def handle_data(self,context,data):
        for stock in context.portfolio.positions.keys():
                position = context.portfolio.positions[stock]
                cur_price = data[stock].close
                threshold = self.__get_stop_profit_threshold(stock,self.period)
                # log.debug("����ֹӯ��ֵ, stock: %s, threshold: %f" %(stock, threshold))
                if cur_price > position.avg_cost * (1 + threshold):
                    self.log_info("==> ����ֹӯ, stock: %s, cur_price: %f, avg_cost: %f, threshold: %f"
                        % (stock,cur_price,self.last_high[stock],threshold))

                    position = context.portfolio.positions[stock]
                    self.close_position(position,False)

    # ��ȡ����ǰn���m������ֵ����
    # ���ӻ�����⵱�ն�λ�ȡ����
    def __get_pct_change(self,security,n,m):
        pct_change = None
        if security in self.pct_change.keys():
            pct_change = self.pct_change[security]
        else:
            h = attribute_history(security,n,unit='1d',fields=('close'),skip_paused=True)
            pct_change = h['close'].pct_change(m)  # 3�յİٷֱȱ�ȣ���3���ǵ�����
            self.pct_change[security] = pct_change
        return pct_change

    # �������ֹӯ��ֵ
    # �㷨������250��������n���Ƿ�
    # ������ֵ
    def __get_stop_profit_threshold(self,security,n=3):
        pct_change = self.__get_pct_change(security,250,n)
        maxr = pct_change.max()

        # ���ݲ���ʱ�������maxrΪnan
        # ������maxr����Ϊ��
        if (not isnan(maxr)) and maxr != 0:
            return abs(maxr)
        return 0.30  # Ĭ������ֹӯ��ֵ����Ƿ�Ϊ30%

    def when_sell_stock(self,position,order,is_normal):
        if order.status == OrderStatus.held and order.filled == order.amount:
            # ȫ���ɽ���ɾ�����֤ȯ����߼ۻ���
            if position.security in self.last_high:
                self.last_high.pop(position.security)
        pass

    def when_buy_stock(self,stock,order):
        self.last_high[stock] = get_close_price(stock,1,'1m')
        pass

    def after_trading_end(self,context):
        self.pct_change = {}
        pass
    def __str__(self):
        return '����ֹӯ��:[��ǰ����۸���: %d ]' % (len(self.last_high))

''' ----------------------��߼���ͼ۱���ֹ��------------------------------'''
class Stop_loss_by_price(Adjust_condition):
    def __init__(self,params):
        self.index = params.get('index','000001.XSHG')
        self.day_count = params.get('day_count',160)
        self.multiple = params.get('multiple',2.2)
        self.is_day_stop_loss_by_price = False
    def update_params(self,context,params):
        self.index = params.get('index',self.index)
        self.day_count = params.get('day_count',self.day_count)
        self.multiple = params.get('multiple',self.multiple)

    def handle_data(self,context,data):
        # ����ָ��ǰ130������߼۳�����ͼ�2���������ֹ��
        # ������ʷ�����ж��������״̬���㣬���춼����仯
        # ���Ӵ�ֹ�𣬻س����ͣ����潵��

        if not self.is_day_stop_loss_by_price:
            h = attribute_history(self.index,self.day_count,unit='1d',fields=('close','high','low'),skip_paused=True)
            low_price_130 = h.low.min()
            high_price_130 = h.high.max()
            if high_price_130 > self.multiple * low_price_130 and h['close'][-1] < h['close'][-4] * 1 and  h['close'][-1] > h['close'][-100]:
                # ���յ�һ�������־
                self.log_info("==> ����ֹ��%sָ��ǰ130������߼۳�����ͼ�2��, ��߼�: %f, ��ͼ�: %f" % (get_security_info(self.index).display_name,high_price_130,low_price_130))
                self.is_day_stop_loss_by_price = True

        if self.is_day_stop_loss_by_price:
            self.clear_position(context)

    def before_trading_start(self,context):
        self.is_day_stop_loss_by_price = False
        pass
    def __str__(self):
        return '���̸ߵͼ۱���ֹ����:[ָ��: %s] [����: %s���������ͼ�: %s��] [��ǰ״̬: %s]' % (
                self.index,self.day_count,self.multiple,self.is_day_stop_loss_by_price)

    @property
    def can_adjust(self):
        return not self.is_day_stop_loss_by_price

''' ----------------------��߼���ͼ۱���ֹ��------------------------------'''
class Stop_loss_by_growth_rate(Adjust_condition):
    def __init__(self,params):
        self.index = params.get('index','000001.XSHG')
        self.stop_loss_growth_rate = params.get('stop_loss_growth_rate', -0.03)
        self.to_stop_loss = False
    def update_params(self,context,params):
        self.index = params.get('index','000001.XSHG')
        self.stop_loss_growth_rate = params.get('stop_loss_growth_rate', -0.03)
        self.to_stop_loss = False

    def handle_data(self,context,data):
        if self.to_stop_loss:
            return
        cur_growth_rate = get_growth_rate(self.index,1)
        if cur_growth_rate < self.stop_loss_growth_rate:
            self.log_warn('�����Ƿ� [%s : %.2f%%] ���ڷ�ֵ %.2f%%,���ֹ��!' % (self.index,
                cur_growth_rate * 100,self.stop_loss_growth_rate))
            self.to_stop_loss = True
            self.clear_position(context)
            return
        self.to_stop_loss = False

    def before_trading_start(self,context):
        self.to_stop_loss = False

    def __str__(self):
        return 'ָ�������Ƿ�����ֹ����:[ָ��: %s] [����Ƿ�: %.2f%%]' % (
                self.index,self.stop_loss_growth_rate * 100)

    @property
    def can_adjust(self):
        return not self.to_stop_loss

''' ----------------------����ѻֹ��------------------------------'''
class Stop_loss_by_3_black_crows(Adjust_condition):
    def __init__(self,params):
        self.index = params.get('index','000001.XSHG')
        self.dst_drop_minute_count = params.get('dst_drop_minute_count',60)
        # ��ʱ����
        self.is_last_day_3_black_crows = False
        self.t_can_adjust = True
        self.cur_drop_minute_count = 0
    def update_params(self,context,params):
        self.index = params.get('index',self.index)
        self.dst_drop_minute_count = params.get('dst_drop_minute_count',self.dst_drop_minute_count)

    def initialize(self,context):
        pass

    def handle_data(self,context,data):
        # ǰ������ѻ���ۼƵ���ÿ�����Ƿ�<0�ķ��Ӽ���
        # ������Ӽ�������һ��ֵ����ʼ��������ѻֹ��
        # ������Ч����ѻ��ֹ��
        if self.is_last_day_3_black_crows:
            if get_growth_rate(self.index,1) < 0:
                self.cur_drop_minute_count += 1

            if self.cur_drop_minute_count >= self.dst_drop_minute_count:
                if self.cur_drop_minute_count == self.dst_drop_minute_count:
                    self.log_info("==> ��������ѻֹ��ʼ")

                self.clear_position(context)
                self.t_can_adjust = False
        else:
            self.t_can_adjust = True
        pass

    def before_trading_start(self,context):
        self.is_last_day_3_black_crows = is_3_black_crows(self.index)
        if self.is_last_day_3_black_crows:
            self.log_info("==> ǰ4���Ѿ���������ѻ��̬")
        pass

    def after_trading_end(self,context):
        self.is_last_day_3_black_crows = False
        self.cur_drop_minute_count = 0
        pass

    def __str__(self):
        return '��������ѻֹ����:[ָ��: %s] [����������: %d] [��ǰ״̬: %s]' % (
            self.index,self.dst_drop_minute_count,self.is_last_day_3_black_crows)

    @property
    def can_adjust(self):
        return self.t_can_adjust

''' ----------------------28ָ��ֵʵʱ����ֹ��------------------------------'''
class Stop_loss_by_28_index(Adjust_condition):
    def __init__(self,params):
        self.index2 = params.get('index2','')
        self.index8 = params.get('index8','')
        self.index_growth_rate = params.get('index_growth_rate',0.01)
        self.dst_minute_count_28index_drop = params.get('dst_minute_count_28index_drop',120)
        # ��ʱ����
        self.t_can_adjust = True
        self.minute_count_28index_drop = 0
    def update_params(self,context,params):
        self.index2 = params.get('index2',self.index2)
        self.index8 = params.get('index8',self.index8)
        self.index_growth_rate = params.get('index_growth_rate',self.index_growth_rate)
        self.dst_minute_count_28index_drop = params.get('dst_minute_count_28index_drop',self.dst_minute_count_28index_drop)
    def initialize(self,context):
        pass

    def handle_data(self,context,data):
        # �ؿ�ָ��ǰ20����Ƿ�
        gr_index2 = get_growth_rate(self.index2)
        gr_index8 = get_growth_rate(self.index8)

        if gr_index2 <= self.index_growth_rate and gr_index8 <= self.index_growth_rate:
            if (self.minute_count_28index_drop == 0):
                self.log_info("��ǰ����ָ����20���Ƿ�ͬʱ����[%.2f%%], %sָ��: [%.2f%%], %sָ��: [%.2f%%]" \
                    % (self.index_growth_rate * 100,
                    get_security_info(self.index2).display_name,
                    gr_index2 * 100,
                    get_security_info(self.index8).display_name,
                    gr_index8 * 100))

            self.minute_count_28index_drop += 1
        else:
            # ������״̬����
            if self.minute_count_28index_drop < self.dst_minute_count_28index_drop:
                self.minute_count_28index_drop = 0

        if self.minute_count_28index_drop >= self.dst_minute_count_28index_drop:
            if self.minute_count_28index_drop == self.dst_minute_count_28index_drop:
                self.log_info("==> ����%sָ����%sָ����20����������[%.2f%%]�ѳ���%d���ӣ�ִ��28ָ��ֹ��" \
                    % (get_security_info(self.index2).display_name,get_security_info(self.index8).display_name,self.index_growth_rate * 100,self.dst_minute_count_28index_drop))

            self.clear_position(context)
            self.t_can_adjust = False
        else:
            self.t_can_adjust = True
        pass

    def after_trading_end(self,context):
        self.t_can_adjust = False
        self.minute_count_28index_drop = 0
        pass

    def __str__(self):
        return '28ָ��ֵʵʱ����ֹ��:[����ָ��: %s %s] [С��ָ��: %s %s] [�ж����ֵĶ���ָ��20������ %.2f%%] [���� %d ���������] ' % (
                self.index2,get_security_info(self.index2).display_name,
                self.index8,get_security_info(self.index8).display_name,
                self.index_growth_rate * 100,
                self.dst_minute_count_28index_drop)

    @property
    def can_adjust(self):
        return self.t_can_adjust

''' ----------------------ͳ����----------------------------'''
class Stat(Rule):
    def __init__(self,params):
        # ����ͳ��ģ��
        self.trade_total_count = 0
        self.trade_success_count = 0
        self.statis = {'win': [],'loss': []}

    def after_trading_end(self,context):
        self.report(context)
    def when_sell_stock(self,position,order,is_normal):
        if order.filled > 0:
            # ֻҪ�гɽ�������ȫ���ɽ����ǲ��ֳɽ�����ͳ��ӯ��
            self.watch(position.security,order.filled,position.avg_cost,position.price)

    def reset(self):
        self.trade_total_count = 0
        self.trade_success_count = 0
        self.statis = {'win': [],'loss': []}

    # ��¼���״�������ͳ��ʤ��
    # �����ɹ������������������ӯ��ͳ��
    def watch(self,stock,sold_amount,avg_cost,cur_price):
        self.trade_total_count += 1
        current_value = sold_amount * cur_price
        cost = sold_amount * avg_cost

        percent = round((current_value - cost) / cost * 100,2)
        if current_value > cost:
            self.trade_success_count += 1
            win = [stock,percent]
            self.statis['win'].append(win)
        else:
            loss = [stock,percent]
            self.statis['loss'].append(loss)

    def report(self,context):
        cash = context.portfolio.cash
        totol_value = context.portfolio.portfolio_value
        position = 1 - cash / totol_value
        self.log_info("���̺�ֲָſ�:%s" % str(list(context.portfolio.positions)))
        self.log_info("��λ�ſ�:%.2f" % position)
        self.print_win_rate(context.current_dt.strftime("%Y-%m-%d"),context.current_dt.strftime("%Y-%m-%d"),context)

    # ��ӡʤ��
    def print_win_rate(self,current_date,print_date,context):
        if str(current_date) == str(print_date):
            win_rate = 0
            if 0 < self.trade_total_count and 0 < self.trade_success_count:
                win_rate = round(self.trade_success_count / float(self.trade_total_count),3)

            most_win = self.statis_most_win_percent()
            most_loss = self.statis_most_loss_percent()
            starting_cash = context.portfolio.starting_cash
            total_profit = self.statis_total_profit(context)
            if len(most_win) == 0 or len(most_loss) == 0:
                return

            s = '\n------------��Ч����------------'
            s += '\n���״���: {0}, ӯ������: {1}, ʤ��: {2}'.format(self.trade_total_count,self.trade_success_count,str(win_rate * 100) + str('%'))
            s += '\n����ӯ�����: {0}, ӯ������: {1}%'.format(most_win['stock'],most_win['value'])
            s += '\n���ο������: {0}, �������: {1}%'.format(most_loss['stock'],most_loss['value'])
            s += '\n���ʲ�: {0}, ����: {1}, ӯ��: {2}, ӯ�����ʣ�{3}%'.format(starting_cash + total_profit,starting_cash,total_profit,total_profit / starting_cash * 100)
            s += '\n--------------------------------'
            self.log_info(s)

    # ͳ�Ƶ���ӯ����ߵĹ�Ʊ
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

    # ͳ�Ƶ��ο�����ߵĹ�Ʊ
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

    # ͳ����ӯ�����
    def statis_total_profit(self,context):
        return context.portfolio.portfolio_value - context.portfolio.starting_cash
    def __str__(self):
        return '���Լ�Чͳ��'

'''-------------------ʵ���׶Խ�-----------------------'''
class Shipane_sync_p(Rule):
    def __init__(self,params):
        self.host = params.get('host','')
        self.port = params.get('port',8888)
        self.key = params.get('key','')
        self._client_param = params.get('client','')
        self.strong_op = params.get('strong_op',True)

    def update_params(self,context,params):
        self.host = params.get('host','')
        self.port = params.get('port',8888)
        self.key = params.get('key','')
        self._client_param = params.get('client','')
        self.strong_op = params.get('strong_op',True)

    # ���ֺ����
    def after_adjust_end(self,context,data):
        self.__sync_position(context)
    # ���ʱ���õĺ���
    def when_clear_position(self,context):
        self.__sync_position(context)

    def __sync_position(self,context):
        try:
            client = shipane_sdk.Client(shipane_sdk._Logger(),key=self.key,host=self.host,port=self.port)
            op_count = 2 if self.strong_op else 1
            # ǿ������������,�����ι�,��ֹ�嵵��û����,ɨ�����嵵û��������˰�
            for i in range(op_count):
                self.__sell(client,context)
            # ǿ������������,���,�����飬��һ��Ϊ�򣬵ڶ���Ϊ��飬��ֹ�����嵵ɨ�껹û�򹻵�
            for i in range(op_count):
                self.__buy(client,context)
            pass
        except Exception as e:
            send_message('ʵ���ײ����쳣��������!<br>' + str(e),channel='weixin')
            self.log_warn('ʵ���ײ����쳣��������!' + str(e))

    # ����
    def __sell(self,client,context):
        sp = self.__get_shipan_p(client)
        mp = self.__get_moni_p(context)
        op_list = self.__get_dif(mp,sp)
        self.log_info('�ֲֲ���:' + str(op_list))
        for x in op_list:
            if x[1] > 0 :
                continue
            try:
                actual_order = client.execute(self._client_param,action='SELL',symbol=x[0]
                    ,type='MARKET',priceType=4,amount=abs(x[1]))
            except Exception as e:
                self.log_warn("[ʵ����] �����쳣 [%s : %d]��%s" % (x[0],x[1],str(e)))

    # ���
    def __buy(self,client,context):
        # ��ȡʵ���ֲܳ�
        sp = self.__get_shipan_p(client)
        # ��ȡģ���ֲ̳�
        mp = self.__get_moni_p(context)
        # ͨ���Աȳֲֻ��Ҫ�����Ĺ�Ʊ������
        op_list = self.__get_dif(mp,sp)
        self.log_info('�ֲֲ���:' + str(op_list))
        # ���
        for x in op_list:
            if x[1] < 0 :
                continue
            stock = x[0]
            buy_count = abs(x[1])
            try:
                # ��ʱ��Ҫ��ȡʵ���ʽ�����ͣ�ۼ������ҵ������롣
                # ���һ��������Ҫ����������롣�������Ͳ����ˡ�
                data = get_current_data()
                max_price = data[stock].high_limit
                for i in range(2):
                    # ��ȡʵ�̿����ʽ�
                    cash = self.__get_shipan_cash(client)
                    if cash < 0:
                        send_message('ʵ���׻�ȡʵ�̿����ʽ�ʧ�ܣ����飡',channel='weixin')
                        self.log_warn('ʵ���׻�ȡʵ�̿����ʽ�ʧ�ܣ�����')
                        return

                    # ���㵱ǰ�����ʽ�����ͣ�۹ҵ������ҵ���
                    max_count = int(int(cash * 1.0 / max_price / 100) * 100)
                    self.log_info('%d �������:[stock : %s][max_price:%f] [cash: %f] [max_count:%d] [aim:%d]' % (
                        i + 1,stock,max_price,cash,max_count,buy_count))
                    if max_count <= 0:
                        break
                    if max_count >= buy_count:
                        # �����ʽ��㹻��һ�������롣
                        actual_order = client.execute(self._client_param,action='BUY',symbol=stock
                            ,type='MARKET',priceType=4,amount=buy_count)
                        break
                    else:
                        # �ʽ��㣬�ִ����롣
                        actual_order = client.execute(self._client_param,action='BUY',symbol=stock
                            ,type='MARKET',priceType=4,amount=max_count)
                        buy_count -= max_count
            except Exception as e:
                self.log_warn("[ʵ����] ���쳣 [%s : %d]��%s" % (stock,buy_count,str(e)))

    # ��ȡʵ���ֽ�
    def __get_shipan_cash(self,client):
        r = None
        # �ظ����λ�ȡ����ֹżȻ���������
        for i in range(3):
            try:
                r = client.get_positions(self._client_param)
                break
            except:
                pass
        if r == None:
            return -1

        try:
            cash = float(r['sub_accounts'][u'����'])
        except:
            cash = -1
        return cash

    # ��ȡʵ�ֲ̳�
    def __get_shipan_p(self,client):
        r = None
        e1 = None
        # �ظ����λ�ȡ����ֹżȻ���������
        for i in range(3):
            try:
                r = client.get_positions(self._client_param)
                break
            except Exception as e:
                e1 = e
                pass
        if r == None:
            # �����쳣
            if e1 != None:
                raise e1
            return
        positions = r.get('positions',None)
        sp = zip(positions[u'֤ȯ����'],positions[u'֤ȯ����'])
        sp = [[normalize_code(x[0]).encode('utf-8'),int(float(x[1]))] for x in sp if x[0] != '' and x[1] != '']
        return sp

    # ��ȡģ���ֲ̳�
    def __get_moni_p(self,context):
        result = []
        total_values = context.portfolio.positions_value + context.portfolio.cash
        for stock in context.portfolio.positions.keys():
            position = context.portfolio.positions[stock]
            if position.total_amount == 0:
                continue
            result.append([stock,position.total_amount])

        return result

    # ��ȡ���ֲ�֮�� mpΪģ���̣�spΪʵ�̡�
    def __get_dif(self,mp,sp):
        sp = [[x[0], -x[1]] for x in sp]
        op_list = mp + sp
        # ȡ�����б�֮��
        s_list = list(set([x[0] for x in op_list]))
        s_list = [[s,sum([x[1] for x in op_list if x[0] == s])] for s in s_list]
        # s_list = [x for x in s_list if x[1] >= 100 or x[1] <= -100]
        # s_list += [x for x in sp if x[1] > -100 and x[1] < 0]
        new_l = []
        for s in s_list:
            if s[1] % 100 == 0:
                new_l.append(s)
                continue
            if s[1] < 0:
                # ����
                # ȡģ���̵ĳֲ���
                t = [x[1] for x in mp if x[0] == s[0]]
                if len(t) == 0 or t[0] == 0:
                    # ���ģ��������ָùɣ���ʵ��ȫ��
                    new_l.append(s)
                    continue
                # �Թ�Ʊȡ��
                n = int(round(s[1] * 1.0 / 100) * 100)
                new_l.append([s[0],n])
            else:
                # ���ֱ����������ȡ��
                n = int(round(s[1] * 1.0 / 100) * 100)
                new_l.append([s[0],n])
        new_l = [x for x in new_l if x[1] != 0]
        new_l = sorted(new_l,key=lambda x:x[1])
        return new_l

    def __str__(self):
        return 'ʵ���׶Խ�ȯ�� [host: %s:%d  key: %s client:%s]' % (self.host,self.port,self.key,self._client_param)

'''-----------------����XueQiuOrder�µ�------------------------'''
class XueQiu_order(Rule):
    def __init__(self,params):
        pass

    def update_params(self,context,params):
        pass
    
    def get_executor(self):
        if self.executor == None:
            # self.executor =
            pass
        return self.executor
        
    def after_trading_end(self,context):
        self.executor = None
        pass

    # ������Ʊʱ���õĺ���
    def when_sell_stock(self,position,order,is_normal):
        try:
            # self.get_executor().execute(order)
            pass
        except:
            self.log_error('ʵ��������ʧ��:' + str(order))
        pass
    
    # �����Ʊʱ���õĺ���
    def when_buy_stock(self,stock,order):
        try:
            # self.get_executor().execute(order)
            pass
        except:
            self.log_error('ʵ��������ʧ��:' + str(order))
        pass

'''-----------------���ݾۿ�Order��ʵ�����µ�------------------'''
class Shipane_order(Rule):
    def __init__(self,params):
        self.host = params.get('host','')
        self.port = params.get('port',8888)
        self.key = params.get('key','')
        self.client = params.get('client','')
        self.executor = None
    def update_params(self,context,params):
        self.host = params.get('host','')
        self.port = params.get('port',8888)
        self.key = params.get('key','')
        self.client = params.get('client','')

    # ��ȡ�µ�ִ����
    def get_executor(self):
        if self.executor == None:
            self.executor = shipane_sdk.JoinQuantExecutor(host=self.host,port=self.port,key=self.key,client=self.client)
        return self.executor

    def after_trading_end(self,context):
        self.executor = None
        pass

    # ������Ʊʱ���õĺ���
    def when_sell_stock(self,position,order,is_normal):
        try:
            self.get_executor().execute(order)
        except:
            self.log_error('ʵ��������ʧ��:' + str(order))
        pass
    
    # �����Ʊʱ���õĺ���
    def when_buy_stock(self,stock,order):
        try:
            self.get_executor().execute(order)
        except:
            self.log_error('ʵ��������ʧ��:' + str(order))
        pass

'''------------------------------ͨ��ʵ�����깺�¹�----------------------'''
class Purchase_new_stocks(Rule):
    def __init__(self,params):
        self.times = params.get('times',[[10,00]])
        self.host = params.get('host','')
        self.port = params.get('port',8888)
        self.key = params.get('key','')
        self.clients = params.get('clients',[])
    def update_params(self,context,params):
        self.times = params.get('times',[[10,00]])
        self.host = params.get('host','')
        self.port = params.get('port',8888)
        self.key = params.get('key','')
        self.clients = params.get('clients',[])

    def handle_data(self,context,data):
        hour = context.current_dt.hour
        minute = context.current_dt.minute
        if not [hour ,minute] in self.times:
            return
        shipane = shipane_sdk.Client(shipane_sdk._Logger(),key=self.key,host=self.host,port=self.port)
        for client_param in self.clients:
            shipane.purchase_new_stocks(client_param)
    def __str__(self):
        return 'ʵ�����깺�¹�[time: %s host: %s:%d  key: %s client:%s] ' % (self.times,self.host,self.port,self.key,self.clients)

'''~~~~~~~~~~~~~~~~~~~~~~~~~~~��������~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'''
def is_3_black_crows(stock):
    # talib.CDL3BLACKCROWS

    # ��ֻ��ѻ˵�����԰ٶȰٿ�
    # 1. ���������������ߣ�ÿ������̼۾�������һ�յ�����
    # 2. ��������ǰһ����г�����Ӧ��Ϊ����
    # 3. �������߱���Ϊ���ĺ�ɫʵ�壬�ҳ���Ӧ�ô������
    # 4. ���̼۽ӽ�ÿ�յ���ͼ�λ
    # 5. ÿ�յĿ��̼۶����ϸ�K�ߵ�ʵ�岿��֮�ڣ�
    # 6. ��һ�����ߵ�ʵ�岿�֣���õ������յ���߼�λ
    #
    # �㷨
    # ��Ч��ֻ��ѻ������˵��硣�����ſ�������ֻ����1��2
    # ����ǰ4�������ж�
    # 3�����ߵ�������4.5%�����������ԣ�

    h = attribute_history(stock,4,'1d',('close','open'),skip_paused=True,df=False)
    h_close = list(h['close'])
    h_open = list(h['open'])

    if len(h_close) < 4 or len(h_open) < 4:
        return False

    # һ������
    if h_close[-4] > h_open[-4] \
        and (h_close[-1] < h_open[-1] and h_close[-2] < h_open[-2] and h_close[-3] < h_open[-3]):
        # and (h_close[-1] < h_close[-2] and h_close[-2] < h_close[-3]) \
        # and h_close[-1] / h_close[-4] - 1 < -0.045:
        return True
    return False


# ��ȡ��Ʊn�������Ƿ������ݵ�ǰ�ۼ���
# n Ĭ��20��
def get_growth_rate(security,n=20):
    lc = get_close_price(security,n)
    # c = data[security].close
    c = get_close_price(security,1,'1m')

    if not isnan(lc) and not isnan(c) and lc != 0:
        return (c - lc) / lc
    else:
        log.error("���ݷǷ�, security: %s, %d�����̼�: %f, ��ǰ��: %f" % (security,n,lc,c))
        return 0

# ��ȡǰn����λʱ�䵱ʱ�����̼�
def get_close_price(security,n,unit='1d'):
    return attribute_history(security,n,unit,('close'),True)['close'][0]


# ===================== VaR��λ���� ===============================================

class PositionControlVar(object):
    """���ڷ��ռ�ֵ����VaR���Ĳ�λ����"""

    def __init__(self, context, risk_money_ratio=0.05, confidencelevel=2.58, moneyfund=['511880.XSHG']):
        """ ��ز���˵����
            1. ���÷��ճ���
            risk_money_ratio = 0.05

            2. ��̬�ֲ����ʱ���׼����Լ�������
                1.96, 95%; 2.06, 96%; 2.18, 97%; 2.34, 98%; 2.58, 99%; 5, 99.9999%
            confidencelevel = 2.58

            3. ʹ�ø����ʽ����ֽ����Ļ���(��������)
            moneyfund = ['511880.XSHG']
        """
        self.risk_money = context.portfolio.portfolio_value * risk_money_ratio
        self.confidencelevel = confidencelevel
        self.moneyfund = delete_new_moneyfund(context, moneyfund, 60)

    def __str__(self):
        return 'VaR��λ����'

    # ������Ʊ
    def sell_the_stocks(self, context, stocks):
        for stock in stocks:
            if stock in context.portfolio.positions.keys():
                # ��δ��벻���Ͻ������Ʒ�ֶ��������⣬������ OK
                if stock not in self.moneyfund:
                    equity_ratio = {}
                    equity_ratio[stock] = 0
                    trade_ratio = self.func_getequity_value(context, equity_ratio)
                    self.func_trade(context, trade_ratio)

    # �����Ʊ
    def buy_the_stocks(self, context, stocks):
        equity_ratio = {}
        ratio = 1.0 / len(stocks)       # TODO ��Ҫ����ԭʼ����ȷ���߼��Ƿ���ȷ
        for stock in stocks:
            equity_ratio[stock] = ratio
        trade_ratio = self.func_getequity_value(context, equity_ratio)
        self.func_trade(context, trade_ratio)

    # ��Ʊ����
    def func_rebalance(self, context):
        myholdlist = list(context.portfolio.positions.keys())
        if myholdlist:
            for stock in myholdlist:
                if stock not in self.moneyfund:
                    equity_ratio = {stock: 1.0}
                    trade_ratio = self.func_getequity_value(context, equity_ratio)
                    self.func_trade(context, trade_ratio)

    # ����Ԥ��� risk_money �� confidencelevel �����㣬��������ö���Ȩ�����ʲ�
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
                # ÿ�ɵ� VaR��VaR = ��һ�յļ۸� * ���ŶȻ�������ı�׼���� * �������ʵı�׼��
                __curVaR = hStocks[stock] * __confidence_ratio * __func_getStd(stock, '1d', 120)
                # һԪ���������ٹ�
                __curAmount = 1 * __equity_ratio[stock] / hStocks[stock]  # 1��λ�ʽ𣬷���ʱ���ù�Ʊ��������ٹ�
                __portfolio_VaR += __curAmount * __curVaR  # 1��λ�ʽ�ʱ���ù�Ʊ�ϵ�ʵ�ʷ��ճ���

            if __portfolio_VaR:
                __equity_value = __risk_money / __portfolio_VaR
            else:
                __equity_value = 0

            if isnan(__equity_value):
                __equity_value = 0

            return __equity_value

        risk_money = self.risk_money
        equity_value, bonds_value = 0, 0

        equity_value = __func_getEquity_value(equity_ratio, risk_money, self.confidencelevel)
        portfolio_value = context.portfolio.portfolio_value
        if equity_value > portfolio_value:
            portfolio_value = equity_value  # TODO: �Ƿ�����equity_value = portfolio_value?
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

        # û�ж� bonds ����֣���Ϊֻ��һ��
        if self.moneyfund:
            stock = self.moneyfund[0]
            if stock in trade_ratio:
                trade_ratio[stock] += round((bonds_value * 1.0 / portfolio_value), 3)
            else:
                trade_ratio[stock] = round((bonds_value * 1.0 / portfolio_value), 3)
        log.info('trade_ratio: %s' % trade_ratio)
        return trade_ratio

    # ���׺���
    def func_trade(self, context, trade_ratio):
        def __func_trade(context, stock, value):
            log.info(stock + " ���ֵ� " + str(round(value, 2)) + "\n")
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
                    # ������������������� 100 �ɣ��������������
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

        # ���в�λ
        holdDict = {}
        hholdstocks = history(1, '1d', 'close', myholdstock, df=False)
        for stock in myholdstock:
            tmpW = round((context.portfolio.positions[stock].total_amount * hholdstocks[stock]) / total_value, 2)
            holdDict[stock] = float(tmpW)

        # �����в�λ������
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

        # ����������Ʊ
        for i in range(len(trade_list)):
            stock = trade_list[i]
            if len(_tmplist) != 0:
                if stock not in _tmplist:
                    __func_tradeStock(context, stock, trade_ratio[stock])
            else:
                __func_tradeStock(context, stock, trade_ratio[stock])


# ���ݲ�ͬ��ʱ������û�����������
def set_slip_fee(context):
    # ����������Ϊ0
    slip_ratio = 0.02
    set_slippage(FixedSlippage(slip_ratio))
    log.info('���û�����: �̶�����%f' % slip_ratio)

    # ���ݲ�ͬ��ʱ�������������
    dt = context.current_dt

    if dt > datetime.datetime(2013, 1, 1):
        set_order_cost(OrderCost(open_tax=0, close_tax=0.001, open_commission=0.0003, close_commission=0.0003, close_today_commission=0, min_commission=5), type='stock')
    elif dt > datetime.datetime(2011, 1, 1):
        set_order_cost(OrderCost(open_tax=0, close_tax=0, open_commission=0.001, close_commission=0.002, close_today_commission=0, min_commission=5), type='stock')
    elif dt > datetime.datetime(2009, 1, 1):
        set_order_cost(OrderCost(open_tax=0, close_tax=0, open_commission=0.002, close_commission=0.003, close_today_commission=0, min_commission=5), type='stock')
    else:
        set_order_cost(OrderCost(open_tax=0, close_tax=0, open_commission=0.003, close_commission=0.004, close_today_commission=0, min_commission=5), type='stock')
