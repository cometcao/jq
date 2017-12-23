# -*- encoding: utf8 -*-
'''
Created on 24 Oct 2017

@author: MetalInvest
'''
try:
    from kuanke.user_space_api import *
except:
    pass
import enum

evs_query_string = '(valuation.market_cap*100000000+balance.total_liability+balance.minority_interests+balance.capital_reserve_fund-balance.cash_equivalents)/(income.total_operating_revenue)'
eve_query_string = '(valuation.market_cap*100000000+balance.total_liability+balance.minority_interests+balance.capital_reserve_fund-balance.cash_equivalents)/(indicator.eps*valuation.capitalization*10000)'


class TaType(enum.Enum):
    MACD = 0,
    RSI = 1,
    BOLL = 2,
    MA = 3, 
    MACD_STATUS = 4,
    TRIX = 5,
    BOLL_UPPER = 6,
    TRIX_STATUS = 7,
    TRIX_PURE = 8,
    MACD_ZERO = 9,
    MACD_CROSS = 10,
    KDJ_CROSS = 11,
    BOLL_MACD = 12

    def __le__(self, b):
        return self.value <= b.value


'''===============================其它基础函数=================================='''


def get_growth_rate(security, n=20):
    '''
    获取股票n日以来涨幅，根据当前价(前1分钟的close）计算
    n 默认20日  
    :param security: 
    :param n: 
    :return: float
    '''
    lc = get_close_price(security, n)
    c = get_close_price(security, 1, '1m')

    if not isnan(lc) and not isnan(c) and lc != 0:
        return (c - lc) / lc
    else:
        log.error("数据非法, security: %s, %d日收盘价: %f, 当前价: %f" % (security, n, lc, c))
        return 0


def get_close_price(security, n, unit='1d'):
    '''
    获取前n个单位时间当时的收盘价
    为防止取不到收盘价，试3遍
    :param security: 
    :param n: 
    :param unit: '1d'/'1m'
    :return: float
    '''
    cur_price = np.nan
    for i in range(3):
        cur_price = attribute_history(security, n, unit, 'close', True)['close'][0]
        if not math.isnan(cur_price):
            break
    return cur_price


# 获取一个对象的类名
def get_obj_class_name(obj):
    cn = str(obj.__class__)
    cn = cn[cn.find('.') + 1:]
    return cn[:cn.find("'")]


def show_stock(stock):
    '''
    获取股票代码的显示信息    
    :param stock: 股票代码，例如: '603822.XSHG'
    :return: str，例如：'603822 嘉澳环保'
    '''
    return "%s %s" % (stock[:6], get_security_info(stock).display_name)


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


def generate_portion(num):
    total_portion = num * (num+1) / 2
    start = num
    while num != 0:
        yield float(num) / float(total_portion)
        num -= 1