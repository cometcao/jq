'''
����С��ֵ��ʱ����

����ָ��Ƶ�ʵĵ����գ��ڵ�����ÿ��ָ��ʱ�䣬���㻦��300ָ������֤500ָ����ǰ��20����
�������2��ָ����20���Ƿ���һ��Ϊ���������ѡ�ɵ��֣�֮�����ѭ��������

ֹ����ԣ�

    ����ֹ��(��ѡ)
        1. ÿ����ȡ����ǰ130�յ���ͼۺ���߼ۣ������ߴ�����͵���������֣�ֹͣ���ס�
        2. ÿ�����жϴ����Ƿ������ֻ��ѻֹ�������������ֲ�ֹͣ���ף��ڶ���ֹͣ��
           ��һ�졣

    ����ֹ��(��ѡ)
        ÿ�����жϸ����Ƿ�ӳֲֺ����߼ۻس����ȣ�����������ɻس���ֵ����ƽ���ùɳֲ�

    ����ֹ��(����)
        ÿ��ָ��ʱ�䣬���㻦��300ָ������֤500ָ����ǰ��20���Ƿ������2��ָ���Ƿ���Ϊ����
        ����֣����õ��ּ��������´ε������������ٲ���

�汾��v2.0.6
���ڣ�2016.08.31
���ߣ�Morningstar
'''

import tradestat
from blacklist import *



def before_trading_start(context):
    log.info("---------------------------------------------")
    #log.info("==> before trading start @ %s", str(context.current_dt))

    # ��ǰ���ж�����ѻ״̬����Ϊ�жϵ�����Ϊǰ4��
    g.is_last_day_3_black_crows = is_3_black_crows(g.index_4_stop_loss_by_3_black_crows)
    if g.is_last_day_3_black_crows:
        log.info("==> ǰ4���Ѿ���������ѻ��̬")
    pass

def after_trading_end(context):
    #log.info("==> after trading end @ %s", str(context.current_dt))
    g.trade_stat.report(context)

    reset_day_param()
    
    # �õ���ǰδ��ɶ���
    orders = get_open_orders()
    for _order in orders.values():
        log.info("canceled uncompleted order: %s" %(_order.order_id))
    pass

def initialize(context):
    log.info("==> initialize @ %s", str(context.current_dt))
    
    # ������������
    set_commission(PerTrade(buy_cost=0.0003, sell_cost=0.0013, min_cost=5))
    # ���û�׼ָ��������300ָ�� '000300.XSHG'
    set_benchmark('000300.XSHG')
    # �趨����Ϊ�ٷֱ�
    # û�е���set_slippage����, ϵͳĬ�ϵĻ�����PriceRelatedSlippage(0.00246)
    #set_slippage(PriceRelatedSlippage(0.004))
    # ʹ����ʵ�۸�ز�(ģ�����Ƽ���ˣ��ز���ע��)
    set_option('use_real_price', True)

    # ����ͳ��ģ��
    g.trade_stat = tradestat.trade_stat()

    # ���ò��Բ���
    # ��������ҪΪ֮ǰ��С��ֵ���ԣ���֤֮ǰ������س�
    # �����Ҫ���ģ�����½�����������������������������
    # 10�յ���
    # �رմ�������ѻ���ߵͼ�ֹ��
    # �رո���ֹӯֹ��
    # �ر�ѡ������
    set_param()

    # �����Ʊ�ֲֺ����߼�
    g.last_high = {}

    # ���²������ܸ���
    if g.is_market_stop_loss_by_price:
        # ��¼�����Ƿ�������̼۸�ֹ��������ÿ���̺�����
        g.is_day_stop_loss_by_price = False

    # ��������ѻ�ж�״̬
    g.is_last_day_3_black_crows = False
    if g.is_market_stop_loss_by_3_black_crows:
        g.cur_drop_minute_count = 0

    if g.is_rank_stock:
        if g.rank_stock_count > g.pick_stock_count:
            g.rank_stock_count = g.pick_stock_count

    if g.is_stock_stop_loss or g.is_stock_stop_profit:
        # ���浱�ո���250��������3���Ƿ������⵱�շ�����ȡ��ÿ���̺����
        g.pct_change = {}

    # ��ӡ���Բ���
    log_param()

def set_param():
    # ����Ƶ�ʣ���λ����
    g.period = 10
    # �����ռ���������λ����
    g.day_count = 0
    # ���õ���ʱ�䣨24Сʱ�����ƣ�
    g.adjust_position_hour = 14
    g.adjust_position_minute = 52

    # ����ѡ�ɲ���

    # ��ѡ��Ʊ��Ŀ
    g.pick_stock_count = 100
    
    # ����ѡ�ɲ���
    # �Ƿ����PEѡ��
    g.pick_by_pe = True
    # �������PEѡ�ɣ�������������СPEֵ
    if g.pick_by_pe:
        g.max_pe = 200
        g.min_pe = 0

    # �Ƿ����EPSѡ��
    g.pick_by_eps = False
    # ����ѡ����СEPSֵ
    if g.pick_by_eps:
        g.min_eps = 0
    
    # �����Ƿ���˴�ҵ���Ʊ
    g.filter_gem = True
    # �����Ƿ���˺�������Ʊ���ز⽨��رգ�ģ������ʱ����
    g.filter_blacklist = True

    # �Ƿ�Թ�Ʊ����
    g.is_rank_stock = False
    if g.is_rank_stock:
        # �������ֵĹ�Ʊ��Ŀ
        g.rank_stock_count = 20

    # �����Ʊ��Ŀ
    g.buy_stock_count = 5
    
    # ���ö���ָ��
    g.index2 = '000300.XSHG'  # ����300ָ������ʾ�������̹�
    g.index8 = '000905.XSHG'  # ��֤500ָ������ʾ�ˣ�С�̹�
    #g.index2 = '000016.XSHG'  # ��֤50ָ��
    #g.index8 = '399333.XSHE'  # ��С��Rָ��
    #g.index8 = '399006.XSHE'  # ��ҵ��ָ��
    
    # �ж����ֵĶ���ָ��20������
    g.index_growth_rate_20 = 0.00
    #g.index_growth_rate_20 = 0.01

    # �����Ƿ���ݴ�����ʷ�۸�ֹ��
    # ����ָ��ǰ130������߼۳�����ͼ�2���������ֹ��
    # ע���رմ�ֹ���������ӣ����س�������
    g.is_market_stop_loss_by_price = True
    if g.is_market_stop_loss_by_price:
        # ���ü۸�ֹ���ж�ָ����Ĭ��Ϊ��ָ֤�������޸�Ϊ����ָ��
        g.index_4_stop_loss_by_price = '000001.XSHG'

    # ��������ѻ�ж�ָ����Ĭ��Ϊ��ָ֤�������޸�Ϊ����ָ��
    g.index_4_stop_loss_by_3_black_crows = '000001.XSHG'

    # �����Ƿ�����������ѻֹ��
    # ������Ϊ��Դ����ж�����ѻЧ�������ã�������Ч��ֻ��ѻ�����жϣ�׼ȷ��ʵ������Ҳ���ã�
    # ��Σ�������ʷ���鿴һ����̳�����ֻ��ѻ��ʱ���Ѿ������ͺ��ˣ�ʹ������ֹ��ʽ���ܻ����
    g.is_market_stop_loss_by_3_black_crows = False
    if g.is_market_stop_loss_by_3_black_crows:
        g.dst_drop_minute_count = 60

    # �����Ƿ����ֹ��
    g.is_stock_stop_loss = True
    # �����Ƿ����ֹӯ
    g.is_stock_stop_profit = False
    
def log_param():
    log.info("������Ƶ��: %d��" %(g.period))
    log.info("����ʱ��: %s:%s" %(g.adjust_position_hour, g.adjust_position_minute))

    log.info("��ѡ��Ʊ��Ŀ: %d" %(g.pick_stock_count))

    log.info("�Ƿ����PEѡ��: %s" %(g.pick_by_pe))
    if g.pick_by_pe:
        log.info("ѡ�����PE: %s" %(g.max_pe))
        log.info("ѡ����СPE: %s" %(g.min_pe))

    log.info("�Ƿ����EPSѡ��: %s" %(g.pick_by_eps))
    if g.pick_by_eps:
        log.info("ѡ����СEPS: %s" %(g.min_eps))
    
    log.info("�Ƿ���˴�ҵ���Ʊ: %s" %(g.filter_gem))
    log.info("�Ƿ���˺�������Ʊ: %s" %(g.filter_blacklist))
    if g.filter_blacklist:
        log.info("��ǰ��Ʊ��������%s" %str(get_blacklist()))

    log.info("�Ƿ�Թ�Ʊ����ѡ��: %s" %(g.is_rank_stock))
    if g.is_rank_stock:
        log.info("���ֱ�ѡ��Ʊ��Ŀ: %d" %(g.rank_stock_count))

    log.info("�����Ʊ��Ŀ: %d" %(g.buy_stock_count))

    log.info("����ָ��֮��: %s - %s" %(g.index2, get_security_info(g.index2).display_name))
    log.info("����ָ��֮��: %s - %s" %(g.index8, get_security_info(g.index8).display_name))
    log.info("�ж����ֵĶ���ָ��20������: %.1f%%" %(g.index_growth_rate_20*100))

    log.info("�Ƿ���������ʷ�ߵͼ۸�ֹ��: %s" %(g.is_market_stop_loss_by_price))
    if g.is_market_stop_loss_by_price:
        log.info("���̼۸�ֹ���ж�ָ��: %s - %s" %(g.index_4_stop_loss_by_price, get_security_info(g.index_4_stop_loss_by_price).display_name))

    log.info("��������ѻֹ���ж�ָ��: %s - %s" %(g.index_4_stop_loss_by_3_black_crows, get_security_info(g.index_4_stop_loss_by_3_black_crows).display_name))
    log.info("�Ƿ�����������ѻֹ��: %s" %(g.is_market_stop_loss_by_3_black_crows))
    if g.is_market_stop_loss_by_3_black_crows:
        log.info("����ѻֹ������Ҫ���մ���Ϊ���ķ��Ӽ����ﵽ: %d" %(g.dst_drop_minute_count))

    log.info("�Ƿ�������ֹ��: %s" %(g.is_stock_stop_loss))
    log.info("�Ƿ�������ֹӯ: %s" %(g.is_stock_stop_profit))

# ���õ��ղ������������Ҫ������Ҫ���õĲ���
def reset_day_param():
    if g.is_market_stop_loss_by_price:
        # ���õ��մ��̼۸�ֹ��״̬
        g.is_day_stop_loss_by_price = False

    if g.is_stock_stop_loss or g.is_stock_stop_profit:
        # ��յ��ո���250��������3���Ƿ��Ļ���
        g.pct_change.clear()

    # ��������ѻ״̬
    g.is_last_day_3_black_crows = False
    if g.is_market_stop_loss_by_3_black_crows:
        g.cur_drop_minute_count = 0

# �����ӻز�
def handle_data(context, data):
    if g.is_market_stop_loss_by_price:
        if market_stop_loss_by_price(context, g.index_4_stop_loss_by_price):
            return

    if g.is_market_stop_loss_by_3_black_crows:
        if market_stop_loss_by_3_black_crows(context, g.index_4_stop_loss_by_3_black_crows, g.dst_drop_minute_count):
            return

    if g.is_stock_stop_loss:
        stock_stop_loss(context, data)

    if g.is_stock_stop_profit:
        stock_stop_profit(context, data)

    # ��õ�ǰʱ��
    hour = context.current_dt.hour
    minute = context.current_dt.minute
    
    # ÿ������14:52����
    if hour == g.adjust_position_hour and minute == g.adjust_position_minute:
        do_handle_data(context, data)

def do_handle_data(context, data):
    log.info("�����ռ��� [%d]" %(g.day_count))
    
    # �ؿ�ָ��ǰ20����Ƿ�
    gr_index2 = get_growth_rate(g.index2)
    gr_index8 = get_growth_rate(g.index8)
    log.info("��ǰ%sָ����20���Ƿ� [%.2f%%]" %(get_security_info(g.index2).display_name, gr_index2*100))
    log.info("��ǰ%sָ����20���Ƿ� [%.2f%%]" %(get_security_info(g.index8).display_name, gr_index8*100))

    if gr_index2 <= g.index_growth_rate_20 and gr_index8 <= g.index_growth_rate_20:
        clear_position(context)
        g.day_count = 0
    else: #if  gr_index2 > g.index_growth_rate_20 or ret_index8 > g.index_growth_rate_20:
        if g.day_count % g.period == 0:
            log.info("==> �����������е���")
            buy_stocks = pick_stocks(context, data)
            log.info("ѡ�ɺ�����Ʊ: %s" %(buy_stocks))
            adjust_position(context, buy_stocks)
        g.day_count += 1

def market_stop_loss_by_price(context, index):
    # ����ָ��ǰ130������߼۳�����ͼ�2���������ֹ��
    # ������ʷ�����ж��������״̬���㣬���춼����仯
    # ���Ӵ�ֹ�𣬻س����ͣ����潵��

    if not g.is_day_stop_loss_by_price:
        h = attribute_history(index, 130, unit='1d', fields=('close', 'high', 'low'), skip_paused=True)
        low_price_130 = h.low.min()
        high_price_130 = h.high.max()
        if high_price_130 > 2 * low_price_130:
            # ���յ�һ�������־
            log.info("==> ����ֹ��%sָ��ǰ130������߼۳�����ͼ�2��, ��߼�: %f, ��ͼ�: %f" %(get_security_info(index).display_name, high_price_130, low_price_130))
            g.is_day_stop_loss_by_price = True

    if g.is_day_stop_loss_by_price:
        clear_position(context)
        g.day_count = 0

    return g.is_day_stop_loss_by_price

def market_stop_loss_by_3_black_crows(context, index, n):
    # ǰ������ѻ���ۼƵ��մ���ָ���Ƿ�<0�ķ��Ӽ���
    # ������Ӽ�������ֵn����ʼ��������ѻֹ��
    # ������Ч����ѻ��ֹ��
    if g.is_last_day_3_black_crows:
        if get_growth_rate(index, 1) < 0:
            g.cur_drop_minute_count += 1

        if g.cur_drop_minute_count >= n:
            if g.cur_drop_minute_count == n:
                log.info("==> ����%sΪ���ѳ���%d���ӣ�ִ������ѻֹ��" %(get_security_info(index).display_name, n))

            clear_position(context)
            g.day_count = 0
            return True

    return False

def is_3_black_crows(stock):
    # talib.CDL3BLACKCROWS

    # ��ֻ��ѻ˵�����԰ٶȰٿ�
    # 1. ���������������ߣ�ÿ������̼۾�������һ�յ�����
    # 2. ��������ǰһ����г�����Ӧ��Ϊ����
    # 3. �������߱���Ϊ���ĺ�ɫʵ�壬�ҳ���Ӧ�ô������
    # 4. ���̼۽ӽ�ÿ�յ���ͼ�λ
    # 5. ÿ�յĿ��̼۶����ϸ�K�ߵ�ʵ�岿��֮�ڣ�
    # 6. ��һ�����ߵ�ʵ�岿�֣���õ������յ���߼�λ
    #
    # �㷨
    # ��Ч��ֻ��ѻ������˵��硣�����ſ�������ֻ����1��2
    # ����ǰ4�������ж�
    # 3�����ߵ�������4.5%�����������ԣ�

    h = attribute_history(stock, 4, '1d', ('close','open'), skip_paused=True, df=False)
    h_close = list(h['close'])
    h_open = list(h['open'])

    if len(h_close) < 4 or len(h_open) < 4:
        return False
    
    # һ������
    if h_close[-4] > h_open[-4] \
        and (h_close[-1] < h_open[-1] and h_close[-2]< h_open[-2] and h_close[-3] < h_open[-3]):
        #and (h_close[-1] < h_close[-2] and h_close[-2] < h_close[-3]) \
        #and h_close[-1] / h_close[-3] - 1 < -0.045:
        return True
    return False
    
'''
def is_3_black_crows(stock, data):
    # talib.CDL3BLACKCROWS
    his =  attribute_history(stock, 2, '1d', ('close','open'), skip_paused=True, df=False)
    closeArray = list(his['close'])
    closeArray.append(data[stock].close)
    openArray = list(his['open'])
    openArray.append(get_current_data()[stock].day_open)

    if closeArray[0]<openArray[0] and closeArray[1]<openArray[1] and closeArray[2]<openArray[2]:
        if closeArray[-1]/closeArray[0]-1>-0.045:
            his2 =  attribute_history(stock, 4, '1d', ('close','open'), skip_paused=True, df=False)
            closeArray1 = his2['close']
            if closeArray[0]/closeArray1[0]-1>0:
                return True
    return False
'''

# ����ֹ��
def stock_stop_loss(context, data):
    for stock in context.portfolio.positions.keys():
        cur_price = data[stock].close

        if g.last_high[stock] < cur_price:
            g.last_high[stock] = cur_price

        threshold = get_stop_loss_threshold(stock, g.period)
        #log.debug("����ֹ����ֵ, stock: %s, threshold: %f" %(stock, threshold))
        if cur_price < g.last_high[stock] * (1 - threshold):
            log.info("==> ����ֹ��, stock: %s, cur_price: %f, last_high: %f, threshold: %f" 
                %(stock, cur_price, g.last_high[stock], threshold))

            position = context.portfolio.positions[stock]
            if close_position(position):
                g.day_count = 0

# ����ֹӯ
def stock_stop_profit(context, data):
    for stock in context.portfolio.positions.keys():
        position = context.portfolio.positions[stock]
        cur_price = data[stock].close
        threshold = get_stop_profit_threshold(stock, g.period)
        #log.debug("����ֹӯ��ֵ, stock: %s, threshold: %f" %(stock, threshold))
        if cur_price > position.avg_cost * (1 + threshold):
            log.info("==> ����ֹӯ, stock: %s, cur_price: %f, avg_cost: %f, threshold: %f" 
                %(stock, cur_price, g.last_high[stock], threshold))

            position = context.portfolio.positions[stock]
            if close_position(position):
                g.day_count = 0

# ��ȡ����ǰn���m������ֵ����
# ���ӻ�����⵱�ն�λ�ȡ����
def get_pct_change(security, n, m):
    pct_change = None
    if security in g.pct_change.keys():
        pct_change = g.pct_change[security]
    else:
        h = attribute_history(security, n, unit='1d', fields=('close'), skip_paused=True)
        pct_change = h['close'].pct_change(m) # 3�յİٷֱȱ�ȣ���3���ǵ�����
        g.pct_change[security] = pct_change
    return pct_change
        
# ������ɻس�ֹ����ֵ
# �������ڳֲ�n�����ܳ��ܵ�������
# �㷨��(����250��������n�յ��� + ����250����ƽ����n�յ���)/2
# ������ֵ
def get_stop_loss_threshold(security, n = 3):
    pct_change = get_pct_change(security, 250, n)
    #log.debug("pct of security [%s]: %s", pct)
    maxd = pct_change.min()
    #maxd = pct[pct<0].min()
    avgd = pct_change.mean()
    #avgd = pct[pct<0].mean()
    # maxd��avgd����Ϊ������ʾ���ʱ����һֱ�������������¹�
    bstd = (maxd + avgd) / 2

    # ���ݲ���ʱ�������bstdΪnan
    if not isnan(bstd):
        if bstd != 0:
            return abs(bstd)
        else:
            # bstd = 0���� maxd <= 0
            if maxd < 0:
                # ��ʱȡ������
                return abs(maxd)

    return 0.099 # Ĭ�����ûز�ֹ����ֵ������Ϊ-9.9%����ֵ��ò�ƻس�����

# �������ֹӯ��ֵ
# �㷨������250��������n���Ƿ�
# ������ֵ
def get_stop_profit_threshold(security, n = 3):
    pct_change = get_pct_change(security, 250, n)
    maxr = pct_change.max()
    
    # ���ݲ���ʱ�������maxrΪnan
    # ������maxr����Ϊ��
    if (not isnan(maxr)) and maxr != 0:
        return abs(maxr)
    return 0.20 # Ĭ������ֹӯ��ֵ����Ƿ�Ϊ20%

# ��ȡ��Ʊn�������Ƿ������ݵ�ǰ�ۼ���
# n Ĭ��20��
def get_growth_rate(security, n=20):
    lc = get_close_price(security, n)
    #c = data[security].close
    c = get_close_price(security, 1, '1m')
    
    if not isnan(lc) and not isnan(c) and lc != 0:
        return (c - lc) / lc
    else:
        log.error("���ݷǷ�, security: %s, %d�����̼�: %f, ��ǰ��: %f" %(security, n, lc, c))
        return 0

# ��ȡǰn����λʱ�䵱ʱ�����̼�
def get_close_price(security, n, unit='1d'):
    return attribute_history(security, n, unit, ('close'), True)['close'][0]

# ���֣�����ָ����ֵ��֤ȯ
# �����ɹ����ɽ�������ȫ���ɽ��򲿷ֳɽ�����ʱ�ɽ�������0��������True
# ����ʧ�ܻ��߱����ɹ�����ȡ������ʱ�ɽ�������0��������False
def open_position(security, value):
    order = order_target_value_(security, value)
    if order != None and order.filled > 0:
        # �����ɹ����гɽ����ʼ����߼�
        cur_price = get_close_price(security, 1, '1m')
        g.last_high[security] = cur_price
        return True
    return False

# ƽ�֣�����ָ���ֲ�
# ƽ�ֳɹ���ȫ���ɽ�������True
# ����ʧ�ܻ��߱����ɹ�����ȡ������ʱ�ɽ�������0�������߱�����ȫ���ɽ�������False
def close_position(position):
    security = position.security
    order = order_target_value_(security, 0) # ���ܻ���ͣ��ʧ��
    if order != None:
        if order.filled > 0:
            # ֻҪ�гɽ�������ȫ���ɽ����ǲ��ֳɽ�����ͳ��ӯ��
            g.trade_stat.watch(security, order.filled, position.avg_cost, position.price)

        if order.status == OrderStatus.held and order.filled == order.amount:
            # ȫ���ɽ���ɾ�����֤ȯ����߼ۻ���
            if security in g.last_high:
                g.last_high.pop(security)
            else:
                log.warn("last high price of %s not found" %(security))
            return True

    return False

# ����������гֲ�
def clear_position(context):
    if context.portfolio.positions:
        log.info("==> ��֣��������й�Ʊ")
        for stock in context.portfolio.positions.keys():
            position = context.portfolio.positions[stock]
            close_position(position)

# �Զ����µ�
# ����Joinquant�ĵ�����ǰ����������������ִ�У�������������order_target_value�����ؼ���ʾ�������
# �����ɹ����ر�����������һ����ɽ��������򷵻�None
def order_target_value_(security, value):
    if value == 0:
        log.debug("Selling out %s" % (security))
    else:
        log.debug("Order %s to value %f" % (security, value))
        
    # �����Ʊͣ�ƣ�����������ʧ�ܣ�order_target_value ����None
    # �����Ʊ�ǵ�ͣ������������ɹ���order_target_value ����Order�����Ǳ�����ȡ��
    # ���ɲ����ı������ۿ�״̬���ѳ�����ʱ�ɽ���>0����ͨ���ɽ����ж��Ƿ��гɽ�
    return order_target_value(security, value)


# ����ͣ�ƹ�Ʊ
def filter_paused_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list if not current_data[stock].paused]

# ����ST�������������б�ǩ�Ĺ�Ʊ
def filter_st_stock(stock_list):
    current_data = get_current_data()
    return [stock for stock in stock_list 
        if not current_data[stock].is_st 
        and 'ST' not in current_data[stock].name 
        and '*' not in current_data[stock].name 
        and '��' not in current_data[stock].name]
        
# ������ͣ�Ĺ�Ʊ
def filter_limitup_stock(context, stock_list):
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    
    # �Ѵ����ڳֲֵĹ�Ʊ��ʹ��ͣҲ�����ˣ�����˹�Ʊ�ٴο��򣬵��򱻹��˶�����ѡ���Ĺ�Ʊ
    return [stock for stock in stock_list if stock in context.portfolio.positions.keys() 
        or last_prices[stock][-1] < current_data[stock].high_limit]
    #return [stock for stock in stock_list if stock in context.portfolio.positions.keys() 
    #    or last_prices[stock][-1] < current_data[stock].high_limit * 0.995]

# ���˵�ͣ�Ĺ�Ʊ
def filter_limitdown_stock(context, stock_list):
    last_prices = history(1, unit='1m', field='close', security_list=stock_list)
    current_data = get_current_data()
    
    return [stock for stock in stock_list if stock in context.portfolio.positions.keys() 
        or last_prices[stock][-1] > current_data[stock].low_limit]
    #return [stock for stock in stock_list if last_prices[stock][-1] > current_data[stock].low_limit]
    #return [stock for stock in stock_list if stock in context.portfolio.positions.keys() 
    #    or last_prices[stock][-1] > current_data[stock].low_limit * 1.005]
    
# ���˺�������Ʊ
def filter_blacklist_stock(context, stock_list):
    blacklist = get_blacklist()
    return [stock for stock in stock_list if stock not in blacklist]

# ���˴�ҵ���Ʊ
def filter_gem_stock(context, stock_list):
    return [stock for stock in stock_list if stock[0:3] != '300']

# ����20��������Ϊ���Ĺ�Ʊ
def filter_by_growth_rate(stock_list, n):
    return [stock for stock in stock_list if get_growth_rate(stock, n) > 0]

# ��Ʊ����
def rank_stocks(data, stock_list):
    dst_stocks = {}
    for stock in stock_list:
        h = attribute_history(stock, 130, unit='1d', fields=('close', 'high', 'low'), skip_paused=True)
        low_price_130 = h.low.min()
        high_price_130 = h.high.max()

        avg_15 = data[stock].mavg(15, field='close')
        cur_price = data[stock].close

        #avg_15 = h['close'][-15:].mean()
        #cur_price = get_close_price(stock, 1, '1m')

        score = (cur_price-low_price_130) + (cur_price-high_price_130) + (cur_price-avg_15)
        #score = ((cur_price-low_price_130) + (cur_price-high_price_130) + (cur_price-avg_15)) / cur_price
        dst_stocks[stock] = score
        
    df = pd.DataFrame(dst_stocks.values(), index=dst_stocks.keys())
    df.columns = ['score']
    df = df.sort(columns='score', ascending=True)
    return df.index

'''
# �����¹�
def filter_new_stock(stock_list):
    stocks = get_all_securities(['stock'])
    stocks = stocks[(context.current_dt.date() - stocks.start_date) > datetime.timedelta(60)].index
'''

# ѡ��
# ѡȡָ����Ŀ��С��ֵ��Ʊ���ٽ��й��ˣ�������ѡָ��������Ŀ�Ĺ�Ʊ
def pick_stocks(context, data):
    q = None
    if g.pick_by_pe:
        if g.pick_by_eps:
            q = query(valuation.code).filter(
                indicator.eps > g.min_eps,
                valuation.pe_ratio > g.min_pe,
                valuation.pe_ratio < g.max_pe
            ).order_by(
                valuation.market_cap.asc()
            ).limit(
                g.pick_stock_count
            )
        else:
            q = query(valuation.code).filter(
                valuation.pe_ratio > g.min_pe,
                valuation.pe_ratio < g.max_pe
            ).order_by(
                valuation.market_cap.asc()
            ).limit(
                g.pick_stock_count
            )
    else:
        if g.pick_by_eps:
            q = query(valuation.code).filter(
                indicator.eps > g.min_eps
            ).order_by(
                valuation.market_cap.asc()
            ).limit(
                g.pick_stock_count
            )
        else:
            q = query(valuation.code).order_by(
                valuation.market_cap.asc()
            ).limit(
                g.pick_stock_count
            )
    
    df = get_fundamentals(q)
    stock_list = list(df['code'])

    if g.filter_gem:
        stock_list = filter_gem_stock(context, stock_list)
        
    if g.filter_blacklist:
        stock_list = filter_blacklist_stock(context, stock_list)
        
    stock_list = filter_paused_stock(stock_list)
    stock_list = filter_st_stock(stock_list)
    stock_list = filter_limitup_stock(context, stock_list)
    stock_list = filter_limitdown_stock(context, stock_list)

    # ����20�չ�Ʊ�Ƿ�����Ч�����ã���ע��
    #stock_list = filter_by_growth_rate(stock_list, 15)
    
    if g.is_rank_stock:
        if len(stock_list) > g.rank_stock_count:
            stock_list = stock_list[:g.rank_stock_count]

        #log.debug("����ǰ��ѡ��Ʊ: %s" %(stock_list))
        if len(stock_list) > 0:
            stock_list = rank_stocks(data, stock_list)
        #log.debug("���ֺ�ѡ��Ʊ: %s" %(stock_list))
    
    # ѡȡָ��������Ŀ�Ĺ�Ʊ
    if len(stock_list) > g.buy_stock_count:
        stock_list = stock_list[:g.buy_stock_count]
    return stock_list

# ���ݴ����Ʊ�����������λ
# ������ͣ�Ƶ�ԭ��û�������Ĺ�Ʊ���������
# ʼ�ձ��ֲֳ���ĿΪg.buy_stock_count
def adjust_position(context, buy_stocks):
    for stock in context.portfolio.positions.keys():
        if stock not in buy_stocks:
            log.info("stock [%s] in position is not buyable" %(stock))
            position = context.portfolio.positions[stock]
            close_position(position)
        else:
            log.info("stock [%s] is already in position" %(stock))
    
    # ���ݹ�Ʊ�����ֲ�
    # �˴�ֻ���ݿ��ý��ƽ�����乺�򣬲��ܱ�֤ÿ����λƽ������
    position_count = len(context.portfolio.positions)
    if g.buy_stock_count > position_count:
        value = context.portfolio.cash / (g.buy_stock_count - position_count)

        for stock in buy_stocks:
            if context.portfolio.positions[stock].total_amount == 0:
                if open_position(stock, value):
                    if len(context.portfolio.positions) == g.buy_stock_count:
                        break

'''
--------------------------------------------------------------------------------

���£�

2016.08.31

v2.0.6
��������ѻ�ж��㷨���ſ��ж���������ǰ������ѻ��̬�£�����Ϊ���ķ��Ӽ����ﵽָ��
ֵ�������ֹ�𣬴˷�����ҪΪ����������ѻ����Ч��

2016.08.30

v2.0.5
���ݰٶȰٿ�������������ѻ�㷨������ǰ4�������жϣ�������ѻ��̬�µ���Ϊ���ķ��Ӽ�
���ﵽָ��ֵ�󣬽���ֹ������Ǳ��bug

2016.08.19

v2.0.4
�޸�ֹӯֹ����ֵ�ļ���Ϊ���ݵ��ּ�����ڻ�ȡ������5�յ������ȡ��ʷ3�յķ���

2016.08.17

v2.0.3
�������ѻ��ָ���۸�ֹ�����ã��Ż���������ѻ��ָ���۸�ֹ�𣬱���ÿ���ӷ�����ȡ
���ݴ�����߻ز�Ч��

2016.08.16

v2.0.2
�޸�����Сbug����л @michaeljrqiu @����Ħ����������

v2.0.1
������ƽ�ֵ�ӯ��ͳ�ƣ���Ҫ��Բ��ֳɽ������������˲���ƽ�ֵ��µ���߼ۻ��汻ɾ��
������

��Ҫ����tradestat.py

2016.08.15

v2.0.0
��л@az����Ĳ��Է�������EPSѡ�ɣ�ѡ�����֣���������ѻ���ߵͼ�ֹ�𣬸���ֹӯֹ
��ȫ����ѡ����

Ĭ�ϲ�������ֻΪ����1.2.8�汾������ͻس��������������������������е������

v1.2.8
���������ӿڣ��ۿ���ڲ��ɲ����ı��������صı���״̬Ϊ�ѳ������޸�Ϊ���ݱ����ɽ�
�����жϱ����Ƿ�ɹ���ͬ������س�����

2016.08.13

v1.2.7
�Ż������ӿڣ�����ǵ�ͣ��Ʊ���������ɹ�����ȡ�����²���Ҫ�ĺ���ͬ������س�
����

2016.07.19

v1.2.6
��л @Special ��ָ����������ʤ��ͳ�Ƶ�bug�������ڹ�Ʊ����ʧ�ܵ�ʱ��������һ��
ͳ�ƣ�������״��������ˣ�ͬ��ʤ�ʽ�����1%������س�����������

2016.07.14

v1.2.5
���ӵ�ͣ��Ʊ���ˣ���л @ɳ�� ���飬ͬ������˲��������ʣ������ʤ�ʣ����������
���ɿ��𣬻س���������

v1.2.4
������־�������ӡ�������ò�����������Ҫ��־Ϊ����

2016.07.13

v1.2.3
����ST��ͣ�ƹ�Ʊ�Ĺ��ˣ����� @�˲����ͷ�����Ż���־

2016.07.12

v1.2.2
�Ż������������

v1.2.1
�Ľ����������ã���л@az��ָ���������˴�ҵ���Ʊ�жϵ�bug

v1.2.0
��л @zw @ɳ�� �����ƣ���������������˹��˿��ƣ���ѡ��������ӯ��ѡ�ɡ����˴�
ҵ�弰���˺�������������pe������������ע�ͣ���Ϊ������peѡ�ɼ������˴�ҵ�壬��
���������ͣ����ǻس�Ҳ��Ӧ������

ע����������ʱЧ�ԣ��ز���ע��

2016.07.02

v1.1.2
������������ֲֹ�Ʊ��ͣ�����˵��±��ü������еĹ�Ʊ�����������⣬����س�Ӱ��
��������˵���ӯ��

˵������ǰ�������Ʊͣ�Ʋ���������ʱ���������У�ʼ�ձ���ָ����Ŀ�Ĺ�Ʊ�ֲ�

2016.07.01

v1.1.1
���� @zx1967 �ķ�����������ѡ����Ŀ��С��g.selected_stock_cnt = 100����ʵ���Ը�
�󣩣�����������Ŀ��С��ǡ��ȫ�����˵��������տ����ƱΪ�գ������������ˣ���
�����

2016.06.30

v1.1.0
��л @Īа�ľ��� �Ľ��飬�޸�Ϊrun_dailyִ�У���Ҫ������˻ز��ٶȣ��ز�ʱ����
���˽�һ��

-------------------------------------------------------------------------------
'''
