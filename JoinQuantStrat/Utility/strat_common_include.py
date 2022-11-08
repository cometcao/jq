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
                                                is_debug=False):
    
    if price_change_filter is not None:
        # filter by past time price change
        history_price = history(count=period_count, 
                                field='close', 
                                security_list = stock_list, 
                                skip_paused = True,
                                df=False)
        # remove nan values so that only stocks with data more than period count remains
        history_price = {x:y for x,y in history_price.items() if len(y[~np.isnan(y)]) >= period_count}
        
        stock_list = [x for x in stock_list if x in history_price and (history_price[x][-1]-history_price[x][0])/history_price[x][0] < price_change_filter / 100]
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
    if is_debug:
        print(cir_mcap.head(10))
    if adjust_concentrated:
        cir_mcap['mfc'] = cir_mcap['net_amount_main']/(cir_mcap['circulating_market_cap'] * (1-cir_mcap['concentrated_ratio']/100/cir_mcap['cir_total']))
    else:
        cir_mcap['mfc'] = cir_mcap['net_amount_main']/cir_mcap['circulating_market_cap']
    return cir_mcap