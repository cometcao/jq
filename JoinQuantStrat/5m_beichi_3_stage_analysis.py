# 此程序应在当日15时后， 次日9点之前运行完毕
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
from jqfactor import *

pd.options.mode.chained_assignment = None

def run_initial_scan():
    result = {}
    filename = 'chan_stocks_initial_scan_daily.txt'
    try:
        content = read_file(filename)
        result = json.loads(content)
#         print(result)
    except Exception as e:
        print("{0} loading error {1}".format(filename, str(e)))

    all_trade_days = get_all_trade_days()
    current_trade_day = get_trade_days(count=1)[0]
    next_trade_day = all_trade_days[np.where(all_trade_days==current_trade_day)[0][0]+1]
    today = datetime.datetime.today()

    if len(np.where(all_trade_days==today)[0]) == 0:
        record_date = next_trade_day
    elif 15 < today.hour < 24:
        record_date = next_trade_day
    elif 0 < today.hour < 9:
        record_date = current_trade_day
    print("processing for {0}".format(record_date))
    
    if str(record_date) in result:
        print("{0} already done".format(record_date))
        return

    stock_results = []
    high_level='1w'
    top_level='30m'
    current_level='5m'
    sub_level = '1m'
    
    expected_current_types = [Chan_Type.I, Chan_Type.INVALID, Chan_Type.I_weak]
    # check_stocks = filter_high_level_by_index(
    #                                         direction=TopBotType.top2bot, 
    #                                         stock_index='000985.XSHG',  # '000906.XSHG' '399905.XSHE'
    #                                         df=False,
    #                                         periods = [high_level],
    #                                         chan_types=[Chan_Type.I,Chan_Type.III])
    check_stocks = get_index_stocks('000985.XSHG')

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


startTime = datetime.time(17, 0, 0)
endTime = datetime.time(23, 55, 0)

while True:
    dates = get_trade_days(count=1)
    today = datetime.datetime.today().date()
    now = datetime.datetime.today().time()
    print("current time:{0}, starting time:{1}".format(now, startTime))
    
    if today not in dates: # today is trading day
        print("non-trading day, wait for 4 hours")
        time.sleep(14400) # sleep for 4 hours
        continue

    if now < startTime:
        td = datetime.datetime.combine(today, startTime) - datetime.datetime.combine(today, now)
        print("sleep till starting time for {0} seconds".format(td.total_seconds()))
        time.sleep(int(td.total_seconds()))
        
    run_initial_scan()
    
    print("finished wait for next trading day")
    if now < endTime:
        time.sleep(72000) # sleep for 20 hours
    else:
        time.sleep(32400) # sleep for 9 hours
