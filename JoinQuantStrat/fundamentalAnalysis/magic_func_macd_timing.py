# ħ����ʽѡ��+MACD��ʱ v0.8

import numpy as np
import pandas as pd
import datetime as dt
import talib as tl
import pickle

def initialize(context):
    # ���÷���
    set_commission(PerTrade(buy_cost=0.00025, sell_cost=0.00125, min_cost=5))
    # ���û�׼ָ��������300ָ�� '000300.XSHG'
    set_benchmark('000300.XSHG')
    # ʹ����ʵ�۸�ز�
    set_option('use_real_price', True)
    
    # ���죬��ֹ����δ������
    g.yesterday = context.current_dt -dt.timedelta(1)
    
    # ��ǰѡ���20ֻ��Ʊ
    g.curr_stocks=None
    # ����ǰ20ֻ��Ʊ�ĸ�Ȩ�۸�Ϳ���һ���Զ���ָ��
    g.stocks_index = None
    
    # ----  ����������뼾��ͳ�����һ��Ķ�Ӧ ---
    # 5�·�Ӧ�ó�����ȥ��4�������걨���ͱ���1����
    # 9�·�Ӧ�ó����˱���2�������б���
    # 11��Ӧ�ó����˱���3����
    # ����û����Ĺ�Ʊ���������ֹ�Ʊ���٣�
    g.map_stat_date = {5:'03-31',9:'06-30',11:'09-30'}

    g.finish_select_stocks = False
    run_monthly(monthly_handle, 2, time='open')

# ÿ�µ���һ�Σ���������������ʱ����ʽѡ��

# ÿ����һ�μ���ѡһ�ι�,Ȼ�����¹�����Ȩ��ָ��
def monthly_handle(context) :
    # ���꼾����ѡ��
    if g.yesterday.month not in g.map_stat_date.keys() and not (g.stocks_index is None):
        return
    
    # ѡ����20ֻ��Ʊ
    g.curr_stocks = select_stocks(context,20)
    
    # ������20ֻ��Ʊ������Ȩ���Զ���ָ����
    #    �Ժ�ÿ�컹��Ҫ����ָ������
    #    ע���ָ���ĳɷֹɱ������ǰ��Ȩ����
    stocks_close = history(60, unit='1d', field='close', security_list=g.curr_stocks, df=True)
    g.stocks_index = stocks_close.sum(axis=1).values
    
    # ��Ǹ������һ��ѡ��
    g.finish_select_stocks = True

# Ҫ����ز�
def handle_data(context, data):
    # �ϸ�������
    g.yesterday = context.current_dt -dt.timedelta(1)
    
    # ��δѡ����
    if g.stocks_index is None or g.curr_stocks is None:
        return
    
    # �����Զ�ָ��
    stock_close = history(1, unit='1d', field='close', security_list=g.curr_stocks, df=True)
    _point = stock_close.sum(axis=1).values[-1]
    g.stocks_index = g.stocks_index.tolist()
    g.stocks_index.append(_point)
    g.stocks_index = np.array(g.stocks_index)
    
    sig = signal_MACD(g.stocks_index)
    unit_money = context.portfolio.portfolio_value/20
    
    # �����ѡ��ɣ����Ƚ��Ϲ�Ʊ����
    if g.finish_select_stocks:
        buy_stocks = g.curr_stocks
        for _stock in context.portfolio.positions:
            if _stock in buy_stocks:
                buy_stocks = buy_stocks[buy_stocks != _stock]
                continue
            order_target(str(_stock), 0)
        if sig != -1:
            for _stock in buy_stocks:
                order_value(str(_stock), unit_money)
        log.info(u'���ֻ���')
        g.finish_select_stocks = False
        return

    # ��������£������ź�����
    if sig == 1:
        for _stock in g.curr_stocks:
            order_value(str(_stock), unit_money)
        log.info(u'��潨��')
    elif sig == -1:
        for _stock in context.portfolio.positions:
            order_target(str(_stock), 0)
        log.info(u'�������')

# TRIX�źţ�����3��ȷ�ϣ�
def signal_TRIX(close):
    trix = tl.TRIX(close,timeperiod=12) 
    trima = tl.MA(trix,timeperiod=20) 
    # ������һʱ��DIFF��DEA����
    #record(TRIX=trix[-1], TRIMA=trima[-1])
    record(TRIX_DELTA=trix[-1]-trima[-1])
    # ����3��ȷ�ϵĽ��
    if trix[-1] > trima[-1] and trix[-2] > trima[-2] \
      and trix[-3] > trima[-3] and trix[-4] < trima[-4]:
        return 1
    # ����3��ȷ�ϵ�����
    if trix[-1] < trima[-1] and trix[-2] < trima[-2] \
      and trix[-3] < trima[-3] and trix[-4] > trima[-4]:
        return -1
    # �м�״̬
    return 0

# MACD�źţ�����3��ȷ�ϣ�               
def signal_MACD(close):
    diff,dea,macd = tl.MACD(close)  # �����macd��ͬ��˳��1/2
    # ������һʱ��DIFF��DEA����
    #record(diff=diff[-1], dea=dea[-1])
    record(MACD=2*macd[-1])
    # ����3��ȷ�ϵĽ��
    if macd[-1] > 0 and macd[-2] > 0 and macd[-3] > 0 and macd[-4] < 0:
        return 1
    # ����3��ȷ�ϵ�����
    if macd[-1] < 0 and macd[-2] < 0 and macd[-3] < 0 and macd[-4] > 0:
        return -1
    # �м�״̬
    return 0
    
                
# ����ħ����ʽ����Ľ������ѡ��
def select_stocks(context,num):
    ROC,EY = cal_magic_formula(context)

    # ��ROC �� EY �������
    ROC_EY = pd.DataFrame({'ROC': ROC,'EY': EY})

    # �� ROC���н�������, ��¼���
    ROC_EY = ROC_EY.sort('ROC',ascending=False)
    idx = pd.Series(np.arange(1,len(ROC)+1), index=ROC_EY['ROC'].index.values)
    ROC_I = pd.DataFrame({'ROC_I': idx})
    ROC_EY = pd.concat([ROC_EY, ROC_I], axis=1)

    # �� EY���н�������, ��¼���
    ROC_EY = ROC_EY.sort('EY',ascending=False)
    idx = pd.Series(np.arange(1,len(EY)+1), index=ROC_EY['EY'].index.values)
    EY_I = pd.DataFrame({'EY_I': idx})
    ROC_EY = pd.concat([ROC_EY, EY_I], axis=1)

    # �������ͣ�����¼֮
    roci = ROC_EY['ROC_I']
    eyi = ROC_EY['EY_I']
    idx = roci + eyi
    SUM_I = pd.DataFrame({'SUM_I': idx})
    ROC_EY = pd.concat([ROC_EY, SUM_I], axis=1)

    # ����źͣ�������������Ȼ��ѡ��������ǰ��20ֻ��Ʊ
    ROC_EY = ROC_EY.sort('SUM_I')
    ROC_EY = ROC_EY.head(num)
    
    return ROC_EY.index.values
    
# ����ħ����ʽ
def cal_magic_formula(context):
    stocks = filter_stocks(context)
    
    q = query(    
        balance.code,                         # ��Ʊ����
        balance.pubDate,                        # ��˾�����Ʊ�����
        balance.statDate,                       # �Ʊ�ͳ�Ƶļ��ȵ����һ��, ����2015-03-31, 2015-06-30
        income.net_profit,                      # ������(Ԫ)
        income.financial_expense,               # �������(Ԫ)
        income.income_tax_expense,              # ����˰����(Ԫ)
        balance.fixed_assets,                   # �̶��ʲ�(Ԫ)
        balance.construction_materials,         # ��������(Ԫ)
        balance.constru_in_process,             # �ڽ�����(Ԫ)
        balance.fixed_assets_liquidation,       # �̶��ʲ�����(Ԫ)
        balance.total_current_assets,           # �����ʲ��ϼ�(Ԫ)
        balance.total_current_liability,        # ������ծ�ϼ�(Ԫ)
        valuation.market_cap,                   # ����ֵ(��Ԫ)
        #valuation.circulating_cap,              # ��ͨ�ɱ�(���)  110000  160000
        balance.total_liability,                # ��ծ�ϼ�(Ԫ)
        cash_flow.cash_and_equivalents_at_end   # ��ĩ�ֽ��ֽ�ȼ������(Ԫ)
    ).filter(
        income.net_profit > 0,
        #valuation.circulating_cap < 110000,   
        balance.code.in_(stocks)
    )
    df = get_fundamentals(q, date=g.yesterday.strftime('%Y-%m-%d')).fillna(value=0).set_index('code')
    _stat_date = g.map_stat_date.get(g.yesterday.month,None)
    if not (_stat_date is None):
        df=df[df.statDate == '%s-%s'%(g.yesterday.year,_stat_date)]
    
    # Ϣ˰ǰ����(EBIT) = ������ + ������� + ����˰����
    NP = df['net_profit']
    FE = df['financial_expense']
    TE = df['income_tax_expense']
    EBIT = NP + FE + TE

    # �̶��ʲ�����(Net Fixed Assets) = �̶��ʲ� - �������� - �ڽ����� - �̶��ʲ�����
    FA = df['fixed_assets']
    CM = df['construction_materials']
    CP = df['constru_in_process']
    FAL = df['fixed_assets_liquidation']
    NFA = FA - CM - CP - FAL

    # ��Ӫ���ʱ�(Net Working Capital)= �����ʲ��ϼƣ�������ծ�ϼ�
    TCA = df['total_current_assets']
    TCL = df['total_current_liability']
    NWC = TCA - TCL

    # ��ҵ��ֵ(Enterprise Value) = ����ֵ + ��ծ�ϼ� �C ��ĩ�ֽ��ֽ�ȼ������
    MC = df['market_cap']*100000000
    TL = df['total_liability']
    TC = df['cash_and_equivalents_at_end']
    EV = MC + TL - TC

    # Net Working Capital + Net Fixed Assets
    NCA = NWC + NFA

    # �޳� NCA �� EV �����Ĺ�Ʊ
    tmp = set(df.index.values)-set(EBIT[EBIT<=0].index.values)-set(EV[EV<=0].index.values)-set(NCA[NCA<=0].index.values)
    EBIT = EBIT[tmp]
    NCA = NCA[tmp]
    EV = EV[tmp]

    # ����ħ����ʽ
    ROC = EBIT / NCA
    EY = EBIT / EV
    
    return [ROC,EY]
    
# ������A���й��˵������ڷ��񣬹�����ҵ����ҵ�壬�¹ɴ��¹ɣ�ST  
def filter_stocks(context):
    # ��ȡ����A��
    df = get_all_securities('stock')
    # �޳����ڷ��񣬹�����ҵ
    tmp = set(df.index.values)-set(get_industry_stocks('J66'))\
            -set(get_industry_stocks('J67'))\
            -set(get_industry_stocks('J68'))\
            -set(get_industry_stocks('J69'))\
            -set(get_industry_stocks('N78')) 
    tmp = np.array(list(tmp))
    df = df.select(lambda code: code in tmp)
    #  �޳���ҵ��
    df = df.select(lambda code: not code.startswith('300'))
    #  �޳��¹ɴ��¹�
    one_year = dt.timedelta(365)
    df = df[df.start_date < g.yesterday.date() - one_year]
    # �޳�ST
    df = df[map(lambda s: not s.startswith("ST") and not s.startswith("*ST") ,df.display_name)]
    
    return df.index.values
