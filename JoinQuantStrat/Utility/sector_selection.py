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
from common_include import filter_paused, filter_new_stocks
from collections import OrderedDict

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
    def __init__(self, 
                 isAnal=False, 
                 limit_pct=5, 
                 isStrong=True, 
                 min_max_strength = 0, 
                 useIntradayData=True, 
                 useAvg=True, 
                 avgPeriod=5, 
                 intraday_period='230m', 
                 isWeighted=False,
                 effective_date=None):
        '''
        Constructor
        '''
        self.useIntradayData = useIntradayData
        self.useAvg = useAvg
        self.isAnal = isAnal
        self.frequency = '1d' # use day period
        self.period = 250
        self.gauge_period = avgPeriod
        self.top_limit = float(limit_pct) / 100.0
        self.isReverse = isStrong
        self.stock_data_buffer = {}
        self.min_max_strength = min_max_strength
        self.intraday_period = intraday_period
        self.isWeighted = isWeighted
        self.effective_date = effective_date
        self.all_industry_data = get_industries("sw_l3", date=effective_date)
        self.jqIndustry = self.all_industry_data.index.tolist()
        self.all_concept_data = get_concepts()
        self.conceptSectors = self.all_concept_data[self.all_concept_data["start_date"]<=effective_date].index.tolist()
        self.filtered_industry = []
        self.filtered_concept = []

    def displayResult(self, industryStrength, isConcept=False):
        limit_value = int(self.top_limit * len(self.conceptSectors) if isConcept else self.top_limit * len(self.jqIndustry))
        for sector, strength in industryStrength[:limit_value]:
            stocks = []
            if isConcept:
                stocks = get_concept_stocks(sector, self.effective_date)
                sector_name = self.all_concept_data.loc[sector, "name"]
            else:
                stocks = get_industry_stocks(sector, self.effective_date)
                sector_name = self.all_industry_data.loc[sector, "name"]
            print (sector_name+'-'+sector+'@'+str(strength)+':'+','.join([get_security_info(s).display_name for s in stocks]))
            
    def sendResult(self, industryStrength, isConcept=False):
        message = ""
        limit_value = int(self.top_limit * len(self.conceptSectors) if isConcept else self.top_limit * len(self.jqIndustry))
        for sector, strength in industryStrength[:limit_value]:
            stocks = []
            if isConcept:
                stocks = get_concept_stocks(sector,self.effective_date)
            else:
                stocks = get_industry_stocks(sector, self.effective_date)
            message += sector + ':'
            message += ','.join([get_security_info(s).display_name for s in stocks])
            message += '***'
        send_message(message, channel='weixin')      

    def processAllIndustrySectors(self, isDisplay=False):
        if self.filtered_industry:
            return self.filtered_industry

        industryStrength = self.processIndustrySectors()
        industry_limit_value = int(self.top_limit * len(self.jqIndustry))
        self.filtered_industry = [sector for sector, strength in industryStrength[:industry_limit_value] if (
            strength >= self.min_max_strength if self.isReverse else strength <= self.min_max_strength)]

        if isDisplay:
            print("industry strength: {0}".format(industryStrength))
            print("matching industries: {0}".format(self.filtered_industry))

        return self.filtered_industry

    def processAllSectors(self, sendMsg=False, display=False, byName=True):
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
        if byName:
            return (self.all_industry_data.loc[self.filtered_industry, "name"].tolist(), 
                    self.all_concept_data.loc[self.filtered_concept, "name"].tolist())
        else:
            return (self.filtered_industry, self.filtered_concept)
        
    def get_market_avg_strength(self, display=False):
        industryStrength = self.processIndustrySectors()
        conceptStrength = self.processConceptSectors()
        if display:
            self.displayResult(industryStrength)
            self.displayResult(conceptStrength, True)
        concept_limit_value = int(self.top_limit * len(self.conceptSectors))
        industry_limit_value = int(self.top_limit * len(self.jqIndustry))
        filtered_industry = [(sector, strength) for sector, strength in industryStrength[:industry_limit_value] if (strength >= self.min_max_strength if self.isReverse else strength <= self.min_max_strength)] 
        filtered_concept = [(sector, strength) for sector, strength in conceptStrength[:concept_limit_value] if (strength >= self.min_max_strength if self.isReverse else strength <= self.min_max_strength)]
        avg_industry_strength = sum([x[1] for x in filtered_industry]) / len(filtered_industry)
        avg_concept_strength = sum([x[1] for x in filtered_concept]) / len(filtered_concept)
        return avg_industry_strength, avg_concept_strength
    
    def processAllIndustrySectorStocks(self, isDisplay=False):
        industry = self.processAllIndustrySectors(isDisplay=isDisplay)
        allstocks = []
        for idu in industry:
            allstocks += get_industry_stocks(idu, self.effective_date)
            
        allstocks = list(OrderedDict.fromkeys(allstocks)) # keep order remove duplicates
        return allstocks
        
    
    def processAllSectorStocks(self, isDisplay=False):
        industry, concept = self.processAllSectors(display=isDisplay, byName=False)
        allstocks = []
        for idu in industry:
            allstocks += get_industry_stocks(idu, self.effective_date)
        for con in concept:
            allstocks += get_concept_stocks(con, self.effective_date)
        return list(set(allstocks))
        
    def processIndustrySectors(self):
        industryStrength = []
        # JQ industry , shenwan
        
        for industry in self.jqIndustry:
            try:
                stocks = get_industry_stocks(industry, self.effective_date)
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
                stocks = get_concept_stocks(concept, self.effective_date)
            except Exception as e:
                print(str(e))
                continue
            if len(stocks) > 3:
                conceptStrength.append((concept, self.gaugeSectorStrength(stocks)))
            
        conceptStrength = sorted(conceptStrength, key=lambda x: x[1], reverse=self.isReverse)
        return conceptStrength
        
    def gaugeSectorStrength(self, sectorStocks):
        sectorStocks = filter_paused(
            stocks=sectorStocks,
            end_date=self.effective_date)
        sectorStocks = filter_new_stocks(
            stocks=sectorStocks, end_dt=self.effective_date, n=250)
        if not sectorStocks:
            return 0
        if not self.useAvg:
            sectorStrength = 0.0
            for stock in sectorStocks:
                stockStrength = self.gaugeStockUpTrendStrength_MA(stock, isWeighted=self.isWeighted, index=-1)
                sectorStrength += stockStrength
            sectorStrength /= len(sectorStocks)
            return sectorStrength
        else:
            avgStrength = 0.0
            for i in range(-1, -self.gauge_period-1, -1): #range
                sectorStrength = 0.0

                for stock in sectorStocks:
                    stockStrength = self.gaugeStockUpTrendStrength_MA(stock, isWeighted=self.isWeighted, index=i)
                    sectorStrength += stockStrength
                sectorStrength /= len(sectorStocks)
                avgStrength += sectorStrength
            avgStrength /= self.gauge_period
            return avgStrength
    
    def gaugeStockUpTrendStrength_MA(self, stock, isWeighted=True, index=-1):
        stock_df = get_bars(
            security=stock,
            count=self.period,
            unit='1d',
            fields=['close'],
            include_now=True,
            end_dt=self.effective_date,
            df=False)
        if index == -1:
            MA_5 = self.simple_moving_avg(stock_df['close'], 5)
            MA_13 = self.simple_moving_avg(stock_df['close'], 13)
            MA_21 = self.simple_moving_avg(stock_df['close'], 21)
            MA_34 = self.simple_moving_avg(stock_df['close'], 34)
            MA_55 = self.simple_moving_avg(stock_df['close'], 55)
            MA_89 = self.simple_moving_avg(stock_df['close'], 89)
            MA_144 = self.simple_moving_avg(stock_df['close'], 144)
            MA_233 = self.simple_moving_avg(stock_df['close'], 233)
            if stock_df['close'][index] < MA_5 or np.isnan(MA_5):
                return 0 if isWeighted else 1
            elif stock_df['close'][index] < MA_13 or np.isnan(MA_13):
                return 5 if isWeighted else 2
            elif stock_df['close'][index] < MA_21 or np.isnan(MA_21):
                return 13 if isWeighted else 3
            elif stock_df['close'][index] < MA_34 or np.isnan(MA_34):
                return 21 if isWeighted else 4
            elif stock_df['close'][index] < MA_55 or np.isnan(MA_55):
                return 34 if isWeighted else 5
            elif stock_df['close'][index] < MA_89 or np.isnan(MA_89):
                return 55 if isWeighted else 6
            elif stock_df['close'][index] < MA_144 or np.isnan(MA_144):
                return 89 if isWeighted else 7
            elif stock_df['close'][index] < MA_233 or np.isnan(MA_233):
                return 144 if isWeighted else 8
            else:
                return 233 if isWeighted else 9
        else: # take average value of past 20 periods
            MA_5 = MA_13 = MA_21 = MA_34 = MA_55 = MA_89 = MA_144 = MA_233 = None
            try:
                if stock not in self.stock_data_buffer:
                    MA_5 = talib.SMA(stock_df['close'], 5)
                    MA_13 = talib.SMA(stock_df['close'], 13)
                    MA_21 = talib.SMA(stock_df['close'], 21)
                    MA_34 = talib.SMA(stock_df['close'], 34)
                    MA_55 = talib.SMA(stock_df['close'], 55)
                    MA_89 = talib.SMA(stock_df['close'], 89)
                    MA_144 = talib.SMA(stock_df['close'], 144)
                    MA_233 = talib.SMA(stock_df['close'], 233)
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
                print(e, stock)
                return -1
            if stock_df['close'][index] < MA_5[index] or np.isnan(MA_5[index]):
                return 0 if isWeighted else 1
            elif stock_df['close'][index] < MA_13[index] or np.isnan(MA_13[index]):
                return 5 if isWeighted else 2
            elif stock_df['close'][index] < MA_21[index] or np.isnan(MA_21[index]):
                return 13 if isWeighted else 3
            elif stock_df['close'][index] < MA_34[index] or np.isnan(MA_34[index]):
                return 21 if isWeighted else 4
            elif stock_df['close'][index] < MA_55[index] or np.isnan(MA_55[index]):
                return 34 if isWeighted else 5
            elif stock_df['close'][index] < MA_89[index] or np.isnan(MA_89[index]):
                return 55 if isWeighted else 6
            elif stock_df['close'][index] < MA_144[index] or np.isnan(MA_144[index]):
                return 89 if isWeighted else 7
            elif stock_df['close'][index] < MA_233[index] or np.isnan(MA_233[index]):
                return 144 if isWeighted else 8
            else:
                return 233 if isWeighted else 9

    def simple_moving_avg(self, series, period):
        total = sum(series[-period:])
        return total/period
