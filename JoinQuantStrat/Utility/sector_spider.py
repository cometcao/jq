'''
Created on 26 Oct 2017

@author: MetalInvest
'''
try:
    from kuanke.user_space_api import *         
except ImportError as ie:
    print(str(ie))
from jqdata import *
import numpy as np
import pandas as pd
import datetime
import requests
from bs4 import BeautifulSoup
from IPython.display import display, HTML


class sectorSpider(object):
    '''
    grab sector information from JQ
    '''
    sector_data_column = ['sector_code', 'sector_name', 'start_date', 'parent_code']
    sector_type_column = ['zjh','jq1','jq2','sw1','sw2','sw3','gn']
    def __init__(self):
        self.jq_sector_data, self.counter = self.grabInfo_v2()

        
    def grabInfo(self):
        r  = requests.get(r'https://www.joinquant.com/data/dict/plateData')
        data = r.content.decode("utf-8")
        soup = BeautifulSoup(data, "lxml")
        
        body = soup.find_all("div", { "class" : "api_container hidden" })[0]
        counter = 0
        mydict = {}
        for text in body.string.split('#'):
            if '|' in text:
                result=text.split('\r\n')
                res = [row.split('|') for row in result if "|" in row and '--' not in row]
                res = pd.DataFrame(res[1:], columns=res[0])
                mydict[result[0]] = res
                counter += 1
        return mydict, counter
    
    def grabInfo_v2(self):
        sector_num = len(sectorSpider.sector_type_column)
        r  = requests.get(r'https://www.joinquant.com/data/dict/plateData')
        data = r.content.decode("utf-8")
        soup = BeautifulSoup(data, "lxml")
        counter = 0
        mydict = {}
        for i in range(sector_num):
            table = soup.find_all('table')[i]
            result = []
            for row in table.find_all('tr'):
                result.append([x.text for x in row.find_all('td')])
            if 4 <= i <= 5:
                sector_data = pd.DataFrame(result[1:], columns=sectorSpider.sector_data_column)
            else:
                sector_data = pd.DataFrame(result[1:], columns=sectorSpider.sector_data_column[:-1])
            sector_data = sector_data.set_index(sectorSpider.sector_data_column[0])
            sector_data['start_date'] = pd.to_datetime(sector_data['start_date'])
            mydict[sectorSpider.sector_type_column[counter]] = sector_data
            counter += 1
        return mydict, counter

    def displayJQInfo(self):
        for sector, dict in self.jq_sector_data.items():
            print("sector[{0}]: ".format(sector))
            print(dict.tail(5))
            print('==============================================')
        
    def getSectorCode(self, sector_type):
        return self.jq_sector_data[sector_type].index.values