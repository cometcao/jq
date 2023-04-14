# -*- encoding: utf8 -*-
from jqdata import *
try:
    from kuanke.user_space_api import *
except:
    pass
import pandas as pd


def filter_stocks_by_price_change(stock_list, period_count, price_change_filter, is_debug=False):
    # filter by past time price change history doesn't contain today's data
    history_price = get_bars(stock_list,
                            count=period_count, 
                            unit='1d', 
                            fields='close',
                            include_now = True,
                            df=False)
    # remove nan values so that only stocks with data more than period count remains
    history_price = {x:y for x,y in history_price.items() if len(y[~np.isnan(y['close'])]) >= period_count}
    
    stock_list = [x for x in stock_list 
                  if x in history_price and (history_price[x]['close'][-1]-history_price[x]['close'][0])/history_price[x]['close'][0] < price_change_filter / 100]
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
        stock_list = filter_stocks_by_price_change(stock_list, period_count, price_change_filter, is_debug)
    
    stock_count = {}
    for stock in stock_list:
        stock_data = get_bars(stock, 
                               count=period_count, 
                               end_dt=current_time, 
                               unit = level_check,
                               fields = ['date','high', 'low'], 
                               df = False,
                               include_now=True)
    
        max_loc = int(np.where(stock_data['high'] == max(stock_data['high']))[0][-1])
        peak_time = stock_data[max_loc]['date']
        peak_count = len(stock_data['high']) - max_loc
        if peak_count < downwards_count_limit:
            continue
        stock_count[stock] = peak_count
    return stock_count

def get_main_money_inflow_over_time_over_circulating_mcap(
                                                stock_count_dict,
                                                prv_date, 
                                                price_change_filter=None,
                                                adjust_concentrated=False, 
                                                force_positive_inflow=True,
                                                is_debug=False):
    stock_list = list(stock_count_dict.keys())
    
    # circulating mcap
    cir_mcap = get_valuation(stock_list, end_date=prv_date, 
                        count=1, fields=['circulating_market_cap', 'market_cap'])
    
    if is_debug:
        print(cir_mcap.head(10))
    
    if adjust_concentrated:
        cir_mcap['cir_total'] = cir_mcap['circulating_market_cap'] / cir_mcap['market_cap']
        cir_mcap['concentrated_ratio'] = 0
        for stock in stock_list:
            q0=query(finance.STK_SHAREHOLDER_FLOATING_TOP10).filter(
                finance.STK_SHAREHOLDER_FLOATING_TOP10.code==stock,
                finance.STK_SHAREHOLDER_FLOATING_TOP10.pub_date<=prv_date.strftime('%Y-%m-%d')
            ).order_by(finance.STK_SHAREHOLDER_FLOATING_TOP10.pub_date.desc()).limit(10)
            latest_date_df = finance.run_query(q0)
            
            if latest_date_df.empty:
                continue
            
            q=query(finance.STK_SHAREHOLDER_FLOATING_TOP10).filter(
                finance.STK_SHAREHOLDER_FLOATING_TOP10.code==stock,
                finance.STK_SHAREHOLDER_FLOATING_TOP10.sharesnature=='流通A股',
                finance.STK_SHAREHOLDER_FLOATING_TOP10.pub_date==latest_date_df['pub_date'].values[0]
                ).order_by(finance.STK_SHAREHOLDER_FLOATING_TOP10.share_ratio.desc()).limit(10)
            top_10_gd=finance.run_query(q)
            circulating_concentrated_pct = top_10_gd[top_10_gd['share_ratio']>=5]['share_ratio'].sum()
            cir_mcap.loc[cir_mcap['code'] == stock, 'concentrated_ratio'] = circulating_concentrated_pct
        if is_debug:
            print(cir_mcap.head(10))
    
    # main money inflow
    stock_money_data_list = []
    for stock in stock_list:
        stock_money_data = get_money_flow(security_list=stock, 
                              end_date=prv_date, 
                              fields=['sec_code','net_amount_main'], 
                              count=stock_count_dict[stock])
        stock_money_data_list.append(stock_money_data)
    
    net_data= pd.concat(stock_money_data_list).groupby("sec_code")['net_amount_main'].sum()
        
    cir_mcap = cir_mcap.merge(net_data.to_frame(), left_on='code', right_on='sec_code')
    cir_mcap['sum_count'] = cir_mcap['code'].map(stock_count_dict)
    if force_positive_inflow:
        cir_mcap = cir_mcap[cir_mcap['net_amount_main'] > 0]
    if is_debug:
        print(cir_mcap.head(10))
    if adjust_concentrated:
        cir_mcap['mfc'] = cir_mcap['net_amount_main']/cir_mcap['sum_count']/(cir_mcap['circulating_market_cap'] * (1-cir_mcap['concentrated_ratio']/100/cir_mcap['cir_total']))
    else:
        cir_mcap['mfc'] = cir_mcap['net_amount_main']/cir_mcap['sum_count']/cir_mcap['circulating_market_cap']
    return cir_mcap

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
                                include_now = True,
                                df=False)
        # remove nan values so that only stocks with data more than period count remains
        history_price = {x:y for x,y in history_price.items() if len(y[~np.isnan(y['close'])]) >= period_count}
        
        stock_list = [x for x in stock_list 
                      if x in history_price and (history_price[x]['close'][-1]-history_price[x]['close'][0])/history_price[x]['close'][0] < price_change_filter / 100]
        if is_debug:
            print(stock_list[:10], len(stock_list))
    
    
    # circulating mcap
    cir_mcap = get_valuation(stock_list, end_date=prv_date, 
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
        cir_mcap['cir_total'] = cir_mcap['circulating_market_cap'] / cir_mcap['market_cap']
        cir_mcap['concentrated_ratio'] = 0
        for stock in stock_list:
            q0=query(finance.STK_SHAREHOLDER_FLOATING_TOP10).filter(
                finance.STK_SHAREHOLDER_FLOATING_TOP10.code==stock,
                finance.STK_SHAREHOLDER_FLOATING_TOP10.pub_date<=prv_date.strftime('%Y-%m-%d')
            ).order_by(finance.STK_SHAREHOLDER_FLOATING_TOP10.pub_date.desc()).limit(10)
            latest_date_df = finance.run_query(q0)
            
            if latest_date_df.empty:
                continue
            
            q=query(finance.STK_SHAREHOLDER_FLOATING_TOP10).filter(
                finance.STK_SHAREHOLDER_FLOATING_TOP10.code==stock,
                finance.STK_SHAREHOLDER_FLOATING_TOP10.sharesnature=='流通A股',
                finance.STK_SHAREHOLDER_FLOATING_TOP10.pub_date==latest_date_df['pub_date'].values[0]
                ).order_by(finance.STK_SHAREHOLDER_FLOATING_TOP10.share_ratio.desc()).limit(10)
            top_10_gd=finance.run_query(q)
            circulating_concentrated_pct = top_10_gd[top_10_gd['share_ratio']>=5]['share_ratio'].sum()
            cir_mcap.loc[cir_mcap['code'] == stock, 'concentrated_ratio'] = circulating_concentrated_pct
        if is_debug:
            print(cir_mcap.head(10))
    
    # main money inflow
    stock_money_data = get_money_flow(security_list=stock_list, 
                          end_date=prv_date, 
                          fields=['sec_code','net_amount_main'], 
                          count=period_count)
    net_data= stock_money_data.groupby("sec_code")['net_amount_main'].sum()
    cir_mcap = cir_mcap.merge(net_data.to_frame(), left_on='code', right_on='sec_code')
    if force_positive_inflow:
        cir_mcap = cir_mcap[cir_mcap['net_amount_main'] > 0]
    if is_debug:
        print(cir_mcap.head(10))
    if adjust_concentrated:
        cir_mcap['mfc'] = cir_mcap['net_amount_main']/(cir_mcap['circulating_market_cap'] * (1-cir_mcap['concentrated_ratio']/100/cir_mcap['cir_total']))
    else:
        cir_mcap['mfc'] = cir_mcap['net_amount_main']/cir_mcap['circulating_market_cap']
    return cir_mcap

def get_main_money_inflow_over_total_money_over_time(
                                                stock_count_dict,
                                                current_time, 
                                                force_positive_inflow=True,
                                                is_debug=False):
    stock_list = list(stock_count_dict.keys())
    
    # all traded money over the designated period
    stock_money_data = {}
    for stock in stock_list:
        money_data = get_bars(stock, 
                               count=stock_count_dict[stock], 
                               end_dt=current_time, 
                               unit = '1d',
                               fields = ['money'], 
                               df = False,
                               include_now=True)
        stock_money_data[stock] = money_data['money'].sum()
    cir_mcap = pd.DataFrame.from_dict(stock_money_data, orient='index', columns=['money'])    
    cir_mcap.index.name = 'code'
    if is_debug:
        print(cir_mcap.head(10))
        
    # main money inflow
    stock_money_data_list = []
    for stock in stock_list:
        stock_money_data = get_money_flow(security_list=stock, 
                              end_date=current_time, 
                              fields=['sec_code','net_amount_main'], 
                              count=stock_count_dict[stock])
        stock_money_data_list.append(stock_money_data)
    
    net_data= pd.concat(stock_money_data_list).groupby("sec_code")['net_amount_main'].sum()
        
    cir_mcap = cir_mcap.merge(net_data.to_frame(), left_on='code', right_on='sec_code')
    cir_mcap['sum_count'] = cir_mcap['code'].map(stock_count_dict)
    if force_positive_inflow:
        cir_mcap = cir_mcap[cir_mcap['net_amount_main'] > 0]
    if is_debug:
        print(cir_mcap.head(10))

    cir_mcap['mfc'] = cir_mcap['net_amount_main']/cir_mcap['money']/cir_mcap['sum_count']
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
