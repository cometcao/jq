'''
Created on 28 Feb 2018

@author: MetalInvest
'''
try:
    from rqdatac import *
except:
    pass
try:
    from jqdata import *
except:
    pass

try: 
    import jqdatasdk
except:
    pass

from enum import Enum 
import datetime
import pandas as pd
import tushare as ts
import json

class DataRetriever():
    @staticmethod
    def get_data(security, start_date='2006-01-01', end_date=str(datetime.datetime.today()), count=100, period='1d', fields=None, skip_suspended=False, adjust_type='pre'):
        pass

    @staticmethod
    def get_research_data(security, start_date='2006-01-01', end_date=str(datetime.datetime.today()), count=100, period='1d', fields=None, skip_suspended=False, adjust_type='pre'):
        pass


class JqDataRetriever(DataRetriever):
    @staticmethod
    def get_data(security, start_date='2006-01-01', end_date=str(datetime.datetime.today()), count=100, period='1d', fields=None, skip_suspended=False, adjust_type='pre', df=True):
        return jqdatasdk.attribute_history(security, count, period, fields = fields, skip_paused=skip_suspended, df=df)
    @staticmethod
    def get_research_data(security, start_date='2006-01-01', end_date=str(datetime.datetime.today()), count=100, period='1d', fields=None, skip_suspended=False, adjust_type='pre'):
        JqDataRetriever.authenticate()
        return jqdatasdk.get_price(security, count=count, end_date=end_date, frequency=period, fields = fields, skip_paused=skip_suspended, fq=adjust_type)
    
    @staticmethod
    def authenticate():
        with open('auth.json', encoding='utf-8') as data_file:
            data = json.loads(data_file.read())
        jqdatasdk.auth(data["user"], data["password"])
        
    @staticmethod
    def get_index_stocks(index):
        JqDataRetriever.authenticate()
        return jqdatasdk.get_index_stocks(index)

    @staticmethod
    def get_trading_date(count=1):
        JqDataRetriever.authenticate()
        return jqdatasdk.get_trade_days(count=count)


class TSDataRetriever(DataRetriever):
    @staticmethod
    def get_data(security, start_date='2006-01-01', end_date=str(datetime.datetime.today()), period='D', adjust_type='qfq', is_index=False):
        try:
            security = security[:6]
            if not isinstance(start_date, str):
                start_date = str(start_date)
            if not isinstance(end_date, str):
                end_date = str(end_date)
                
            s_dataframe = TSDataRetriever.get_k_data(code=security, start=start_date, end=end_date, ktype=period, autype=adjust_type, index=is_index)
            
            if period == 'D':
                s_dataframe['date'] = s_dataframe.apply(lambda row: datetime.datetime.strptime(row['date'], '%Y-%m-%d'), axis=1)
            elif period == '30': # only consider this case for now
                s_dataframe['date'] = s_dataframe.apply(lambda row: datetime.datetime.strptime(row['date'], '%Y-%m-%d %H:%M'), axis=1)
            s_dataframe.set_index('date', drop=True, inplace=True, verify_integrity=True)
            s_dataframe.rename(columns={'volume': 'money'}, inplace=True)
            s_dataframe = s_dataframe[['open', 'close', 'high', 'low', 'money']]
            
#             print(start_date)
#             print(end_date)
#             print(s_dataframe.head(3))
#             print(s_dataframe.tail(3))
            
            return s_dataframe
        except Exception as e:
            print("Failed to retrieve TS data:{0}".format(str(e)))
            return None
    
    @staticmethod
    def get_k_data(code, start, end, ktype, autype, index):
        s_dataframe = ts.get_k_data(code=code, start=start, end=end, ktype=ktype, autype=autype, index=index)
        print("fetched from {0} to {1}".format(s_dataframe.iloc[0, 0], s_dataframe.iloc[-1, 0]))
        while s_dataframe.iloc[0,0] > start:
            new_end = s_dataframe.iloc[0,0]
            print("continue fetching {0} to {1}".format(start, new_end))
            part_s_dataframe = ts.get_k_data(code=code, start=start, end=new_end, ktype=ktype, autype=autype, index=index)
            if part_s_dataframe.empty or part_s_dataframe.iloc[0, 0] == new_end:
                print("no more data returned")
                break
            print("continue fetched {0} to {1}".format(part_s_dataframe.iloc[0, 0], part_s_dataframe.iloc[-1, 0]))
            s_dataframe = pd.concat(part_s_dataframe, s_dataframe)
        return s_dataframe
            

def convertIntTimestamptodatetime(time):
    year = int(time / 1e10)
    time = time % 1e10 
    month = int(time / 1e8)
    time = time % 1e8
    day = int(time / 1e6)
    time = time % 1e6
    hour = int(time / 1e4)
    time = time % 1e4
    minute = int(time / 100)
    time = time % 100
    second = int(time)
    timestamp = np.datetime64(datetime.datetime(year, month, day, hour, minute, second))
    return timestamp
    

class RqDataRetriever(DataRetriever):
    @staticmethod
    def get_data(security, count=100, period='1d', fields=None, skip_suspended=False, adjust_type='pre', df=True, include_now=False):
        if df and 'datetime' not in fields:
            fields.append('datetime')
        try:
            data_array = history_bars(security, bar_count=count, frequency=period, fields = fields, skip_suspended=skip_suspended, include_now=include_now)
            if df:
                if data_array is not None and data_array.size > 0:
                    data_array = pd.DataFrame(data_array, columns=fields)
                    data_array['datetimestamp'] = data_array.apply(lambda row: convertIntTimestamptodatetime(row['datetime']), axis=1)
                    data_array.set_index('datetimestamp', inplace=True, drop=True)
                    data_array = data_array.drop(['datetime'], axis=1)
                else:
                    data_array = pd.DataFrame(columns=fields)
            else:
                if data_array is None:
                    data_array = np.array([])
            return data_array
        except Exception as e:
            print("stock {0} data error: {1}".format(security, e))
            print("count{0}, period{1}, fields{2}, skip_suspended{3}, adjust_type{4}, df{5}, include_now{6}".format(count, period, fields, skip_suspended, adjust_type, df, include_now))
            if df:
                return pd.DataFrame(columns=fields)
            else: 
                return np.array([])


    @staticmethod
    def get_research_data(security, start_date='2006-01-01', end_date=None, period='1d', fields=None, skip_suspended=False, adjust_type='pre', df=True):
        data_df = get_price(security, start_date=start_date, end_date=end_date, frequency=period, fields = fields, skip_suspended=skip_suspended, adjust_type=adjust_type)
        if not df:
            data_df = data_df.values
        return data_df

class SecurityDataManager():
    """
    This class is the ultimate class to provide all sourcing data for TTC system
    """
    @classmethod
    def get_research_data_jq(cls, security, start_date='2006-01-01', end_date=str(datetime.datetime.today()), count=100, period='1d', fields=None, skip_suspended=False, adjust_type='pre'):
        return JqDataRetriever.get_research_data(security, start_date, end_date, count, period, fields, skip_suspended, adjust_type)
    
    @classmethod
    def get_run_data_jq(cls, security, start_date='2006-01-01', end_date=str(datetime.datetime.today()), count=100, period='1d', fields=None, skip_suspended=False, adjust_type='pre', df=True):
        return JqDataRetriever.get_data(security, start_date, end_date, count, period, fields, skip_suspended, adjust_type, df)
    
    @classmethod
    def get_research_data_rq(cls, security, start_date='2006-01-01', end_date=None, period='1d', fields=None, skip_suspended=False, adjust_type='pre', df=True):
        return RqDataRetriever.get_research_data(security, start_date, end_date, period, fields, skip_suspended, adjust_type, df)
        
    @classmethod
    def get_data_rq(cls, security, count=100, period='1d', fields=None, skip_suspended=False, adjust_type='pre', df=True, include_now=False):
        return RqDataRetriever.get_data(security, count, period, fields, skip_suspended, adjust_type, df, include_now)
    
    @classmethod
    def get_data_ts(cls, security, start_date='2006-01-01', end_date=None, period='D', adjust_type='qfq', is_index=False):
        # only for basic security data [open, close, high, low, money]
        return TSDataRetriever.get_data(security, start_date, end_date, period, adjust_type, is_index)