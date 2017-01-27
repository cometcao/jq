import seaborn as sns
import pandas as pd
import numpy as np
import datetime
import time
from jqdata import *
from six import StringIO
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn import metrics

def write_csv(data, file_name):
    write_file(file_name,data.to_csv(), append=False)
def read_csv(file_name):
    body=read_file(file_name)
    data=pd.read_csv(StringIO(body),index_col=[0])
    return data

class TrainDataGenerator:
    def __init__(self, name="train_samples", need_target=True, train_size_perc=0.8):
        self.samples=None
        self.path="data/TrainPool/"
        self.fullpath=self.path+name+".csv"
        self.target_columns=['down','high','open']
        
        self.need_target = need_target
        self.train_size_perc = train_size_perc
        self.high_threshhold=0.1
        self.down_threshhold=-0.05
    def save(self):
        self.samples = self.samples.dropna()
        write_csv(self.samples, self.fullpath)
    def load(self):
        self.samples = read_csv(self.fullpath)
        self.samples = self.samples.dropna()
    def gen(self):
        self.permutation()
        if(self.need_target):
            self.split_XY()
            self.gen_y()
        else:
            self.X=self.samples.copy()
        if(self.train_size_perc < 1):
            self.split_test()
    def permutation(self):
        self.samples=self.samples.iloc[np.random.permutation(len(self.samples))]
    def split_XY(self):
        self.Y= self.samples[self.target_columns]
        self.X= self.samples.copy()
        for c in self.target_columns:
            self.X.pop(c)
        return self.X, self.Y
    def gen_y(self):
        high_score=(self.Y['high']-self.Y['open'])/self.Y['open']
        down_score=(self.Y['down']-self.Y['open'])/self.Y['open']
        pos_mask=(high_score>self.high_threshhold)&(down_score>self.down_threshhold)
        self.y=pd.Series(-np.ones(self.Y.shape[0]), index=pos_mask.index)
        self.y[pos_mask]=1
        return self.y
    def split_test(self):
        train_size = np.int16(np.round(self.train_size_perc * self.X.shape[0]))
        self.X_train, self.y_train = self.X.iloc[:train_size, :], self.y.iloc[:train_size]
        self.X_test, self.y_test = self.X.iloc[train_size:, :], self.y.iloc[train_size:]
class MMModel:
    def __init__(self, name='mmm', path='data/TrainPool/',n_pca='mle', C_svr=1.0):
        self.n_pca=n_pca
        self.C_svr=C_svr
        self.name=name
        self.path=path
        self.fullpath= self.path+self.name+".pkl"
    def save(self):
        dump_pickle(self, self.fullpath)
    def load(self):
        return load_pickle(self.fullpath)
    def fit(self,X,y):
        self.mod_norm=StandardScaler()
        Xtrans = self.mod_norm.fit_transform(X)
        
        self.mod_demR=PCA(n_components=self.n_pca, svd_solver='full')
        Xtrans = self.mod_demR.fit_transform(Xtrans)
        
        self.mod_train=SVC(kernel='rbf', C=self.C_svr)
        w,weight=self.gen_svr_w(y)
        if(weight<1 or weight>40):
            print("unbalance sample: " + weight)
        self.mod_train.fit(Xtrans,y,w)
    def gen_svr_w(self,y):
        tol=y.shape[0]
        pos=y[y==1].shape[0]
        neg=tol-pos
        
        w=pd.Series(np.ones(y.shape[0]), y.index)
        if(pos==0 or neg==0):
            return w,0
        if(pos<neg):
            weight=float(neg)/pos
            w[y==1]=weight
        else:
            weight=float(pos)/neg
            w[y==-1]=weight
        return w,weight
    def transform(self,X,y=None):
        Xtrans = self.mod_norm.transform(X)
        Xtrans = self.mod_demR.transform(Xtrans)
        return Xtrans
    def predict(self,X,y=None):
        Xtrans =self.transform(X)
        return self.mod_train.predict(Xtrans)
    def report(self,X,y=None):
        Xtrans =self.transform(X)
        p=self.mod_train.predict(Xtrans)
        d=self.mod_train.decision_function(Xtrans)
        return pd.DataFrame({'predict':p, 'dec_func':d})
    def score(self,X,y=None):
        Xtrans =self.transform(X)
        return self.mod_train.score(Xtrans,y), metrics.f1_score(y,self.predict(X))