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
# current_time = datetime.now() - timedelta(days=100)
print("current time: {0}".format(current_time))
# working_date = datetime.strptime('2022-04-28', "%Y-%m-%d")

debug = False
level_check = '1d'
stock_list = get_all_securities(['stock']).index.values.tolist()


def filter_out_stock_by_mfc(work_stock_list, period_count, current_time, use_money, debug):
    # downwards_count_limit = 5 if period_count == 120 else 3
    print("period count: {0}, limit: {1}, use_money: {2}".format(period_count, downwards_count_limit, use_money))
    # I: find a rough downwards movement and worm out the period
    #stock_count = get_stock_downwards_count(
    #    work_stock_list, period_count, current_time, '1d', downwards_count_limit, 0, debug)
    stock_count = {stock:period_count for stock in work_stock_list}

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
                                                               force_positive_inflow=True,
                                                               use_cir_mcap=True,
                                                               use_money=use_money,
                                                               is_debug=debug)
    # remove STI stocks
    # cir_mcap = cir_mcap[cir_mcap['code'].map(lambda x: x[:3] != '688')]

    cir_mcap = cir_mcap.sort_values(by='mfc', ascending=False)
    cir_mcap = cir_mcap.reset_index();

    # only consider top 100
    stock_value_list = cir_mcap.head(1000)[['code', 'mfc']].values.tolist()

    if debug:
        print(stock_value_list)
    return stock_value_list


stock_list_20_val = filter_out_stock_by_mfc(stock_list, 20, current_time, False, debug)
stock_list_20 = [stock for stock,_ in stock_list_20_val]
stock_list_60_val = filter_out_stock_by_mfc(stock_list_20, 60, current_time, False, debug)
stock_list_60 = [stock for stock,_ in stock_list_60_val]
stock_list_120_val = filter_out_stock_by_mfc(stock_list_60, 120, current_time, False, debug)
stock_list_120 = [stock for stock,_ in stock_list_120_val]

####################################################################################################
print("Intermediate list 60: {0} {1}".format(stock_list_60, len(stock_list_60)))
print("Final list: {0} {1}".format(stock_list_120, len(stock_list_120)))
