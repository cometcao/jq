import pandas as pd
import numpy as np
import enum
import math
import time
import simplejson as json
import datetime

pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

#=========================================common==========================
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

def show_stock(stock):
    '''
    获取股票代码的显示信息    
    :param stock: 股票代码，例如: '603822.XSHG'
    :return: str，例如：'603822 嘉澳环保'
    '''
    return "%s:%s" % (stock[:6], get_stock_info(stock, field="stock_name")[stock]["stock_name"])

# ==================================strategy_frame==================================
'''=================================基础类======================================='''

class Global_variable(object):
    context = None
    _owner = None
    
    buy_stocks = []  # 选股列表
    # 以下参数需配置  Run_Status_Recorder 规则进行记录。
    run_day = 0  # 运行天数，持仓天数为正，空仓天数为负
    position_record = [False]  # 持仓空仓记录表。True表示持仓，False表示空仓。一天一个。
    curve_protect = False # 持仓资金曲线保护flag 
    monitor_buy_list = [] # 当日通过板块选股 外加周 日表里关系 选出的股票
    long_record = {} # 记录买入技术指标
    short_record = {} # 记录卖出技术指标

    def __init__(self, owner):
        self._owner = owner

    ''' ==============================持仓操作函数，共用================================'''
    def workout_num_hand(self, security, data, value):
        cur_price = data[security]['close']
        if math.isnan(cur_price):
            return False, 0
        amount = int(round(value / cur_price / 100) * 100)
        new_value = amount * cur_price
        return True, new_value

    def find_market_type(self, security):
        market_type = 4
        if security[:3] == "688":
            market_type = 0
        elif security[:2] == "60":
            market_type = 1
        elif security[:3] == "300" or security[:2] == "00":
            market_type = 0
        return market_type

    def wait_for_orders(self, order_type=0, wait_sec=6): # order_type: 1 buy, -1 sell, 0 all
        for order in get_orders():
            if order.status == '9':
                log.info('废单:{0}'.format(order))
            elif order.status != '8' \
                and (order_type == 0 \
                     or order_type == -1 and order.amount < 0 \
                     or order_type == 1 and order.amount > 0):
                log.info('之前交易未成交等待中:{0}'.format(order))
                time.sleep(wait_sec)
            else:
                pass

    # 开仓，买入指定价值的证券
    # 报单成功并成交（包括全部成交或部分成交，此时成交量大于0），返回True
    # 报单失败或者报单成功但被取消（此时成交量等于0），返回False
    # 报单成功，触发所有规则的when_buy_stock函数
    def open_position(self, sender, security, value):
        order_id = None
        if is_trade():
            self.wait_for_orders(order_type=0)
            snap_shot = get_snapshot(security)[security]
            last_px = snap_shot["last_px"]
            up_px = snap_shot["up_px"]
            amount = value / last_px // 100 * 100
            order_id = order_market(security, 
                                    amount = amount, 
                                    market_type = self.find_market_type(security),
                                    limit_price = up_px)
        else:
            order_id = order_value(security, value)
        if order_id != None:
            order = get_order(order_id)[0]
            if order.status == '8': 
            # 订单成功，则调用规则的买股事件 。（注：这里只适合市价，挂价单不适合这样处理）
                self._owner.on_buy_stock(security, order, self.context)
                return True
        return False

    def adjust_position(self, context, security, value):
        if get_position(security).amount > 0:
            pos_value = get_position(security).amount * get_position(security).last_sale_price
            if abs(1 - pos_value/value) <= 0.055:
                return True # don't need to make adjustments

        self.wait_for_orders(order_type=0)
        order_id = order_target_value(security, value)
        if order_id != None:
            order = get_order(order_id)[0]
            if order.status == '8': 
                # 订单成功，则调用规则的买股事件 。（注：这里只适合市价，挂价单不适合这样处理）
                self._owner.on_buy_stock(security, order, self.context)
                return True
        return False


    # 平仓，卖出指定持仓
    # 平仓成功并全部成交，返回True
    # 报单失败或者报单成功但被取消（此时成交量等于0），或者报单非全部成交，返回False
    # 报单成功，触发所有规则的when_sell_stock函数
    def close_position(self, sender, position, is_normal=True):
        security = position.sid
        order_id = None
        if is_trade():
            snap_shot = get_snapshot(security)[security]
            st_status = get_stock_status(security, 'ST')
            if st_status[security]:
                order_id = order_target_value(
                    security, 0, limit_price=snap_shot.get("down_px", 0.1))
            else:
                order_id = order_market(security, 
                                        amount = -position.enable_amount, 
                                        market_type = self.find_market_type(security),
                                        limit_price = snap_shot.get("down_px", 0.1)) # 可能会因停牌失败
        else:
            order_id = order_target_value(security, 0)

        if order_id != None:
            order = get_order(order_id)[0]
            if order.status == '8': 
                self._owner.on_sell_stock(position, order, is_normal,self.context)
                return True
        return False

    # 清空卖出所有持仓
    # 清仓时，调用所有规则的 when_clear_position
    def clear_position(self, sender, context):
        if context.porfolio.positions_value > 0:
            log.info(("清仓，卖出所有股票"))
            for position in context.portfolio.positions:
                self.close_position(sender, position, False)
        # 调用规则器的清仓事件
        self._owner.on_clear_position(context, pindexs)
        
        # send port details while clear portfolio
        self.send_port_info(context)
        
    def send_port_info(self, context):
        port_msg = self.getCurrentPosRatio(context)
        print(str(port_msg))
        if is_trade():
            pass

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
    
    def isFirstTradingDayOfWeek(self, context, num_of_day=1):
        trading_days = get_trade_days(end_date=context.current_dt.date(), count=num_of_day+1)
        today = trading_days[-1]
        last_trading_day = trading_days[-(num_of_day+1)]
        return (today.isocalendar()[1] != last_trading_day.isocalendar()[1])
        
    def isFirstTradingDayOfMonth(self, context, num_of_day=1):
        trading_days = get_trade_days(end_date=context.current_dt.date(), count=num_of_day+1)
        today = trading_days[-1]
        last_trading_day = trading_days[-(num_of_day+1)]
        return (today.month != last_trading_day.month)
    
    def isFirstNTradingDayOfPeriod(self, context, num_of_day=1, period='W'):
        if period == 'W':
            print ("Weekly Update Data with num {0}".format(num_of_day))
            return self.isFirstTradingDayOfWeek(context, num_of_day)
        elif period == 'M':
            print ("Monthly Update Data with num {0}".format(num_of_day))
            return self.isFirstTradingDayOfMonth(context, num_of_day)
        else:
            print ("Invalid period return FALSE")
            return False
    
    def getCurrentPosRatio(self, context):
        total_value = context.portfolio.positions_value
        pos_ratio = {}
        for stock in context.portfolio.positions.keys():
            pos = context.portfolio.positions[stock]
            if pos.amount > 0 and total_value > 0:
                pos_ratio[stock] = (pos.amount * pos.last_sale_price) / total_value
        return pos_ratio

# ''' ==============================规则基类================================'''
class Rule(object):
    g = None  # 所属的策略全局变量
    name = ''  # obj名，可以通过该名字查找到
    memo = ''  # 默认描述
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
        self.l_g = g

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
        # obj.g = self.l_g
        obj.set_g(self.l_g)
        obj.name = name
        obj.memo = memo
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
        self.l_g = self._params.get('g_class', Global_variable)(self)
        self.memo = self._params.get('memo', self.memo)
        self.name = self._params.get('name', self.name)
        self.l_g.context = context
        Group_rules.initialize(self, context)

    def handle_data(self, context, data):
        for rule in self.rules:
            rule.handle_data(context, data)
            if rule.to_return and not isinstance(rule, Strategy_Group):  # 这里新增控制，假如是其它策略组合器要求退出的话，不退出。
                self.is_to_return = True
                return
        self.is_to_return = False
        pass

    # 重载 set_g函数,self.l_g不再被外部修改
    def set_g(self, g):
        if self.l_g is None:
            self.l_g = g
        

'''=========================选股规则相关==================================='''

# '''==============================选股 query过滤器基类=============================='''
class Create_stock_list(Rule):
    def filter(self, context, data):
        return None

# '''==============================选股 query过滤器基类=============================='''
class Filter_query(Rule):
    def filter(self, context, data, q):
        return None


# '''==============================选股 stock_list过滤器基类=============================='''
class Filter_stock_list(Rule):
    def filter(self, context, data, stock_list):
        return None
    
    
class Early_Filter_stock_list(Rule):
    def filter(self, context, stock_list):
        return None

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
        self.l_g.send_port_info(context)
        if self.is_to_return:
            return


# '''==============================调仓规则器基类=============================='''
# 需要 before_adjust_start和after_adjust_end的子类可继承
class Adjust_expand(Rule):
    def before_adjust_start(self, context, data):
        pass

    def after_adjust_end(self, context, data):
        pass

'''==================================其它=============================='''


# '''---------------------------------系统参数一般性设置---------------------------------'''
class Set_sys_params(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        # pd.options.mode.chained_assignment = None
        # try:
        #     # 一律使用真实价格
        #     set_option('use_real_price', self._params.get('use_real_price', True))
        #     set_option("avoid_future_data", True)
        # except:
        #     import traceback
        #     print(traceback.format_exc())
        # try:
        #     # 过滤log
        #     log.set_level(*(self._params.get('level', ['order', 'error'])))
        # except:
        #     import traceback
        #     print(traceback.format_exc())
        # try:
        #     # 设置基准
        #     set_benchmark(self._params.get('benchmark', '000300.XSHG'))
        # except:
        #     import traceback
        #     print(traceback.format_exc())

    def __str__(self):
        return '设置系统参数：[使用真实价格交易] [防止未来函数] [忽略order 的 log] [设置基准]'


# '''------------------设置手续费-----------------'''
# 根据不同的时间段设置滑点与手续费并且更新指数成分股
class Set_slip_fee(Rule):
    def before_trading_start(self, context):
        try:
            # 根据不同的时间段设置手续费
            dt = context.current_dt
            if dt > datetime.datetime(2013, 1, 1):
                set_commission(commission_ratio=0.0003, min_commission=5.0, type="STOCK")
    
            elif dt > datetime.datetime(2011, 1, 1):
                set_commission(commission_ratio=0.001, min_commission=5.0, type="STOCK")
    
            elif dt > datetime.datetime(2009, 1, 1):
                set_commission(commission_ratio=0.002, min_commission=5.0, type="STOCK")
            else:
                set_commission(commission_ratio=0.003, min_commission=5.0, type="STOCK")
        except:
            import traceback
            print(traceback.format_exc())

    def __str__(self):
        return '根据时间设置不同的交易费率'


#===================================adjust_pos==========================================
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
        self.on_clear_wait_days = params.get('clear_wait', 2)
        self.day_count = 0
        self.mark_today = {}

    def update_params(self, context, params):
        Weight_Base.update_params(self, context, params)
#         self.on_clear_wait_days = params.get('clear_wait', 2)
#         self.mark_today = {}
        pass

    def handle_data(self, context, data):
        self.is_to_return = self.day_count < 0 or\
                            self.day_count % self.period != 0 or\
                            (self.mark_today[context.current_dt.date()] if context.current_dt.date() in self.mark_today else False)
        
        if context.current_dt.date() not in self.mark_today: # only increment once per day
            log.info("调仓日计数 [%d]" % (self.day_count))
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
        if self.l_g.curve_protect or self.on_clear_wait_days > 0:
            self.day_count = -self.on_clear_wait_days
            self.l_g.curve_protect = False
        pass

    def __str__(self):
        return '调仓日计数器:[调仓频率: %d日] [调仓日计数 %d] [清仓等待: %d日]' % (self.period, self.day_count, self.on_clear_wait_days)


'''===================================调仓相关============================'''

# '''---------------卖出股票规则--------------'''
class Sell_stocks(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        
    def handle_data(self, context, data):
        to_sell = []
        self.l_g.monitor_buy_list = [stock for stock in self.l_g.monitor_buy_list if stock not in to_sell]        
        self.adjust(context, data, self.l_g.monitor_buy_list)

    def adjust(self, context, data, buy_stocks):
        log.info("卖出不在待买股票列表中的股票")
        # 对于因停牌等原因没有卖出的股票则继续持有
        for stock in context.portfolio.positions.keys():
            if stock not in buy_stocks:
                position = context.portfolio.positions[stock]
                self.l_g.close_position(self, position, True)
                    
    def recordTrade(self, stock_list):
        pass

    def __str__(self):
        return '股票调仓卖出规则：卖出不在buy_stocks的股票'


# '''---------------买入股票规则--------------'''
class Buy_stocks(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        self.buy_count = params.get('buy_count', 3)
        self.use_portion = params.get('use_portion', 1.0)

    def update_params(self, context, params):
        Rule.update_params(self, context, params)
        self.buy_count = params.get('buy_count', self.buy_count)

    def handle_data(self, context, data):
        if self.is_to_return:
            log.info('无法执行买入!! self.is_to_return 未开启')
            return
        to_buy = self.l_g.monitor_buy_list[:self.buy_count]
        log.info("待选股票: "+join_list([show_stock(stock) for stock in to_buy], ' ', 10))
        self.l_g.wait_for_orders(order_type=-1, wait_sec=60)
        holding_stocks = [context.portfolio.positions[pos].sid for pos in context.portfolio.positions.keys() if context.portfolio.positions[pos].amount > 0]
        pos_count = len(holding_stocks)
        if self.buy_count > pos_count:
            target_avg = context.portfolio.portfolio_value / self.buy_count * self.use_portion
            pos_value = context.portfolio.positions_value / pos_count if pos_count > 0 else target_avg
            log.info("执行调仓买入:{}".format([stock for stock in to_buy if stock not in holding_stocks]))
            if abs(pos_value / target_avg) - 1 > 0.382:
                log.info("平衡仓位")
                self.adjust_avg(context, data, to_buy)
            else:
                self.adjust(context, data, to_buy)
        else:
            log.info("持仓数量完整:{}".format([(stock, context.portfolio.positions[stock].amount) for stock in context.portfolio.positions.keys()]))
        
    def adjust(self, context, data, buy_stocks):
        # 买入股票
        # 始终保持持仓数目为g.buy_stock_count
        # 根据股票数量分仓
        # 此处只根据可用金额平均分配购买，不能保证每个仓位平均分配
        position_count = sum([1 for pos in context.portfolio.positions.keys() if context.portfolio.positions[pos].amount > 0])
        if self.buy_count > position_count:
            value = min(context.portfolio.portfolio_value / self.buy_count * self.use_portion,
                        context.portfolio.cash / (self.buy_count - position_count))
            for stock in buy_stocks:
                if stock not in context.portfolio.positions.keys():
                    if self.l_g.open_position(self, stock, value):
                        pass
    
    def adjust_avg(self, context, data, buy_stocks):
        sorted_holding_stocks_data = sorted([(pos, context.portfolio.positions[pos].amount * context.portfolio.positions[pos].last_sale_price)
                                        for pos in context.portfolio.positions.keys() if context.portfolio.positions[pos].amount > 0], key=lambda x: x[1], reverse = True)
        sorted_holding_stocks = [i[0] for i in sorted_holding_stocks_data]

        buy_stocks = [stock for stock in buy_stocks if stock not in sorted_holding_stocks]
        buy_stocks = sorted_holding_stocks + buy_stocks

        avg_value = context.portfolio.portfolio_value / self.buy_count * self.use_portion
        for stock in buy_stocks:
            if self.l_g.adjust_position(context, stock, avg_value):
                pass
                    
    def after_trading_end(self, context):
        pass
        
    def recordTrade(self, stock_list):
        pass

    def __str__(self):
        return '股票调仓买入规则：现金平分式买入股票达目标股票数: {0} 仓位: {1}'.format(self.buy_count, self.use_portion)


#===================================select stock========================================
# '''-----------------选股组合器2-----------------------'''
class Pick_stocks2(Group_rules):
    def __init__(self, params):
        Group_rules.__init__(self, params)
        self.has_run = False
        self.file_path = params.get('write_to_file', None)

    def handle_data(self, context, data):
        try:
            to_run_one = self._params.get('day_only_run_one', False)
        except:
            to_run_one = False
        if to_run_one and self.has_run:
            # log.info('设置一天只选一次，跳过选股。')
            return

        stock_list = self.l_g.buy_stocks
        for rule in self.rules:
            if isinstance(rule, Filter_stock_list):
                stock_list = rule.filter(context, data, stock_list)

        # dirty hack
        self.l_g.monitor_buy_list = stock_list
        log.info(
            '今日选股:\n' + join_list(["[%s]" % (show_stock(x)) for x in stock_list], ' ', 10))
        self.has_run = True

    def before_trading_start(self, context):
        self.has_run = False
        # clear the buy list this variable stores the initial list of
        # candidates for the day
        self.l_g.buy_stocks = []
        for rule in self.rules:
            if isinstance(rule, Create_stock_list):
                self.l_g.buy_stocks = self.l_g.buy_stocks + \
                    rule.before_trading_start(context)

        for rule in self.rules:
            if isinstance(rule, Early_Filter_stock_list):
                rule.before_trading_start(context)

        for rule in self.rules:
            if isinstance(rule, Early_Filter_stock_list):
                self.l_g.buy_stocks = rule.filter(context, self.l_g.buy_stocks)

        checking_stocks = self.l_g.buy_stocks
        if self.file_path:
            if self.file_path == "daily":
                write_file(
                    "daily_stocks/{0}.txt".format(str(context.current_dt.date())), ",".join(checking_stocks))
            else:
                write_file(self.file_path, ",".join(checking_stocks))
                log.info('file written:{0}'.format(self.file_path))

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
        full_file_path = get_research_path() + "/upload_file/" + self.filename
        try:
            with open(full_file_path, 'rb') as f:
                stock_list = json.load(f)
                stock_list = [stock.replace('XSHE', 'SZ').replace(
                    'XSHG', 'SS') for stock in stock_list]
        except:
            log.info(
                "file {0} read failed hold on current positions".format(self.filename))
            stock_list = list(context.portfolio.positions.keys())

        log.info("stocks {0} read from file {1}".format(
            stock_list, self.filename))

        ##########################
        # import random
        # random.shuffle(stock_list)
        # stock_list = stock_list[:8]
        ##########################
        return stock_list


#======================================sort_stock========================================
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
    
#======================================record_stats======================================

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
        self.op_sell_stocks.append([position.sid, -order.filled])

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
        # 显示买卖日志
        if len(self.op_sell_stocks) > 0:
            log.info(
                '\n' + join_list(["卖出 %s : %d" % (show_stock(x[0]), x[1]) for x in self.op_sell_stocks], '\n', 1))
        if len(self.op_buy_stocks) > 0:
            log.info(
                '\n' + join_list(["买入 %s : %d" % (show_stock(x[0]), x[1]) for x in self.op_buy_stocks], '\n', 1))
        # 显示完就清除
        self.op_buy_stocks = []
        self.op_sell_stocks = []

    def __str__(self):
        return '显示调仓时买卖的股票'

# ''' ----------------------统计类----------------------------'''
class Stat(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        # 加载统计模块
        self.trade_total_count = 0
        self.trade_success_count = 0
        self.statis = {'win': [], 'loss': []}

    def after_trading_end(self, context):
        if self._params.get('trade_stats', True):
            self.l_g.long_record = {}
            self.l_g.short_record = {}
        self.report(context)

    def on_sell_stock(self, position, order, is_normal, pindex=0,context=None):
        if order.filled > 0:
            # 只要有成交，无论全部成交还是部分成交，则统计盈亏
            self.watch(position.sid, order.filled, position.cost_basis, position.last_sale_price)

    def on_buy_stock(self,stock,order,pindex=0,context=None):
        pass

    def reset(self):
        self.trade_total_count = 0
        self.trade_success_count = 0
        self.statis = {'win': [], 'loss': []}

    # 记录交易次数便于统计胜率
    # 卖出成功后针对卖出的量进行盈亏统计
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
        position = 1 - cash / totol_value
        log.info("收盘后持仓概况:%s" % str(list(context.portfolio.positions)))
        log.info("仓位概况:%.2f" % position)
        self.print_win_rate(context.current_dt.strftime("%Y-%m-%d"), context.current_dt.strftime("%Y-%m-%d"), context)

    def print_win_rate_v2(self):
        pass

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
            log.info(s)

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

# ==================================策略配置==============================================
def select_strategy(context):
    g.strategy_memo = '混合策略'
    g.buy_count = 8

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
        [True, '', '从研究文件中获取选股', Pick_stock_list_from_file,{
            'filename': "low_valuation_stocks.json",
            }],

        [True, '', '获取最终选股数', Filter_buy_count, {
            'buy_count': 13  # 最终入选股票数
        }],
    ]
    pick_new = [
        [True, '_pick_stocks_', '选股', Pick_stocks2, {
            'config': pick_config,
            'day_only_run_one': True, 
            'write_to_file': None,
        }]
    ]

    ''' --------------------------配置 4 调仓规则------------------ '''
    adjust_position_config = [
        [True, '', '卖出股票', Sell_stocks, {}],
        [True, '', '买入股票', Buy_stocks, {
            'buy_count': g.buy_count,
            'use_portion': 1 - 1 / g.buy_count * 0.2
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
        [False, '', '设置系统参数', Set_sys_params, {
            'benchmark': '000300.SS'  # 指定基准为次新股指
        }],
        [False, '', '手续费设置器', Set_slip_fee, {}],
        [False, '', '统计执行器', Stat, {'trade_stats':False}],
        [False, '', '自动调参器', Update_Params_Auto, {}],
    ]
    common_config = [
        [False, '_other_pre_', '预先处理的辅助规则', Group_rules, {
            'config': common_config_list
        }]
    ]
    # 组合成一个总的策略
    return (common_config
                     + adjust_condition_config
                     + pick_new
                     + adjust_position_config)

def initialize(context):
    log.info("=========================initialize=========================================")
    pass


# 进程启动(一天一次)
def process_initialize(context):
    log.info("=========================process_initialize=====================================")
    # 策略配置
    main_config = select_strategy(context)
    # 创建策略组合
    g.main = Strategy_Group({'config': main_config
                                , 'g_class': Global_variable
                                , 'memo': g.strategy_memo
                                , 'name': '_main_'})
    g.main.initialize(context)

    # 打印规则参数
    log.info(g.main.show_strategy())


# 按分钟回测
def handle_data(context, data):
    # 保存context到全局变量量，主要是为了方便规则器在一些没有context的参数的函数里使用。
    g.main.l_g.context = context
    # 执行策略
    g.main.handle_data(context, data)


# 开盘
def before_trading_start(context, data):
    log.info("=========================before_trading_start===================================")
    process_initialize(context)
    g.main.l_g.context = context
    g.main.before_trading_start(context)


# 收盘
def after_trading_end(context,data):
    log.info("=========================after_trading_end======================================")
    g.main.l_g.context = context
    g.main.after_trading_end(context)
    g.main.l_g.context = None
    g.main = None


# 这里示例进行模拟更改回测时，如何调整策略,基本通用代码。
def after_code_changed(context):
    log.info("=========================after_code_changed=====================================")
    pass
    
    
# ''' ----------------------参数自动调整----------------------------'''
class Update_Params_Auto(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)

    def before_trading_start(self, context):
        if self.l_g.isFirstTradingDayOfWeek(context):
            self.dynamicBuyCount(context)
            log.info("修改全局参数")
    
    def dynamicBuyCount(self, context):
        import math
        g.buy_count = int(math.ceil(math.log(context.portfolio.portfolio_value/10000)))

    def __str__(self):
        return '参数自动调整'
