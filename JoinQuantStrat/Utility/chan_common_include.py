# -*- encoding: utf8 -*-
'''
Created on 09 Feb 2020

@author: MetalInvest
'''
try:
    from kuanke.user_space_api import *         
except ImportError as ie:
    print(str(ie))
from jqdata import *
import datetime
import numpy as np
from enum import Enum 
######################## common method ###############################

def float_less(a, b):
    return a < b and not np.isclose(a, b)

def float_more(a, b):
    return a > b and not np.isclose(a, b)

def float_less_equal(a, b):
    return a < b or np.isclose(a, b)

def float_more_equal(a, b):
    return a > b or np.isclose(a, b)

def float_equal(a, b):
    return np.isclose(a, b)


######################## chan_kbar_filter ##########################
TYPE_III_NUM = 7
TYPE_I_NUM = 10
TYPE_III_STRONG_NUM = 89

######################## kBarprocessor #############################
GOLDEN_RATIO = 0.618
MIN_PRICE_UNIT=0.01

PRICE_UPPER_LIMIT = 200

######################## Central Region ###########################

class ZhongShuLevel(Enum):
    previousprevious = -2
    previous = -1
    current = 0
    next = 1
    nextnext = 2
    @classmethod
    def value2type(cls, val):
        if val == -2:
            return cls.previousprevious
        elif val == -1:
            return cls.previous
        elif val == 0:
            return cls.current
        elif val == 1:
            return cls.next
        elif val == 2:
            return cls.nextnext
        else:
            return cls.current
    
class ZouShi_Type(Enum):
    INVALID = -2
    Qu_Shi_Down = -1
    Pan_Zheng = 0
    Qu_Shi_Up = 1
    Pan_Zheng_Composite = 2
    @classmethod
    def value2type(cls,val):
        if val == 0:
            return cls.Pan_Zheng
        elif val == 1:
            return cls.Qu_Shi_Up
        elif val == -1:
            return cls.Qu_Shi_Down
        elif val == 2:
            return cls.Pan_Zheng_Composite
        elif val == -2:
            return cls.INVALID

    
class Chan_Type(Enum):
    INVALID = 0
    I = 1
    II = 2
    III = 3
    III_weak = 4
    II_weak = 5
    III_strong = 6
    I_weak = 7
    PANBEI = 8
    BEICHI = 9
    INVIGORATE = 10
    
    @classmethod
    def value2type(cls, val):
        if val == 0:
            return cls.INVALID
        elif val == 1:
            return cls.I
        elif val == 2:
            return cls.II
        elif val == 3:
            return cls.III
        elif val == 4:
            return cls.III_weak
        elif val == 5:
            return cls.II_weak
        elif val == 6:
            return cls.III_strong
        elif val == 7:
            return cls.I_weak
        elif val == 8:
            return cls.PANBEI
        elif val == 9:
            return cls.BEICHI
        elif val == 10:
            return cls.INVIGORATE
        else:
            return cls.INVALID
        
        
###################################################
def work_out_count(start_dt, end_dt, unit):
    if type(start_dt) is str:
        start_dt = datetime.datetime.strptime(start_dt, "%Y-%m-%d %H:%M:%S")
    if type(end_dt) is str:
        end_dt = datetime.datetime.strptime(end_dt, "%Y-%m-%d %H:%M:%S")
        if end_dt.hour < 9:
            end_dt = (end_dt - datetime.timedelta(days = 1)).replace(hour=15, minute=0)
        elif end_dt.hour > 14:
            end_dt = end_dt.replace(hour=15, minute=0)

    start_time_delta = start_dt.replace(hour=15, minute=0) - start_dt if start_dt.hour >= 13 else start_dt.replace(hour=13, minute=30) - start_dt
    end_time_delta = end_dt - end_dt.replace(hour=9, minute=30) if end_dt.hour <= 11 else end_dt - end_dt.replace(hour=11, minute=0)
    
    trade_days = get_trade_days(start_date=start_dt.date(), end_date=end_dt.date())
    day_diff = len(trade_days) - 2
    time_delta_seconds = start_time_delta.total_seconds() + end_time_delta.total_seconds() + day_diff * 4 * 60 * 60

    if unit == '1d':
        count = np.ceil(time_delta_seconds / (60*30*8))
    elif unit == '30m':
        count = np.ceil(time_delta_seconds / (60*30))
    elif unit == '5m':
        count = np.ceil(time_delta_seconds / (60*5))
    elif unit == '1m':
        count = np.ceil(time_delta_seconds / 60)
    else:
        print("Unconventional unit, return 1000 for count")
        count = 1000
    count = count + 1 # inclusion for end_dt
    return count

def get_bars_new(security, 
                 unit='1d',
                 fields=['date', 'open','high','low','close'],
                 include_now=True, 
                 end_dt=None, 
                 start_dt=None, 
                 fq_ref_date=None, 
                 df=False):
    
    count = work_out_count(start_dt, end_dt, unit)

    return get_bars(security, 
                    count=int(count), 
                    unit=unit,
                    fields=fields,
                    include_now=include_now, 
                    end_dt=end_dt, 
                    fq_ref_date=fq_ref_date, 
                    df=df)