'''
Created on 24 Feb 2017

@author: MetalInvest
'''

from kuanke.user_space_api import *
from jqdata import *
from scipy.signal import argrelextrema

class chip_migration_II(object):
    '''
    use listed tuple for chip migration calculation
    '''
    
    def __init__(self, df, collective_tr_sum=100):
        '''
        Constructor
        '''
        self.collective_tr_sum = collective_tr_sum
        self.chip_sum = 0
        self.df = df
        self._createInitialView()
        self._decayView()
        
    def _initialIndex(self, df):
        total = 0
        row_size, _ = df.shape
        for i in range(0, row_size):
            dai = df.index[i]
            total += df.loc[dai, 'turnover_ratio']
            if total > self.collective_tr_sum:
                return i
        return -1        
    
    def _createInitialView(self):
        ii = self._initialIndex(self.df)
        self.df.ix[-1, 'chip_density'] = 1 # to do
        initial_df = self.df
        if ii != -1:
            initial_df = self.df.iloc[:ii+1]
        chip_view = initial_df.groupby('avg').agg({'turnover_ratio':'sum'})
        self.chip_sum = chip_view.ix[:,'turnover_ratio'].sum()
        self.decay_view = self.df.iloc[ii+1:]
        self.view  = [(float(x[0]),float(x[1])) for x in chip_view.itertuples(index=True)]
    
    def _decayView(self):
        for da, item in self.decay_view.iterrows():
            avg = item['avg']
            tr = item['turnover_ratio']
            self._chip_change(avg, tr)
            wave_range = (self.view[-1][0] - self.view[0][0]) / self.view[0][0]
            density = self.chip_sum / wave_range
            self.df.loc[da, 'chip_density'] = density
    
    def _price_sensitivity(self):
        bottomIndex = argrelextrema(self.df.low.values, np.less_equal,order=3)[0]
        topIndex = argrelextrema(self.df.high.values, np.greater,order=3)[0]
        allIndex = bottomIndex + topIndex
        total_len = len(allIndex)
        for i in xrange(0,total_len):
            j = i + 1
            if j == total_len:
                break
            currentIndex = allIndex[i]
            nextIndex = allIndex[j]
        pass
    
    def _chip_change(self, avg, tr):
        self._work_out_change_portion(avg, tr)
        a1, t1 = zip(*self.view)
        a2, t2 = zip(*self.moved_tr)
        self.view = zip(a1, [x - y for x, y in zip(t1, t2)])
        self.view.append((avg, tr))
        self.view.sort()
        
        while True:
            size = len(self.view)
            list_to_remove = []
            for i in xrange(0, size//2):
                _, t1 = self.view[i]
                _, t2 = self.view[-(i+1)]
                if t1 < 0:
                    list_to_remove.append((self.view[i], self.view[i+1]))
                if t2 < 0:
                    list_to_remove.append((self.view[-(i+1)], self.view[-(i+2)]))
                if list_to_remove:
                    break
            if not list_to_remove:
                break
            for a, b in list_to_remove:
                c = (b[0], a[1]+b[1])
                try:
                    self.view.remove(a)
                    self.view.remove(b)
                    self.view.append(c)
                except ValueError:
                    pass
            self.view.sort()
        
        
    def _work_out_change_portion(self, avg, tr):
        pct_change = [(x[0], abs((x[0]-avg)/avg)) for x in self.view]
        total_change = sum([x[1] for x in pct_change])
        self.moved_tr = [(x[0], x[1]/total_change * tr) for x in pct_change]
        
def chip_concentration(context, stock_list):
    density_dict = []
    for stock in stock_list:
#         print "working on stock %s" % stock
        df = attribute_history(stock, count = 120, unit='1d', fields=('avg', 'volume'), skip_paused=True)
        df_dates = df.index
        for da in df_dates:
            df_fund = get_fundamentals(query(
                    valuation.turnover_ratio
                ).filter(
                    valuation.code.in_([stock])
                ), date=da)
            if not df_fund.empty:
                df.loc[da, 'turnover_ratio'] = df_fund['turnover_ratio'][0]
        df = df.dropna()
        ch = chip_migration_II(df)
        concentration_number, latest_concentration_rate= analyze_chip_density(ch.df)
        density_dict.append((stock, concentration_number * latest_concentration_rate))
    return sorted(density_dict, key=lambda x : x[1], reverse=True)

def analyze_chip_density(df):
    df = df.dropna()
    df = df.drop_duplicates(cols='chip_density')
    bottomIndex = argrelextrema(df.chip_density.values, np.less_equal,order=3)[0]
    concentration_num = len(bottomIndex)
    latest_concentration_rate = df.chip_density.values[-1] / df.chip_density[bottomIndex[-1]]
    return concentration_num, latest_concentration_rate
