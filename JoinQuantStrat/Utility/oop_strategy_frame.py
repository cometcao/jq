# -*- encoding: utf8 -*-
'''
Created on 4 Dec 2017

@author: MetalInvest
'''

try:
    from kuanke.user_space_api import *
except:
    pass
from jqdata import *
from common_include import *
import enum
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
    
    print("DEBUG CALLED")
    import traceback
    for line in traceback.format_stack():
        print(line.strip())
    
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
    intraday_long_stock = []
    pair_zscore = []
    market_timing_check = {}
    stock_index_dict = {}
    position_proportion = {} # 仓位控制比例
#     stock_chan_type = {} # record chan types
    industry_sector_list = [] # record industry sector names
    all_pos_return_stocks = set()
    all_neg_return_stocks = set()
    enchanced_long_stocks = set()

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


    def adjust_position(self, context, security, value, pindex=0):
        cur_price = get_close_price(security, 1, '1m')
        if math.isnan(cur_price):
            return False
        # 通过当前价，四乘五入的计算要买的股票数。
        amount = int(round(value / cur_price / 100) * 100)
        new_value = amount * cur_price

        if security in context.subportfolios[pindex].long_positions.keys() and\
            abs(1 - context.subportfolios[pindex].long_positions[security].value/new_value) <= 0.055:
            return True # don't need to make adjustments

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
        
        # send port details while clear portfolio
        self.send_port_info(context)
        
    def send_port_info(self, context):
        port_msg = [(context.portfolio.positions[stock].security, context.portfolio.positions[stock].total_amount * context.portfolio.positions[stock].price / context.portfolio.total_value) for stock in context.portfolio.positions]
        print(str(port_msg))
        if context.run_params.type == 'sim_trade':
            send_message(port_msg, channel='weixin')

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
        total_value = context.portfolio.total_value
        pos_ratio = {}
        for stock in context.portfolio.positions:
            pos = context.portfolio.positions[stock]
            pos_ratio[stock] = (pos.total_amount * pos.price) / total_value
        return pos_ratio
    
    def getFundamentalThrethold(self, factor, threthold = 0.95):
        eval_factor = eval(factor)
        queryDf = get_fundamentals(query(
            eval_factor, valuation.code
            ).order_by(
                eval_factor.asc()
            ))
        queryDf = queryDf.dropna()
        total_num = queryDf.shape[0]
        threthold_index = int(total_num * threthold)
        return queryDf[queryDf.columns.values[0]][threthold_index]  


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
        self.g.send_port_info(context)
        if self.is_to_return:
            return


# '''==============================调仓规则器基类=============================='''
# 需要 before_adjust_start和after_adjust_end的子类可继承
class Adjust_expand(Rule):
    def before_adjust_start(self, context, data):
        pass

    def after_adjust_end(self, context, data):
        pass


'''=========================选股规则相关==================================='''

# 选取财务数据的参数
# 使用示例 FD_param('valuation.market_cap',None,100) #先取市值小于100亿的股票
# 注：传入类型为 'valuation.market_cap'字符串而非 valuation.market_cap 是因 valuation.market_cap等存在序列化问题！！
# 具体传入field 参考  https://www.joinquant.com/data/dict/fundamentals
class FD_Factor(object):
    def __init__(self, factor, **kwargs):
        self.factor = factor
        self.min = kwargs.get('min', None)
        self.max = kwargs.get('max', None)
        self.isComplex = kwargs.get('isComplex', False)


'''==================================其它=============================='''


# '''---------------------------------系统参数一般性设置---------------------------------'''
class Set_sys_params(Rule):
    def __init__(self, params):
        Rule.__init__(self, params)
        pd.options.mode.chained_assignment = None
        try:
            # 一律使用真实价格
            set_option('use_real_price', self._params.get('use_real_price', True))
            set_option("avoid_future_data", True)
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

    def __str__(self):
        return '设置系统参数：[使用真实价格交易] [防止未来函数] [忽略order 的 log] [设置基准]'


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
