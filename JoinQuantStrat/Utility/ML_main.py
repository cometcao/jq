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


from ML_kbar_prep import *
from ML_model_prep import *
from os import listdir
from os.path import isfile, join

if __name__ == '__main__':
    pass

#################### TRAINING ######################

def batch(iterable, n=1):
    l = len(iterable)
    for ndx in range(0, l, n): # 500
        yield [ndx,min(ndx + n, l)]


class ML_biaoli_train(object):
    def __init__(self, params):
        self.index_list = params.get('index_list', ['000016.XSHG','399300.XSHE', '399333.XSHE', '000905.XSHG', '399673.XSHE'])
        self.rq = params.get('rq', False)
        self.isAnal = params.get('isAnal', False)

    def prepare_mass_training_data(self, folder_path='./training_data'):
        mld = MLDataPrep(isAnal=False, rq=self.rq)
        index_stocks = []
        for index in self.index_list:
            stocks = get_index_stocks(index) #000016.XSHG 000905.XSHG 399300.XSHE
            index_stocks = index_stocks + stocks
        index_stocks = list(set(index_stocks))
        
        for x in batch(range(0, len(index_stocks)), 20): #
            stocks = index_stocks[x[0]:x[1]]
            print(stocks)
            mld.retrieve_stocks_data(stocks=stocks,period_count=2500, filename='{0}/training_{1}.pkl'.format(folder_path,str(x[1])))

    def prepare_initial_training_data(self, initial_path):
        mld = MLDataPrep(isAnal=self.isAnal, rq=self.rq)
        mld.retrieve_stocks_data(stocks=self.index_list,period_count=2500, filename='{0}/training_index.pkl'.format(initial_path))

    def initial_training(self, initial_data_path, model_name, epochs=10):
        mld = MLDataPrep(isAnal=self.isAnal, rq=self.rq)
        x_train, x_test, y_train, y_test = mld.prepare_stock_data_cnn(initial_data_path)
        
        mdp = MLDataProcess(model_name=model_name)
        mdp.define_conv_lstm_model(x_train, x_test, y_train, y_test, num_classes=3, epochs=epochs)        
        
        # filenames = ['training_data/cnn_training_test_index_v3_list.pkl']
        # x_train, x_test, y_train, y_test = mld.prepare_stock_data_cnn(filenames)
        
        # mdp = MLDataProcess(model_name='training_data/cnn_model_index_test.h5')
        # mdp.define_conv2d_model(x_train, x_test, y_train, y_test, num_classes=3, epochs=50)
        
        # mdp = MLDataProcess(model_name='training_data/cnn_lstm_model_index_test.h5')
        # mdp.define_conv_lstm_model(x_train, x_test, y_train, y_test, num_classes=3, epochs=50)

    def continue_training(self, model_name, folder_path='./training_data'):
        mld = MLDataPrep(isAnal=self.isAnal, rq=self.rq)
        mdp = MLDataProcess(model_name=None)
        mdp.load_model(model_name)
        filenames = [f for f in listdir(folder_path) if isfile(join(folder_path, f))]
        for file in filenames:
            x_train, x_test, y_train, y_test = mld.prepare_stock_data_cnn(['{0}/{1}'.format(folder_path, file)])
            x_train = np.expand_dims(x_train, axis=2) 
            x_test = np.expand_dims(x_test, axis=2) 
        
            x_train = np.expand_dims(x_train, axis=1)
            x_test = np.expand_dims(x_test, axis=1)
            mdp.process_model(mdp.model, x_train, x_test, y_train, y_test, epochs=5)

    def full_training(self, stocks, period_count=90, training_data_name=None, model_name=None, batch_size=20, epochs=3):
        if not stocks:
            return None
        mld = MLDataPrep(isAnal=self.isAnal, rq=self.rq)    
        tmp_data, tmp_label = mld.retrieve_stocks_data(stocks, period_count=period_count, filename=training_data_name)
        x_train, x_test, y_train, y_test = mld.prepare_stock_data_set(tmp_data, tmp_label)
        
        mdp = MLDataProcess(model_name=model_name)
        mdp.define_conv_lstm_model(x_train, x_test, y_train, y_test, num_classes=3, batch_size=batch_size, epochs=epochs) 
        return mdp.model

#################### PREDICTION ######################

class ML_biaoli_check(object):
    """use CNNLSTM to predict biaoli level"""
    def __init__(self, params):
        self.threthold = params.get('threthold', 0.9)
        self.model_path = params.get('model_path', None)
        self.rq = params.get('rq', True)
        self.isAnal = params.get('isAnal', False)
        self.extra_training = params.get('extra_training', False)
        self.extra_training_period = params.get('extra_training_period', 120)
        self.extra_training_file = params.get('extra_training_file', None)
        self.save_new_model = params.get('save_new_model', False)
        self.model = params.get('model', None)
        if not self.model and self.model_path is not None:
            self.prepare_model()

    
    def prepare_model(self):
        self.mdp = MLDataProcess(model_name=self.model_path, isAnal=self.isAnal)
        self.mdp.load_model(model_name=self.model_path)#
        if not self.save_new_model:
            self.mdp.model_name = None # we don't want to save the modified model
        
    def gauge_stocks(self, stocks, isLong=True, today_date=None):    
        if not stocks:
            return []
        return [stock for stock in stocks if (self.gauge_long(stock, today_date) if isLong else self.gauge_short(stock, today_date))]
        
    def gauge_long(self, stock, today_date=None):
        lp, _ = self.gauge_stock(stock, today_date)
        return lp
        
    def gauge_short(self, stock, today_date=None):
        _, sp = self.gauge_stock(stock, today_date)
        return sp
        
    def gauge_stocks_analysis(self, stocks, today_date=None):
        if not stocks:
            return [] 
        return [(stock, self.gauge_stock(stock, today_date)) for stock in stocks]
    
    def gauge_stock(self, stock, today_date=None):    
        (y_class, pred), origin_size = self.model_predict(stock, today_date)
        conf = self.interpret(pred)    
        
        old_pred = pred[:origin_size]
        old_y_class = y_class[:origin_size]
        old_conf = conf[:origin_size]    
        
        long_pred = short_pred = False
        # make sure current check is adequate
        # 1 none of past pivots were predicted as 0
        # 2 all past pivots were confident
        try:
            if (old_y_class[-3:-1] != 0).all():  #and old_conf.all()
                long_pred = (old_y_class[-1] == -1 and old_conf[-1])
                short_pred = (len(old_y_class) >= 2 and old_y_class[-2] == 1 and old_y_class[-1] == 0 and old_conf[-1] and old_conf[-2]) or\
                        (old_y_class[-1] == 1 and old_conf[-1])
                print(old_pred)
                print(old_y_class)
            else:
                print("use gapped pivots for prediction")
                new_y_class = y_class[origin_size:]
                new_conf = conf[origin_size:]
                new_pred = pred[origin_size:]
                long_pred = (new_y_class[-1] == -1 and new_conf[-1])# or (new_y_class[-2] == -1 and new_conf[-2])
                short_pred = (new_y_class[-1] == 1 and new_conf[-1])# or (new_y_class[-2] == 1 and new_conf[-2])
                print(new_pred)
                print(new_y_class)
        except:
            long_pred = short_pred = False
        return (long_pred, short_pred)
    
        
    def model_predict(self, stock, today_date=None):
        print("ML working on {0} at date {1}".format(stock, today_date if today_date else ""))
        mld = MLDataPrep(isAnal=self.isAnal, rq=self.rq)
        data_set, origin_data_length = mld.prepare_stock_data_predict(stock, today_date=today_date) # 000001.XSHG
        if data_set is None: # can't predict
            return ([0],[[0]], 0)
        try:
            if self.extra_training:
                tmp_data, tmp_label = mld.retrieve_stocks_data([stock], period_count=self.extra_training_period, filename=self.extra_training_file, today_date=today_date)
                x_train, x_test, y_train, y_test = mld.prepare_stock_data_set(tmp_data, tmp_label)
                x_train, x_test = self.mdp.define_conv_lstm_dimension(x_train, x_test)
                self.mdp.process_model(self.mdp.model, x_train, x_test, y_train, y_test, batch_size = 30,epochs = 3)
                
            unique_index = np.array([-1, 0, 1])
            
            return self.mdp.model_predict_cnn_lstm(data_set, unique_index), origin_data_length
        except Exception as e: 
            print(e)
            return ([0],[[0]], 0)
    
    def interpret(self, pred, thre=0):
        """Our confidence level must be above the threthold"""
        max_val = np.max(pred, axis=1)
        if thre == 0:
            return max_val >= self.threthold
        else:
            return max_val >= thre