from jqdata import *
import pandas as pd

def get_main_money_inflow_over_circulating_mcap(stock_list, context, period_count, adjust_concentrated=False, is_debug=False):
    # circulating mcap
    cir_mcap = get_valuation(stock_list, end_date=context.previous_date, 
                        count=1, fields=['circulating_market_cap'])
    # cir_mcap = get_fundamentals(query(
    #         valuation.code,
    #         valuation.day,
    #         valuation.circulating_market_cap
    #     ).filter(
    #         # 这里不能使用 in 操作, 要使用in_()函数
    #         valuation.code.in_(stock_list)
    #     ), date=context.previous_date)
    if is_debug:
        print(cir_mcap.head(10))
    
    if adjust_concentrated:
        cir_mcap['concentrated_ratio'] = 0
        for stock in stock_list:
            q=query(finance.STK_SHAREHOLDER_FLOATING_TOP10).filter(
                finance.STK_SHAREHOLDER_FLOATING_TOP10.code==stock,
                finance.STK_SHAREHOLDER_FLOATING_TOP10.pub_date>'2015-01-01').limit(10)
            top_10_gd=finance.run_query(q)
            circulating_concentrated_pct = top_10_gd[top_10_gd['share_ratio']>=5]['share_ratio'].sum()
            cir_mcap.loc[cir_mcap['code'] == stock, 'concentrated_ratio'] = circulating_concentrated_pct
        if is_debug:
            print(cir_mcap.head(10))
    
    # main money inflow
    stock_money_data = get_money_flow(security_list=stock_list, 
                          end_date=context.previous_date, 
                          fields=['sec_code','net_amount_main'], 
                          count=period_count)
    net_data= stock_money_data.groupby("sec_code")['net_amount_main'].sum()
    cir_mcap = cir_mcap.merge(net_data.to_frame(), left_on='code', right_on='sec_code')
    if is_debug:
        print(cir_mcap.head(10))
    if adjust_concentrated:
        cir_mcap['mfc'] = cir_mcap['net_amount_main']/(cir_mcap['circulating_market_cap'] * (100 - cir_mcap['concentrated_ratio']) / 100)
    else:
        cir_mcap['mfc'] = cir_mcap['net_amount_main']/cir_mcap['circulating_market_cap']
    return cir_mcap