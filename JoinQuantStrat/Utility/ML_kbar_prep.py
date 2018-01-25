from kBarProcessor import *
from jqdata import *
import talib

class MLKbarPrep(object):
    '''
    Turn multiple level of kbar data into Chan Biaoli status,
    return a dataframe with combined biaoli status
    data types:
    biaoli status, high/low prices, volume/turnover ratio/money, MACD, sequence index
    '''

    monitor_level = ['1d', '30m']
    def __init__(self, params):
        self.isAnal = params.get('isAnal', False)
        self.count = params.get('count', 100)
        self.stock_df_dict = {}
    
    def retrieve_stock_data(self, stock):
        for level in MLKbarPrep.monitor_level:
            stock_df = None
            if self.isAnal:
                stock_df = attribute_history(stock, self.count, level, fields = ['open','close','high','low', 'money'], skip_paused=True, df=True)  
            else:
                latest_trading_day = get_trade_days(count=1)[-1]
                stock_df = get_price(stock, count=self.count, end_date=latest_trading_day, frequency=level, fields = ['open','close','high','low', 'money'], skip_paused=True)          
            stock_df = self.prepare_df_data(stock_df)
            self.stock_df_dict[level] = stock_df
    
    def prepare_df_data(self, stock_df):
        # MACD
        stock_df.loc[:,'macd_raw'], _, stock_df.loc[:,'macd']  = talib.MACD(stock_df['close'])
        # BiaoLi
        stock_df = self.prepare_biaoli(stock_df)
        return stock_df
        
    
    def prepare_biaoli(self, stock_df):
        kb = KBarProcessor(stock_df)
        kb_marked = kb.getMarkedBL()
        stock_df = pd.merge(stock_df, kb_marked, on=kb_marked.index, how='outer')
        return stock_df
    
    def prepare_training_data(self):
        higher_df = self.stock_df_dict[MLKbarPrep.monitor_level[0]]
        lower_df = self.stock_df_dict[MLKbarPrep.monitor_level[1]]