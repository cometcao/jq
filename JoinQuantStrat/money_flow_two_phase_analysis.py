# main money inflow over ciculating market cap adjusted by top 10 concentrated ownership
from jqdata import *
from datetime import datetime, timedelta
import pandas as pd
pd.set_option('display.max_columns', 500)

from biaoLiStatus import TopBotType
from chan_common_include import ZouShi_Type, Chan_Type
from strat_common_include import get_stock_downwards_count, get_main_money_inflow_over_total_money_over_time
from chan_kbar_filter import analyze_MA_zoushi_by_stock

# current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
current_time = datetime.now()
# working_date = datetime.today()# - timedelta(days=1)
print("current time: {0}".format(current_time))
# working_date = datetime.strptime('2022-04-28', "%Y-%m-%d")

debug = False
level_check = '1d'
stock_list = get_all_securities(['stock']).index.values.tolist()


def filter_out_stock_by_mfc(work_stock_list, period_count, current_time, use_money, debug):
    downwards_count_limit = 10 if period_count == 60 else 5
    print("period count: {0}, limit: {1}, use_money: {2}".format(period_count, downwards_count_limit, use_money))
    # I: find a rough downwards movement and worm out the period
    stock_count = get_stock_downwards_count(
        work_stock_list, period_count, current_time, '1d', downwards_count_limit, 0, debug)

    # II: find positive top money inflow / free share portion ######################################
    # check all stocks
    # cir_mcap = get_main_money_inflow_over_time_over_circulating_mcap(stock_count, 
    #                                                                current_time, 
    #                                                                price_change_filter = 0,
    #                                                                adjust_concentrated=True, 
    #                                                                force_positive_inflow=True,
    #                                                                is_debug=debug)
    cir_mcap = get_main_money_inflow_over_total_money_over_time(stock_count, 
                                                               current_time, 
                                                               force_positive_inflow=False,
                                                               use_cir_mcap=True,
                                                               use_money=use_money,
                                                               is_debug=debug)

    # remove STI stocks
    # cir_mcap = cir_mcap[cir_mcap['code'].map(lambda x: x[:3] != '688')]

    cir_mcap = cir_mcap.sort_values(by='mfc', ascending=False)
    cir_mcap = cir_mcap.reset_index();

    # only consider top 100
    stock_value_list = cir_mcap.head(100)[['code', 'mfc']].values.tolist()

    print(stock_value_list)
    return stock_value_list

# False True 17
# False False 21
# True True 28 26 27 30jul 56 1Aug 50  2Aug 50
# True False 19

stock_list_20_val = filter_out_stock_by_mfc(stock_list, 20, current_time, True, debug)
stock_list_20 = [stock for stock,_ in stock_list_20_val]
stock_list_60_val = filter_out_stock_by_mfc(stock_list_20, 60, current_time, True, debug)
stock_value_list = []
for stock_60, stock_60_val in stock_list_60_val:
    for stock_20, stock_20_val in stock_list_20_val:
        if stock_60 == stock_20 and stock_60_val > stock_20_val:
            stock_value_list.append(stock_60)
            break
        elif stock_60 == stock_20:
            break
####################################################################################################
intermediate_list = [stock for stock, _ in stock_list_60_val if stock in stock_list_20]
print("Intermediate list: {0} {1}".format(intermediate_list, len(intermediate_list)))
print("final list 60 > 20: {0} {1}".format(stock_value_list, len(stock_value_list)))
money_inflow_list = stock_value_list

# III: apply zoushi analysis ##################################################################
expected_zoushi_down = [ZouShi_Type.Pan_Zheng, ZouShi_Type.Qu_Shi_Down] #  
expected_exhaustion_down = [Chan_Type.PANBEI, Chan_Type.BEICHI] #Chan_Type.INVIGORATE

def get_translated_count(count, level):
    if count <= 20 and level == '1d':
        return [(count * 4, '60m'), (count * 8, '30m')]
    elif count <= 60 and level == '1d':
        return [(count, '1d')] 
    else:
        return [(count, level)]
picked_stocks = []
for stock in money_inflow_list:
    current_time=pd.datetime.now()

    for check_count_level, level in get_translated_count(20, '1d'):
        stock_data = get_bars(stock, 
                               count=check_count_level, 
                               end_dt=current_time, 
                               unit=level,
                               fields= ['date','high', 'low'], 
                               df = False,
                               include_now=True)

        max_loc = int(np.where(stock_data['high'] == max(stock_data['high']))[0][-1])
        peak_time = stock_data[max_loc]['date']
        peak_count = len(stock_data['high']) - max_loc
        if peak_count <= 0:
            continue

        result_zoushi, result_exhaustion = analyze_MA_zoushi_by_stock(stock=stock,
                                                                  period=level, 
                                                                  count=peak_count,
                                                                  end_dt=current_time, 
                                                                  df=False, 
                                                                  zoushi_types=expected_zoushi_down, 
                                                                  direction=TopBotType.top2bot)
        if result_zoushi in expected_zoushi_down and result_exhaustion in expected_exhaustion_down:
            print("stock: {0} zoushi: {1} exhaustion:{2} level:{3}".format(stock, result_zoushi, result_exhaustion, level))
            picked_stocks.append(stock)
            continue
print(picked_stocks)