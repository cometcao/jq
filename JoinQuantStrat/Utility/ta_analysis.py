# -*- encoding: utf8 -*-
'''
Created on 4 Dec 2017

@author: MetalInvest
'''

try:
    from kuanke.user_space_api import *
except:
    pass
from jqdata import *
from common_include import *
from oop_strategy_frame import *
from macd_divergence import *


#######################################################
class TA_Factor(Rule):
    global_var = None
    def __init__(self, params):
        super(TA_Factor, self).__init__(params)
        self.period = params.get('period', '1d')
        self.ta_type = params.get('ta_type', None)
        self.count = params.get('count', 100)
        self.isLong = params.get('isLong', True)
        self.use_latest_data = params.get('use_latest_data', False)
        self.method = None

    def update_params(self, context, params):
        self.use_latest_data = params.get('use_latest_data', False)

    def filter(self, stock_list):
#         print self.method.__name__
        result = [stock for stock in stock_list if self.method(stock)]
        if result:
            print("通过技术指标 %s 参数 %s %s:" % (str(self.ta_type), self.period, "买点" if self.isLong else "卖点") + join_list([show_stock(stock) for stock in result[:10]], ' ', 10))
            self.recordBiaoLiStatus(result)
        return result
    
    def recordBiaoLiStatus(self, stock_list):
        for stock in stock_list:
            if not TA_Factor.global_var:
                break
            if self.isLong:
                if stock not in TA_Factor.global_var.long_record:
                    TA_Factor.global_var.long_record[stock] = (None, self.ta_type, self.period)
                else:
                    if len(TA_Factor.global_var.long_record[stock]) != 3: # not ordered
                        TA_Factor.global_var.long_record[stock] = (None, self.ta_type, self.period)
            else:
                if stock not in TA_Factor.global_var.short_record:
                    TA_Factor.global_var.short_record[stock] = (None, self.ta_type, self.period)
                else:
                    if len(TA_Factor.global_var.short_record[stock]) != 3: # not ordered
                        TA_Factor.global_var.short_record[stock] = (None, self.ta_type, self.period)
        
    def getlatest_df(self, stock, count, period, fields, dataframe_flag = True, sub_period='230m'):
        df_data = attribute_history(stock, count, period, fields, df=dataframe_flag)
        if not self.use_latest_data:
            return df_data
        latest_stock_data = attribute_history(stock, 1, sub_period, fields, skip_paused=True, df=dataframe_flag) # 14:50
        if dataframe_flag:
            current_date = latest_stock_data.index[-1].date()
            latest_stock_data = latest_stock_data.reset_index(drop=False)
            latest_stock_data.ix[0, 'index'] = pd.DatetimeIndex([current_date])[0]
            latest_stock_data = latest_stock_data.set_index('index')
            df_data = df_data.reset_index().drop_duplicates(subset='index').set_index('index')
            try:
                df_data = df_data.append(latest_stock_data, verify_integrity=True) # True
            except Exception as e:
                print ("data error:" + str(e))
                pass
        else:
            final_fields = []
            if isinstance(fields, basestring):
                final_fields.append(fields)
            else:
                final_fields = list(fields)
            for field in final_fields:
                df_data[field] = np.append(df_data[field], latest_stock_data[field][-1])
        return df_data

    def get_rsi(self, cData):
        rsi6  = talib.RSI(cData, timeperiod=6)
        rsi12  = talib.RSI(cData, timeperiod=12)
        rsi24  = talib.RSI(cData, timeperiod=24)
        return rsi6, rsi12, rsi24

class TA_Factor_Short(TA_Factor):
    def __init__(self, params):
        super(TA_Factor_Short, self).__init__(params)
        if self.ta_type == TaType.MA:
            self.method = self.check_MA_list
        elif self.ta_type == TaType.MACD_STATUS:
            self.method = self.check_MACD_STATUS_list
        elif self.ta_type == TaType.RSI:
            self.method = self.check_RSI_list
        elif self.ta_type == TaType.TRIX:
            self.method = self.check_TRIX_list
        elif self.ta_type == TaType.MACD:
            self.method = self.check_MACD_list
        elif self.ta_type == TaType.BOLL:
            self.method = self.check_BOLL_list
        elif self.ta_type == TaType.BOLL_UPPER:
            self.method = self.check_BOLL_UPPER_list
        elif self.ta_type == TaType.BOLL_MACD:
            self.method = self.check_BOLL_MACD_list
        elif self.ta_type == TaType.TRIX_STATUS:
            self.method = self.check_TRIX_STATUS_list
        elif self.ta_type == TaType.TRIX_PURE:
            self.method = self.check_TRIX_PURE_list
        elif self.ta_type == TaType.MACD_CROSS:
            self.method = self.check_MACD_CROSS_list
        elif self.ta_type == TaType.KDJ_CROSS:
            self.method = self.check_KDJ_CROSS_list
    
    def check_KDJ_CROSS_list(self, stock):
        result = 0
        macd_cross = self.check_MACD_CROSS_list(stock)
        hData = self.getlatest_df(stock, self.count, self.period, ('close', 'high', 'low','volume'), dataframe_flag=False)
        slowk, slowd = talib.STOCH(hData['high'],
                                   hData['low'],
                                   hData['close'],
                                   fastk_period=9,
                                   slowk_period=3,
                                   slowk_matype=0,
                                   slowd_period=3,
                                   slowd_matype=0)
        slowj = 3 * slowk - 2 * slowd
        kdj_cross = False
        for i in range(1, 3): 
            kdj_cross = kdj_cross \
                or (slowk[-i] < slowd[-i] and slowk[-i-1] > slowd[-i-1]) \
                or (slowk[-i] < slowk[-i-1] and slowd[-1] < slowd[-i-1] and slowk[-i] < slowd[-i] and slowk[-i-1] < slowd[-i-1])
            if kdj_cross:
                break
        rsi_gold = self.check_RSI_CROS_list(stock, step=3)
        result = result + 1 if macd_cross else result
        result = result + 1 if kdj_cross else result
        result = result + 1 if rsi_gold else result
        return result >= 2
    
    def check_RSI_CROS_list(self, stock, step=3):
        hData =  self.getlatest_df(stock, self.count, self.period, ('close'), dataframe_flag=False)
        close = hData['close']
        rsi6_day,rsi12_day,rsi24_day = self.get_rsi(close)        
        if rsi6_day[-1] < rsi12_day[-1] < rsi24_day[-1]:
            for i in range(1, step):
                if rsi6_day[-1-i] > rsi12_day[-1-i] > rsi24_day[-1-i]:
                    return True
        return False 
    
    def check_MACD_CROSS_list(self, stock):
        fastperiod=12
        slowperiod=26
        signalperiod=9
        hData = self.getlatest_df(stock, self.count, self.period, ('close'), dataframe_flag=False)
        close = hData['close']
        _dif, _dea, _macd = talib.MACD(close, fastperiod, slowperiod, signalperiod)
        return _macd[-1] < 0 and _macd[-2] > 0      
        
    def check_BOLL_UPPER_list(self, stock):
        hData = self.getlatest_df(stock, self.count, self.period, ('close','high', 'volume','open'), dataframe_flag=False, sub_period='230m')
        close = hData['close']
        hopen = hData['open']
        high = hData['high']
        volume = hData['volume']
        # use BOLL to mitigate risk
        upper, _, lower = talib.BBANDS(close, timeperiod=21, nbdevup=2, nbdevdn=2, matype=0)
        vol_ma = talib.SMA(volume, 20)
        return high[-1] > upper[-1] and close[-1] < upper[-1] and close[-1] < hopen[-1] \
                and (volume[-1] > (vol_ma[-1] * 1.618) or volume[-2] > (vol_ma[-2] * 1.618)) \
                and high[-1] <= high[-2]
    
    def check_BOLL_MACD_list(self, stock):
        # macd chan combine with boll lower band
        df = self.getlatest_df(stock, self.count, self.period, ('high', 'low', 'open', 'close', 'volume'), dataframe_flag=True, sub_period='230m')
        if (np.isnan(df['high'][-1])) or (np.isnan(df['low'][-1])) or (np.isnan(df['close'][-1])):
            return False
        
        df.loc[:,'macd_raw'], _, df.loc[:,'macd'] = talib.MACD(df['close'].values, 12, 26, 9)
        df.loc[:,'upper'], _, _ = talib.BBANDS(df['close'].values, timeperiod=21, nbdevup=2, nbdevdn=2, matype=0)
        df = df.dropna()

        md = macd_divergence()
        return md.checkAtTopDoubleCross_chan(df) 
    
    def check_BOLL_list(self, stock):
        # for high rise stocks dropping below Boll top band, sell
        hData = self.getlatest_df(stock, self.count, self.period, ('close','high','open'), dataframe_flag=False)
        close = hData['close']
        hopen = hData['open']
        high = hData['high']
        upper, middle, lower = talib.BBANDS(close, timeperiod=21, nbdevup=2, nbdevdn=2, matype=0)
        first_band = upper[-1] - lower[-1]
        second_band = upper[-2] - lower[-2]
        third_band = upper[-3] - lower[-3]
        return close[-1] < hopen[-1] and close[-1] < upper[-1] and \
                ((high[-2] > upper[-2] and high[-3] > upper[-3]) or \
                (self.increaseRate(second_band, first_band) <= self.increaseRate(third_band, second_band) and high[-2] > upper[-2]))
    
    def increaseRate(self, a, b):
        return (b-a) / float(a)
    
    def check_MACD_list(self, stock):
        df = self.getlatest_df(stock, self.count, self.period, ('high', 'low', 'open', 'close', 'volume'), dataframe_flag=True, sub_period='230m')
        if (np.isnan(df['high'][-1])) or (np.isnan(df['low'][-1])) or (np.isnan(df['close'][-1])):
            return False
        
        df.loc[:,'macd_raw'], _, df.loc[:,'macd'] = talib.MACD(df['close'].values, 12, 26, 9)
        df.loc[:,'vol_ma'] = talib.SMA(df['volume'].values, 5)
        df = df.dropna()

        md = macd_divergence()
        df2 = self.getlatest_df(stock, self.count, self.period, ('high', 'low', 'open', 'close', 'volume'), dataframe_flag=False, sub_period='230m')
        return md.checkAtTopDoubleCross_v3(df2)# or md.checkAtTopDoubleCross_chan(df, False)
        
    def check_TRIX_list(self, stock, trix_span=12, trix_ma_span=9):
        hData = self.getlatest_df(stock, self.count, self.period, ('close','volume'), dataframe_flag=False, sub_period='230m')
        close = hData['close']
        volume = hData['volume']
        trix = talib.TRIX(close, trix_span)
        if np.isnan(close[-1]) or np.isnan(trix[-1]):
            return False
        ma_trix = talib.SMA(trix, trix_ma_span)
        # macd_raw,_,macd = talib.MACD(close, 12, 26, 9)
        obv = talib.OBV(close, volume)
        ma_obv = talib.SMA(obv, 30)
        return trix[-1] < ma_trix[-1] and obv[-1] > ma_obv[-1]#and macd_raw[-1] > 0
    
    def check_TRIX_STATUS_list(self, stock, trix_span=12, trix_ma_span=9):
        hData = self.getlatest_df(stock, self.count, self.period, ('close'), dataframe_flag=False)
        close = hData['close']
        trix = talib.TRIX(close, trix_span)
        if np.isnan(trix[-1]):
            return False
        ma_trix = talib.SMA(trix, trix_ma_span)
        return trix[-1] < trix[-2] and ((trix[-1] < ma_trix[-1] and (ma_trix[-1]-trix[-1]) > (ma_trix[-2]-trix[-2])) or \
                (trix[-1] >= ma_trix[-1] and (trix[-1] - ma_trix[-1]) < (trix[-2] - ma_trix[-2])))
    
    def check_TRIX_PURE_list(self, stock, trix_span=12, trix_ma_span=9):
        hData = self.getlatest_df(stock, self.count, self.period, ('close'), dataframe_flag=False)
        close = hData['close']
        trix = talib.TRIX(close, trix_span)
        if np.isnan(close[-1]) or np.isnan(trix[-1]):
            return False
        ma_trix = talib.SMA(trix, trix_ma_span)
        return trix[-1] <= ma_trix[-1] and trix[-1] < trix[-2]
 
    
    def check_RSI_list(self, stock):
        pass        
    
    def check_MACD_STATUS_list(self, stock):
        fastperiod=12
        slowperiod=26
        signalperiod=9
        hData = self.getlatest_df(stock, self.count, self.period, ('close'), dataframe_flag=False)
        close = hData['close']
        _dif, _dea, _macd = talib.MACD(close, fastperiod, slowperiod, signalperiod)
        return _macd[-1] < _macd[-2] and _macd[-1] < _macd[-3]
    
    def check_MACD_ZERO_list(self, stock):
        fastperiod=12
        slowperiod=26
        signalperiod=9
        hData = self.getlatest_df(stock, self.count, self.period, ('close'), dataframe_flag=False)
        close = hData['close']
        _dif, _dea, _macd = talib.MACD(close, fastperiod, slowperiod, signalperiod)
        return _dif[-1] >= 0 or _dea[-1] >=0
    
    def check_MA_list(self, stock):
        hData = self.getlatest_df(stock, self.count, self.period, ('close'), dataframe_flag=False)
        close = hData['close']
        ma = sum(close)/len(close)
        return close[-1] < ma
        
class TA_Factor_Long(TA_Factor):
    def __init__(self, params):
        super(TA_Factor_Long, self).__init__(params)
        if self.ta_type == TaType.RSI:
            self.method = self.check_rsi_list_v2
        elif self.ta_type == TaType.MACD:
            self.method = self.check_macd_list
        elif self.ta_type == TaType.MA:
            self.method = self.check_ma_list
        elif self.ta_type == TaType.TRIX:
            self.method = self.check_trix_list
        elif self.ta_type == TaType.TRIX_PURE:
            self.method = self.check_trix_pure_list
        elif self.ta_type == TaType.TRIX_STATUS:    
            self.method = self.check_trix_status_list
        elif self.ta_type == TaType.BOLL_MACD:
            self.method = self.check_boll_macd_list
        elif self.ta_type == TaType.BOLL_UPPER:
            self.method = self.check_boll_upper_list
        elif self.ta_type == TaType.MACD_STATUS:
            self.method = self.check_macd_status_list
        elif self.ta_type == TaType.MACD_ZERO:
            self.method = self.check_macd_zero_list
        elif self.ta_type == TaType.MACD_CROSS:
            self.method = self.check_macd_cross_list
        elif self.ta_type == TaType.KDJ_CROSS:
            self.method = self.check_kdj_cross_list
    
    def check_kdj_cross_list(self, stock):
        macd_cross = self.check_macd_cross_list(stock)# and self.check_macd_zero_list(stock)
        hData = self.getlatest_df(stock, self.count, self.period, ('close','high', 'low'), dataframe_flag=False)
        slowk, slowd = talib.STOCH(hData['high'],
                                   hData['low'],
                                   hData['close'],
                                   fastk_period=9,
                                   slowk_period=3,
                                   slowk_matype=0,
                                   slowd_period=3,
                                   slowd_matype=0)
        slowj = 3 * slowk - 2 * slowd
        kdj_cross = False
        for i in range(1, 3): #6
            kdj_cross = kdj_cross \
                or (slowk[-i] > slowd[-i] and slowk[-i-1] < slowd[-i-1]) \
                or (slowk[-i] > slowk[-i-1] and slowd[-1] > slowd[-i-1] and slowk[-i] > slowd[-i] and slowk[-i-1] > slowd[-i-1])            
            if kdj_cross:
                break
        rsi_gold = self.check_rsi_cross_list(stock, step=3)
        return kdj_cross and (macd_cross and rsi_gold)
    
    def check_rsi_cross_list(self, stock, step=3):
        hData = self.getlatest_df(stock, self.count, self.period, ('close'), dataframe_flag=False)
        close = hData['close']
        rsi6_day,rsi12_day,rsi24_day = self.get_rsi(close)        
        if rsi6_day[-1] > rsi12_day[-1] > rsi24_day[-1]:
            for i in range(1, step):
                if rsi6_day[-1-i] < rsi12_day[-1-i] < rsi24_day[-1-i]:
                    return True
        return False

    def check_macd_cross_list(self, stock):
        fastperiod=12
        slowperiod=26
        signalperiod=9
        hData = self.getlatest_df(stock, self.count, self.period, ('close'), dataframe_flag=False)
        close = hData['close']
        _dif, _dea, _macd = talib.MACD(close, fastperiod, slowperiod, signalperiod)
        return _macd[-1] > 0 and _macd[-2] < 0

    def check_boll_upper_list(self, stock):
        hData = self.getlatest_df(stock, self.count, self.period, ('close','high'), dataframe_flag=False)
        close = hData['close']
        high = hData['high']
        # use BOLL to mitigate risk
        upper, _, _ = talib.BBANDS(close, timeperiod=21, nbdevup=2, nbdevdn=2, matype=0)
        return high[-1] < upper[-1] or (high[-1] > upper[-1] and close[-1] < upper[-1])
    
    def check_macd_zero_list(self, stock):
        fastperiod=12
        slowperiod=26
        signalperiod=9
        hData = self.getlatest_df(stock, self.count, self.period, ('close'), dataframe_flag=False)
        close = hData['close']
        _dif, _dea, _macd = talib.MACD(close, fastperiod, slowperiod, signalperiod)
        return _dif[-1] <= 0 or _dea[-1] <=0  

    def check_macd_status_list(self, stock):
        fastperiod=12
        slowperiod=26
        signalperiod=9
        hData = self.getlatest_df(stock, self.count, self.period, ('close'), dataframe_flag=False)
        close = hData['close']
        _dif, _dea, _macd = talib.MACD(close, fastperiod, slowperiod, signalperiod)
        return _macd[-1] > _macd[-2] and _macd[-1] > _macd[-3]
    
    def check_boll_macd_list(self, stock):
        # macd chan combine with boll lower band
        df = self.getlatest_df(stock, self.count, self.period, ('high', 'low', 'open', 'close', 'volume'), dataframe_flag=True)
        if (np.isnan(df['high'][-1])) or (np.isnan(df['low'][-1])) or (np.isnan(df['close'][-1])):
            return False
        
        df.loc[:,'macd_raw'], _, df.loc[:,'macd'] = talib.MACD(df['close'].values, 12, 26, 9)
        _, _, df.loc[:, 'lower'] = talib.BBANDS(df['close'].values, timeperiod=21, nbdevup=2, nbdevdn=2, matype=0)
        df = df.dropna()
        md = macd_divergence()
        return md.checkAtBottomDoubleCross_chan(df)

    def check_trix_list(self, stock, trix_span=12, trix_ma_span=9):
        # special treatment for the long case
        hData = self.getlatest_df(stock, self.count, self.period, ('close','volume'), dataframe_flag=False, sub_period='230m')
        close = hData['close']
        volume = hData['volume']
        trix = talib.TRIX(close, trix_span)
        if np.isnan(trix[-1]) or np.isnan(close[-1]):
            return False
        ma_trix = talib.SMA(trix, trix_ma_span)
        obv = talib.OBV(close, volume)
        ma_obv = talib.SMA(obv, 30)
        return trix[-1] > ma_trix[-1] and trix[-2] < ma_trix[-2] and obv[-1] < ma_obv[-1]
        
    def check_trix_pure_list(self, stock, trix_span=12, trix_ma_span=9):
        hData = self.getlatest_df(stock, self.count, self.period, ('close'), dataframe_flag=False)
        close = hData['close']
        trix = talib.TRIX(close, trix_span)
        if np.isnan(close[-1]) or np.isnan(trix[-1]):
            return False
        ma_trix = talib.SMA(trix, trix_ma_span)
        return trix[-1] > ma_trix[-1] and trix[-1] > trix[-2]

    def check_trix_status_list(self, stock, trix_span=12, trix_ma_span=9):
        hData = self.getlatest_df(stock, self.count, self.period, ('close'), dataframe_flag=False)
        close = hData['close']
        trix = talib.TRIX(close, trix_span)
        if np.isnan(trix[-1]):
            return False
        ma_trix = talib.SMA(trix, trix_ma_span)
        return trix[-1] >= trix[-2] and ((trix[-1] < ma_trix[-1] and (ma_trix[-1]-trix[-1]) < (ma_trix[-2]-trix[-2])) or \
                (trix[-1] >= ma_trix[-1] and (trix[-1] - ma_trix[-1]) > (trix[-2] - ma_trix[-2])))


    def check_ma_list(self, stock):
        hData = self.getlatest_df(stock, self.count, self.period, ('close'), dataframe_flag=False)
        close = hData['close']
        ma = sum(close)/len(close)
        return close[-1] > ma

    def check_rsi_list_old(self, stock):
        hData = self.getlatest_df(stock, self.count, self.period, ('close'), dataframe_flag=False)
        close = hData['close']
        is_suddenly_rise = False
        n=10
        rsi6_day,rsi12_day,rsi24_day = self.get_rsi(close)
        for i in range(-n,-3): #i==-5,-4,-3,-2
            if (rsi6_day[i] <rsi12_day[i]) and (rsi6_day[i]< rsi24_day[i]) and(rsi6_day[i-1] <rsi12_day[i-1]) and (rsi6_day[i-1]< rsi24_day[i-1]):
                for a in range(i+1,-2):
                    if (rsi6_day[a] > rsi12_day[a]) and (rsi6_day[a]>rsi24_day[a]):
                        for b in range(a+1,-1):
                            if rsi12_day[b] >= rsi6_day[b]:
                                for c in range(b+1,0):
                                    if (rsi12_day[c] <=rsi6_day[c]) and (rsi6_day[-1]>rsi6_day[-2]):
                                        is_suddenly_rise = True
        return  is_suddenly_rise 

    def check_rsi_list(self, stock):
        hData = self.getlatest_df(stock, self.count, self.period, ('close'), dataframe_flag=False)
        close = hData['close']
        is_ticked = False
        n=10
        rsi6_day,rsi12_day,rsi24_day = self.get_rsi(close)
        if rsi6_day[-1] > rsi12_day[-1] > rsi24_day[-1]: #最新多头排列
            current6 = rsi6_day[-1]
            if rsi6_day[-2] < rsi12_day[-2] < rsi24_day[-2]: 
                if rsi6_day[-3] > rsi12_day[-3] and rsi6_day[-3] > rsi24_day[-3]:
                    is_ticked=True
        return is_ticked
        
    def check_rsi_list_v2(self, stock, step=3):
        hData = self.getlatest_df(stock, self.count, self.period, ('close'), dataframe_flag=False)
        close = hData['close']
        is_ticked = False
        n=10
        rsi6_day,rsi12_day,rsi24_day = self.get_rsi(close)
        if rsi6_day[-1] > rsi12_day[-1] > rsi24_day[-1] >= 50 \
            and (rsi6_day[-1] > rsi6_day[-2] and rsi12_day[-1] > rsi12_day[-2] and rsi24_day[-1] > rsi24_day[-2]): #最新多头排列 且大于50
#             current6 = rsi6_day[-1]
            for gap1 in range(2, step): # 3
                if rsi6_day[-1-gap1] < rsi12_day[-1-gap1] < rsi24_day[-1-gap1]: 
                    if rsi6_day[-1-gap1] < 50 and rsi6_day[-1-gap1] < rsi6_day[-gap1] and rsi6_day[-1-gap1] < rsi6_day[-2-gap1]:
                        for gap2 in range(1, step):
                            if rsi6_day[-1-gap1-gap2] > rsi12_day[-1-gap1-gap2] >= rsi24_day[-1-gap1-gap2]:
                                is_ticked=True
#         check_trix_status = True
        return is_ticked #and check_trix_status
        
    def check_macd_list(self, stock):
        df = self.getlatest_df(stock, self.count, self.period, ('high', 'low', 'open', 'close', 'volume'), dataframe_flag=True, sub_period='230m')
        if (np.isnan(df['high'][-1])) or (np.isnan(df['low'][-1])) or (np.isnan(df['close'][-1])):
            return False
        
        df.loc[:,'macd_raw'], _, df.loc[:,'macd'] = talib.MACD(df['close'].values, 12, 26, 9)
        df.loc[:,'vol_ma'] = talib.SMA(df['volume'].values, 5)
        df = df.dropna()

        md = macd_divergence()
        # df2 = attribute_history(stock, self.count, self.period, ('high', 'low', 'open', 'close', 'volume'), df=False)
        return md.checkAtBottomDoubleCross_v2(df) #or md.checkAtBottomDoubleCross_v3(df2) #or md.checkAtBottomDoubleCross_chan(df, False)

class checkTAIndicator(Filter_stock_list):
    def __init__(self, params):
        Filter_stock_list.__init__(self, params)
    
class checkTAIndicator_OR(checkTAIndicator):
    def __init__(self, params):
        checkTAIndicator.__init__(self, params)
        self.filters = params.get('TA_Indicators', None)
        self.isLong = params.get('isLong', True)
    def filter(self, context, data, stock_list):
        result_list = []
        for fil,period,count in self.filters:
            ta = TA_Factor_Long({'ta_type':fil, 'period':period, 'count':count, 'isLong':self.isLong}) if self.isLong else TA_Factor_Short({'ta_type':fil, 'period':period, 'count':count, 'isLong':self.isLong})
            result_list += ta.filter(stock_list)
        return [stock for stock in stock_list if stock in result_list]

    def __str__(self):
        return '按照技术指标过滤-OR'

class checkTAIndicator_AND(checkTAIndicator):
    def __init__(self, params):
        checkTAIndicator.__init__(self, params)
        self.filters = params.get('TA_Indicators', None)
        self.isLong = params.get('isLong', True)
    def filter(self, context, data, stock_list):
        result_list = stock_list
        for fil,period,count in self.filters:
            ta = TA_Factor_Long({'ta_type':fil, 'period':period, 'count':count, 'isLong':self.isLong}) if self.isLong else TA_Factor_Short({'ta_type':fil, 'period':period, 'count':count, 'isLong':self.isLong})
            filtered_list = ta.filter(stock_list)
            result_list = [stock for stock in result_list if stock in filtered_list]
            if not result_list:
                return []
        return result_list

    def __str__(self):
        return '按照技术指标过滤-AND'
