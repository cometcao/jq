'''
�汾����������ع� ������ʱС��ֵv2.0.7
�ڣ�2017.1.4
ԭ���ߣ�Morningstar
�޸��ߣ������С��
'''
from seek_cash_flow import * 
from chip_migration import *
from scipy.signal import argrelextrema
'''
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
# enable_profile()
'''ѡ�������ϳ�һ����������'''
def select_strategy():
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
    g.cs_enabled,g.cs_memo,g.cs_class_name,g.cs_param = range(4)
    

    # 0.�Ƿ����ã�1.������2.����ʵ��������3.���򴫵ݲ���(dict)]
    period = 5                                      # ����Ƶ��
    # ���� 1.�ֲֹ�Ʊ�Ĵ������ (������Ҫ�����Ƿ���и���ֹ��ֹӯ)
    g.position_stock_config = [
        [False,'����ֹ��',Stop_loss_stocks,{
            'period':period                     # ����Ƶ�ʣ���
            },],
        [False,'����ֹӯ',Stop_profit_stocks,
            {'period':period ,                  # ����Ƶ�ʣ���
            }]
    ]
        
    # ���� 2.���������жϹ��� 
    g.adjust_condition_config = [
        [True,'ָ����ߵͼ۱�ֵֹ��',Stop_loss_by_price,{
            'index':'000001.XSHG',                  # ʹ�õ�ָ��,Ĭ�� '000001.XSHG'
             'day_count':160,                       # ��ѡ ȡday_count���ڵ���߼ۣ���ͼۡ�Ĭ��160
             'multiple':2.2                         # ��ѡ ��߼�Ϊ��ͼ۵�multiple��ʱ���� �����
            }],
        [True,'ָ������ѻֹ��',Stop_loss_by_3_black_crows,{
            'index':'000001.XSHG',                  # ʹ�õ�ָ��,Ĭ�� '000001.XSHG'
             'dst_drop_minute_count':60,            # ��ѡ��������ѻ��������£�һ��֮���ж��ٷ����Ƿ�<0,�򴥷�ֹ��Ĭ��60����
            }],
        [False,'28ʵʱֹ��',Stop_loss_by_28_index,{
                    'index2' : '000016.XSHG',       # ����ָ��
                    'index8' : '399333.XSHE',       # С��ָ��
                    'index_growth_rate': 0.01,      # �ж����ֵĶ���ָ��20������
                    'dst_minute_count_28index_drop': 120 # ���������������ٷ��������
                }],
        [True,'����ʱ��',Time_condition,{
                'houre': 14,                    # ����ʱ��,Сʱ
                'minute' : 40                   # ����ʱ�䣬����
            }],
        [True,'28������ʱ',Index28_condition,{    # �õ����������ܻ���������Ϊ
                'index2' : '000016.XSHG',       # ����ָ��
                'index8' : '399333.XSHE',       # С��ָ��
                'index_growth_rate': 0.01,      # �ж����ֵĶ���ָ��20������
            }],
        [True,'�����ռ�����',Period_condition,{
                'period' : period ,             # ����Ƶ��,��
            }],
    ]
        
    # ���� 3.Queryѡ�ɹ���
    g.pick_stock_by_query_config = [
        [False,'ѡȡС��ֵ',Pick_small_cap,{}],
        [True,'ѡȡׯ��',Pick_by_market_cap,{'mcap_limit':300}],
        [False,'ѡȡׯ�ɣ���ͨ��ֵ��',Pick_by_cir_market_cap,{'cir_mcap_limit':200}],
        [True,'����PE',Filter_pe,{ 
            'pe_min':0                          # ��СPE
            ,'pe_max':200                       # ���PE
            }],
        [True,'����EPS',Filter_eps,{
            'eps_min':0                         # ��СEPS
            }],
        [True,'��ѡ��Ʊ����',Filter_limite,{
            'pick_stock_count':600              # ��ѡ��Ʊ��Ŀ
            }]
    ]
    
    # ���� 4.��Ʊ�ع��˹���
    g.filter_stock_list_config = [
        [True,'���˴�ҵ��',Filter_gem,{}],
        [True,'����ST',Filter_st,{}],
        [True,'����ͣ��',Filter_paused_stock,{}],
        [True,'������ͣ',Filter_limitup,{}],
        [True,'���˵�ͣ',Filter_limitdown,{}],
        [False,'����n��������Ϊ���Ĺ�Ʊ',Filter_growth_is_down,{
            'day_count':20                      # �ж϶��������Ƿ�
            }],
        [False,'���˺�����',Filter_blacklist,{}],
        [False,'��Ʊ����',Filter_rank,{
            'rank_stock_count': 50              # ���ֹ���
            }],
        [True,'ׯ������',Filter_cash_flow_rank,{'rank_stock_count':600}],
        [False,'����ֲ�����',Filter_chip_density,{'rank_stock_count':50}],
        [True,'��ȡ����ѡ����',Filter_buy_count,{
            'buy_count': 3                      # ������ѡ��Ʊ��
            }],
    ]
        
    # ���� 5.���ֹ���
    g.adjust_position_config = [
        [True,'������Ʊ',Sell_stocks,{}],
        [False,'�����Ʊ',Buy_stocks,{
            'buy_count': 4                      # ���������Ʊ��
            }],
        [True,'�����������Ʊ',Buy_stocks_portion,{'buy_count':3}]
    ]
    
    # ���� 6.��������
    g.other_config = [
        [True,'ͳ��',Stat,{}]
    ]

# ����һ������ִ����������ʼ��һЩͨ���¼�
def create_rule(class_type,params,memo):
    obj = class_type(params)
    obj.on_open_position = open_position    # ���
    obj.on_close_position = close_position  # ����
    obj.on_clear_position = clear_position  # ���
    obj.on_get_obj_by_class_type = get_obj_by_class_type # ͨ�������õ����ʵ��
    obj.memo = memo
    return obj
    
# ���ݹ������ô�������ִ����
def create_rules(config):
    # config�� 0.�Ƿ����ã�1.������2.����ʵ��������3.���򴫵ݲ���(dict)]
    return [create_rule(c[g.cs_class_name],c[g.cs_param],c[g.cs_memo]) for c in config if c[g.cs_enabled]]

def initialize(context):
    log.info("==> initialize @ %s"%(str(context.current_dt)))
    set_commission(PerTrade(buy_cost=0.0003, sell_cost=0.0013, min_cost=5))
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    log.set_level('order','error')
    
    select_strategy()
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
def handle_data(context, data):
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
        
    log.info("handle_data: ѡ�ɺ�����Ʊ: %s" %(stock_list))
    
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
        log.info("canceled uncompleted order: %s" %(_order.order_id))

# ��������(һ��һ��)
def process_initialize(context):
    for rule in g.all_rules:
        rule.process_initialize(context)

# ����ʾ������ģ����Ļز�ʱ����ε�������,����ͨ�ô��롣
def after_code_changed(context):
    # # ��Ϊ��ʾ�����ڲ���ģ������»ز�����ʱ���ǲ���Ҫ�ģ�����ֱ���˳�
    # return
    print '���´��룺'
    # ��������ͨ��ʵ������
    # ��ȡ�²���
    select_strategy()
    # ���²���˳�����������б��������֮ǰ���ڣ����Ƶ����б����������½���
    # ����֮ǰ�ɵĹ����б���ʲô˳��һ�ʰ����б���������
    def check_chang(rules,config):
        nl = []
        for c in config:
        # ��˳��ѭ�������¹���
            if not c[g.cs_enabled]: # ��ʹ��������
                continue
            # ���Ҿɹ����Ƿ����
            find_old = None
            for old_r in rules:
                if old_r.__class__ == c[g.cs_class_name]:
                    find_old = old_r
                    break
            if find_old != None:
                # �ɹ����������ӵ����б���,�����ù���ĸ��º��������²�����
                nl.append(find_old)
                find_old.update_params(context,c[g.cs_param])
            else:
                # �ɹ��򲻴��ڣ��򴴽������
                new_r = create_rule(c[g.cs_class_name],c[g.cs_param])
                nl.append(new_r)
                # ���ó�ʼ��ʱ��ִ�еĺ���
                rule.initialize(context)
        return nl
    
    # �������й���
    g.position_stock_rules      = check_chang(g.position_stock_rules,g.position_stock_config)
    g.adjust_condition_rules    = check_chang(g.adjust_condition_rules,g.adjust_condition_config)
    g.pick_stock_by_query_rules = check_chang(g.pick_stock_by_query_rules,g.pick_stock_by_query_config)
    g.filter_stock_list_rules   = check_chang(g.filter_stock_list_rules,g.filter_stock_list_config)
    g.adjust_position_rules     = check_chang(g.adjust_position_rules,g.adjust_position_config)
    g.other_rules               = check_chang(g.other_rules,g.other_config)
    
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
        return '\n'.join(['   %d.%s '%(i+1,str(r)) for i,r in enumerate(rules)]) + '\n'
    s = '\n---------------------����һ����������������----------------------------\n'
    s += 'һ���ֲֹ�Ʊ�Ĵ������:\n'  + get_rules_str(g.position_stock_rules)
    s += '�������������жϹ���:\n'    + get_rules_str(g.adjust_condition_rules)
    s += '����Queryѡ�ɹ���:\n'       + get_rules_str(g.pick_stock_by_query_rules)
    s += '�ġ���Ʊ�ع��˹���:\n'      + get_rules_str(g.filter_stock_list_rules)
    s += '�塢���ֹ���:\n'            + get_rules_str(g.adjust_position_rules)
    s += '������������:\n'            + get_rules_str(g.other_rules)
    s += '--------------------------------------------------------------------------'
    print s

''' ==============================�ֲֲ�������������================================'''
# ���֣�����ָ����ֵ��֤ȯ
# �����ɹ����ɽ�������ȫ���ɽ��򲿷ֳɽ�����ʱ�ɽ�������0��������True
# ����ʧ�ܻ��߱����ɹ�����ȡ������ʱ�ɽ�������0��������False
# �����ɹ����������й����when_buy_stock����
def open_position(sender,security, value):
    order = order_target_value_(sender,security, value)
    if order != None and order.filled > 0:
        for rule in g.all_rules:
            rule.when_buy_stock(security,order)
        return True
    return False

# ƽ�֣�����ָ���ֲ�
# ƽ�ֳɹ���ȫ���ɽ�������True
# ����ʧ�ܻ��߱����ɹ�����ȡ������ʱ�ɽ�������0�������߱�����ȫ���ɽ�������False
# �����ɹ����������й����when_sell_stock����
def close_position(sender,position,is_normal = True):
    security = position.security
    order = order_target_value_(sender,security, 0) # ���ܻ���ͣ��ʧ��
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
def order_target_value_(sender,security, value):
    if value == 0:
        sender.log_debug("Selling out %s" % (security))
    else:
        sender.log_debug("Order %s to value %f" % (security, value))
        
    # �����Ʊͣ�ƣ�����������ʧ�ܣ�order_target_value ����None
    # �����Ʊ�ǵ�ͣ������������ɹ���order_target_value ����Order�����Ǳ�����ȡ��
    # ���ɲ����ı������ۿ�״̬���ѳ�����ʱ�ɽ���>0����ͨ���ɽ����ж��Ƿ��гɽ�
    return order_target_value(security, value)
    
# ͨ��������͵õ��Ѵ����Ķ���ʵ��
def get_obj_by_class_type(class_type):
    for rule in g.all_rules:
        if rule.__class__ == class_type:
            return rule
''' ==============================�������================================'''
class Rule(object):
    # �ֲֲ������¼�
    on_open_position = None # ��ɵ����ⲿ����
    on_close_position = None # ���ɵ����ⲿ����
    on_clear_position = None # ��ֵ����ⲿ����
    on_get_obj_by_class_type = None # ͨ��������Ͳ����Ѵ��������ʵ��
    memo = ''   # �����Ҫ˵��
    
    def __init__(self,params):
        pass
    def initialize(self,context):
        pass
    def handle_data(self,context, data):
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
    # priceΪ��ǰ�ۣ�amountΪ�����Ĺ�Ʊ��,is_normail������������ΪTrue��ֹ������ΪFalse
    def when_sell_stock(self,position,order,is_normal):
        pass
    # �����Ʊʱ���õĺ���
    # priceΪ��ǰ�ۣ�amountΪ�����Ĺ�Ʊ��
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
    def open_position(self,security, value):
        if self.on_open_position != None:
            return self.on_open_position(self,security,value)
    def close_position(self,position,is_normal = True):
        if self.on_close_position != None:
            return self.on_close_position(self,position,is_normal = True)
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
        log.info('%s: %s'%(self.memo,msg))
    def log_warn(self,msg):
        log.warn('%s: %s'%(self.memo,msg))
    def log_debug(self,msg):
        log.debug('%s: %s'%(self.memo,msg))
 
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
class Time_condition(Adjust_condition):
    def __init__(self,params):
        # ���õ���ʱ�䣨24Сʱ�����ƣ�
        self.hour = params.get('hour',14)
        self.minute = params.get('minute',50)
    def update_params(self,context,params):
        self.hour = params.get('hour',self.hour)
        self.minute = params.get('minute',self.minute)
        pass
    @property   
    def can_adjust(self):
        return self.t_can_adjust

    def handle_data(self,context, data):
        hour = context.current_dt.hour
        minute = context.current_dt.minute
        self.t_can_adjust = hour == self.hour and minute == self.minute
        pass
    

    def __str__(self):
        return '����ʱ�������: [����ʱ��: %d:%d]'%(
                self.hour,self.minute)
'''-------------------------�����ռ�����-----------------------'''
class Period_condition(Adjust_condition):
    def __init__(self,params):
        # �����ռ���������λ����
        self.period = params.get('period',3)
        self.day_count = 0
        self.t_can_adjust = False
        
    def update_params(self,context,params):
        self.period  = params.get('period',self.period )
        
    @property   
    def can_adjust(self):
        return self.t_can_adjust

    def handle_data(self,context, data):
        self.log_info("�����ռ��� [%d]"%(self.day_count))
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
        return '�����ռ�����:[����Ƶ��: %d��] [�����ռ��� %d]'%(
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

    def handle_data(self,context, data):
        # �ؿ�ָ��ǰ20����Ƿ�
        gr_index2 = get_growth_rate(self.index2)
        gr_index8 = get_growth_rate(self.index8)
        self.log_info("��ǰ%sָ����20���Ƿ� [%.2f%%]" %(get_security_info(self.index2).display_name, gr_index2*100))
        self.log_info("��ǰ%sָ����20���Ƿ� [%.2f%%]" %(get_security_info(self.index8).display_name, gr_index8*100))
        if gr_index2 <= self.index_growth_rate and gr_index8 <= self.index_growth_rate:
            self.clear_position(context)
            self.t_can_adjust = False
        else:
            self.t_can_adjust = True
        pass
    
    def before_trading_start(self,context):
        pass
    
    def __str__(self):
        return '28ָ����ʱ:[����ָ��:%s %s] [С��ָ��:%s %s] [�ж����ֵĶ���ָ��20������ %.2f%%]'%(
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
        return '����PE��Χѡȡ��Ʊ�� [ %d < pe < %d]'%(self.pe_min,self.pe_max)
        
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
        return '����EPS��Χѡȡ��Ʊ�� [ %d < eps ]'%(self.eps_min)
    
class Filter_limite(Filter_query):
    def __init__(self,params):
        self.pick_stock_count = params.get('pick_stock_count',100)
    def update_params(self,context,params):
        self.pick_stock_count = params.get('pick_stock_count',self.pick_stock_count)
    def filter(self,context,data,q):
        return q.limit(self.pick_stock_count)
    def __str__(self):
        return '��ѡ��Ʊ����: %d'%(self.pick_stock_count)

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
        return [stock for stock in stock_list if get_growth_rate(stock, self.day_count) > 0]
    def __str__(self):
        return '����n��������Ϊ���Ĺ�Ʊ'

class Filter_blacklist(Filter_stock_list):
    def __get_blacklist(self):
        # ������һ��������ʱ�� 2016.7.10 by ɳ��
        # �ƺ�ɷݡ�̫�հ�ҵ��һ��2016���������ֱ��������ͣ���з���
        blacklist = ["600656.XSHG", "300372.XSHE", "600403.XSHG", "600421.XSHG", "600733.XSHG", "300399.XSHE",
                     "600145.XSHG", "002679.XSHE", "000020.XSHE", "002330.XSHE", "300117.XSHE", "300135.XSHE",
                     "002566.XSHE", "002119.XSHE", "300208.XSHE", "002237.XSHE", "002608.XSHE", "000691.XSHE",
                     "002694.XSHE", "002715.XSHE", "002211.XSHE", "000788.XSHE", "300380.XSHE", "300028.XSHE",
                     "000668.XSHE", "300033.XSHE", "300126.XSHE", "300340.XSHE", "300344.XSHE", "002473.XSHE"]
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
        df = cow_stock_value(stock_list[:self.rank_stock_count])
        return df.index

class Filter_chip_density(Filter_stock_list):
    def __init__(self,params):
        self.rank_stock_count = params.get('rank_stock_chip_density',50)
    def update_params(self,context,params):
        self.rank_stock_count = params.get('self.rank_stock_count',self.rank_stock_count)
    def __str__(self):
        return '����ֲ��������� [���ֹ���] %d' % self.rank_stock_count  
    def filter(self, context, data, stock_list):
        density_list = self.__chip_migration(context, data, stock_list[:self.rank_stock_count])
        return [l[0] for l in sorted(density_list, key=lambda x : x[1], reverse=True)]
    def __chip_migration(self, context, data, stock_list):
        density_dict = []
        for stock in stock_list:
            # print "working on stock %s" % stock
            df = attribute_history(stock, count = 120, unit='1d', fields=('avg', 'volume'), skip_paused=True)
            df_dates = df.index
            for da in df_dates:
                df_fund = get_fundamentals(query(
                        valuation.turnover_ratio
                    ).filter(
                        # ���ﲻ��ʹ�� in ����, Ҫʹ��in_()����
                        valuation.code.in_([stock])
                    ), date=da)
                if not df_fund.empty:
                    df.loc[da, 'turnover_ratio'] = df_fund['turnover_ratio'][0]
            df = df.dropna()
            df = chip_migration(df)
            concentration_number, latest_concentration_rate= self.__analyze_chip_density(df)
            density_dict.append((stock, concentration_number * latest_concentration_rate))
        return density_dict

    def __analyze_chip_density(self, df):
        df = df.dropna()
        df = df.drop_duplicates(cols='chip_density')
        bottomIndex = argrelextrema(df.chip_density.values, np.less_equal,order=3)[0]
        concentration_num = len(bottomIndex)
        latest_concentration_rate = df.chip_density.values[-1] / df.chip_density[bottomIndex[-1]]
        return concentration_num, latest_concentration_rate
        
        
class Filter_rank(Filter_stock_list):
    def __init__(self,params):
        self.rank_stock_count = params.get('rank_stock_count',20)
    def update_params(self,context,params):
        self.rank_stock_count = params.get('self.rank_stock_count',self.rank_stock_count)
    def filter(self,context,data,stock_list):
        if len(stock_list) > self.rank_stock_count:
            stock_list = stock_list[:self.rank_stock_count]
        
        dst_stocks = {}
        for stock in stock_list:
            h = attribute_history(stock, 130, unit='1d', fields=('close', 'high', 'low'), skip_paused=True)
            low_price_130 = h.low.min()
            high_price_130 = h.high.max()
    
            avg_15 = data[stock].mavg(15, field='close')
            cur_price = data[stock].close

            score = (cur_price-low_price_130) + (cur_price-high_price_130) + (cur_price-avg_15)
            dst_stocks[stock] = score
            
        df = pd.DataFrame(dst_stocks.values(), index=dst_stocks.keys())
        df.columns = ['score']
        df = df.sort(columns='score', ascending=True)
        return list(df.index)
        
    def __str__(self):
        return '��Ʊ�������� [���ֹ���: %d ]'%(self.rank_stock_count)
        
class Filter_buy_count(Filter_stock_list):
    def __init__(self,params):
        self.buy_count = params.get('buy_count',5)
    def update_params(self,context,params):
        self.buy_count = params.get('buy_count',self.buy_count)
    def filter(self,context,data,stock_list):
        if len(stock_list) > self.buy_count:
            return stock_list[:self.buy_count]
        else:
            return stock_list
    def __str__(self):
        return '��ȡ���մ������Ʊ��:[ %d ]'%(self.buy_count)
        
'''---------------������Ʊ����--------------'''        
class Sell_stocks(Adjust_position):
    def adjust(self,context,data,buy_stocks):
        # �������ڴ����Ʊ�б��еĹ�Ʊ
        # ������ͣ�Ƶ�ԭ��û�������Ĺ�Ʊ���������
        for stock in context.portfolio.positions.keys():
            if stock not in buy_stocks:
                self.log_info("stock [%s] in position is not buyable" %(stock))
                position = context.portfolio.positions[stock]
                self.close_position(position)
            else:
                self.log_info("stock [%s] is already in position" %(stock))
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
                    if self.open_position(stock, value):
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
    def handle_data(self,context, data):
        for stock in context.portfolio.positions.keys():
            cur_price = data[stock].close
            xi = attribute_history(stock, 2, '1d', 'high', skip_paused=True)
            ma = xi.max()
            if self.last_high[stock] < cur_price:
                self.last_high[stock] = cur_price

            threshold = self.__get_stop_loss_threshold(stock, self.period)
            #log.debug("����ֹ����ֵ, stock: %s, threshold: %f" %(stock, threshold))
            if cur_price < self.last_high[stock] * (1 - threshold):
                self.log_info("==> ����ֹ��, stock: %s, cur_price: %f, last_high: %f, threshold: %f" 
                    %(stock, cur_price, self.last_high[stock], threshold))
    
                position = context.portfolio.positions[stock]
                self.close_position(position,False)
    
    # ��ȡ����ǰn���m������ֵ����
    # ���ӻ�����⵱�ն�λ�ȡ����
    def __get_pct_change(self,security, n, m):
        pct_change = None
        if security in self.pct_change.keys():
            pct_change = self.pct_change[security]
        else:
            h = attribute_history(security, n, unit='1d', fields=('close'), skip_paused=True)
            pct_change = h['close'].pct_change(m) # 3�յİٷֱȱ�ȣ���3���ǵ�����
            self.pct_change[security] = pct_change
        return pct_change
        
    # ������ɻس�ֹ����ֵ
    # �������ڳֲ�n�����ܳ��ܵ�������
    # �㷨��(����250��������n�յ��� + ����250����ƽ����n�յ���)/2
    # ������ֵ
    def __get_stop_loss_threshold(self,security, n = 3):
        pct_change = self.__get_pct_change(security, 250, n)
        #log.debug("pct of security [%s]: %s", pct)
        maxd = pct_change.min()
        #maxd = pct[pct<0].min()
        avgd = pct_change.mean()
        #avgd = pct[pct<0].mean()
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
    
        return 0.099 # Ĭ�����ûز�ֹ����ֵ������Ϊ-9.9%����ֵ��ò�ƻس�����

    def when_sell_stock(self,position,order,is_normal):
        if position.security in self.last_high:
            self.last_high.pop(position.security)
        pass
    
    def when_buy_stock(self,stock,order):
        if order.status == OrderStatus.held and order.filled == order.amount:
            # ȫ���ɽ���ɾ�����֤ȯ����߼ۻ���
            self.last_high[stock] = get_close_price(stock, 1, '1m')
        pass
    
    def after_trading_end(self,context):
        self.pct_change = {}
        pass
                
    def __str__(self):
        return '����ֹ����:[��ǰ����۸���: %d ]'%(len(self.last_high))
        
''' ----------------------����ֹӯ------------------------------'''
class Stop_profit_stocks(Rule):
    def __init__(self,params):
        self.last_high = {}
        self.period = params.get('period',3)
        self.pct_change = {}
    def update_params(self,context,params):
        self.period = params.get('period',self.period)    
    # ����ֹӯ
    def handle_data(self,context, data):
        for stock in context.portfolio.positions.keys():
                position = context.portfolio.positions[stock]
                cur_price = data[stock].close
                threshold = self.__get_stop_profit_threshold(stock, self.period)
                #log.debug("����ֹӯ��ֵ, stock: %s, threshold: %f" %(stock, threshold))
                if cur_price > position.avg_cost * (1 + threshold):
                    self.log_info("==> ����ֹӯ, stock: %s, cur_price: %f, avg_cost: %f, threshold: %f" 
                        %(stock, cur_price, self.last_high[stock], threshold))
        
                    position = context.portfolio.positions[stock]
                    self.close_position(position,False)

    # ��ȡ����ǰn���m������ֵ����
    # ���ӻ�����⵱�ն�λ�ȡ����
    def __get_pct_change(self,security, n, m):
        pct_change = None
        if security in self.pct_change.keys():
            pct_change = self.pct_change[security]
        else:
            h = attribute_history(security, n, unit='1d', fields=('close'), skip_paused=True)
            pct_change = h['close'].pct_change(m) # 3�յİٷֱȱ�ȣ���3���ǵ�����
            self.pct_change[security] = pct_change
        return pct_change
    
    # �������ֹӯ��ֵ
    # �㷨������250��������n���Ƿ�
    # ������ֵ
    def __get_stop_profit_threshold(self,security, n = 3):
        pct_change = self.__get_pct_change(security, 250, n)
        maxr = pct_change.max()
        
        # ���ݲ���ʱ�������maxrΪnan
        # ������maxr����Ϊ��
        if (not isnan(maxr)) and maxr != 0:
            return abs(maxr)
        return 0.30 # Ĭ������ֹӯ��ֵ����Ƿ�Ϊ30%
    
    def when_sell_stock(self,position,order,is_normal):
        if order.status == OrderStatus.held and order.filled == order.amount:
            # ȫ���ɽ���ɾ�����֤ȯ����߼ۻ���
            if position.security in self.last_high:
                self.last_high.pop(position.security)
        pass
    
    def when_buy_stock(self,stock,order):
        self.last_high[stock] = get_close_price(stock, 1, '1m')
        pass
    
    def after_trading_end(self,context):
        self.pct_change = {}
        pass
    def __str__(self):
        return '����ֹӯ��:[��ǰ����۸���: %d ]'%(len(self.last_high))

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

    def handle_data(self,context, data):
        # ����ָ��ǰ130������߼۳�����ͼ�2���������ֹ��
        # ������ʷ�����ж��������״̬���㣬���춼����仯
        # ���Ӵ�ֹ�𣬻س����ͣ����潵��
    
        if not self.is_day_stop_loss_by_price:
            h = attribute_history(self.index, self.day_count, unit='1d', fields=('close', 'high', 'low'), skip_paused=True)
            low_price_130 = h.low.min()
            high_price_130 = h.high.max()
            if high_price_130 > self.multiple * low_price_130 and h['close'][-1]<h['close'][-4]*1 and  h['close'][-1]> h['close'][-100]:
                # ���յ�һ�������־
                self.log_info("==> ����ֹ��%sָ��ǰ130������߼۳�����ͼ�2��, ��߼�: %f, ��ͼ�: %f" %(get_security_info(self.index).display_name, high_price_130, low_price_130))
                self.is_day_stop_loss_by_price = True
    
        if self.is_day_stop_loss_by_price:
            self.clear_position(context)

    def before_trading_start(self,context):
        self.is_day_stop_loss_by_price = False
        pass
    def __str__(self):
        return '���̸ߵͼ۱���ֹ����:[ָ��: %s] [����: %s���������ͼ�: %s��] [��ǰ״̬: %s]'%(
                self.index,self.day_count,self.multiple,self.is_day_stop_loss_by_price)
        
    @property
    def can_adjust(self):
        return not self.is_day_stop_loss_by_price

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
        self.index = params.get('index',self.index )
        self.dst_drop_minute_count = params.get('dst_drop_minute_count',self.dst_drop_minute_count)
        
    def initialize(self,context):
        pass
    
    def handle_data(self,context, data):
        # ǰ������ѻ���ۼƵ���ÿ�����Ƿ�<0�ķ��Ӽ���
        # ������Ӽ�������һ��ֵ����ʼ��������ѻֹ��
        # ������Ч����ѻ��ֹ��
        if self.is_last_day_3_black_crows:
            if get_growth_rate(self.index, 1) < 0:
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
        return '��������ѻֹ����:[ָ��: %s] [����������: %d] [��ǰ״̬: %s]'%(
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
    
    def handle_data(self,context, data):
        # �ؿ�ָ��ǰ20����Ƿ�
        gr_index2 = get_growth_rate(self.index2)
        gr_index8 = get_growth_rate(self.index8)
    
        if gr_index2 <= self.index_growth_rate and gr_index8 <= self.index_growth_rate:
            if (self.minute_count_28index_drop == 0):
                self.log_info("��ǰ����ָ����20���Ƿ�ͬʱ����[%.2f%%], %sָ��: [%.2f%%], %sָ��: [%.2f%%]" \
                    %(self.index_growth_rate*100, 
                    get_security_info(self.index2).display_name, 
                    gr_index2*100, 
                    get_security_info(self.index8).display_name, 
                    gr_index8*100))
    
            self.minute_count_28index_drop += 1
        else:
            # ������״̬����
            if self.minute_count_28index_drop < self.dst_minute_count_28index_drop:
                self.minute_count_28index_drop = 0
    
        if self.minute_count_28index_drop >= self.dst_minute_count_28index_drop:
            if self.minute_count_28index_drop == self.dst_minute_count_28index_drop:
                self.log_info("==> ����%sָ����%sָ����20����������[%.2f%%]�ѳ���%d���ӣ�ִ��28ָ��ֹ��" \
                    %(get_security_info(self.index2).display_name, get_security_info(self.index8).display_name, self.index_growth_rate*100, self.dst_minute_count_28index_drop))
    
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
        return '28ָ��ֵʵʱ����ֹ��:[����ָ��: %s %s] [С��ָ��: %s %s] [�ж����ֵĶ���ָ��20������ %.2f%%] [���� %d ���������] '%(
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
        self.statis = {'win': [], 'loss': []}
        
    def after_trading_end(self,context):
        self.report(context)
    def when_sell_stock(self,position,order,is_normal):
        if order.filled > 0:
            # ֻҪ�гɽ�������ȫ���ɽ����ǲ��ֳɽ�����ͳ��ӯ��
            self.watch(position.security, order.filled, position.avg_cost, position.price)
            
    def reset(self):
        self.trade_total_count = 0
        self.trade_success_count = 0
        self.statis = {'win': [], 'loss': []}

    # ��¼���״�������ͳ��ʤ��
    # �����ɹ������������������ӯ��ͳ��
    def watch(self, stock, sold_amount, avg_cost, cur_price):
        self.trade_total_count += 1
        current_value = sold_amount * cur_price
        cost = sold_amount * avg_cost

        percent = round((current_value - cost) / cost * 100, 2)
        if current_value > cost:
            self.trade_success_count += 1
            win = [stock, percent]
            self.statis['win'].append(win)
        else:
            loss = [stock, percent]
            self.statis['loss'].append(loss)

    def report(self, context):
        cash = context.portfolio.cash
        totol_value = context.portfolio.portfolio_value
        position = 1 - cash/totol_value
        self.log_info("���̺�ֲָſ�:%s" % str(list(context.portfolio.positions)))
        self.log_info("��λ�ſ�:%.2f" % position)
        self.print_win_rate(context.current_dt.strftime("%Y-%m-%d"), context.current_dt.strftime("%Y-%m-%d"), context)

    # ��ӡʤ��
    def print_win_rate(self, current_date, print_date, context):
        if str(current_date) == str(print_date):
            win_rate = 0
            if 0 < self.trade_total_count and 0 < self.trade_success_count:
                win_rate = round(self.trade_success_count / float(self.trade_total_count), 3)

            most_win = self.statis_most_win_percent()
            most_loss = self.statis_most_loss_percent()
            starting_cash = context.portfolio.starting_cash
            total_profit = self.statis_total_profit(context)
            if len(most_win)==0 or len(most_loss)==0:
                return

            s = '\n------------��Ч����------------'
            s += '\n���״���: {0}, ӯ������: {1}, ʤ��: {2}'.format(self.trade_total_count, self.trade_success_count, str(win_rate * 100) + str('%'))
            s += '\n����ӯ�����: {0}, ӯ������: {1}%'.format(most_win['stock'], most_win['value'])
            s += '\n���ο������: {0}, �������: {1}%'.format(most_loss['stock'], most_loss['value'])
            s += '\n���ʲ�: {0}, ����: {1}, ӯ��: {2}, ӯ�����ʣ�{3}%'.format(starting_cash + total_profit, starting_cash, total_profit, total_profit / starting_cash * 100)
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
    def statis_total_profit(self, context):
        return context.portfolio.portfolio_value - context.portfolio.starting_cash
    def __str__(self):
        return '���Լ�Чͳ��'       
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

    h = attribute_history(stock, 4, '1d', ('close','open'), skip_paused=True, df=False)
    h_close = list(h['close'])
    h_open = list(h['open'])

    if len(h_close) < 4 or len(h_open) < 4:
        return False
    
    # һ������
    if h_close[-4] > h_open[-4] \
        and (h_close[-1] < h_open[-1] and h_close[-2]< h_open[-2] and h_close[-3] < h_open[-3]):
        #and (h_close[-1] < h_close[-2] and h_close[-2] < h_close[-3]) \
        #and h_close[-1] / h_close[-4] - 1 < -0.045:
        return True
    return False
    

# ��ȡ��Ʊn�������Ƿ������ݵ�ǰ�ۼ���
# n Ĭ��20��
def get_growth_rate(security, n=20):
    lc = get_close_price(security, n)
    #c = data[security].close
    c = get_close_price(security, 1, '1m')
    
    if not isnan(lc) and not isnan(c) and lc != 0:
        return (c - lc) / lc
    else:
        log.error("���ݷǷ�, security: %s, %d�����̼�: %f, ��ǰ��: %f" %(security, n, lc, c))
        return 0

# ��ȡǰn����λʱ�䵱ʱ�����̼�
def get_close_price(security, n, unit='1d'):
    return attribute_history(security, n, unit, ('close'), True)['close'][0]
