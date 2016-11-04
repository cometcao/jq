'''
Created on 15 Oct 2016

@author: MetalInvest
'''
import pandas as pd
import numpy as np
from jqdata import *
from sklearn import preprocessing
from sklearn import svm
from sklearn.ensemble import RandomForestClassifier
from sklearn.naive_bayes import GaussianNB
import datetime

def prepareTraining(df_dates, df, training_sample_size = 30, test_size = 365):
    # prepare training set
    x_all = []
    y_all = []
    
    for index in range(training_sample_size,len(df_dates)-test_size):
        start_da = df_dates[index-training_sample_size]
        pre_da = df_dates[index-1]
        da = df_dates[index]
        # setup training data
        features = []
        [features.append(x) for x in df.loc[start_da:pre_da,'open']]
        [features.append(x) for x in df.loc[start_da:pre_da,'close']]
        [features.append(x) for x in df.loc[start_da:pre_da,'high']]
        [features.append(x) for x in df.loc[start_da:pre_da,'low']]
        [features.append(x) for x in df.loc[start_da:pre_da,'turnover_ratio']]

        label = df.loc[da,'strength']

        x_all.append(features)
        y_all.append(label)

    #from sklearn import svm

    #��ʼ���û���ѧϰ�㷨����
    clf = svm.SVC()
    #     clf = RandomForestClassifier(n_estimators=50)
    #     clf = GaussianNB()
    #ѵ���Ĵ���
    clf.fit(x_all, y_all)
    #�õ����Խ���Ĵ���
    return clf

def makePrediction(df_dates, df, clf, stock, training_sample_size=30,test_size = 365):
    for index in range(len(df_dates)-test_size,len(df_dates)):
        start_da = df_dates[index-training_sample_size]
        pre_da = df_dates[index-1]
        da = df_dates[index]

        x_test = []
        [x_test.append(x) for x in df.loc[start_da:pre_da,'open']]
        [x_test.append(x) for x in df.loc[start_da:pre_da,'close']]
        [x_test.append(x) for x in df.loc[start_da:pre_da,'high']]
        [x_test.append(x) for x in df.loc[start_da:pre_da,'low']]
        [x_test.append(x) for x in df.loc[start_da:pre_da,'turnover_ratio']]

        prediction = clf.predict([x_test])
        df.loc[da, 'prediction'] = prediction

    # ����Ԥ�����û
    df['results_acc'] = (df['prediction'] == df['strength'])
    df['results_sign'] = (df['prediction'] * df['strength'] > 0)
    df_results_acc = df.ix[-test_size:,'results_acc']
    df_results_suc = df.ix[-test_size:,'results_sign']
    accrate = len(df_results_acc[df_results_acc==True]) / float(test_size)
    sucrate = len(df_results_suc[df_results_suc==True]) / float(test_size)
    print "success rate: %f" % sucrate
    print "accurate rate: %f" % accrate
    result = pd.DataFrame([[sucrate, accrate]], columns=["success","accurate"], index=[stock])
    return result


def getStrength(rt):
    label = 0
    if rt >= 1.02:
        label = 2
    elif rt >= 1:
        label = 1
    elif rt <= 0.98:
        label = -2
    elif rt < 1:
        label = -1
    return label

def initialize(context):
    # filter out new shares & ending shares & ended shares
    g.compute = True # make sure we only analyze once only
    g.total_days = 1095
    today_date = context.current_dt.date()
    past_date = today_date - datetime.timedelta(days=g.total_days)

    # all A share
    stock_pd = get_all_securities(types=['stock'], date=today_date)
    mask = stock_pd['start_date'] <= past_date
    mask2 = stock_pd['end_date'] == datetime.date(2200, 01, 01)
    stock_pd=stock_pd[mask==True][mask2==True]

    stock_list = stock_pd.index
    # filter out st shares
    is_st_list = get_extras('is_st', stock_list, start_date=context.current_dt, end_date=context.current_dt, df=False)
    stock_list = [x for x in is_st_list.keys() if is_st_list[x][0]==False]
    
    # control stock sector
    tmp_stock_list = get_index_stocks('399333.XSHE') # any thing else 000300.XSHG 399333.XSHE
    g.final_stock_list = [x for x in tmp_stock_list if x in stock_list]

# ÿ����λʱ��(�������ز�,��ÿ�����һ��,���������,��ÿ���ӵ���һ��)����һ��
def handle_data(context, data):
    if g.compute:
        today_date = context.current_dt.date()
        ##########################################################################################################
        pd_result = pd.DataFrame(columns=["success","accurate"])
        # only deal with one stock a time
        #     stock = final_stock_list[0]
        for stock in g.final_stock_list:
            print("analyzing {} ...".format(stock))
            df = get_price(stock, end_date=today_date, frequency='daily', fields=['open', 'close','high','low','money','volume'], skip_paused=True, fq='pre',count=g.total_days)
            df['return_1'] = (df['close'] - df['close'].shift(1)) / abs(df['close']) + 1
            df['strength'] = df['return_1'].apply(getStrength)
        
            df_dates=df.index 
            # preprocess data
            for da in df_dates:
                df_fund = get_fundamentals(query(
                        valuation.turnover_ratio
                    ).filter(
                        # ���ﲻ��ʹ�� in ����, Ҫʹ��in_()����
                        valuation.code.in_([stock])
                    ), date=da)
                if not df_fund.empty:
                    df.loc[da, 'turnover_ratio'] = df_fund['turnover_ratio'][0]
        
            df_mtss = get_mtss([stock], df_dates[0], df_dates[-1], fields=["date", "fin_value", "fin_buy_value", "fin_refund_value", "sec_value", "sec_sell_value", "sec_refund_value", "fin_sec_value"])
            # make sure we have data
            if not df_mtss.empty:
                df_mtss = df_mtss.set_index('date')
                df = df.merge(df_mtss, left_index=True, right_index=True, how='inner')
        
            df = df.dropna()
            df_dates=df.index 
        
            clf = prepareTraining(df_dates, df)
            pd_result = pd_result.append(makePrediction(df_dates, df, clf, stock))
        
        pd_result=pd_result.sort(['success', 'accurate'], ascending=[False, False])
        print(pd_result.head(10))
        g.compute=False
