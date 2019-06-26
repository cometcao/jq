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
import math
import json
from pickle import dump
from pickle import load
import numpy as np
import io
from keras.utils.np_utils import to_categorical
from sklearn.preprocessing import MinMaxScaler, StandardScaler

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

    if not np.isnan(lc) and not np.isnan(c) and lc != 0:
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
    return "%s:%s" % (stock[:6], get_security_info(stock).display_name)


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
        
def batch(iterable, n=1):
    l = len(iterable)
    for ndx in range(0, l, n): # restart
        yield [ndx,min(ndx + n, l)]    
            
def save_dataset(dataset, filename, isDebug=True):
    dump(dataset, open(filename, 'wb'))
    if isDebug:
        print('Saved: %s' % filename)
    
def load_dataset(filename, isDebug=True):
    if isDebug:
        print('Loaded: %s' % filename)
    return load(open(filename, 'rb'))

def save_dataset_json(dataset, filename):
    with open(filename, 'w', encoding="latin-1") as outfile: #'utf-8'
        memfile = io.BytesIO()
        np.save(memfile, dataset)
        memfile.seek(0)
        json_dump = json.dumps(memfile.read().decode("latin-1"))    
        outfile.write(json_dump)
        print('Saved: %s' % filename)
        
def load_dataset_json(filename):    
    with open(filename, encoding='utf-8') as data_file:
        data = json.loads(data_file.read())
        memfile = io.BytesIO()
        memfile.write(json.loads(data).encode('utf-8'))
        memfile.seek(0)
        print('Loaded: %s' % filename)
        return np.load(memfile)  
    
def save_dataset_np(dataset, filename):
    np.save(filename, dataset)
    print('Saved: %s' % filename)
    
def load_dataset_np(filename):
    print('Loaded: %s' % filename)
    return np.load(filename)

def pad_each_training_array(data_list, max_sequence_length):
    new_shape = findmaxshape(data_list)
    if max_sequence_length != 0: # force padding to global max length
        new_shape = (max_sequence_length, new_shape[1]) 
    new_data_list = fillwithzeros(data_list, new_shape)
    return new_data_list

def fillwithzeros(inputarray, outputshape):
    """
    Fills input array with dtype 'object' so that all arrays have the same shape as 'outputshape'
    inputarray: input numpy array
    outputshape: max dimensions in inputarray (obtained with the function 'findmaxshape')

    output: inputarray filled with zeros
    """
    length = len(inputarray)
    output = np.zeros((length,)+outputshape)
    for i in range(length):
        if inputarray[i].shape[0] <= outputshape[0]:
            output[i][:inputarray[i].shape[0],:inputarray[i].shape[1]] = inputarray[i]
        else:
            output[i][:outputshape[0], :outputshape[1]] = inputarray[i][-outputshape[0]:,-outputshape[1]:]
#                 print(inputarray[i].shape)
#                 print(output[i].shape)
#                 print(inputarray[i])
#                 print(output[i])
    return output

def findmaxshape(inputarray):
    """
    Finds maximum x and y in an inputarray with dtype 'object' and 3 dimensions
    inputarray: input numpy array

    output: detected maximum shape
    """
    max_x, max_y = 0, 0
    for array in inputarray:
        x, y = array.shape
        if x > max_x:
            max_x = x
        if y > max_y:
            max_y = y
    return(max_x, max_y)

def sort_training_dataset_by_sublength(dataset, label):
    """
    Input: training/testing dataset label
    output: training/testing dataset label sorted by sub sequence length in dataset
    """
    narrayData = sorted(dataset, key=len, reverse=False)
    length_index = np.argsort([len(seq) for seq in dataset])

    narrayLabel = np.array(label)[length_index]
        
    return narrayData, narrayLabel
    
def encode_category(label_set): # this is assuming we have full label in the sample
    uniques, ids = np.unique(label_set, return_inverse=True)
    y_code = to_categorical(ids, len(uniques))
    return y_code

def normalize(df, norm_range=[0, 1], fields = ['open', 'close', 'high', 'low', 'money']):
    scaler = MinMaxScaler(feature_range=norm_range) if norm_range is not None else StandardScaler()
    df[fields] = scaler.fit_transform(df[fields]) 
    return df