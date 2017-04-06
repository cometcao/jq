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
    # 实盘易操作SDK,新版SDK已解决聚宽序列化问题。
    import shipane_sdk
except:
    pass


'''
版本：面向对象重构 二八择时小市值v2.0.7
日期：2017.1.4
原作者：Morningstar
修改者：晚起的小虫
'''

'''
2017-02-23更新:
    1. 新增通过实盘易自动申购新股的规则类 Purchase_new_stocks
    2. 更改回调用实盘易官方SDK的shipane_sdk.py的方法。方便日后更新。
    
2017-02-21更新:
    1. 把原SDK的JoinQuantExecutor类整合到Shipane_order规则里。
        使用Rule的几种log方法，避免原先的_logger带来的无法序列化错误。
    2. 把原SDK的Client更改为继承Rule，并删除_logger。
        使用Rule的几种log方法，避免原先的_logger带来的无法序列化错误。
    3. Shipane_order 下单时加Try，以避免下单错误时导致模拟盘异常退出。
        这里只是简单粗暴的处理下单失败，其实可以更进一步避免失败(未 )。
        1) 下卖单时，通过获取持仓信息，来判断有多少可卖的，是否达到order要求
        2) 下买单时，通过获取持仓信息，来判断下的买单数量是否达到order要求，是否需要拆单
            这里可参考Shipane_sync_p的一些处理方式。
    
2017-02-16更新:
    1. 修正模拟盘更新代码的潜藏BUG。原机制，假如一个规则创建两个实例，就会更新规则错乱。
    规则配置 [True,'_filter_gem_','过滤创业板',Filter_gem,{}],第二 个字段为定义一个对象名。
    如果一个规则只用了一次，可以不写。假如同一个规则使用多次，则需要一定要写名字。
    例如 创建两个实盘易规则，去操作两个通达信帐号。
    2. 修正Filter_rank 传入Stock_list为空时异常的Bug。
    3. Shipane_sync_p 在执行完买卖单后sleep一定时间，避免操作太快，持仓信息没更新
2017-02-15更新:
    1. 更改原Shipane类名为 Shipane_sync_p
    2. Shipane_sync_p新增清仓时执行同步持仓。
    3. 新增按聚宽下单的order用实盘易跟单实盘下单规则类 Shepane_order。
    
2017-02-14更新:
    1.增加通过实盘易对接实盘的代码，使策略可以直接实盘 Shipane类。
        实盘操作逻辑说明：
        核心思路是使实盘持仓尽量向模拟盘持仓靠拢。
        通过实盘持仓与模拟盘持仓的仓位对比，取得有差别的股票及数量。进行实盘下单。
        而不是根据策略买卖下单进行实盘下单的。
        (如需按策略下单去实盘下单，可以用实盘易官方SDK里的代码)
        关于实盘易的配置请上它的官网:http://www.iguuu.com/e
        该方法优缺点：
        优点：模拟盘与实盘持仓会相同或接近，有利于策略有效性检验，也使回测意义增大。
        缺点：在模拟盘与实盘资金差别比较大的时候，有可能会导致一些股票被频繁小部分的买卖。
              解决办法也有，就是模拟盘资金比实盘多时，买股前把可用资金先减去差额再去计算买股量。本策略暂时没加这部分
        Shipane规则默认未启用。如需要请配置好参数再开启
        注：代码未经严格实盘测试，请慎重使用！或用 通达信模拟炒股测试。
2017-1-11更新：
    1.策略组合选取配置那里，所有类 由 写类写字符串改为直接写类名
    2.Rule基类增加 on_get_obj_by_class_type外接函数。通过它实现一个规则得到另一个规则的实例
        方便某些情况下规则的相互调用。不再局限于只能handle_data顺序调用。本策略相对逻辑简单，没有使用。
    3.去除所有对象的__name__定义。更新代码时，直接用类的类型对比。
    4.为Rule添加memo属性，对象的memo直接以策略配置里的memo字段赋值，日志更直观
2017-1-5 更新
    1.修正不使用Query选股规则时报错的BUG
    2.修正28实时止损器 Stop_loss_by_28_index 的BUG
    3.Rule增加log_info和log_warn方法，增加显示是由哪个规则器输出的日志。
    4.把 tradestat也重构为规则类，集成到代码里。这样不用外部引用tradestat.py模块了
'''

'''选择规则组合成一个量化策略'''
def select_strategy(context):
    '''
    策略选择设置说明:
    策略由以下步骤规则组合，组合而成:
    1.持仓股票的处理规则
    2.调仓条件判断规则
    3.Query选股规则 (可选，有些规则可能不需要这个)
    4.股票池过滤规则 (可选，有些规则可能不需要这个)
    5.调仓规则
    6.其它规则(如统计)
    
    每个步骤的规则组合为一个二维数组
    一维指定由什么规则组成，注意顺序，程序将会按顺序创建，按顺序执行。
    不同的规则组合可能存在一定的顺序关系。
    二维指定具体规则配置，由 [0.是否启用，1.描述，2.规则实现类名，3.规则传递参数(dict)]] 组成。
    注：所有规则类都必需继承自Rule类或Rule类的子类
    '''
    # 规则配置list下标描述变量。提高可读性与未来添加更多规则配置。
    g.cs_enabled,g.cs_name,g.cs_memo,g.cs_class_name,g.cs_param = range(5)

    # 0.是否启用，1.描述，2.规则实现类名，3.规则传递参数(dict)]
    period = 3  # 调仓频率
    # 配置 1.持仓股票的处理规则 (这里主要配置是否进行个股止损止盈)
    g.position_stock_config = [
        [False,'','个股止损',Stop_loss_stocks,{
            'period':period  # 调仓频率，日
            },],
        [False,'','个股止盈',Stop_profit_stocks,
            {'period':period ,  # 调仓频率，日
            }]
    ]

    # 配置 2.调仓条件判断规则
    g.adjust_condition_config = [
        [True,'','指数最高低价比值止损',Stop_loss_by_price,{
            'index':'000001.XSHG',  # 使用的指数,默认 '000001.XSHG'
             'day_count':160,  # 可选 取day_count天内的最高价，最低价。默认160
             'multiple':2.2  # 可选 最高价为最低价的multiple倍时，触 发清仓
            }],
        [True,'','指数三乌鸦止损',Stop_loss_by_3_black_crows,{
            'index':'000001.XSHG',  # 使用的指数,默认 '000001.XSHG'
             'dst_drop_minute_count':60,  # 可选，在三乌鸦触发情况下，一天之内有多少分钟涨幅<0,则触发止损，默认60分钟
            }],
        [False,'','_Stop_loss_by_growth_rate_','当日指数涨幅止损器',Stop_loss_by_growth_rate,{
            'index':'000001.XSHG',  # 使用的指数,默认 '000001.XSHG'
             'stop_loss_growth_rate':-0.05,
            }],
        [False,'','28实时止损',Stop_loss_by_28_index,{
                    'index2' : '000016.XSHG',       # 大盘指数
                    'index8' : '399333.XSHE',       # 小盘指数
                    'index_growth_rate': 0.01,      # 判定调仓的二八指数20日增幅
                    'dst_minute_count_28index_drop': 120 # 符合条件连续多少分钟则清仓
                }],
        [True,'','调仓时间',Time_condition,{
            'sell_hour': 14,  # 调仓时间,小时
            'sell_minute': 50,  # 调仓时间，分钟
            'buy_hour': 14,  # 调仓时间,小时
            'buy_minute': 50 # 调仓时间，分钟
            }],
        [True,'','28调仓择时',Index28_condition,{  # 该调仓条件可能会产生清仓行为
                'index2' : '000016.XSHG',  # 大盘指数
                'index8' : '399333.XSHE',  # 小盘指数
                'index_growth_rate': 0.01,  # 判定调仓的二八指数20日增幅
            }],
        [True,'','调仓日计数器',Period_condition,{
                'period' : period ,  # 调仓频率,日
            }],
    ]

    # 配置 3.Query选股规则
    g.pick_stock_by_query_config = [
        [False,'','选取小市值',Pick_small_cap,{}],
        [True,'','选取庄股',Pick_by_market_cap,{'mcap_limit':300}],
        [False,'','选取庄股（流通市值）',Pick_by_cir_market_cap,{'cir_mcap_limit':300}],
        # [False'',,'过滤PE',Filter_pe,{
        #     'pe_min':0                          # 最小PE
        #     ,'pe_max':200                       # 最大PE
        #     }],
        [True,'','过滤EPS',Filter_eps,{
            'eps_min':0  # 最小EPS
            }],
        [True,'','初选股票数量',Filter_limite,{
            'pick_stock_count':100  # 备选股票数目
            }]
    ]

    # 配置 4.股票池过滤规则
    g.filter_stock_list_config = [
        [True,'_filter_gem_','过滤创业板',Filter_gem,{}],
        [True,'','过滤ST',Filter_st,{}],
        [True,'','过滤停牌',Filter_paused_stock,{}],
        # [False,'','过滤次新股',Filter_new_stock,{'day_count':130}],
        [True,'','过滤涨停',Filter_limitup,{}],
        [True,'','过滤跌停',Filter_limitdown,{}],
        # [False,'','过滤n日增长率为负的股票',Filter_growth_is_down,{
        #     'day_count':20                      # 判断多少日内涨幅
        #     }],
        # [False,'','过滤黑名单',Filter_blacklist,{}],
        [False,'','庄股评分',Filter_cash_flow_rank,{'rank_stock_count':50}],
        [True,'','筹码分布评分',Filter_chip_density,{'rank_stock_count':50}],        
        [True,'','股票评分',Filter_rank,{
            'rank_stock_count': 20  # 评分股数
            }],
        [True,'','获取最终选股数',Filter_buy_count,{
            'buy_count': 3  # 最终入选股票数
            }],
    ]

    # 配置 5.调仓规则
    g.adjust_position_config = [
        [True,'','卖出股票',Sell_stocks,{}],
        [False,'','买入股票',Buy_stocks,{
            'buy_count': 4  # 最终买入股票数
            }],
        [False,'','按比重买入股票',Buy_stocks_portion,{'buy_count':3}],
        [True,'','VaR方式买入股票', Buy_stocks_var, {'buy_count': 3}]
    ]

    # 判断是否在模拟盘运行
    g.is_sim_trade = context.run_params.type == 'sim_trade'

    # 配置 6.其它规则
    g.other_config = [
        
        # [False,'trade_Xq','Xue Qiu Webtrader',XueQiu_order,{}],
        # 注意：Shipane_order 和 Shipane_sync_p 启用一个就行了。
        # 请配置正确的实盘易IP，端口，Key,client

        # 可通过 g.is_sim_trade 来控制回测时不启用，模拟盘才启用实盘易操作接口
        [False,'Shipane_order_moni','实盘易跟order下单',Shipane_order,{
            'host':'192.168.0.5',  # 实盘易IP
            'port':8888,  # 端口
            'key':'',  # 实盘易 key
            'client' : 'title:moni',  # 设置操作的券商,只有一个可以为''
            }],

        # [g.is_sim_trade,'_shipane_moni_','实盘易-对比持仓下单',Shipane_sync_p,{
        [False,'_shipane_moni_','实盘易-对比持仓下单',Shipane_sync_p,{
            'host':'192.168.0.5',  # 实盘易IP
            'port':8888,  # 端口
            'key':'',  # 实盘易 key
            'client' : 'title:moni',  # 设置操作的券商,只有一个可以为''
            'strong_op' : True,  # 设置是否为强力买卖模式,几十万以上建议开启。小资金无所谓，关闭效率高一点点
                }],

        # 通过实盘易自动申购新股
        [False,'_Purchase_new_stocks_','实盘易申购新股',Purchase_new_stocks,{
            'times':[[9,40]],  # 执行申购新股的时间
            'host':'192.168.0.5',  # 实盘易IP
            'port':8888,  # 端口
            'key':'',  # 实盘易 key
            'clients':['title:moni']  # 执行申购新股的券商标题list，可以写多个，
                }],

        [True,'','统计',Stat,{}]
    ]


# 创建一个规则执行器，并初始化一些通用事件
def create_rule(class_type,name,params,memo):
    obj = class_type(params)
    obj.name = name
    obj.on_open_position = open_position  # 买股
    obj.on_close_position = close_position  # 卖股
    obj.on_clear_position = clear_position  # 清仓
    obj.on_get_obj_by_class_type = get_obj_by_class_type  # 通过类名得到类的实例
    obj.memo = memo
    return obj

# 根据规则配置创建规则执行器
def create_rules(config):
    # config里 0.是否启用，1.描述，2.规则实现类名，3.规则传递参数(dict)]
    return [create_rule(c[g.cs_class_name],c[g.cs_name],c[g.cs_param],c[g.cs_memo]) for c in config if c[g.cs_enabled]]



# 1 设置参数
def set_params():
    # 设置基准收益
    set_benchmark('000300.XSHG')


# 2 设置中间变量
def set_variables(context):
    # 设置 VaR 仓位控制参数。风险敞口: 0.05,
    # 正态分布概率表，标准差倍数以及置信率: 0.96, 95%; 2.06, 96%; 2.18, 97%; 2.34, 98%; 2.58, 99%; 5, 99.9999%
    # 赋闲资金可以买卖银华日利做现金管理: ['511880.XSHG']
    set_slip_fee(context)
    context.pc_var = PositionControlVar(context, 0.07, 2.18, [])


# 3 设置回测条件
def set_backtest():
    set_option('use_real_price', True)  # 用真实价格交易
    log.set_level('order', 'error')
    log.set_level('strategy', 'info')


def initialize(context):
    log.info("==> initialize @ %s" % (str(context.current_dt)))
    try:
        set_params()  # 1设置策略参数
        set_variables(context)  # 2设置中间变量
        set_backtest()  # 3设置回测条件
        # set_commission(PerTrade(buy_cost=0.0003,sell_cost=0.0013,min_cost=5))
        # set_benchmark('000300.XSHG')
        # set_option('use_real_price',True)
        # log.set_level('order','error')
    except:
        pass
    # 判定是否是模拟盘状态
    g.is_sim_trade = context.run_params.type == 'sim_trade'

    select_strategy(context)
    '''-----1.持仓股票的处理规则:-----'''
    g.position_stock_rules = create_rules(g.position_stock_config)

    '''-----2.调仓条件判断规则:-----'''
    g.adjust_condition_rules = create_rules(g.adjust_condition_config)

    '''-----3.Query选股规则:-----'''
    g.pick_stock_by_query_rules = create_rules(g.pick_stock_by_query_config)

    '''-----4.股票池过滤规则:-----'''
    g.filter_stock_list_rules = create_rules(g.filter_stock_list_config)

    '''-----5.调仓规则:器-----'''
    g.adjust_position_rules = create_rules(g.adjust_position_config)

    '''-----6.其它规则:-------'''
    g.other_rules = create_rules(g.other_config)

    # 把所有规则合并排重生成一个总的规则收录器。以方便各处共同调用的
    g.all_rules = list(set(g.position_stock_rules
            + g.adjust_condition_rules
            + g.pick_stock_by_query_rules
            + g.filter_stock_list_rules
            + g.adjust_position_rules
            + g.other_rules
        ))

    for rule in g.all_rules:
        rule.initialize(context)

    # 打印规则参数
    log_param()

# 按分钟回测
def handle_data(context,data):
    # 执行其它辅助规则
    for rule in g.other_rules:
        rule.handle_data(context,data)

    # 持仓股票动作的执行,目前为个股止损止盈
    for rule in g.position_stock_rules:
        rule.handle_data(context,data)

    # ----------这部分当前本策略其实并没有啥用，扩展用--------------
    # 这里执行选股器调仓器的handle_data主要是为了扩展某些选股方式可能需要提前处理数据。
    # 举例：动态获取黑名单，可以调仓前一段时间先执行。28小市值规则这里都是空动作。
    for rule in g.pick_stock_by_query_rules:
        rule.handle_data(context,data)

    for rule in g.filter_stock_list_rules:
        rule.handle_data(context,data)

    # 调仓器的分钟处理
    for rule in g.adjust_position_rules:
        rule.handle_data(context,data)
    # -----------------------------------------------------------

    # 判断是否满足调仓条件，所有规则以and 逻辑执行
    for rule in g.adjust_condition_rules:
        rule.handle_data(context,data)
        if not rule.can_adjust:
            return
    # ---------------------调仓--------------------------
    log.info("handle_data: ==> 满足条件进行调仓")
    # 调仓前预处理
    for rule in g.all_rules:
        rule.before_adjust_start(context,data)

    # Query 选股
    q = None
    for rule in g.pick_stock_by_query_rules:
        q = rule.filter(context,data,q)

    # 过滤股票列表
    stock_list = list(get_fundamentals(q)['code']) if q != None else []
    for rule in g.filter_stock_list_rules:
        stock_list = rule.filter(context,data,stock_list)

    log.info("handle_data: 选股后可买股票: %s" % (stock_list))

    # 执行调仓
    for rule in g.adjust_position_rules:
        rule.adjust(context,data,stock_list)

    # 调仓后处理
    for rule in g.all_rules:
        rule.after_adjust_end(context,data)
    # ----------------------------------------------------

# 开盘
def before_trading_start(context):
    log.info("==========================================================================")
    for rule in g.all_rules:
        rule.before_trading_start(context)

# 收盘
def after_trading_end(context):
    for rule in g.all_rules:
        rule.after_trading_end(context)

    # 得到当前未完成订单
    orders = get_open_orders()
    for _order in orders.values():
        log.info("canceled uncompleted order: %s" % (_order.order_id))

# 进程启动(一天一次)
def process_initialize(context):
    # 这里Try一下，防止更新代码时出错。
    try:
        for rule in g.all_rules:
            rule.process_initialize(context)
    except:
        pass

# 这里示例进行模拟更改回测时，如何调整策略,基本通用代码。
def after_code_changed(context):
    try:
        g.all_rules
    except:
        print '原先非面向对象策略代码，重新初始化'
        initialize(context)
        return

    print '更新代码：'
    # 调整策略通用实例代码
    # 获取新策略
    select_strategy(context)
    # 按新策略顺序重整规则列表，如果对象之前存在，则移到新列表，不存在则新建。
    # 不管之前旧的规则列表是什么顺序，一率按新列表重新整理。
    def check_chang(rules,config):
        nl = []
        for c in config:
        # 按顺序循环处理新规则
            if not c[g.cs_enabled]:  # 不使用则跳过
                continue
            # 查找旧规则是否存在
            find_old = None
            for old_r in rules:
                if old_r.__class__ == c[g.cs_class_name] and old_r.name == c[g.cs_name]:
                    find_old = old_r
                    break
            if find_old != None:
                # 旧规则存在则添加到新列表中,并调用规则的更新函数，更新参数。
                nl.append(find_old)
                find_old.update_params(context,c[g.cs_param])
            else:
                # 旧规则不存在，则创建并添加
                new_r = create_rule(c[g.cs_class_name],c[g.cs_name],c[g.cs_param],c[g.cs_mome])
                nl.append(new_r)
                # 调用初始化时该执行的函数
                rule.initialize(context)
        return nl

    # 重整所有规则
    g.position_stock_rules = check_chang(g.position_stock_rules,g.position_stock_config)
    g.adjust_condition_rules = check_chang(g.adjust_condition_rules,g.adjust_condition_config)
    g.pick_stock_by_query_rules = check_chang(g.pick_stock_by_query_rules,g.pick_stock_by_query_config)
    g.filter_stock_list_rules = check_chang(g.filter_stock_list_rules,g.filter_stock_list_config)
    g.adjust_position_rules = check_chang(g.adjust_position_rules,g.adjust_position_config)
    g.other_rules = check_chang(g.other_rules,g.other_config)

    # 重新生成所有规则的list
    g.all_rules = list(set(
            g.position_stock_rules
            + g.adjust_condition_rules
            + g.pick_stock_by_query_rules
            + g.filter_stock_list_rules
            + g.adjust_position_rules
            + g.other_rules
        ))
    log_param()

# 显示策略组成
def log_param():
    def get_rules_str(rules):
        return '\n'.join(['   %d.%s ' % (i + 1,str(r)) for i,r in enumerate(rules)]) + '\n'
    s = '\n---------------------策略一览：规则组合与参数----------------------------\n'
    s += '一、持仓股票的处理规则:\n' + get_rules_str(g.position_stock_rules)
    s += '二、调仓条件判断规则:\n' + get_rules_str(g.adjust_condition_rules)
    s += '三、Query选股规则:\n' + get_rules_str(g.pick_stock_by_query_rules)
    s += '四、股票池过滤规则:\n' + get_rules_str(g.filter_stock_list_rules)
    s += '五、调仓规则:\n' + get_rules_str(g.adjust_position_rules)
    s += '六、其它规则:\n' + get_rules_str(g.other_rules)
    s += '--------------------------------------------------------------------------'
    print s

''' ==============================持仓操作函数，共用================================'''
# 开仓，买入指定价值的证券
# 报单成功并成交（包括全部成交或部分成交，此时成交量大于0），返回True
# 报单失败或者报单成功但被取消（此时成交量等于0），返回False
# 报单成功，触发所有规则的when_buy_stock函数
def open_position(sender,security,value):
    order = order_target_value_(sender,security,value)
    if order != None and order.filled > 0:
        for rule in g.all_rules:
            rule.when_buy_stock(security,order)
        return True
    return False

# 平仓，卖出指定持仓
# 平仓成功并全部成交，返回True
# 报单失败或者报单成功但被取消（此时成交量等于0），或者报单非全部成交，返回False
# 报单成功，触发所有规则的when_sell_stock函数
def close_position(sender,position,is_normal=True):
    security = position.security
    order = order_target_value_(sender,security,0)  # 可能会因停牌失败
    if order != None:
        if order.filled > 0:
            for rule in g.all_rules:
                rule.when_sell_stock(position,order,is_normal)
            return True
    return False

# 清空卖出所有持仓
# 清仓时，调用所有规则的 when_clear_position
def clear_position(sender,context):
    if context.portfolio.positions:
        sender.log_info("==> 清仓，卖出所有股票")
        for stock in context.portfolio.positions.keys():
            position = context.portfolio.positions[stock]
            close_position(sender,position,False)
    for rule in g.all_rules:
        rule.when_clear_position(context)

# 自定义下单
# 根据Joinquant文档，当前报单函数都是阻塞执行，报单函数（如order_target_value）返回即表示报单完成
# 报单成功返回报单（不代表一定会成交），否则返回None
def order_target_value_(sender,security,value):
    if value == 0:
        sender.log_debug("Selling out %s" % (security))
    else:
        sender.log_debug("Order %s to value %f" % (security,value))

    # 如果股票停牌，创建报单会失败，order_target_value 返回None
    # 如果股票涨跌停，创建报单会成功，order_target_value 返回Order，但是报单会取消
    # 部成部撤的报单，聚宽状态是已撤，此时成交量>0，可通过成交量判断是否有成交
    return order_target_value(security,value)

# 通过类的类型得到已创建的对象实例
def get_obj_by_class_type(class_type):
    for rule in g.all_rules:
        if rule.__class__ == class_type:
            return rule
''' ==============================规则基类================================'''
class Rule(object):
    # 持仓操作的事件
    on_open_position = None  # 买股调用外部函数
    on_close_position = None  # 卖股调用外部函数
    on_clear_position = None  # 清仓调用外部函数
    on_get_obj_by_class_type = None  # 通过类的类型查找已创建的类的实例
    memo = ''  # 对象简要说明
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
    # 卖出股票时调用的函数
    # is_normail正常规则卖出为True，止损卖出为False
    def when_sell_stock(self,position,order,is_normal):
        pass
    # 买入股票时调用的函数
    def when_buy_stock(self,stock,order):
        pass
    # 清仓时调用的函数
    def when_clear_position(self,context):
        pass
    # 调仓前调用
    def before_adjust_start(self,context,data):
        pass
    # 调仓后调用用
    def after_adjust_end(slef,context,data):
        pass
    # 更改参数
    def update_params(self,context,params):
        pass

    # 持仓操作事件的简单判断处理，方便使用。
    def open_position(self,security,value):
        if self.on_open_position != None:
            return self.on_open_position(self,security,value)
    def close_position(self,position,is_normal=True):
        if self.on_close_position != None:
            return self.on_close_position(self,position,is_normal=True)
    def clear_position(self,context):
        if self.on_clear_position != None:
            self.on_clear_position(self,context)
    # 通过类的类型获取已创建的类的实例对象
    # 示例 obj = get_obj_by_class_type(Index28_condition)
    def get_obj_by_class_type(self,class_type):
        if self.on_get_obj_by_class_type != None:
            return self.on_get_obj_by_class_type(class_type)
        else:
            return None
    # 为日志显示带上是哪个规则器输出的
    def log_info(self,msg):
        log.info('%s: %s' % (self.memo,msg))
    def log_warn(self,msg):
        log.warn('%s: %s' % (self.memo,msg))
    def log_debug(self,msg):
        log.debug('%s: %s' % (self.memo,msg))
    def log_error(self,msg):
        log.error('%s: %s' % (self.memo,msg))

'''==============================调仓条件判断器基类=============================='''
class Adjust_condition(Rule):
    # 返回能否进行调仓
    @property
    def can_adjust(self):
        return True

'''==============================选股 query过滤器基类=============================='''
class Filter_query(Rule):
    def filter(self,context,data,q):
        return None
'''==============================选股 stock_list过滤器基类=============================='''
class Filter_stock_list(Rule):
    def filter(self,context,data,stock_list):
        return None
'''==============================调仓的操作基类=============================='''
class Adjust_position(Rule):
    def adjust(self,context,data,buy_stocks):
        pass

'''-------------------------调仓时间控制器-----------------------'''
# class Time_condition(Adjust_condition):
#     def __init__(self,params):
#         # 配置调仓时间（24小时分钟制）
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
#         return '调仓时间控制器: [调仓时间: %s ]' % (
#                 str(['%d:%d' % (x[0],x[1]) for x in self.times]))
                
class Time_condition(Adjust_condition):
    """调仓时间控制器"""

    def __init__(self, params):
        # 配置调仓时间（24小时分钟制）
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
        return '调仓时间控制器: [卖出时间: %d:%d] [买入时间: %d:%d]' % (
            self.sell_hour, self.sell_minute, self.buy_hour, self.buy_minute)

'''-------------------------调仓日计数器-----------------------'''
class Period_condition(Adjust_condition):
    def __init__(self,params):
        # 调仓日计数器，单位：日
        self.period = params.get('period',3)
        self.day_count = 0
        self.t_can_adjust = False

    def update_params(self,context,params):
        self.period = params.get('period',self.period)

    @property
    def can_adjust(self):
        return self.t_can_adjust

    def handle_data(self,context,data):
        self.log_info("调仓日计数 [%d]" % (self.day_count))
        self.t_can_adjust = self.day_count % self.period == 0
        self.day_count += 1
        pass

    def before_trading_start(self,context):
        self.t_can_adjust = False
        pass
    def when_sell_stock(self,position,order,is_normal):
        if not is_normal:
            # 个股止损止盈时，即非正常卖股时，重置计数，原策略是这么写的
            self.day_count = 0
        pass
    # 清仓时调用的函数
    def when_clear_position(self,context):
        self.day_count = 0
        pass

    def __str__(self):
        return '调仓日计数器:[调仓频率: %d日] [调仓日计数 %d]' % (
                self.period,self.day_count)
'''-------------------------28指数涨幅调仓判断器----------------------'''
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
        # 回看指数前20天的涨幅
        gr_index2 = get_growth_rate(self.index2)
        gr_index8 = get_growth_rate(self.index8)
        self.log_info("当前%s指数的20日涨幅 [%.2f%%]" % (get_security_info(self.index2).display_name,gr_index2 * 100))
        self.log_info("当前%s指数的20日涨幅 [%.2f%%]" % (get_security_info(self.index8).display_name,gr_index8 * 100))
        if gr_index2 <= self.index_growth_rate and gr_index8 <= self.index_growth_rate:
            self.clear_position(context)
            self.t_can_adjust = False
        else:
            self.t_can_adjust = True
        pass

    def before_trading_start(self,context):
        pass

    def __str__(self):
        return '28指数择时:[大盘指数:%s %s] [小盘指数:%s %s] [判定调仓的二八指数20日增幅 %.2f%%]' % (
                self.index2,get_security_info(self.index2).display_name,
                self.index8,get_security_info(self.index8).display_name,
                self.index_growth_rate * 100)

'''------------------小市值选股器-----------------'''
class Pick_small_cap(Filter_query):
    def filter(self,context,data,q):
        return query(valuation).order_by(valuation.market_cap.asc())
    def __str__(self):
        return '按市值倒序选取股票'

class Pick_by_market_cap(Filter_query):
    def __init__(self,params):
        self.mcap_limit = params.get('mcap_limit',300)
    def filter(self, context, data,q):
        return query(valuation).filter(valuation.market_cap<=self.mcap_limit).order_by(valuation.market_cap.asc())
    def __str__(self):
        return '按市值区域倒序选取股票: [ market_cap < %d ]' % self.mcap_limit
        
class Pick_by_cir_market_cap(Filter_query):
    def __init__(self,params):
        self.cir_mcap_limit = params.get('cir_mcap_limit',200)
    def filter(self, context, data,q):
        return query(valuation).filter(valuation.circulating_market_cap<=self.cir_mcap_limit,
                                        valuation.circulating_market_cap>50).order_by(valuation.circulating_market_cap.asc())
    def __str__(self):
        return '按流通市值区域倒序选取股票: [ cir_market_cap < %d ]' % self.cir_mcap_limit    

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
        return '根据PE范围选取股票： [ %d < pe < %d]' % (self.pe_min,self.pe_max)

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
        return '根据EPS范围选取股票： [ %d < eps ]' % (self.eps_min)

class Filter_limite(Filter_query):
    def __init__(self,params):
        self.pick_stock_count = params.get('pick_stock_count',0)
    def update_params(self,context,params):
        self.pick_stock_count = params.get('pick_stock_count',self.pick_stock_count)
    def filter(self,context,data,q):
        return q.limit(self.pick_stock_count)
    def __str__(self):
        return '初选股票数量: %d' % (self.pick_stock_count)

class Filter_gem(Filter_stock_list):
    def filter(self,context,data,stock_list):
        return [stock for stock in stock_list if stock[0:3] != '300']
    def __str__(self):
        return '过滤创业板股票'

class Filter_paused_stock(Filter_stock_list):
    def filter(self,context,data,stock_list):
        current_data = get_current_data()
        return [stock for stock in stock_list if not current_data[stock].paused]
    def __str__(self):
        return '过滤停牌股票'

class Filter_limitup(Filter_stock_list):
    def filter(self,context,data,stock_list):
        threshold = 1.00
        return [stock for stock in stock_list if stock in context.portfolio.positions.keys()
            or data[stock].close < data[stock].high_limit * threshold]
    def __str__(self):
        return '过滤涨停股票'

class Filter_limitdown(Filter_stock_list):
    def filter(self,context,data,stock_list):
        threshold = 1.00
        return [stock for stock in stock_list if stock in context.portfolio.positions.keys()
            or data[stock].close > data[stock].low_limit * threshold]
    def __str__(self):
        return '过滤跌停股票'

class Filter_old_stock(Filter_stock_list):
    def __init__(self,params):
        self.day_count = params.get('day_count',365)
    def update_params(self,context,params):
        self.day_count = params.get('day_count',self.day_count)
    def filter(self,context,data,stock_list):
        tmpList = []
        for stock in stock_list :
            days_public = (context.current_dt.date() - get_security_info(stock).start_date).days
            # 上市未超过1年
            if days_public < self.day_count:
                tmpList.append(stock)
        return tmpList
    def __str__(self):
        return '过滤上市时间超过 %d 天的股票' % (self.day_count)

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
        return '过滤上市时间未超过 %d 天的次新股' % (self.day_count)

class Filter_st(Filter_stock_list):
    def filter(self,context,data,stock_list):
        current_data = get_current_data()
        return [stock for stock in stock_list
            if not current_data[stock].is_st
            and not current_data[stock].name.startswith('退')]
    def __str__(self):
        return '过滤ST股票'

class Filter_growth_is_down(Filter_stock_list):
    def __init__(self,params):
        self.day_count = params.get('day_count',20)
    def update_params(self,context,params):
        self.day_count = params.get('day_count',self.day_count)
    def filter(self,context,data,stock_list):
        return [stock for stock in stock_list if get_growth_rate(stock,self.day_count) > 0]
    def __str__(self):
        return '过滤n日增长率为负的股票'

class Filter_blacklist(Filter_stock_list):
    def __get_blacklist(self):
        # 黑名单一览表，更新时间 2016.7.10 by 沙米
        # 科恒股份、太空板业，一旦2016年继续亏损，直接面临暂停上市风险
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
        return '过滤黑名单股票'

class Filter_cash_flow_rank(Filter_stock_list):
    def __init__(self,params):
        self.rank_stock_count = params.get('rank_stock_count',300)
    def update_params(self,context,params):
        self.rank_stock_count = params.get('self.rank_stock_count',self.rank_stock_count)
    def __str__(self):
        return '庄股评分排序 [评分股数] %d' % self.rank_stock_count    
    def filter(self, context, data, stock_list):
        df = cow_stock_value(stock_list[:self.rank_stock_count], score_threthold=0)
        return df.index

class Filter_chip_density(Filter_stock_list):
    def __init__(self,params):
        self.rank_stock_count = params.get('rank_stock_chip_density',50)
    def update_params(self,context,params):
        self.rank_stock_count = params.get('self.rank_stock_count',self.rank_stock_count)
    def __str__(self):
        return '筹码分布评分排序 [评分股数] %d' % self.rank_stock_count  
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
        return '股票评分排序 [评分股数: %d ]' % (self.rank_stock_count)

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
        return '获取最终待购买股票数:[ %d ]' % (self.buy_count)

'''---------------卖出股票规则--------------'''
class Sell_stocks(Adjust_position):
    def adjust(self,context,data,buy_stocks):
        # 卖出不在待买股票列表中的股票
        # 对于因停牌等原因没有卖出的股票则继续持有
        for stock in context.portfolio.positions.keys():
            if stock not in buy_stocks:
                self.log_info("stock [%s] in position is not buyable" % (stock))
                position = context.portfolio.positions[stock]
                self.close_position(position)
            else:
                self.log_info("stock [%s] is already in position" % (stock))
    def __str__(self):
        return '股票调仓卖出规则：卖出不在buy_stocks的股票'

'''---------------买入股票规则--------------'''
class Buy_stocks(Adjust_position):
    def __init__(self,params):
        self.buy_count = params.get('buy_count',3)
    def update_params(self,context,params):
        self.buy_count = params.get('buy_count',self.buy_count)
    def adjust(self,context,data,buy_stocks):
        # 买入股票
        # 始终保持持仓数目为g.buy_stock_count
        # 根据股票数量分仓
        # 此处只根据可用金额平均分配购买，不能保证每个仓位平均分配
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
        return '股票调仓买入规则：现金平分式买入股票达目标股票数'

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
        # 买入股票
        # 始终保持持仓数目为g.buy_stock_count
        # 根据股票数量分仓
        # 此处只根据可用金额平均分配购买，不能保证每个仓位平均分配
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
        return '股票调仓买入规则：现金比重式买入股票达目标股票数'    

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
    """使用 VaR 方法做调仓控制"""

    def __init__(self, params):
        self.buy_count = params.get('buy_count', 3)

    def update_params(self, context, params):
        self.buy_count = params.get('buy_count', self.buy_count)

    def adjust(self, context, data, buy_stocks):
        if not context.flags_can_buy:
            self.log_warn('无法执行买入!! context.flags_can_buy 未开启')
            return
        # 买入股票或者进行调仓
        # 始终保持持仓数目为g.buy_stock_count
        position_count = len(context.portfolio.positions)
        if self.buy_count > position_count:
            buy_num = self.buy_count - position_count
            context.pc_var.buy_the_stocks(context, buy_stocks[:buy_num])
        else:
            context.pc_var.func_rebalance(context)
        pass

    def __str__(self):
        return '股票调仓买入规则：使用 VaR 方式买入或者调整股票达目标股票数'

# 剔除上市时间较短的基金产品
def delete_new_moneyfund(context, equity, deltaday):
    deltaDate = context.current_dt.date() - datetime.timedelta(deltaday)

    tmpList = []
    for stock in equity:
        if get_security_info(stock).start_date < deltaDate:
            tmpList.append(stock)

    return tmpList


'''---------------个股止损--------------'''
class Stop_loss_stocks(Rule):
    # get_period_func 为获取period的函数,无传入参数，传出参数为period
    # on_close_position_func 卖出股票时触发的事件，传入参数为 stock,无返回
    def __init__(self,params):
        self.last_high = {}
        self.period = params.get('period',3)
        self.pct_change = {}
    def update_params(self,context,params):
        self.period = params.get('period',self.period)
    # 个股止损
    def handle_data(self,context,data):
        for stock in context.portfolio.positions.keys():
            cur_price = data[stock].close
            xi = attribute_history(stock,2,'1d','high',skip_paused=True)
            ma = xi.max()
            if self.last_high[stock] < cur_price:
                self.last_high[stock] = cur_price

            threshold = self.__get_stop_loss_threshold(stock,self.period)
            # log.debug("个股止损阈值, stock: %s, threshold: %f" %(stock, threshold))
            if cur_price < self.last_high[stock] * (1 - threshold):
                self.log_info("==> 个股止损, stock: %s, cur_price: %f, last_high: %f, threshold: %f"
                    % (stock,cur_price,self.last_high[stock],threshold))

                position = context.portfolio.positions[stock]
                self.close_position(position,False)

    # 获取个股前n天的m日增幅值序列
    # 增加缓存避免当日多次获取数据
    def __get_pct_change(self,security,n,m):
        pct_change = None
        if security in self.pct_change.keys():
            pct_change = self.pct_change[security]
        else:
            h = attribute_history(security,n,unit='1d',fields=('close'),skip_paused=True)
            pct_change = h['close'].pct_change(m)  # 3日的百分比变比（即3日涨跌幅）
            self.pct_change[security] = pct_change
        return pct_change

    # 计算个股回撤止损阈值
    # 即个股在持仓n天内能承受的最大跌幅
    # 算法：(个股250天内最大的n日跌幅 + 个股250天内平均的n日跌幅)/2
    # 返回正值
    def __get_stop_loss_threshold(self,security,n=3):
        pct_change = self.__get_pct_change(security,250,n)
        # log.debug("pct of security [%s]: %s", pct)
        maxd = pct_change.min()
        # maxd = pct[pct<0].min()
        avgd = pct_change.mean()
        # avgd = pct[pct<0].mean()
        # maxd和avgd可能为正，表示这段时间内一直在增长，比如新股
        bstd = (maxd + avgd) / 2

        # 数据不足时，计算的bstd为nan
        if not isnan(bstd):
            if bstd != 0:
                return abs(bstd)
            else:
                # bstd = 0，则 maxd <= 0
                if maxd < 0:
                    # 此时取最大跌幅
                    return abs(maxd)

        return 0.099  # 默认配置回测止损阈值最大跌幅为-9.9%，阈值高貌似回撤降低

    def when_sell_stock(self,position,order,is_normal):
        if position.security in self.last_high:
            self.last_high.pop(position.security)
        pass

    def when_buy_stock(self,stock,order):
        if order.status == OrderStatus.held and order.filled == order.amount:
            # 全部成交则删除相关证券的最高价缓存
            self.last_high[stock] = get_close_price(stock,1,'1m')
        pass

    def after_trading_end(self,context):
        self.pct_change = {}
        pass

    def __str__(self):
        return '个股止损器:[当前缓存价格数: %d ]' % (len(self.last_high))

''' ----------------------个股止盈------------------------------'''
class Stop_profit_stocks(Rule):
    def __init__(self,params):
        self.last_high = {}
        self.period = params.get('period',3)
        self.pct_change = {}
    def update_params(self,context,params):
        self.period = params.get('period',self.period)
    # 个股止盈
    def handle_data(self,context,data):
        for stock in context.portfolio.positions.keys():
                position = context.portfolio.positions[stock]
                cur_price = data[stock].close
                threshold = self.__get_stop_profit_threshold(stock,self.period)
                # log.debug("个股止盈阈值, stock: %s, threshold: %f" %(stock, threshold))
                if cur_price > position.avg_cost * (1 + threshold):
                    self.log_info("==> 个股止盈, stock: %s, cur_price: %f, avg_cost: %f, threshold: %f"
                        % (stock,cur_price,self.last_high[stock],threshold))

                    position = context.portfolio.positions[stock]
                    self.close_position(position,False)

    # 获取个股前n天的m日增幅值序列
    # 增加缓存避免当日多次获取数据
    def __get_pct_change(self,security,n,m):
        pct_change = None
        if security in self.pct_change.keys():
            pct_change = self.pct_change[security]
        else:
            h = attribute_history(security,n,unit='1d',fields=('close'),skip_paused=True)
            pct_change = h['close'].pct_change(m)  # 3日的百分比变比（即3日涨跌幅）
            self.pct_change[security] = pct_change
        return pct_change

    # 计算个股止盈阈值
    # 算法：个股250天内最大的n日涨幅
    # 返回正值
    def __get_stop_profit_threshold(self,security,n=3):
        pct_change = self.__get_pct_change(security,250,n)
        maxr = pct_change.max()

        # 数据不足时，计算的maxr为nan
        # 理论上maxr可能为负
        if (not isnan(maxr)) and maxr != 0:
            return abs(maxr)
        return 0.30  # 默认配置止盈阈值最大涨幅为30%

    def when_sell_stock(self,position,order,is_normal):
        if order.status == OrderStatus.held and order.filled == order.amount:
            # 全部成交则删除相关证券的最高价缓存
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
        return '个股止盈器:[当前缓存价格数: %d ]' % (len(self.last_high))

''' ----------------------最高价最低价比例止损------------------------------'''
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
        # 大盘指数前130日内最高价超过最低价2倍，则清仓止损
        # 基于历史数据判定，因此若状态满足，则当天都不会变化
        # 增加此止损，回撤降低，收益降低

        if not self.is_day_stop_loss_by_price:
            h = attribute_history(self.index,self.day_count,unit='1d',fields=('close','high','low'),skip_paused=True)
            low_price_130 = h.low.min()
            high_price_130 = h.high.max()
            if high_price_130 > self.multiple * low_price_130 and h['close'][-1] < h['close'][-4] * 1 and  h['close'][-1] > h['close'][-100]:
                # 当日第一次输出日志
                self.log_info("==> 大盘止损，%s指数前130日内最高价超过最低价2倍, 最高价: %f, 最低价: %f" % (get_security_info(self.index).display_name,high_price_130,low_price_130))
                self.is_day_stop_loss_by_price = True

        if self.is_day_stop_loss_by_price:
            self.clear_position(context)

    def before_trading_start(self,context):
        self.is_day_stop_loss_by_price = False
        pass
    def __str__(self):
        return '大盘高低价比例止损器:[指数: %s] [参数: %s日内最高最低价: %s倍] [当前状态: %s]' % (
                self.index,self.day_count,self.multiple,self.is_day_stop_loss_by_price)

    @property
    def can_adjust(self):
        return not self.is_day_stop_loss_by_price

''' ----------------------最高价最低价比例止损------------------------------'''
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
            self.log_warn('当日涨幅 [%s : %.2f%%] 低于阀值 %.2f%%,清仓止损!' % (self.index,
                cur_growth_rate * 100,self.stop_loss_growth_rate))
            self.to_stop_loss = True
            self.clear_position(context)
            return
        self.to_stop_loss = False

    def before_trading_start(self,context):
        self.to_stop_loss = False

    def __str__(self):
        return '指数当日涨幅限制止损器:[指数: %s] [最低涨幅: %.2f%%]' % (
                self.index,self.stop_loss_growth_rate * 100)

    @property
    def can_adjust(self):
        return not self.to_stop_loss

''' ----------------------三乌鸦止损------------------------------'''
class Stop_loss_by_3_black_crows(Adjust_condition):
    def __init__(self,params):
        self.index = params.get('index','000001.XSHG')
        self.dst_drop_minute_count = params.get('dst_drop_minute_count',60)
        # 临时参数
        self.is_last_day_3_black_crows = False
        self.t_can_adjust = True
        self.cur_drop_minute_count = 0
    def update_params(self,context,params):
        self.index = params.get('index',self.index)
        self.dst_drop_minute_count = params.get('dst_drop_minute_count',self.dst_drop_minute_count)

    def initialize(self,context):
        pass

    def handle_data(self,context,data):
        # 前日三黑鸦，累计当日每分钟涨幅<0的分钟计数
        # 如果分钟计数超过一定值，则开始进行三黑鸦止损
        # 避免无效三黑鸦乱止损
        if self.is_last_day_3_black_crows:
            if get_growth_rate(self.index,1) < 0:
                self.cur_drop_minute_count += 1

            if self.cur_drop_minute_count >= self.dst_drop_minute_count:
                if self.cur_drop_minute_count == self.dst_drop_minute_count:
                    self.log_info("==> 超过三黑鸦止损开始")

                self.clear_position(context)
                self.t_can_adjust = False
        else:
            self.t_can_adjust = True
        pass

    def before_trading_start(self,context):
        self.is_last_day_3_black_crows = is_3_black_crows(self.index)
        if self.is_last_day_3_black_crows:
            self.log_info("==> 前4日已经构成三黑鸦形态")
        pass

    def after_trading_end(self,context):
        self.is_last_day_3_black_crows = False
        self.cur_drop_minute_count = 0
        pass

    def __str__(self):
        return '大盘三乌鸦止损器:[指数: %s] [跌计数分钟: %d] [当前状态: %s]' % (
            self.index,self.dst_drop_minute_count,self.is_last_day_3_black_crows)

    @property
    def can_adjust(self):
        return self.t_can_adjust

''' ----------------------28指数值实时进行止损------------------------------'''
class Stop_loss_by_28_index(Adjust_condition):
    def __init__(self,params):
        self.index2 = params.get('index2','')
        self.index8 = params.get('index8','')
        self.index_growth_rate = params.get('index_growth_rate',0.01)
        self.dst_minute_count_28index_drop = params.get('dst_minute_count_28index_drop',120)
        # 临时参数
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
        # 回看指数前20天的涨幅
        gr_index2 = get_growth_rate(self.index2)
        gr_index8 = get_growth_rate(self.index8)

        if gr_index2 <= self.index_growth_rate and gr_index8 <= self.index_growth_rate:
            if (self.minute_count_28index_drop == 0):
                self.log_info("当前二八指数的20日涨幅同时低于[%.2f%%], %s指数: [%.2f%%], %s指数: [%.2f%%]" \
                    % (self.index_growth_rate * 100,
                    get_security_info(self.index2).display_name,
                    gr_index2 * 100,
                    get_security_info(self.index8).display_name,
                    gr_index8 * 100))

            self.minute_count_28index_drop += 1
        else:
            # 不连续状态归零
            if self.minute_count_28index_drop < self.dst_minute_count_28index_drop:
                self.minute_count_28index_drop = 0

        if self.minute_count_28index_drop >= self.dst_minute_count_28index_drop:
            if self.minute_count_28index_drop == self.dst_minute_count_28index_drop:
                self.log_info("==> 当日%s指数和%s指数的20日增幅低于[%.2f%%]已超过%d分钟，执行28指数止损" \
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
        return '28指数值实时进行止损:[大盘指数: %s %s] [小盘指数: %s %s] [判定调仓的二八指数20日增幅 %.2f%%] [连续 %d 分钟则清仓] ' % (
                self.index2,get_security_info(self.index2).display_name,
                self.index8,get_security_info(self.index8).display_name,
                self.index_growth_rate * 100,
                self.dst_minute_count_28index_drop)

    @property
    def can_adjust(self):
        return self.t_can_adjust

''' ----------------------统计类----------------------------'''
class Stat(Rule):
    def __init__(self,params):
        # 加载统计模块
        self.trade_total_count = 0
        self.trade_success_count = 0
        self.statis = {'win': [],'loss': []}

    def after_trading_end(self,context):
        self.report(context)
    def when_sell_stock(self,position,order,is_normal):
        if order.filled > 0:
            # 只要有成交，无论全部成交还是部分成交，则统计盈亏
            self.watch(position.security,order.filled,position.avg_cost,position.price)

    def reset(self):
        self.trade_total_count = 0
        self.trade_success_count = 0
        self.statis = {'win': [],'loss': []}

    # 记录交易次数便于统计胜率
    # 卖出成功后针对卖出的量进行盈亏统计
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
        self.log_info("收盘后持仓概况:%s" % str(list(context.portfolio.positions)))
        self.log_info("仓位概况:%.2f" % position)
        self.print_win_rate(context.current_dt.strftime("%Y-%m-%d"),context.current_dt.strftime("%Y-%m-%d"),context)

    # 打印胜率
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

            s = '\n------------绩效报表------------'
            s += '\n交易次数: {0}, 盈利次数: {1}, 胜率: {2}'.format(self.trade_total_count,self.trade_success_count,str(win_rate * 100) + str('%'))
            s += '\n单次盈利最高: {0}, 盈利比例: {1}%'.format(most_win['stock'],most_win['value'])
            s += '\n单次亏损最高: {0}, 亏损比例: {1}%'.format(most_loss['stock'],most_loss['value'])
            s += '\n总资产: {0}, 本金: {1}, 盈利: {2}, 盈亏比率：{3}%'.format(starting_cash + total_profit,starting_cash,total_profit,total_profit / starting_cash * 100)
            s += '\n--------------------------------'
            self.log_info(s)

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
    def statis_total_profit(self,context):
        return context.portfolio.portfolio_value - context.portfolio.starting_cash
    def __str__(self):
        return '策略绩效统计'

'''-------------------实盘易对接-----------------------'''
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

    # 调仓后调用
    def after_adjust_end(self,context,data):
        self.__sync_position(context)
    # 清仓时调用的函数
    def when_clear_position(self,context):
        self.__sync_position(context)

    def __sync_position(self,context):
        try:
            client = shipane_sdk.Client(shipane_sdk._Logger(),key=self.key,host=self.host,port=self.port)
            op_count = 2 if self.strong_op else 1
            # 强力买卖条件下,卖两次股,防止五档都没卖掉,扫两次五档没卖完就算了吧
            for i in range(op_count):
                self.__sell(client,context)
            # 强力买卖条件下,买股,买两遍，第一遍为买，第二遍为检查，防止部分五档扫完还没买够的
            for i in range(op_count):
                self.__buy(client,context)
            pass
        except Exception as e:
            send_message('实盘易操作异常！！请检查!<br>' + str(e),channel='weixin')
            self.log_warn('实盘易操作异常！！请检查!' + str(e))

    # 卖股
    def __sell(self,client,context):
        sp = self.__get_shipan_p(client)
        mp = self.__get_moni_p(context)
        op_list = self.__get_dif(mp,sp)
        self.log_info('持仓差异:' + str(op_list))
        for x in op_list:
            if x[1] > 0 :
                continue
            try:
                actual_order = client.execute(self._client_param,action='SELL',symbol=x[0]
                    ,type='MARKET',priceType=4,amount=abs(x[1]))
            except Exception as e:
                self.log_warn("[实盘易] 卖单异常 [%s : %d]：%s" % (x[0],x[1],str(e)))

    # 买股
    def __buy(self,client,context):
        # 获取实盘总持仓
        sp = self.__get_shipan_p(client)
        # 获取模拟盘持仓
        mp = self.__get_moni_p(context)
        # 通过对比持仓获得要操作的股票及数量
        op_list = self.__get_dif(mp,sp)
        self.log_info('持仓差异:' + str(op_list))
        # 买股
        for x in op_list:
            if x[1] < 0 :
                continue
            stock = x[0]
            buy_count = abs(x[1])
            try:
                # 买单时需要获取实际资金，以涨停价计算最大挂单数买入。
                # 最后一单经常需要拆成两单买入。还有误差就不管了。
                data = get_current_data()
                max_price = data[stock].high_limit
                for i in range(2):
                    # 获取实盘可用资金
                    cash = self.__get_shipan_cash(client)
                    if cash < 0:
                        send_message('实盘易获取实盘可用资金失败，请检查！',channel='weixin')
                        self.log_warn('实盘易获取实盘可用资金失败，请检查')
                        return

                    # 计算当前可用资金以涨停价挂单的最大挂单数
                    max_count = int(int(cash * 1.0 / max_price / 100) * 100)
                    self.log_info('%d 次买计算:[stock : %s][max_price:%f] [cash: %f] [max_count:%d] [aim:%d]' % (
                        i + 1,stock,max_price,cash,max_count,buy_count))
                    if max_count <= 0:
                        break
                    if max_count >= buy_count:
                        # 可用资金足够，一次性买入。
                        actual_order = client.execute(self._client_param,action='BUY',symbol=stock
                            ,type='MARKET',priceType=4,amount=buy_count)
                        break
                    else:
                        # 资金不足，分次买入。
                        actual_order = client.execute(self._client_param,action='BUY',symbol=stock
                            ,type='MARKET',priceType=4,amount=max_count)
                        buy_count -= max_count
            except Exception as e:
                self.log_warn("[实盘易] 买单异常 [%s : %d]：%s" % (stock,buy_count,str(e)))

    # 获取实盘现金
    def __get_shipan_cash(self,client):
        r = None
        # 重复三次获取，防止偶然性网络错误
        for i in range(3):
            try:
                r = client.get_positions(self._client_param)
                break
            except:
                pass
        if r == None:
            return -1

        try:
            cash = float(r['sub_accounts'][u'可用'])
        except:
            cash = -1
        return cash

    # 获取实盘持仓
    def __get_shipan_p(self,client):
        r = None
        e1 = None
        # 重复三次获取，防止偶然性网络错误
        for i in range(3):
            try:
                r = client.get_positions(self._client_param)
                break
            except Exception as e:
                e1 = e
                pass
        if r == None:
            # 重抛异常
            if e1 != None:
                raise e1
            return
        positions = r.get('positions',None)
        sp = zip(positions[u'证券代码'],positions[u'证券数量'])
        sp = [[normalize_code(x[0]).encode('utf-8'),int(float(x[1]))] for x in sp if x[0] != '' and x[1] != '']
        return sp

    # 获取模拟盘持仓
    def __get_moni_p(self,context):
        result = []
        total_values = context.portfolio.positions_value + context.portfolio.cash
        for stock in context.portfolio.positions.keys():
            position = context.portfolio.positions[stock]
            if position.total_amount == 0:
                continue
            result.append([stock,position.total_amount])

        return result

    # 获取两持仓之差 mp为模拟盘，sp为实盘。
    def __get_dif(self,mp,sp):
        sp = [[x[0], -x[1]] for x in sp]
        op_list = mp + sp
        # 取两个列表之差
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
                # 卖股
                # 取模拟盘的持仓量
                t = [x[1] for x in mp if x[0] == s[0]]
                if len(t) == 0 or t[0] == 0:
                    # 如果模拟盘已清仓该股，则实盘全卖
                    new_l.append(s)
                    continue
                # 对股票取整
                n = int(round(s[1] * 1.0 / 100) * 100)
                new_l.append([s[0],n])
            else:
                # 买股直接四舍五入取整
                n = int(round(s[1] * 1.0 / 100) * 100)
                new_l.append([s[0],n])
        new_l = [x for x in new_l if x[1] != 0]
        new_l = sorted(new_l,key=lambda x:x[1])
        return new_l

    def __str__(self):
        return '实盘易对接券商 [host: %s:%d  key: %s client:%s]' % (self.host,self.port,self.key,self._client_param)

'''-----------------根据XueQiuOrder下单------------------------'''
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

    # 卖出股票时调用的函数
    def when_sell_stock(self,position,order,is_normal):
        try:
            # self.get_executor().execute(order)
            pass
        except:
            self.log_error('实盘易卖股失败:' + str(order))
        pass
    
    # 买入股票时调用的函数
    def when_buy_stock(self,stock,order):
        try:
            # self.get_executor().execute(order)
            pass
        except:
            self.log_error('实盘易卖股失败:' + str(order))
        pass

'''-----------------根据聚宽Order用实盘易下单------------------'''
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

    # 获取下单执行器
    def get_executor(self):
        if self.executor == None:
            self.executor = shipane_sdk.JoinQuantExecutor(host=self.host,port=self.port,key=self.key,client=self.client)
        return self.executor

    def after_trading_end(self,context):
        self.executor = None
        pass

    # 卖出股票时调用的函数
    def when_sell_stock(self,position,order,is_normal):
        try:
            self.get_executor().execute(order)
        except:
            self.log_error('实盘易卖股失败:' + str(order))
        pass
    
    # 买入股票时调用的函数
    def when_buy_stock(self,stock,order):
        try:
            self.get_executor().execute(order)
        except:
            self.log_error('实盘易卖股失败:' + str(order))
        pass

'''------------------------------通过实盘易申购新股----------------------'''
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
        return '实盘易申购新股[time: %s host: %s:%d  key: %s client:%s] ' % (self.times,self.host,self.port,self.key,self.clients)

'''~~~~~~~~~~~~~~~~~~~~~~~~~~~基础函数~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'''
def is_3_black_crows(stock):
    # talib.CDL3BLACKCROWS

    # 三只乌鸦说明来自百度百科
    # 1. 连续出现三根阴线，每天的收盘价均低于上一日的收盘
    # 2. 三根阴线前一天的市场趋势应该为上涨
    # 3. 三根阴线必须为长的黑色实体，且长度应该大致相等
    # 4. 收盘价接近每日的最低价位
    # 5. 每日的开盘价都在上根K线的实体部分之内；
    # 6. 第一根阴线的实体部分，最好低于上日的最高价位
    #
    # 算法
    # 有效三只乌鸦描述众说纷纭，这里放宽条件，只考虑1和2
    # 根据前4日数据判断
    # 3根阴线跌幅超过4.5%（此条件忽略）

    h = attribute_history(stock,4,'1d',('close','open'),skip_paused=True,df=False)
    h_close = list(h['close'])
    h_open = list(h['open'])

    if len(h_close) < 4 or len(h_open) < 4:
        return False

    # 一阳三阴
    if h_close[-4] > h_open[-4] \
        and (h_close[-1] < h_open[-1] and h_close[-2] < h_open[-2] and h_close[-3] < h_open[-3]):
        # and (h_close[-1] < h_close[-2] and h_close[-2] < h_close[-3]) \
        # and h_close[-1] / h_close[-4] - 1 < -0.045:
        return True
    return False


# 获取股票n日以来涨幅，根据当前价计算
# n 默认20日
def get_growth_rate(security,n=20):
    lc = get_close_price(security,n)
    # c = data[security].close
    c = get_close_price(security,1,'1m')

    if not isnan(lc) and not isnan(c) and lc != 0:
        return (c - lc) / lc
    else:
        log.error("数据非法, security: %s, %d日收盘价: %f, 当前价: %f" % (security,n,lc,c))
        return 0

# 获取前n个单位时间当时的收盘价
def get_close_price(security,n,unit='1d'):
    return attribute_history(security,n,unit,('close'),True)['close'][0]


# ===================== VaR仓位控制 ===============================================

class PositionControlVar(object):
    """基于风险价值法（VaR）的仓位控制"""

    def __init__(self, context, risk_money_ratio=0.05, confidencelevel=2.58, moneyfund=['511880.XSHG']):
        """ 相关参数说明：
            1. 设置风险敞口
            risk_money_ratio = 0.05

            2. 正态分布概率表，标准差倍数以及置信率
                1.96, 95%; 2.06, 96%; 2.18, 97%; 2.34, 98%; 2.58, 99%; 5, 99.9999%
            confidencelevel = 2.58

            3. 使用赋闲资金做现金管理的基金(银华日利)
            moneyfund = ['511880.XSHG']
        """
        self.risk_money = context.portfolio.portfolio_value * risk_money_ratio
        self.confidencelevel = confidencelevel
        self.moneyfund = delete_new_moneyfund(context, moneyfund, 60)

    def __str__(self):
        return 'VaR仓位控制'

    # 卖出股票
    def sell_the_stocks(self, context, stocks):
        for stock in stocks:
            if stock in context.portfolio.positions.keys():
                # 这段代码不甚严谨，多产品轮动会有问题，本案例 OK
                if stock not in self.moneyfund:
                    equity_ratio = {}
                    equity_ratio[stock] = 0
                    trade_ratio = self.func_getequity_value(context, equity_ratio)
                    self.func_trade(context, trade_ratio)

    # 买入股票
    def buy_the_stocks(self, context, stocks):
        equity_ratio = {}
        ratio = 1.0 / len(stocks)       # TODO 需要比照原始代码确认逻辑是否正确
        for stock in stocks:
            equity_ratio[stock] = ratio
        trade_ratio = self.func_getequity_value(context, equity_ratio)
        self.func_trade(context, trade_ratio)

    # 股票调仓
    def func_rebalance(self, context):
        myholdlist = list(context.portfolio.positions.keys())
        if myholdlist:
            for stock in myholdlist:
                if stock not in self.moneyfund:
                    equity_ratio = {stock: 1.0}
                    trade_ratio = self.func_getequity_value(context, equity_ratio)
                    self.func_trade(context, trade_ratio)

    # 根据预设的 risk_money 和 confidencelevel 来计算，可以买入该多少权益类资产
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
                # 每股的 VaR，VaR = 上一日的价格 * 置信度换算得来的标准倍数 * 日收益率的标准差
                __curVaR = hStocks[stock] * __confidence_ratio * __func_getStd(stock, '1d', 120)
                # 一元会分配买多少股
                __curAmount = 1 * __equity_ratio[stock] / hStocks[stock]  # 1单位资金，分配时，该股票可以买多少股
                __portfolio_VaR += __curAmount * __curVaR  # 1单位资金时，该股票上的实际风险敞口

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
            portfolio_value = equity_value  # TODO: 是否有误？equity_value = portfolio_value?
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

        # 没有对 bonds 做配仓，因为只有一个
        if self.moneyfund:
            stock = self.moneyfund[0]
            if stock in trade_ratio:
                trade_ratio[stock] += round((bonds_value * 1.0 / portfolio_value), 3)
            else:
                trade_ratio[stock] = round((bonds_value * 1.0 / portfolio_value), 3)
        log.info('trade_ratio: %s' % trade_ratio)
        return trade_ratio

    # 交易函数
    def func_trade(self, context, trade_ratio):
        def __func_trade(context, stock, value):
            log.info(stock + " 调仓到 " + str(round(value, 2)) + "\n")
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
                    # 如果是银华日利，多卖 100 股，避免个股买少了
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

        # 已有仓位
        holdDict = {}
        hholdstocks = history(1, '1d', 'close', myholdstock, df=False)
        for stock in myholdstock:
            tmpW = round((context.portfolio.positions[stock].total_amount * hholdstocks[stock]) / total_value, 2)
            holdDict[stock] = float(tmpW)

        # 对已有仓位做排序
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

        # 交易其他股票
        for i in range(len(trade_list)):
            stock = trade_list[i]
            if len(_tmplist) != 0:
                if stock not in _tmplist:
                    __func_tradeStock(context, stock, trade_ratio[stock])
            else:
                __func_tradeStock(context, stock, trade_ratio[stock])


# 根据不同的时间段设置滑点与手续费
def set_slip_fee(context):
    # 将滑点设置为0
    slip_ratio = 0.02
    set_slippage(FixedSlippage(slip_ratio))
    log.info('设置滑点率: 固定滑点%f' % slip_ratio)

    # 根据不同的时间段设置手续费
    dt = context.current_dt

    if dt > datetime.datetime(2013, 1, 1):
        set_order_cost(OrderCost(open_tax=0, close_tax=0.001, open_commission=0.0003, close_commission=0.0003, close_today_commission=0, min_commission=5), type='stock')
    elif dt > datetime.datetime(2011, 1, 1):
        set_order_cost(OrderCost(open_tax=0, close_tax=0, open_commission=0.001, close_commission=0.002, close_today_commission=0, min_commission=5), type='stock')
    elif dt > datetime.datetime(2009, 1, 1):
        set_order_cost(OrderCost(open_tax=0, close_tax=0, open_commission=0.002, close_commission=0.003, close_today_commission=0, min_commission=5), type='stock')
    else:
        set_order_cost(OrderCost(open_tax=0, close_tax=0, open_commission=0.003, close_commission=0.004, close_today_commission=0, min_commission=5), type='stock')
