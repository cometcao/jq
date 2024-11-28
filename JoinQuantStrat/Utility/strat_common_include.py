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
        print(f"filter_stocks_by_price_change with size: {len(stock_list)}")
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
        if stock_data.size == 0:
            continue

        max_loc = int(
            np.where(stock_data['high'] == max(stock_data['high']))[0][-1])
        peak_time = stock_data[max_loc]['date']
        peak_count = len(stock_data['high']) - max_loc
        if peak_count < downwards_count_limit:
            continue
        stock_count[stock] = peak_count
    if is_debug:
        print(f"get_stock_downwards_count with size: {len(stock_count.keys())}")
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
        print(f"get_cir_mcap get_valuation size: {cir_mcap.shape[0]}")
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
        print(f"get_cir_mcap after size: {cir_mcap.shape[0]}")
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

    capital_size = (cir_mcap['circulating_market_cap']
                    * (1 - cir_mcap['concentrated_ratio']
                       / 100
                       / cir_mcap['cir_total']
                       ) 
                    * 100000000) if use_cir_mcap else cir_mcap['circulating_market_cap']

    money_flow = cir_mcap['money'] if use_money else cir_mcap['net_amount_main'] * 10000

    cir_mcap['mfc'] = money_flow / capital_size / cir_mcap['sum_count']

    cir_mcap.index.name = 'code'
    if is_debug:
        print(f"get_main_money_inflow_over_total_money_over_time cir_mcap size: {cir_mcap.shape[0]}")
    return cir_mcap
