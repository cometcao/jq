# enable_profile()
import talib
import numpy as np
import pandas as pd

def initialize(context):
    set_commission(PerTrade(buy_cost=0.0003, sell_cost=0.0013, min_cost=5))    # ����������
    g.owning = 7                    # �ֲֹ�Ʊ��
    g.muster = []                   # Ԥѡ��Ʊ��
    g.summit = {}                   # ������߼�
    
def before_trading_start(context):
    # ȡ�õ�ǰ����
    g.today = context.current_dt.strftime('%Y-%m-%d')
    # ����Ԥѡ��Ʊ
    g.muster = doSelect(g.today)
    set_universe(g.muster)
    # �����Ʊ��ֵ��Ϣ
    for stock in g.summit.keys():
        if stock not in context.portfolio.positions: del g.summit[stock]

# ÿ����λʱ�����һ��(�������ز�,��ÿ�����һ��,���������,��ÿ���ӵ���һ��)
def handle_data(context, data):
    # H0��ȡ�ý����Ʊ�۸���Ϣ--------------------------------------------------
    grid = get_price(context.universe, g.today, g.today, fields=['paused', 'open', 'high_limit', 'low_limit'])
    # H1����ֲ���--------------------------------------------------�����ֲֹ�Ʊ
    for stock in context.portfolio.positions:
        # SS����¼��Ʊ��ֵ��Ϣ
        if g.summit.get(stock, 0)<data[stock].high: g.summit[stock]=data[stock].high
        # SP������ͣ�ƹ�Ʊ
        if grid.paused[stock][0]: continue
        # S1��Ŀǰ�ֲֲ���Ԥѡ��Ʊ����(g.muster)�����
        if stock not in g.muster:
            doLaunch(g.owning, stock, 'Խ�����')
        # S2���س�10%�����
        elif grid.open[stock][0]/g.summit[stock]<0.9:
            doLaunch(g.owning, stock, '�س����')
        # S3��ָ�������źš�ֹӯ���
        if doDecide(stock)['dead']:
            doLaunch(g.owning, stock, '�������')
    # HS�������ж�--------------------------------------------------�жϴ�������
    # if not doSafety(context, data, '000300.XSHG'): return
    # H2�����ֲ���--------------------------------------------------����Ԥѡ��Ʊ
    for stock in g.muster:
        # BP������ͣ�ƹ�Ʊ
        if grid.paused[stock][0]: continue
        # B1��ָ�������ź�
        if doDecide(stock)['gold']:
            if doLaunch(g.owning, stock, '��潨��', context)['enough']: break

# ѡ�ɺ���======================================================================
def doSelect(stamp, scale=0.14):
    # 1��ѡ�����й�Ʊ����ֵ���򣨴��롢��ֵ��-----------------------------------
    result = get_fundamentals(query(valuation.code, valuation.market_cap)) 
    result = result.dropna().sort(columns='market_cap',ascending=True)
    choice = int(len(result) * scale)
    result = result.head(choice)
    # 2��ɾ���ӣԡ����ӣ�-------------------------------------------------------
    result = list(result['code'])
    extras = get_extras('is_st', result, start_date=stamp, end_date=stamp, df=False)
    for stock in extras.keys():
        if extras[stock][0]: result.remove(stock)
    # 3�����ز�ѯ���-----------------------------------------------------------
    return result

# ��������======================================================================
def doSafety(context, data, index='000300.XSHG'):
    fast = 11
    slow = 26
    sign =  5
    rows = (fast + slow + sign) * 5
    suit = {'dif':0, 'dea':0, 'macd':0, 'safe':False, 'gold':False, 'dead':False}
    grid = attribute_history(index, rows, fields=['open', 'high', 'low', 'close', 'high_limit', 'low_limit']).dropna()
    try:
        dif, dea, macd = talib.MACD(grid['close'].values, fastperiod=fast, slowperiod=slow, signalperiod=sign)
        suit['safe'] = macd[-1]>0
    except:
        pass
    return suit['safe']

# �µ�����======================================================================
def doLaunch(total, stock, title, context=None):
    assign = 0
    direct = None
    result = {'enough': False}
    # �ж��򵥻�������----------------------------------------------------------
    if context: # ��
        assign = doAssign(total, context)
        if assign>0: direct = order_value(stock, assign)
        else:        result['enough'] = True
    else:       # ����
        direct = order_target(stock, 0)
    # ��¼��־------------------------------------------------------------------
    if direct: 
        print '%s��stock=%s,�µ�����=%d,�ɽ�����=%d,�ɽ��۸�=%.2f,�ɽ����=%.2f,Ŀ����=%.2f' % (title, stock, direct.amount, direct.filled, direct.price, direct.filled*direct.price, assign)
    else:
        print '%s��stock=%s,Ŀ����=%.2f,�µ�ʧ��!' % (title, stock, assign)
    # ���ؽ��------------------------------------------------------------------
    return result

# �ʽ����======================================================================
def doAssign(total, context):
    # ����ֲֹ�Ʊ����������Ʊ����--------------------------------------------
    remain = 0
    for stock in context.portfolio.positions:
        if context.portfolio.positions[stock].amount>0: remain+=1
    for stock in context.portfolio.unsell_positions:
        if context.portfolio.unsell_positions[stock].amount>0: remain+=1
    margin = total - remain
    # ������Ʊ����ƽ������ʣ���ֽ�--------------------------------------------
    if context.portfolio.cash>0 and margin>0: 
        result = context.portfolio.cash/margin
    else:
        result = 0
    # ���ؽ��------------------------------------------------------------------
    return result

# ���ߺ���======================================================================
def doDecide(stock):
    fast = 11
    slow = 26
    sign =  5
    rows = (fast + slow + sign) * 5
    suit = {'dif':0, 'dea':0, 'macd':0, 'gold':False, 'dead':False}
    grid = attribute_history(stock, rows, fields=['close']).dropna()
    try:
        grid['dif'], grid['dea'], grid['macd'] = talib.MACD(grid['close'].values, fast, slow, sign)
        grid = grid.dropna()
        # �ױ���----------------------------------------------------------------
        mask = grid['macd']>0
        mask = mask[mask==True][mask.shift(1)==False]
        key2 = mask.keys()[-2]
        key1 = mask.keys()[-1]
        suit['gold'] = grid.close[key2]>grid.close[key1] and \
                       grid.dif[key2]<grid.dif[key1]<0   and \
                       grid.macd[-2]<0<grid.macd[-1]
        # ������----------------------------------------------------------------
        mask = grid['macd']<0
        mask = mask[mask==True][mask.shift(1)==False]
        key2 = mask.keys()[-2]
        key1 = mask.keys()[-1]
        suit['dead'] = grid.close[key2]<grid.close[key1] and \
                       grid.dif[key2]>grid.dif[key1]>0   and \
                       grid.macd[-2]>0>grid.macd[-1]
    except:
        pass
    return suit