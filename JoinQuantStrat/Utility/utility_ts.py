'''
Created on 19 May 2018

@author: MetalInvest
'''
import tushare as ts
import datetime
import numpy as np


def get_trading_date_ts(count, end=datetime.datetime.today()):
    dates = ts.trade_cal()
    dates = dates[dates['isOpen']==1] # trading days
    dates['calendarDate'] = dates.apply(lambda row: datetime.datetime.strptime(row['calendarDate'], '%Y-%m-%d'), axis=1)
    dates.set_index('calendarDate', inplace=True, drop=True)
    if isinstance(end, datetime.datetime):
        dates = dates.loc[:str(end.date()), :]
    elif isinstance(end, datetime.date):
        dates = dates.loc[:str(end),:]
    elif isinstance(end, str):
        dates = dates.loc[:end, :]
    else:
        print("Invalid Date! return today's date")
        return [str(datetime.datetime.today().date())]
    return dates.index[-count:]