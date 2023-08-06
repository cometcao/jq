# -*- encoding: utf8 -*-
from jqdata import *
try:
    from kuanke.user_space_api import *
except:
    pass
import pandas as pd


def get_main_money_inflow_over_circulating_mcap(stock_list,
                                                prv_date,
                                                period_count,
                                                price_change_filter=None,
                                                adjust_concentrated=False,
                                                force_positive_inflow=True,
                                                is_debug=False):

    if price_change_filter is not None:
        # filter by past time price change
        history_price = get_bars(stock_list,
                                 count=period_count,
                                 unit='1d',
                                 fields='close',
                                 include_now=True,
                                 df=False)
        # remove nan values so that only stocks with data more than period
        # count remains
        history_price = {x: y for x, y in history_price.items() if len(
            y[~np.isnan(y['close'])]) >= period_count}

        stock_list = [x for x in stock_list
                      if x in history_price and (history_price[x]['close'][-1] - history_price[x]['close'][0]) / history_price[x]['close'][0] < price_change_filter / 100]
        if is_debug:
            print(stock_list[:10], len(stock_list))

    # circulating mcap
    cir_mcap = get_cir_mcap(stock_list, prv_date,
                            adjust_concentrated, is_debug)

    # main money inflow
    stock_money_data = get_money_flow(security_list=stock_list,
                                      end_date=prv_date,
                                      fields=['sec_code', 'net_amount_main'],
                                      count=period_count)
    net_data = stock_money_data.groupby("sec_code")['net_amount_main'].sum()

    cir_mcap = cir_mcap.merge(
        net_data.to_frame(), left_on='code', right_on='sec_code')
    if force_positive_inflow:
        cir_mcap = cir_mcap[cir_mcap['net_amount_main'] > 0]
    if is_debug:
        print(cir_mcap.head(10))
    if adjust_concentrated:
        cir_mcap['mfc'] = cir_mcap['net_amount_main'] / (cir_mcap['circulating_market_cap'] * (
            1 - cir_mcap['concentrated_ratio'] / 100 / cir_mcap['cir_total'])) / 10000
    else:
        cir_mcap['mfc'] = cir_mcap['net_amount_main'] / \
            cir_mcap['circulating_market_cap'] / 10000
    return cir_mcap


def filter_stocks_by_price_change(stock_list, period_count, price_change_filter, is_debug=False):
    # filter by past time price change history doesn't contain today's data
    history_price = get_bars(stock_list,
                             count=period_count,
                             unit='1d',
                             fields='close',
                             include_now=True,
                             df=False)
    # remove nan values so that only stocks with data more than period count
    # remains
    history_price = {x: y for x, y in history_price.items() if len(
        y[~np.isnan(y['close'])]) >= period_count}

    stock_list = [x for x in stock_list
                  if x in history_price and (history_price[x]['close'][-1] - history_price[x]['close'][0]) / history_price[x]['close'][0] < price_change_filter / 100]
    if is_debug:
        print(stock_list[:10], len(stock_list))
    return stock_list


def get_stock_downwards_count(stock_list,
                              period_count,
                              current_time,
                              level_check,
                              downwards_count_limit,
                              price_change_filter=None,
                              is_debug=False):
    if price_change_filter is not None:
        # filter by past time price change
        stock_list = filter_stocks_by_price_change(
            stock_list, period_count, price_change_filter, is_debug)

    stock_count = {}
    for stock in stock_list:
        stock_data = get_bars(stock,
                              count=period_count,
                              end_dt=current_time,
                              unit=level_check,
                              fields=['date', 'high', 'low'],
                              df=False,
                              include_now=True)

        max_loc = int(
            np.where(stock_data['high'] == max(stock_data['high']))[0][-1])
        peak_time = stock_data[max_loc]['date']
        peak_count = len(stock_data['high']) - max_loc
        if peak_count < downwards_count_limit:
            continue
        stock_count[stock] = peak_count
    return stock_count


def get_cir_mcap(stock_list,
                 current_time,
                 adjust_concentrated=False,
                 is_debug=False
                 ):
    # circulating mcap
    cir_mcap = get_valuation(stock_list, end_date=current_time,
                             count=1, fields=['circulating_market_cap', 'market_cap'])
    # cir_mcap = get_fundamentals(query(
    #         valuation.code,
    #         valuation.day,
    #         valuation.circulating_market_cap,
    #         valuation.total_market_cap.lable('market_cap')
    #     ).filter(
    #         valuation.code.in_(stock_list)
    #     ), date=prv_date)

    if is_debug:
        print(cir_mcap.head(10))

    if adjust_concentrated:
        cir_mcap['cir_total'] = cir_mcap['circulating_market_cap'] / \
            cir_mcap['market_cap']
        cir_mcap['concentrated_ratio'] = 0
        for stock in stock_list:
            q0 = query(finance.STK_SHAREHOLDER_FLOATING_TOP10).filter(
                finance.STK_SHAREHOLDER_FLOATING_TOP10.code == stock,
                finance.STK_SHAREHOLDER_FLOATING_TOP10.pub_date <= current_time.strftime(
                    '%Y-%m-%d')
            ).order_by(finance.STK_SHAREHOLDER_FLOATING_TOP10.pub_date.desc()).limit(10)
            latest_date_df = finance.run_query(q0)

            if latest_date_df.empty:
                continue

            q = query(finance.STK_SHAREHOLDER_FLOATING_TOP10).filter(
                finance.STK_SHAREHOLDER_FLOATING_TOP10.code == stock,
                finance.STK_SHAREHOLDER_FLOATING_TOP10.sharesnature == '流通A股',
                finance.STK_SHAREHOLDER_FLOATING_TOP10.pub_date == latest_date_df[
                    'pub_date'].values[0]
            ).order_by(finance.STK_SHAREHOLDER_FLOATING_TOP10.share_ratio.desc()).limit(10)
            top_10_gd = finance.run_query(q)
            circulating_concentrated_pct = top_10_gd[top_10_gd['share_ratio'] >= 5]['share_ratio'].sum(
            )
            cir_mcap.loc[cir_mcap['code'] == stock,
                         'concentrated_ratio'] = circulating_concentrated_pct
        if is_debug:
            print(cir_mcap.head(10))
    return cir_mcap


def get_main_money_inflow(stock_list, prv_date, stock_count_dict):
    stock_money_data_list = []
    for stock in stock_list:
        stock_money_data = get_money_flow(security_list=stock,
                                          end_date=prv_date,
                                          fields=['sec_code',
                                                  'net_amount_main'],
                                          count=stock_count_dict[stock])
        stock_money_data_list.append(stock_money_data)
    net_data = pd.concat(stock_money_data_list).groupby(
        "sec_code")['net_amount_main'].sum()
    return net_data


def get_main_money_inflow_over_time_over_circulating_mcap(
        stock_count_dict,
        prv_date,
        price_change_filter=None,
        adjust_concentrated=False,
        force_positive_inflow=True,
        is_debug=False):
    stock_list = list(stock_count_dict.keys())

    # circulating mcap
    cir_mcap = get_cir_mcap(stock_list, prv_date,
                            adjust_concentrated, is_debug)

    # main money inflow
    net_data = get_main_money_inflow(stock_list, prv_date, stock_count_dict)

    cir_mcap = cir_mcap.merge(
        net_data.to_frame(), left_on='code', right_on='sec_code')
    cir_mcap['sum_count'] = cir_mcap['code'].map(stock_count_dict)
    if force_positive_inflow:
        cir_mcap = cir_mcap[cir_mcap['net_amount_main'] > 0]
    if is_debug:
        print(cir_mcap.head(10))
    if adjust_concentrated:
        cir_mcap['mfc'] = cir_mcap['net_amount_main'] / cir_mcap['sum_count'] / \
            (cir_mcap['circulating_market_cap'] * (1 -
                                                   cir_mcap['concentrated_ratio'] / 100 / cir_mcap['cir_total'])) / 10000
    else:
        cir_mcap['mfc'] = cir_mcap['net_amount_main'] / \
            cir_mcap['sum_count'] / \
            (cir_mcap['circulating_market_cap']) / 10000
    return cir_mcap


def get_main_money_inflow_over_total_money_over_time(
        stock_count_dict,
        current_time,
        force_positive_inflow=True,
        adjust_concentrated=True,
        use_cir_mcap=True,
        use_money=True,
        is_debug=False):
    stock_list = list(stock_count_dict.keys())

    # circulating mcap
    cir_mcap = get_cir_mcap(stock_list, current_time,
                            adjust_concentrated, is_debug)
    cir_mcap = cir_mcap.set_index('code')

    # all traded money over the designated period
    stock_money_data = {}
    for stock in stock_list:
        money_data = get_bars(stock,
                              count=stock_count_dict[stock],
                              end_dt=current_time,
                              unit='1d',
                              fields=['money'],
                              df=False,
                              include_now=True)
        stock_money_data[stock] = money_data['money'].sum()
    # cir_mcap = pd.DataFrame.from_dict(stock_money_data, orient='index', columns=['money'])
    # results in real money number
    cir_mcap['money'] = pd.Series(stock_money_data)

    if is_debug:
        print(cir_mcap.head(10))

    # main money inflow
    net_data = get_main_money_inflow(
        stock_list, current_time, stock_count_dict)

    cir_mcap = cir_mcap.merge(
        net_data.to_frame(), left_index=True, right_index=True)
    cir_mcap['sum_count'] = pd.Series(stock_count_dict)
    if force_positive_inflow:
        cir_mcap = cir_mcap[cir_mcap['net_amount_main'] > 0]
    else:
        cir_mcap.loc[:, 'net_amount_main'] = abs(cir_mcap['net_amount_main'])

    capital_size = (cir_mcap['circulating_market_cap'] * (1 - cir_mcap['concentrated_ratio'] / 100 /
                                                          cir_mcap['cir_total']) * 100000000) if use_cir_mcap else cir_mcap['circulating_market_cap']

    money_flow = cir_mcap['money'] if use_money else cir_mcap['net_amount_main'] * 10000

    cir_mcap['mfc'] = money_flow / capital_size / cir_mcap['sum_count']

    cir_mcap.index.name = 'code'
    if is_debug:
        print(cir_mcap.head(10))
    return cir_mcap

############################
############################
############################
# single stock analysis

# from jqdata import *
# from datetime import datetime, timedelta
# import pandas as pd
# pd.set_option('display.max_columns', 500)
# pd.set_option('display.max_rows', 500)
#
# stocks = ['301035.XSHE']
# working_date = datetime.today()# - timedelta(days=1)
# # working_date = datetime.strptime('2022-10-11', "%Y-%m-%d")
# inflow_count = 2
# display_count = 10
#
# cir_mcap = get_valuation(stocks,
#                          end_date=working_date,
#                         count=display_count, fields=['circulating_market_cap','market_cap'])
# cir_mcap['cir_total'] = cir_mcap['circulating_market_cap'] / cir_mcap['market_cap']
# cir_mcap['concentrated_ratio'] = 0
# for stock in stocks:
#     q0=query(finance.STK_SHAREHOLDER_FLOATING_TOP10).filter(
#         finance.STK_SHAREHOLDER_FLOATING_TOP10.code==stock,
#         finance.STK_SHAREHOLDER_FLOATING_TOP10.pub_date<=working_date.strftime('%Y-%m-%d')
#     ).order_by(finance.STK_SHAREHOLDER_FLOATING_TOP10.pub_date.desc()).limit(10)
#     latest_date_df = finance.run_query(q0)
#
#     q=query(finance.STK_SHAREHOLDER_FLOATING_TOP10).filter(
#         finance.STK_SHAREHOLDER_FLOATING_TOP10.code==stock,
#         finance.STK_SHAREHOLDER_FLOATING_TOP10.sharesnature=='流通A股',
#         finance.STK_SHAREHOLDER_FLOATING_TOP10.pub_date==latest_date_df['pub_date'].values[0]
#     ).order_by(finance.STK_SHAREHOLDER_FLOATING_TOP10.share_ratio.desc() ).limit(10)
#     top_10_gd=finance.run_query(q)
# #     print(top_10_gd)
#
#     circulating_concentrated_pct = top_10_gd[top_10_gd['share_ratio']>=5]['share_ratio'].sum()
#     cir_mcap.loc[cir_mcap['code'] == stock, 'concentrated_ratio'] = circulating_concentrated_pct
#
# cir_mcap['day'] = cir_mcap['day'].apply(lambda x: pd.Timestamp(x))
#
# stock_money_data = get_money_flow(security_list=stocks,
#                       end_date=working_date,
#                       fields=['sec_code','net_amount_main', 'date'],
#                       count=display_count)
#
# cir_mcap = cir_mcap.merge(stock_money_data,
#                           left_on=['code','day'], right_on=['sec_code', 'date'])
# cir_mcap = cir_mcap.sort_values(by=['code', 'day'])
#
# net_amount_roll = cir_mcap.groupby("sec_code")['net_amount_main'].rolling(inflow_count).sum()
# # print(net_amount_roll)
# cir_mcap['net_amount_main_roll'] = net_amount_roll.values
# cir_mcap['mfc'] = cir_mcap['net_amount_main_roll']/(cir_mcap['circulating_market_cap'] * (1-cir_mcap['concentrated_ratio'] / 100/cir_mcap['cir_total']))/10000
#
# print(cir_mcap[['code', 'day', 'net_amount_main', 'net_amount_main_roll', 'mfc']])

# # main money inflow over ciculating market cap adjusted by top 10 concentrated ownership
# from jqdata import *
# from datetime import datetime, timedelta
# import pandas as pd
# pd.set_option('display.max_columns', 500)
#
# from biaoLiStatus import TopBotType
# from chan_common_include import ZouShi_Type, Chan_Type
# from strat_common_include import get_stock_downwards_count, get_main_money_inflow_over_total_money_over_time
# from chan_kbar_filter import analyze_MA_zoushi_by_stock
#
# # current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
# current_time = datetime.now()
# working_date = datetime.today()# - timedelta(days=1)
# print("current time: {0}".format(current_time))
# # working_date = datetime.strptime('2022-04-28', "%Y-%m-%d")
#
# period_count = 20
# downwards_count_limit = 10 if period_count == 60 else 5
# print("period count: {0}, limit: {1}".format(period_count, downwards_count_limit))
# debug = False
#
# level_check = '1d'
# stock_list = get_all_securities(['stock']).index.values.tolist()
#
# # I: find a rough downwards movement and worm out the period
# stock_count = get_stock_downwards_count(stock_list, period_count, current_time, '1d', downwards_count_limit, 0, debug)
#
#
# # II: find positive top money inflow / free share portion ##############
# # check all stocks
# # cir_mcap = get_main_money_inflow_over_time_over_circulating_mcap(stock_count,
# #                                                                current_time,
# #                                                                price_change_filter = 0,
# #                                                                adjust_concentrated=True,
# #                                                                force_positive_inflow=True,
# #                                                                is_debug=debug)
# cir_mcap = get_main_money_inflow_over_total_money_over_time(stock_count,
#                                                            current_time,
#                                                            force_positive_inflow=False,
#                                                            use_cir_mcap=True,
#                                                            use_money=True,
#                                                            is_debug=debug)
#
# # remove STI stocks
# # cir_mcap = cir_mcap[cir_mcap['code'].map(lambda x: x[:3] != '688')]
#
# cir_mcap = cir_mcap.sort_values(by='mfc', ascending=False)
# cir_mcap = cir_mcap.reset_index();
#
# # only consider top 100
# stock_value_list = cir_mcap.head(100)[['code', 'mfc']].values.tolist()
#
# print(stock_value_list)
# money_inflow_list = [stock for stock, _ in stock_value_list]
#
# # III: apply zoushi analysis ###########################################
# expected_zoushi_down = [ZouShi_Type.Pan_Zheng, ZouShi_Type.Qu_Shi_Down] #
# expected_exhaustion_down = [Chan_Type.PANBEI, Chan_Type.BEICHI] #Chan_Type.INVIGORATE
#
# def get_translated_count(count, level):
#     if count <= 20 and level == '1d':
#         return [(count * 4, '60m'), (count * 8, '30m')]
#     elif count <= 60 and level == '1d':
#         return [(count, '1d')]
#     else:
#         return [(count, level)]
# picked_stocks = []
# for stock in money_inflow_list:
#     current_time=pd.datetime.now()
#
#     for check_count_level, level in get_translated_count(period_count, '1d'):
#         stock_data = get_bars(stock,
#                                count=check_count_level,
#                                end_dt=current_time,
#                                unit=level,
#                                fields= ['date','high', 'low'],
#                                df = False,
#                                include_now=True)
#
#         max_loc = int(np.where(stock_data['high'] == max(stock_data['high']))[0][-1])
#         peak_time = stock_data[max_loc]['date']
#         peak_count = len(stock_data['high']) - max_loc
#         if peak_count <= 0:
#             continue
#
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
