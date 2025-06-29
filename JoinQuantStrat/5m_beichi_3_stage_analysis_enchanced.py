from jqdata import *
from sector_selection import *
from kBar_Chan import *
from centralRegion import *
from equilibrium import *
from chan_kbar_filter import *
from jqdata import *
import pandas as pd
import numpy as np
import datetime
import time
import json

pd.options.mode.chained_assignment = None

filename = 'chan_stocks_initial_scan_daily.txt'
startTime = datetime.time(17, 0, 0)
endTime = datetime.time(23, 55, 0)

def get_stock_by_sectors():
    ss = SectorSelection(limit_pct=3, 
            isStrong=True, 
            min_max_strength=0, 
            useIntradayData=False,
            useAvg=False,
            avgPeriod=55,
            isWeighted=True,
            effective_date=datetime.datetime.today())
    stock_list = ss.processAllSectorStocks(isDisplay = True)
    print(stock_list, len(stock_list))
    return stock_list

def read_record_file():
    result = {}
    try:
        content = read_file(filename)
        result = json.loads(content)
#         print(result)
    except Exception as e:
        print("{0} loading error {1}".format(filename, str(e)))
    return result

def run_initial_scan(result, record_date):
    stock_results = []
    high_level='1w'
    top_level='30m'
    current_level='5m'
    sub_level = '1m'
    
    expected_current_types = [Chan_Type.I, Chan_Type.INVALID, Chan_Type.I_weak]
    check_stocks = get_stock_by_sectors()

    for stock in check_stocks:
        current_time=pd.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        m_result, xd_m_result, m_profile = check_chan_by_type_exhaustion(stock=stock, 
                                                                  end_time=current_time, 
                                                                  count=3000, 
                                                                  periods=[top_level], 
                                                                  direction=TopBotType.top2bot, 
                                                                  chan_type=[Chan_Type.INVALID, Chan_Type.I, Chan_Type.I_weak], 
                                                                  isdebug=False, 
                                                                  is_description=False,
                                                                  check_structure=True)
        
        if m_result and xd_m_result:
            c_result, xd_c_result, c_profile, current_zhongshu_formed = check_stock_sub(stock=stock, 
                                                                        end_time=current_time, 
                                                                        periods=[current_level], 
                                                                        count=4800, 
                                                                        direction=TopBotType.top2bot, 
                                                                        chan_types=expected_current_types, 
                                                                        isdebug=False, 
                                                                        is_anal=False, 
                                                                        is_description=False,
                                                                        split_time=None,
                                                                        check_bi=False,
                                                                        force_zhongshu=True,
                                                                        force_bi_zhongshu=True,
                                                                        ignore_sub_xd=True)

            if c_profile and c_profile[0][0]  in expected_current_types:
                c_type, c_direction, c_price, c_slope, c_force, zoushi_time, split_time = c_profile[0]
                m_type = m_profile[0][0]
                stock_results.append([stock, 
                                     m_type.value,
                                     c_type.value, 
                                     top_level,
                                     current_level,
                                     c_direction.value, 
                                     c_price, 
                                     c_slope, 
                                     c_force,
                                     zoushi_time.strftime("%Y-%m-%d %H:%M:%S"),
                                     split_time.strftime("%Y-%m-%d %H:%M:%S")])

    result[str(record_date)] = stock_results
    result_json=json.dumps(result)
    write_file(filename, result_json)
    print([x[0] for x in stock_results])

def check_status():
    result = read_record_file()
    check_result = False
    
    all_trade_days = get_all_trade_days()
    dates = get_trade_days(count=1)
    current_trade_day = dates[0]
    next_trade_day = all_trade_days[np.where(all_trade_days==current_trade_day)[0][0]+1]
    today_dt = datetime.datetime.today()
    
    today_date = datetime.datetime.today().date()
    now = datetime.datetime.today().time()
    print("current time:{0}, starting time:{1}".format(now, startTime))

    if now < startTime:
        td = datetime.datetime.combine(today_date, startTime) - datetime.datetime.combine(today_date, now)
        print("sleep till starting time for {0} seconds".format(td.total_seconds()))
        return result, check_result, int(td.total_seconds()) + 5, next_trade_day

    if today_date not in dates and str(next_trade_day) in result: # today is trading day
        print("non-trading day, wait for 4 hours")
        return result, check_result, 14400, next_trade_day

    if len(np.where(all_trade_days==today_dt)[0]) == 0:
        record_date = next_trade_day
        check_result = True
    elif 15 < today_dt.hour < 24:
        record_date = next_trade_day
        check_result = True
    elif 0 < today_dt.hour < 9:
        record_date = current_trade_day
        check_result = True
    print("processing for {0}".format(record_date))

    if str(record_date) in result:
        print("{0} already done".format(record_date))
        return result, False, 32400, record_date

    return result, check_result, 72000 if now < endTime else 32400, record_date

while True:
    file_result, check_result, wait_sec, record_date = check_status()
    if check_result:
        run_initial_scan(file_result, record_date)
        print("finished wait for next trading day")
    else:
        time.sleep(wait_sec)

