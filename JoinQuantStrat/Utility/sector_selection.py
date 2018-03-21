# -*- encoding: utf8 -*-
'''
Created on 2 Aug 2017

@author: MetalInvest
'''

try:
    from kuanke.user_space_api import *         
except ImportError as ie:
    print(str(ie))
from jqdata import *
import numpy as np
import pandas as pd
import talib
import datetime
from sector_spider import *

def get_data(stock, count, level, fields, skip_paused=False, df_flag=True, isAnal=False):
    df = None
    try:
        if isAnal:
            latest_trading_day = datetime.datetime.now().date()
            df = get_price(stock, count=count, end_date=latest_trading_day, frequency=level, fields = fields, skip_paused=skip_paused)
        else:
            df = attribute_history(stock, count, unit=level, fields = fields, skip_paused=skip_paused, df=df_flag)
    except:
        df = pd.DataFrame(columns=fields)
    return df

class SectorSelection(object):
    '''
    This class implement the methods to rank the sectors
    '''
    def __init__(self, isAnal=False, limit_pct=5, isStrong=True, min_max_strength = 0, useIntradayData=True, useAvg=True, avgPeriod=5, intraday_period='230m'):
        '''
        Constructor
        '''
        self.useIntradayData = useIntradayData
        self.useAvg = useAvg
        self.isAnal = isAnal
        self.frequency = '1d' # use day period
        self.period = 270
        self.gauge_period = avgPeriod
        self.top_limit = float(limit_pct) / 100.0
        self.isReverse = isStrong
        self.stock_data_buffer = {}
        self.min_max_strength = min_max_strength
        self.intraday_period = intraday_period
        
        self.ss = sectorSpider()
        self.jqIndustry = self.ss.getSectorCode('sw2') # SW2
        self.conceptSectors = self.ss.getSectorCode('gn')
        self.filtered_industry = []
        self.filtered_concept = []

    def displayResult(self, industryStrength, isConcept=False):
#         print industryStrength
        limit_value = int(self.top_limit * len(self.conceptSectors) if isConcept else self.top_limit * len(self.jqIndustry))
        for sector, strength in industryStrength[:limit_value]:
            stocks = []
            if isConcept:
                stocks = get_concept_stocks(sector)
            else:
                stocks = get_industry_stocks(sector)
            print (sector+'@'+str(strength)+':'+','.join([get_security_info(s).display_name for s in stocks]))
            
    def sendResult(self, industryStrength, isConcept=False):
        message = ""
        limit_value = int(self.top_limit * len(self.conceptSectors) if isConcept else self.top_limit * len(self.jqIndustry))
        for sector, strength in industryStrength[:limit_value]:
            stocks = []
            if isConcept:
                stocks = get_concept_stocks(sector)
            else:
                stocks = get_industry_stocks(sector)
            message += sector + ':'
            message += ','.join([get_security_info(s).display_name for s in stocks])
            message += '***'
        send_message(message, channel='weixin')      

    def processAllSectors(self, sendMsg=False, display=False):
        if self.filtered_concept and self.filtered_industry:
            print ("use cached sectors")
            return (self.filtered_industry, self.filtered_concept)
        
        industryStrength = self.processIndustrySectors()
        conceptStrength = self.processConceptSectors()
        if display:
            self.displayResult(industryStrength)
            self.displayResult(conceptStrength, True)
        if sendMsg:
            self.sendResult(industryStrength)
            self.sendResult(conceptStrength, True)
        concept_limit_value = int(self.top_limit * len(self.conceptSectors))
        industry_limit_value = int(self.top_limit * len(self.jqIndustry))
        self.filtered_industry = [sector for sector, strength in industryStrength[:industry_limit_value] if (strength >= self.min_max_strength if self.isReverse else strength <= self.min_max_strength)] 
        self.filtered_concept = [sector for sector, strength in conceptStrength[:concept_limit_value] if (strength >= self.min_max_strength if self.isReverse else strength <= self.min_max_strength)]
        return (self.ss.getSectorCodeName('sw2', self.filtered_industry).tolist(), self.ss.getSectorCodeName('gn', self.filtered_concept).tolist())
    
    def processAllSectorStocks(self, isDisplay=False):
        industry, concept = self.processAllSectors(display=isDisplay)
        allstocks = []
        for idu in industry:
            allstocks += get_industry_stocks(idu)
        for con in concept:
            allstocks += get_concept_stocks(con)
        return list(set(allstocks))
        
    def processIndustrySectors(self):
        industryStrength = []
        # JQ industry , shenwan
        
        for industry in self.jqIndustry:
            try:
                stocks = get_industry_stocks(industry)
            except Exception as e:
                print(str(e))
                continue
            if len(stocks) > 3:
                industryStrength.append((industry, self.gaugeSectorStrength(stocks)))
        industryStrength = sorted(industryStrength, key=lambda x: x[1], reverse=self.isReverse)
        return industryStrength
    
    def processConceptSectors(self):
        # concept
        conceptStrength = []

        for concept in self.conceptSectors:
            try:
                stocks = get_concept_stocks(concept)
            except Exception as e:
                print(str(e))
                continue
            if len(stocks) > 3:
                conceptStrength.append((concept, self.gaugeSectorStrength(stocks)))
            
        conceptStrength = sorted(conceptStrength, key=lambda x: x[1], reverse=self.isReverse)
        return conceptStrength
        
    def gaugeSectorStrength(self, sectorStocks):
        if not self.useAvg:
            sectorStrength = 0.0
            removed = 0
            for stock in sectorStocks:
                stockStrength = self.gaugeStockUpTrendStrength_MA(stock, isWeighted=False, index=-1)
                if stockStrength == -1:
                    removed+=1
                else:
                    sectorStrength += stockStrength
            if len(sectorStocks)==removed:
                sectorStrength = 0.0
            else:
                sectorStrength /= (len(sectorStocks)-removed)
            return sectorStrength  
        else:
            avgStrength = 0.0
            for i in range(-1, -self.gauge_period-1, -1): #range
                sectorStrength = 0.0
                removed = 0
                for stock in sectorStocks:
                    stockStrength = self.gaugeStockUpTrendStrength_MA(stock, isWeighted=False, index=i)
                    if stockStrength == -1:
                        removed+=1
                    else:
                        sectorStrength += stockStrength
                if len(sectorStocks)==removed:
                    sectorStrength = 0.0
                else:
                    sectorStrength /= (len(sectorStocks)-removed)
                avgStrength += sectorStrength
            avgStrength /= self.gauge_period
            return avgStrength    
    
    def gaugeStockUpTrendStrength_MA(self, stock, isWeighted=True, index=-1):
        if index == -1:
            stock_df = self.getlatest_df(stock, self.period, ['close','paused'], skip_paused=False, df_flag=True)
            MA_5 = self.simple_moving_avg(stock_df.close.values, 5)
            MA_13 = self.simple_moving_avg(stock_df.close.values, 13)
            MA_21 = self.simple_moving_avg(stock_df.close.values, 21)
            MA_34 = self.simple_moving_avg(stock_df.close.values, 34)
            MA_55 = self.simple_moving_avg(stock_df.close.values, 55)
            MA_89 = self.simple_moving_avg(stock_df.close.values, 89)
            MA_144 = self.simple_moving_avg(stock_df.close.values, 144)
            MA_233 = self.simple_moving_avg(stock_df.close.values, 233)
            if stock_df.empty or stock_df.paused[index]: # paused we need to remove it from calculation
                return -1 
            elif stock_df.close[index] < MA_5 or np.isnan(MA_5):
                return 0 if isWeighted else 1
            elif stock_df.close[index] < MA_13 or np.isnan(MA_13):
                return 5 if isWeighted else 2
            elif stock_df.close[index] < MA_21 or np.isnan(MA_21):
                return 13 if isWeighted else 3
            elif stock_df.close[index] < MA_34 or np.isnan(MA_34):
                return 21 if isWeighted else 4
            elif stock_df.close[index] < MA_55 or np.isnan(MA_55):
                return 34 if isWeighted else 5
            elif stock_df.close[index] < MA_89 or np.isnan(MA_89):
                return 55 if isWeighted else 6
            elif stock_df.close[index] < MA_144 or np.isnan(MA_144):
                return 89 if isWeighted else 7
            elif stock_df.close[index] < MA_233 or np.isnan(MA_233):
                return 144 if isWeighted else 8
            else:
                return 233 if isWeighted else 9
        else: # take average value of past 20 periods
            stock_df = MA_5 = MA_13 = MA_21 = MA_34 = MA_55 = MA_89 = MA_144 = MA_233 = None
            try:
                if stock not in self.stock_data_buffer:
                    stock_df = self.getlatest_df(stock, self.period, ['close','paused'], skip_paused=False, df_flag=True)
                    MA_5 = talib.SMA(stock_df.close.values, 5)
                    MA_13 = talib.SMA(stock_df.close.values, 13)
                    MA_21 = talib.SMA(stock_df.close.values, 21)
                    MA_34 = talib.SMA(stock_df.close.values, 34)
                    MA_55 = talib.SMA(stock_df.close.values, 55)
                    MA_89 = talib.SMA(stock_df.close.values, 89)
                    MA_144 = talib.SMA(stock_df.close.values, 144)
                    MA_233 = talib.SMA(stock_df.close.values, 233)
                    self.stock_data_buffer[stock]=[stock_df, MA_5, MA_13, MA_21, MA_34, MA_55, MA_89, MA_144, MA_233]
                else:
                    stock_df = self.stock_data_buffer[stock][0]
                    MA_5 = self.stock_data_buffer[stock][1]
                    MA_13 = self.stock_data_buffer[stock][2]
                    MA_21 = self.stock_data_buffer[stock][3]
                    MA_34 = self.stock_data_buffer[stock][4]
                    MA_55 = self.stock_data_buffer[stock][5]
                    MA_89 = self.stock_data_buffer[stock][6]
                    MA_144 = self.stock_data_buffer[stock][7]
                    MA_233 = self.stock_data_buffer[stock][8]
            except Exception as e:
                print (str(e))
                return -1
            if stock_df.paused[index]: # paused we need to remove it from calculation
                return -1 
            elif stock_df.close[index] < MA_5[index] or np.isnan(MA_5[index]):
                return 0 if isWeighted else 1
            elif stock_df.close[index] < MA_13[index] or np.isnan(MA_13[index]):
                return 5 if isWeighted else 2
            elif stock_df.close[index] < MA_21[index] or np.isnan(MA_21[index]):
                return 13 if isWeighted else 3
            elif stock_df.close[index] < MA_34[index] or np.isnan(MA_34[index]):
                return 21 if isWeighted else 4
            elif stock_df.close[index] < MA_55[index] or np.isnan(MA_55[index]):
                return 34 if isWeighted else 5
            elif stock_df.close[index] < MA_89[index] or np.isnan(MA_89[index]):
                return 55 if isWeighted else 6
            elif stock_df.close[index] < MA_144[index] or np.isnan(MA_144[index]):
                return 89 if isWeighted else 7
            elif stock_df.close[index] < MA_233[index] or np.isnan(MA_233[index]):
                return 144 if isWeighted else 8
            else:
                return 233 if isWeighted else 9

    def simple_moving_avg(self, series, period):
        total = sum(series[-period:])
        return total/period
    
    def getlatest_df(self, stock, count, fields, skip_paused=True, df_flag = True):
#         df = attribute_history(stock, count, '1d', fields, df=df_flag)
        df = get_data(stock, count, level='1d', fields=fields, skip_paused=skip_paused, df_flag=df_flag, isAnal=self.isAnal)
        if df.empty:
            return df
        if self.useIntradayData:
            containPaused = 'paused' in fields
            if containPaused:
                fields.remove('paused')
            latest_stock_data = attribute_history(stock, 1, self.intraday_period, fields, skip_paused=skip_paused, df=df_flag)
            if containPaused:
                latest_stock_data.assign(paused=np.nan)
                cd = get_current_data()
                latest_stock_data.ix[-1,'paused'] = cd[stock].paused

            if df_flag:
                current_date = latest_stock_data.index[-1].date()
                latest_stock_data = latest_stock_data.reset_index(drop=False)
                latest_stock_data.ix[0, 'index'] = pd.DatetimeIndex([current_date])[0]
                latest_stock_data = latest_stock_data.set_index('index')
                df = df.reset_index().drop_duplicates(subset='index').set_index('index')
                try:
                    df = df.append(latest_stock_data, verify_integrity=True) # True
                except:
                    print "stock %s has invalid history data" % stock 
            else:
                final_fields = []
                if isinstance(fields, basestring):
                    final_fields.append(fields)
                else:
                    final_fields = list(fields)
#                 [np.append(df[field], latest_stock_data[field][-1]) for field in final_fields]
                for field in final_fields:
                    df[field] = np.append(df[field], latest_stock_data[field][-1])
        return df