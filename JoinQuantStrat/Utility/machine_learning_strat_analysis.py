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

def zscore(series):
    return (series - series.mean()) / np.std(series)

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
        open_series_z = zscore(df.loc[start_da:pre_da,'open'])
        close_series_z = zscore(df.loc[start_da:pre_da,'close'])
        high_series_z = zscore(df.loc[start_da:pre_da,'high'])
        low_series_z = zscore(df.loc[start_da:pre_da,'low'])
        turnover_series_z = zscore(df.loc[start_da:pre_da,'turnover_ratio'])
        [features.append(x) for x in open_series_z]
        [features.append(x) for x in close_series_z]
        [features.append(x) for x in high_series_z]
        [features.append(x) for x in low_series_z]
        [features.append(x) for x in turnover_series_z]
        
        if "fin_value" in df.columns and \
        "sec_value" in df.columns and \
        "fin_sec_value" in df.columns:
        # "fin_buy_value" in df.columns and \
        # "fin_refund_value" in df.columns and \
        # "sec_sell_value" in df.columns and \
        # "sec_refund_value" in df.columns and \

            fin_value_z = zscore(df.loc[start_da:pre_da,'fin_value'])
            # fin_buy_value_z = zscore(df.loc[start_da:pre_da,'fin_buy_value'])
            # fin_refund_value_z = zscore(df.loc[start_da:pre_da,'fin_refund_value'])
            sec_value_z = zscore(df.loc[start_da:pre_da,'sec_value'])
            # sec_sell_value_z = zscore(df.loc[start_da:pre_da,'sec_sell_value'])
            # sec_refund_value_z = zscore(df.loc[start_da:pre_da,'sec_refund_value'])
            fin_sec_value_z = zscore(df.loc[start_da:pre_da,'fin_sec_value'])
            if np.isfinite(fin_value_z).all() and \
            np.isfinite(sec_value_z).all() and \
            np.isfinite(fin_sec_value_z).all():
            # np.isfinite(fin_buy_value_z).all() and \
            # np.isfinite(fin_refund_value_z).all() and \
            # np.isfinite(sec_sell_value_z).all() and \
            # np.isfinite(sec_refund_value_z).all() and \

                [features.append(x) for x in fin_value_z]
                # [features.append(x) for x in fin_buy_value_z]
                # [features.append(x) for x in fin_refund_value_z]
                [features.append(x) for x in sec_value_z]
                # [features.append(x) for x in sec_sell_value_z]
                # [features.append(x) for x in sec_refund_value_z]
                [features.append(x) for x in fin_sec_value_z]
            else:
                continue

        label = df.loc[da,'strength']

        x_all.append(features)
        y_all.append(label)

    #from sklearn import svm

    #开始利用机器学习算法计算
    clf = svm.SVC()
    #     clf = RandomForestClassifier(n_estimators=50)
    #     clf = GaussianNB()
    #训练的代码
    clf.fit(x_all, y_all)
    #得到测试结果的代码
    return clf

def makePrediction(df_dates, df, clf, stock, training_sample_size=30,test_size = 365):
    for index in range(len(df_dates)-test_size,len(df_dates)):
        start_da = df_dates[index-training_sample_size]
        pre_da = df_dates[index-1]
        da = df_dates[index]

        x_test = []
        open_series_z = zscore(df.loc[start_da:pre_da,'open'])
        close_series_z = zscore(df.loc[start_da:pre_da,'close'])
        high_series_z = zscore(df.loc[start_da:pre_da,'high'])
        low_series_z = zscore(df.loc[start_da:pre_da,'low'])
        turnover_series_z = zscore(df.loc[start_da:pre_da,'turnover_ratio'])        

        [x_test.append(x) for x in open_series_z]
        [x_test.append(x) for x in close_series_z]
        [x_test.append(x) for x in high_series_z]
        [x_test.append(x) for x in low_series_z]
        [x_test.append(x) for x in turnover_series_z]
        if "fin_value" in df.columns and \
        "sec_value" in df.columns and \
        "fin_sec_value" in df.columns:
        # "fin_buy_value" in df.columns and \
        # "fin_refund_value" in df.columns and \
        # "sec_sell_value" in df.columns and \
        # "sec_refund_value" in df.columns and \

            fin_value_z = zscore(df.loc[start_da:pre_da,'fin_value'])
            # fin_buy_value_z = zscore(df.loc[start_da:pre_da,'fin_buy_value'])
            # fin_refund_value_z = zscore(df.loc[start_da:pre_da,'fin_refund_value'])
            sec_value_z = zscore(df.loc[start_da:pre_da,'sec_value'])
            # sec_sell_value_z = zscore(df.loc[start_da:pre_da,'sec_sell_value'])
            # sec_refund_value_z = zscore(df.loc[start_da:pre_da,'sec_refund_value'])
            fin_sec_value_z = zscore(df.loc[start_da:pre_da,'fin_sec_value'])
            if np.isfinite(fin_value_z).all() and \
            np.isfinite(sec_value_z).all() and \
            np.isfinite(fin_sec_value_z).all():
            # np.isfinite(fin_buy_value_z).all() and \
            # np.isfinite(fin_refund_value_z).all() and \
            # np.isfinite(sec_sell_value_z).all() and \
            # np.isfinite(sec_refund_value_z).all() and \
                [x_test.append(x) for x in fin_value_z]
                # [x_test.append(x) for x in fin_buy_value_z]
                # [x_test.append(x) for x in fin_refund_value_z]
                [x_test.append(x) for x in sec_value_z]
                # [x_test.append(x) for x in sec_sell_value_z]
                # [x_test.append(x) for x in sec_refund_value_z]
                [x_test.append(x) for x in fin_sec_value_z]
            else:
                continue
            
        prediction = clf.predict([x_test])
        df.loc[da, 'prediction'] = prediction

    # 看看预测对了没
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
    g.compute = 0 # analyze index
    g.total_days = 1095
    #today_date = context.current_dt.date()
    
    g.today_date = datetime.datetime.now().date()
    trade_days = get_trade_days( end_date=g.today_date, count=g.total_days)
    g.today_date = trade_days[-1]
    past_date = trade_days[-2]

    # all A share
    stock_pd = get_all_securities(types=['stock'], date=g.today_date)
    mask = stock_pd['start_date'] <= past_date
    mask2 = stock_pd['end_date'] == datetime.date(2200, 01, 01)
    stock_pd=stock_pd[mask==True][mask2==True]

    stock_list = stock_pd.index
    # filter out st shares
    is_st_list = get_extras('is_st', stock_list, start_date=g.today_date, end_date=g.today_date, df=False)
    stock_list = [x for x in is_st_list.keys() if is_st_list[x][0]==False]
    
    # control stock sector
    tmp_stock_list = get_index_stocks('000002.XSHG') # any thing else 000300.XSHG 399333.XSHE
    g.final_stock_list = [x for x in tmp_stock_list if x in stock_list]
    g.pd_result = pd.DataFrame(columns=["success","accurate"])

# 每个单位时间(如果按天回测,则每天调用一次,如果按分钟,则每分钟调用一次)调用一次
def handle_data(context, data):
    ##########################################################################################################
    for index in xrange(g.compute, len(g.final_stock_list)):
        stock = g.final_stock_list[index]
        print("analyzing {} ...".format(stock))
        df = get_price(stock, end_date=g.today_date, frequency='daily', fields=['open', 'close','high','low','money','volume'], skip_paused=True, fq='pre',count=g.total_days)
        df['return_1'] = (df['close'] - df['close'].shift(1)) / abs(df['close']) + 1
        df['strength'] = df['return_1'].apply(getStrength)
    
        df_dates=df.index 
        # preprocess data
        for da in df_dates:
            df_fund = get_fundamentals(query(
                    valuation.turnover_ratio
                ).filter(
                    # 这里不能使用 in 操作, 要使用in_()函数
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
    
        try:
            clf = prepareTraining(df_dates, df)
            g.pd_result = g.pd_result.append(makePrediction(df_dates, df, clf, stock))
        except:
            print "failed to analyze %s" % stock
        
        if index % 150 == 0:
            g.compute = index+1
            break
    
    g.pd_result=g.pd_result.sort(['success', 'accurate'], ascending=[False, False])
    print(g.pd_result.head(50))
