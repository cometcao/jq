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
# current_time = datetime.now() - timedelta(days=30)
print("current time: {0}".format(current_time))
# working_date = datetime.strptime('2022-04-28', "%Y-%m-%d")

debug = False
level_check = '1d'
stock_list = get_all_securities(['stock'], date=current_time).index.values.tolist()


def filter_out_stock_by_mfc(work_stock_list, period_count, current_time, use_money, only_downward_slope, output, debug):
    downwards_count_limit = 5
    print(f"period count: {period_count}, use_money: {use_money}, +only_down_slope: {only_downward_slope}, limit: {downwards_count_limit}, output: {output}")
    # I: find a rough downwards movement and worm out the period
    if only_downward_slope:
        stock_count = get_stock_downwards_count(
           work_stock_list, period_count, current_time, '1d', downwards_count_limit, 0, debug)
    else:
        stock_count = {stock:period_count for stock in work_stock_list}

    # II: find positive top money inflow / free share portion ######################################
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
    
    stock_value_dict = cir_mcap.head(output)[['code', 'mfc']].set_index('code').T.to_dict('records')[0]

    if debug:
        print(stock_value_dict)
    return stock_value_dict

# False True 17
# False False 21
# True True 28 26 27 30jul 56 1Aug 50  2Aug 50
# True False 19

stock_list_5_val = filter_out_stock_by_mfc(stock_list, 5, current_time, False, True, 1000, debug)
stock_list_5 = list(stock_list_5_val.keys())
stock_list_20_val = filter_out_stock_by_mfc(stock_list_5, 20, current_time, False, False, 1000, debug)
stock_list_20 = list(stock_list_20_val.keys())
# stock_list_60_val = filter_out_stock_by_mfc(stock_list_5, 60, current_time, False, False, 1000, debug)
# stock_list_60 = [stock for stock,_ in stock_list_60_val]
# stock_list_120_val = filter_out_stock_by_mfc(stock_list, 120, current_time, False, False, debug)
# stock_list_120 = [stock for stock,_ in stock_list_120_val]
final_list = [stock for stock in stock_list_20 if stock_list_5_val[stock] < stock_list_20_val[stock]]
# final_list = list(set(stock_list_5) & set(stock_list_20) & set(stock_list_60))
####################################################################################################
print("Intermediate list 5: {0}".format(len(stock_list_5)))
print("Intermediate list 20: {0}".format(len(stock_list_20)))
# print("Intermediate list 60: {0}".format(len(stock_list_60)))
# print("Intermediate list 120: {0}".format(len(stock_list_120)))
print("Final list: {0} {1}".format(final_list, len(final_list)))

# money_inflow_list = stock_value_list
# III: apply zoushi analysis ##################################################################
# expected_zoushi_down = [ZouShi_Type.Pan_Zheng, ZouShi_Type.Qu_Shi_Down] #  
# expected_exhaustion_down = [Chan_Type.PANBEI, Chan_Type.BEICHI] #Chan_Type.INVIGORATE

# def get_translated_count(count, level):
#     if count <= 20 and level == '1d':
#         return [(count * 4, '60m'), (count * 8, '30m')]
#     elif count <= 60 and level == '1d':
#         return [(count, '1d')] 
#     else:
#         return [(count, level)]
# picked_stocks = []
# for stock in money_inflow_list:
#     for check_count_level, level in get_translated_count(20, '1d'):
#         stock_data = get_bars(stock, 
#                                count=check_count_level, 
#                                end_dt=current_time, 
#                                unit=level,
#                                fields= ['date','high', 'low'], 
#                                df = False,
#                                include_now=True)

#         max_loc = int(np.where(stock_data['high'] == max(stock_data['high']))[0][-1])
#         peak_time = stock_data[max_loc]['date']
#         peak_count = len(stock_data['high']) - max_loc
#         if peak_count <= 0:
#             continue

#         result_zoushi, result_exhaustion = analyze_MA_zoushi_by_stock(stock=stock,
#                                                                   period=level, 
#                                                                   count=peak_count,
#                                                                   end_dt=current_time, 
#                                                                   df=False, 
#                                                                   zoushi_types=expected_zoushi_down, 
#                                                                   direction=TopBotType.top2bot)
#         if result_zoushi in expected_zoushi_down and result_exhaustion in expected_exhaustion_down:
#             print("stock: {0} zoushi: {1} exhaustion:{2} level:{3}".format(stock, result_zoushi, result_exhaustion, level))
#             picked_stocks.append(stock)
#             continue
# print(picked_stocks)