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

# ֤�����ҵ
HY_ZJH = ['A01','A02','A03','A04','A05','B06','B07','B08','B09','B11','C13','C14','C15','C17','C18','C19','C20','C21','C22','C23','C24','C25','C26','C27','C28','C29','C30','C31','C32','C33','C34','C35','C36','C37','C38','C39','C40','C41','C42','D44','D45','D46','E47','E48','E50','F51','F52','G53','G54','G55','G56','G58','G59','H61','H62','I63','I64','I65','J66','J67','J68','J69','K70','L71','L72','M73','M74','N77','N78','P82','Q83','R85','R86','R87','S90']
# �ۿ�һ����ҵ
HY_ZY_1 = ['HY001','HY002','HY003','HY004','HY005','HY006','HY007','HY008','HY009','HY010','HY011']
# �ۿ������ҵ
HY_ZY_2 = ['HY401','HY402','HY403','HY404','HY405','HY406','HY407','HY408','HY409','HY410','HY411','HY412','HY413','HY414','HY415','HY416','HY417','HY418','HY419','HY420','HY421','HY422','HY423','HY424','HY425','HY426','HY427','HY428','HY429','HY432','HY433','HY434','HY435','HY436','HY437','HY438','HY439','HY440','HY441','HY442','HY443','HY444','HY445','HY446','HY447','HY448','HY449','HY450','HY451','HY452','HY453','HY454','HY455','HY457','HY458','HY459','HY460','HY461','HY462','HY463','HY464','HY465','HY466','HY467','HY468','HY469','HY470','HY471','HY472','HY473','HY474','HY476','HY477','HY478','HY479','HY480','HY481','HY483','HY484','HY485','HY486','HY487','HY488','HY489','HY491','HY492','HY493','HY494','HY496','HY497','HY500','HY501','HY504','HY505','HY506','HY509','HY510','HY511','HY512','HY513','HY514','HY515','HY516','HY517','HY518','HY519','HY520','HY521','HY523','HY524','HY525','HY526','HY527','HY528','HY529','HY530','HY531','HY570','HY571','HY572','HY573','HY574','HY576','HY578','HY579','HY587','HY588','HY591','HY593','HY595','HY596','HY597','HY598','HY601']
# ����һ����ҵ
SW1 = ['801010','801020','801030','801040','801050','801080','801110','801120','801130','801140','801150','801160','801170','801180','801200','801210','801230','801710','801720','801730','801740','801750','801760','801770','801780','801790','801880','801890']
# ���������ҵ
SW2 = ['801011','801012','801013','801014','801015','801016','801017','801018','801021','801022','801023','801024','801032','801033','801034','801035','801036','801037','801041','801051','801053','801054','801055','801072','801073','801074','801075','801076','801081','801082','801083','801084','801085','801092','801093','801094','801101','801102','801111','801112','801123','801131','801132','801141','801142','801143','801144','801151','801152','801153','801154','801155','801156','801161','801162','801163','801164','801171','801172','801173','801174','801175','801176','801177','801178','801181','801182','801191','801192','801193','801194','801202','801203','801204','801205','801211','801212','801213','801214','801215','801222','801223','801231','801711','801712','801713','801721','801722','801723','801724','801725','801731','801732','801733','801734','801741','801742','801743','801744','801751','801752','801761','801881']
# ����������ҵ
SW3 = ['850111','850112','850113','850121','850122','850131','850141','850151','850152','850154','850161','850171','850181','850211','850221','850222','850231','850241','850242','850311','850313','850321','850322','850323','850324','850331','850332','850333','850334','850335','850336','850337','850338','850339','850341','850342','850343','850344','850345','850351','850352','850353','850361','850362','850363','850372','850373','850381','850382','850383','850411','850412','850521','850522','850523','850531','850541','850542','850543','850544','850551','850552','850553','850611','850612','850614','850615','850616','850623','850711','850712','850713','850714','850715','850716','850721','850722','850723','850724','850725','850726','850727','850728','850729','850731','850741','850751','850811','850812','850813','850822','850823','850831','850832','850833','850841','850851','850852','850911','850912','850913','850921','850935','850936','850941','851012','851013','851014','851021','851111','851112','851113','851114','851115','851121','851122','851231','851232','851233','851234','851235','851236','851241','851242','851243','851244','851311','851312','851313','851314','851315','851316','851322','851323','851324','851325','851326','851327','851411','851421','851432','851433','851434','851435','851441','851511','851512','851521','851531','851541','851551','851561','851611','851612','851613','851614','851615','851621','851631','851641','851711','851721','851731','851741','851751','851761','851771','851781','851811','851821','851911','851921','851931','851941','852021','852031','852032','852033','852041','852051','852052','852111','852112','852121','852131','852141','852151','852211','852221','852222','852223','852224','852225','852226','852241','852242','852243','852244','852311','857221','857231','857232','857233','857234','857235','857241','857242','857243','857244','857251','857321','857322','857323','857331','857332','857333','857334','857335','857336','857341','857342','857343','857344','857411','857421','857431','858811']
# ������
GN = ['GN001','GN028','GN030','GN031','GN032','GN034','GN035','GN036','GN039','GN040','GN041','GN045','GN046','GN050','GN057','GN062','GN069','GN074','GN075','GN076','GN077','GN079','GN080','GN081','GN086','GN087','GN088','GN089','GN090','GN091','GN092','GN093','GN096','GN098','GN099','GN100','GN101','GN103','GN104','GN106','GN107','GN109','GN110','GN111','GN112','GN113','GN114','GN115','GN116','GN119','GN121','GN123','GN124','GN125','GN126','GN127','GN128','GN129','GN130','GN131','GN132','GN133','GN134','GN135','GN136','GN137','GN138','GN139','GN140','GN141','GN142','GN144','GN145','GN146','GN148','GN149','GN151','GN152','GN153','GN154','GN155','GN156','GN157','GN158','GN159','GN160','GN161','GN162','GN163','GN164','GN165','GN166','GN167','GN168','GN169','GN170','GN171','GN172','GN173','GN174','GN175','GN176','GN177','GN178','GN179','GN180','GN181','GN182','GN183','GN184','GN185','GN186','GN187','GN188','GN189','GN190','GN191','GN192','GN193','GN194','GN195','GN196','GN197','GN198','GN199','GN200','GN201','GN202','GN203','GN204','GN205','GN206','GN207','GN208','GN209','GN210','GN211','GN212','GN213','GN214','GN215','GN216','GN217','GN218','GN219','GN220','GN221','GN222','GN223','GN224','GN225','GN226','GN227','GN228','GN229','GN230']

def get_data(stock, count, level, fields, skip_paused=False, df_flag=True, isAnal=False):
    df = None
    if isAnal:
        latest_trading_day = datetime.datetime.now().date()
        df = get_price(stock, count=count, end_date=latest_trading_day, frequency=level, fields = fields, skip_paused=skip_paused)
    else:
        df = attribute_history(stock, count, unit=level, fields = fields, skip_paused=skip_paused, df=df_flag)
    return df

class SectorSelection(object):
    '''
    This class implement the methods to rank the sectors
    '''
    def __init__(self, context = None, isAnal=False):
        '''
        Constructor
        '''
        self.context = context
        self.isAnal = isAnal
        self.frequency = '1d' # use day period
        self.period = 270
        self.gauge_period = 5
        self.top_limit = 5
        self.stock_data_buffer = {}

    def displayResult(self, industryStrength, isConcept=False):
#         print industryStrength
        for sector, strength in industryStrength[:self.top_limit]:
            stocks = []
            if isConcept:
                stocks = get_concept_stocks(sector)
            else:
                stocks = get_industry_stocks(sector)
            print (sector+':'+','.join([get_security_info(s).display_name for s in stocks]))
            
    def sendResult(self, industryStrength, isConcept=False):
        message = ""
        for sector, strength in industryStrength[:self.top_limit]:
            stocks = []
            if isConcept:
                stocks = get_concept_stocks(sector)
            else:
                stocks = get_industry_stocks(sector)
            message += sector + ':'
            message += ','.join([get_security_info(s).display_name for s in stocks])
            message += '***'
        send_message(message, channel='weixin')      

    def processAllSectors(self, sendMsg=False):
        industryStrength = self.processIndustrySectors()
        conceptStrength = self.processConceptSectors()
        self.displayResult(industryStrength)
        self.displayResult(conceptStrength, True)
        if sendMsg:
            self.sendResult(industryStrength)
            self.sendResult(conceptStrength, True)
        industry = [sector for sector, _ in industryStrength[:self.top_limit]] 
        concept = [sector for sector, _ in conceptStrength[:self.top_limit]]
        return (industry, concept)
    
    def processAllSectorStocks(self):
        industry, concept = self.processAllSectors()
        allstocks = []
        for idu in industry:
            allstocks += get_industry_stocks(idu)
        for con in concept:
            allstocks += get_concept_stocks(con)
        return list(set(allstocks))
        
    def processIndustrySectors(self):
        industryStrength = []
        # JQ industry , shenwan
        jqIndustry = SW3
        
        for industry in jqIndustry:
            try:
                stocks = get_industry_stocks(industry)
            except Exception as e:
                print(str(e))
                continue
            if len(stocks) > 3:
                industryStrength.append((industry, self.gaugeSectorStrength(stocks)))
        industryStrength = sorted(industryStrength, key=lambda x: x[1], reverse=True)
        return industryStrength
    
    def processConceptSectors(self):
        # concept
        conceptStrength = []
        conceptSectors = GN
        for concept in conceptSectors:
            try:
                stocks = get_concept_stocks(concept)
            except Exception as e:
                print(str(e))
                continue
            if len(stocks) > 3:
                conceptStrength.append((concept, self.gaugeSectorStrength(stocks)))
            
        conceptStrength = sorted(conceptStrength, key=lambda x: x[1], reverse=True)
        return conceptStrength
        
    def gaugeSectorStrength(self, sectorStocks,isSimpleMA=False):
        if isSimpleMA:
            sectorStrength = 0.0
            removed = 0
            for stock in sectorStocks:
                stockStrength = self.gaugeStockUpTrendStrength_MA(stock, isWeighted=False, index=-1)
                if stockStrength == -1:
                    removed+=1
                else:
                    sectorStrength += stockStrength
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
    
#     def gaugeStockUpTrendStrength_MA_best_effort(self, stock):
#         stock_df = attribute_history(stock, self.period, self.frequency, ('close','paused'), skip_paused=False) if not self.context else self.getlatest_df(stock, self.period, ['close','paused'])
#         MA_5 = talib.SMA(stock_df.close.values, 5)
#         MA_13 = talib.SMA(stock_df.close.values, 13)
#         MA_21 = talib.SMA(stock_df.close.values, 21)
#         MA_34 = talib.SMA(stock_df.close.values, 34)
#         MA_55 = talib.SMA(stock_df.close.values, 55)
#         MA_89 = talib.SMA(stock_df.close.values, 89)
#         MA_144 = talib.SMA(stock_df.close.values, 144)
#         MA_233 = talib.SMA(stock_df.close.values, 233)
#         pass
        
    
    def gaugeStockUpTrendStrength_MA(self, stock, isWeighted=True, index=-1):
#         stock_df = get_price(stock, count=self.period, end_date='2017-08-01', frequency='daily', fields=['close','paused'], skip_paused=False)
        if index == -1:
#             stock_df = attribute_history(stock, self.period, self.frequency, ('close','paused'), skip_paused=False) if not self.context else self.getlatest_df(stock, self.period, ['close','paused'])
            stock_df = self.getlatest_df(stock, self.period, ['close','paused'], skip_paused=False, df_flag=True)
            MA_5 = self.simple_moving_avg(stock_df.close.values, 5)
            MA_13 = self.simple_moving_avg(stock_df.close.values, 13)
            MA_21 = self.simple_moving_avg(stock_df.close.values, 21)
            MA_34 = self.simple_moving_avg(stock_df.close.values, 34)
            MA_55 = self.simple_moving_avg(stock_df.close.values, 55)
            MA_89 = self.simple_moving_avg(stock_df.close.values, 89)
            MA_144 = self.simple_moving_avg(stock_df.close.values, 144)
            MA_233 = self.simple_moving_avg(stock_df.close.values, 233)
            if stock_df.paused[index]: # paused we need to remove it from calculation
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
            if stock not in self.stock_data_buffer:
#                 stock_df = attribute_history(stock, self.period, self.frequency, ('close','paused'), skip_paused=False) if not self.context else self.getlatest_df(stock, self.period, ['close','paused'])
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
        if self.context:
            containPaused = 'paused' in fields
            if containPaused:
                fields.remove('paused')
            latest_stock_data = attribute_history(stock, 1, '230m', fields, skip_paused=skip_paused, df=df_flag)
            if containPaused:
                latest_stock_data.assign(paused=np.nan)
                cd = get_current_data()
                latest_stock_data.ix[-1,'paused'] = cd[stock].paused
    
            if df_flag:
                latest_stock_data = latest_stock_data.reset_index(drop=False)
                latest_stock_data.ix[0, 'index'] = pd.DatetimeIndex([self.context.current_dt.date()])[0]
                latest_stock_data = latest_stock_data.set_index('index')
                df = df.reset_index().drop_duplicates(subset='index').set_index('index')
                df = df.append(latest_stock_data, verify_integrity=True) # True
            else:
                final_fields = []
                if isinstance(fields, basestring):
                    final_fields.append(fields)
                else:
                    final_fields = list(fields)
                [np.append(df[field], latest_stock_data[field][-1]) for field in final_fields]
    
        return df