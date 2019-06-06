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

import sys
# stdout = sys.stdout
# sys.stdout = open(os.devnull, 'w')
# import keras
# sys.stdout = stdout
stderr = sys.stderr
sys.stderr = open(os.devnull, 'w')
import keras
sys.stderr = stderr

#################### TRAINING ######################

def batch(iterable, n=1):
    l = len(iterable)
    for ndx in range(0, l, n): # 500
        yield [ndx,min(ndx + n, l)]


class ML_biaoli_train(object):
    def __init__(self, params):
        self.index_list = params.get('index_list', ['000016.XSHG','399300.XSHE', '399333.XSHE', '000905.XSHG', '399673.XSHE'])
        self.rq = params.get('rq', False)
        self.ts = params.get('ts', True)
        self.isAnal = params.get('isAnal', False)
        self.isDebug = params.get('isDebug', False)
        self.use_standardized_sub_df = params.get('use_standardized_sub_df', True)
        self.sub_level_max_length = params.get('sub_level_max_length', 1200)
        self.check_level = params.get('check_level', ['1d','30m'])
        

    def prepare_mass_training_data(self, folder_path='./training_data'):
        mld = MLDataPrep(isAnal=False, 
                         rq=self.rq, 
                         ts=self.ts, 
                         use_standardized_sub_df=self.use_standardized_sub_df, 
                         isDebug=self.isDebug,
                         monitor_level=self.check_level, 
                         max_length_for_pad=self.sub_level_max_length)
        index_stocks = []
        for index in self.index_list:
            stocks = get_index_stocks(index) #000016.XSHG 000905.XSHG 399300.XSHE
            index_stocks = index_stocks + stocks
        index_stocks = list(set(index_stocks))
        index_stocks.sort()
        
        for x in batch(range(0, len(index_stocks)), 20): #
            stocks = index_stocks[x[0]:x[1]]
            print(stocks)
            mld.retrieve_stocks_data(stocks=stocks,period_count=2500, filename='{0}/training_{1}.pkl'.format(folder_path,str(x[1])))

    def prepare_initial_training_data(self, initial_path):
        mld = MLDataPrep(isAnal=self.isAnal, 
                         rq=self.rq, ts=self.ts, 
                         use_standardized_sub_df=self.use_standardized_sub_df, 
                         isDebug=self.isDebug,
                         monitor_level=self.check_level,
                         max_length_for_pad=self.sub_level_max_length)
        mld.retrieve_stocks_data(stocks=self.index_list,period_count=2500, filename='{0}/training_index.pkl'.format(initial_path))

    def initial_training(self, initial_data_path, model_name, epochs=10, use_ccnlstm=True, background_data_generation=True):
        mld = MLDataPrep(isAnal=self.isAnal, 
                         rq=self.rq, ts=self.ts, 
                         use_standardized_sub_df=self.use_standardized_sub_df, 
                         isDebug=self.isDebug,monitor_level=self.check_level,
                         max_length_for_pad=self.sub_level_max_length)
        x_train, x_test, y_train, y_test = mld.prepare_stock_data_cnn(initial_data_path, background_data_generation=background_data_generation)
        
        mdp = MLDataProcess(model_name=model_name)
        if use_ccnlstm:
            mdp.define_conv_lstm_model(x_train, x_test, y_train, y_test, num_classes=3, epochs=epochs, verbose=2)        
        else:
            mdp.define_conv2d_model(x_train, x_test, y_train, y_test, num_classes=3, epochs=epochs, verbose=2)

    def continue_training(self, model_name, folder_path='./training_data'):
        mld = MLDataPrep(isAnal=self.isAnal, 
                         rq=self.rq, 
                         ts=self.ts, 
                         use_standardized_sub_df=self.use_standardized_sub_df, 
                         isDebug=self.isDebug,
                         monitor_level=self.check_level,
                         max_length_for_pad=self.sub_level_max_length)
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

    def extra_training(self, model, stocks, period_count=90, training_data_name=None, batch_size=20, epochs=3, detailed_bg=False):
        if not stocks:
            return model
        
        mld = MLDataPrep(isAnal=self.isAnal, 
                         rq=self.rq, 
                         ts=self.ts, 
                         detailed_bg=detailed_bg, 
                         use_standardized_sub_df=self.use_standardized_sub_df, 
                         isDebug=self.isDebug,
                         monitor_level=self.check_level,
                         max_length_for_pad=self.sub_level_max_length)    
        tmp_data, tmp_label = mld.retrieve_stocks_data(stocks, period_count=period_count, filename=training_data_name)
        x_train, x_test, y_train, y_test = mld.prepare_stock_data_set(tmp_data, tmp_label)
        
        mdp = MLDataProcess()
        mdp.process_model(model, x_train, x_test, y_train, y_test, batch_size=batch_size, epochs=epochs) 
        return mdp.model
        

    def full_training(self, stocks, period_count=90, training_data_name=None, model_name=None, batch_size=20, epochs=3,detailed_bg=False):
        if not stocks:
            return None
        mld = MLDataPrep(isAnal=self.isAnal, 
                         rq=self.rq, ts=self.ts, 
                         detailed_bg=detailed_bg, 
                         use_standardized_sub_df=self.use_standardized_sub_df, 
                         isDebug=self.isDebug,
                         monitor_level=self.check_level,
                         max_length_for_pad=self.sub_level_max_length)      
        tmp_data, tmp_label = mld.retrieve_stocks_data(stocks, period_count=period_count, filename=training_data_name)
        x_train, x_test, y_train, y_test = mld.prepare_stock_data_set(tmp_data, tmp_label)
        
        mdp = MLDataProcess(model_name=model_name)
        mdp.define_conv_lstm_model(x_train, x_test, y_train, y_test, num_classes=3, batch_size=batch_size, epochs=epochs) 
        return mdp.model
    
    def specified_stock_training(self, stocks, period_count=90, training_data_path=None, model_name=None, batch_size=20, epochs=3,detailed_bg=False):
        if not stocks:
            return None    
        
        filenames = [f for f in listdir(training_data_path) if isfile(join(training_data_path, f))]
        mld = MLDataPrep(isAnal=self.isAnal, 
                         rq=self.rq, ts=self.ts, 
                         detailed_bg=detailed_bg, 
                         use_standardized_sub_df=self.use_standardized_sub_df, 
                         isDebug=self.isDebug,
                         monitor_level=self.check_level,
                         max_length_for_pad=self.sub_level_max_length) 
        
        for stock in stocks:
            if stock in filenames:
                print("data {0} exists".format(stock))
                x_train, x_test, y_train, y_test = mld.prepare_stock_data_cnn(['{0}/{1}'.format(training_data_path,stock)])
            else:
                tmp_data, tmp_label = mld.retrieve_stocks_data(stocks, period_count=period_count, filename='{0}/{1}'.format(training_data_path, stock))
                x_train, x_test, y_train, y_test = mld.prepare_stock_data_set(tmp_data, tmp_label)                
            
            mdp = MLDataProcess(model_name=None, isAnal=True)
            mdp.load_model(model_name)
            model_path = model_name.split('/')
            mdp.model_name = '{0}/{1}/{2}.h5'.format(model_path[0], model_path[1], stock)
            
            x_train, x_test, _ = mdp.define_conv_lstm_dimension(x_train, x_test)
            mdp.process_model(mdp.model, x_train, x_test, y_train, y_test, batch_size=batch_size, epochs=epochs, verbose=2) 
        

    def initial_training_gen(self, initial_data_path, model_name, epochs=10, use_ccnlstm=True):
        mld = MLDataPrep(isAnal=self.isAnal, 
                         rq=self.rq, ts=self.ts, 
                         use_standardized_sub_df=self.use_standardized_sub_df, 
                         isDebug=self.isDebug,monitor_level=self.check_level,
                         max_length_for_pad=self.sub_level_max_length)
        data_gen, validation_gen = mld.prepare_stock_data_cnn_gen(initial_data_path)
        
        mdp = MLDataProcess(model_name=model_name)
        if use_ccnlstm:
            mdp.define_conv_lstm_model_gen(data_gen, validation_gen, num_classes=3, epochs=epochs, verbose=2)
            
    def continue_training_gen(self, model_name, folder_path='./training_data'):
        mld = MLDataPrep(isAnal=self.isAnal, 
                         rq=self.rq, 
                         ts=self.ts, 
                         use_standardized_sub_df=self.use_standardized_sub_df, 
                         isDebug=self.isDebug,
                         monitor_level=self.check_level,
                         max_length_for_pad=self.sub_level_max_length)
        mdp = MLDataProcess(model_name=None)
        mdp.load_model(model_name)
        filenames = [f for f in listdir(folder_path) if isfile(join(folder_path, f))]
        
        full_names = ['{0}/{1}'.format(folder_path, file) for file in filenames]
        data_gen, validation_gen = mld.prepare_stock_data_cnn_gen(full_names)
        mdp.process_model_generator(mdp.model, data_gen, steps=100000, epochs=5, verbose=2, validation_data=validation_gen, evaluate_generator=validation_gen) 


#################### PREDICTION ######################

class ML_biaoli_check(object):
    """use CNNLSTM to predict biaoli level"""
    def __init__(self, params):
        self.long_threthold = params.get('long_threthold', 0.999)
        self.short_threthold = params.get('short_threthold', 0.99)
        self.model_path = params.get('model_path', None)
        self.rq = params.get('rq', False)
        self.ts = params.get('ts', True)
        self.isAnal = params.get('isAnal', False)
        self.extra_training = params.get('extra_training', False)
        self.extra_training_period = params.get('extra_training_period', 120)
        self.extra_training_file = params.get('extra_training_file', None)
        self.save_new_model = params.get('save_new_model', False)
        self.model = params.get('model', None)
        self.isDebug = params.get('isDebug', False)
        self.use_latest_pivot = params.get('use_latest_pivot', True)
        self.use_standardized_sub_df = params.get('use_standardized_sub_df', True)
        self.use_cnn_lstm = params.get('use_cnn_lstm', True)
        self.use_cnn = params.get('use_cnn', False)
        self.check_level = params.get('check_level', ['1d','30m'])
        self.sub_level_max_length = params.get('sub_level_max_length', 1200)
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
        lp, _ = self.gauge_stock(stock, today_date, check_status=True)
        return lp
        
    def gauge_short(self, stock, today_date=None):
        _, sp = self.gauge_stock(stock, today_date, check_status=True)
        return sp
        
    def gauge_stocks_analysis(self, stocks, today_date=None, check_status=False):
        if not stocks:
            return [] 
        return [(stock, self.gauge_stock(stock, today_date, check_status=check_status)) for stock in stocks]
    
    def gauge_stock(self, stock, today_date=None, check_status=False):    
        (y_class, pred), origin_size, past_pivot_status = self.model_predict(stock, today_date)
        long_conf, short_conf = self.interpret(pred)    
        
        old_pred = pred[:origin_size]
        old_y_class = y_class[:origin_size]
        old_long_conf = long_conf[:origin_size]    
        old_short_conf = short_conf[:origin_size]
        
        long_pred = short_pred = False
        # make sure current check is adequate
        # 1 none of past pivots were predicted as 0
        # 2 all past pivots were confident
        try:
            if (old_y_class[-2:-1] != 0).all():  # old_conf.all()
                long_pred = (old_y_class[-1] == -1 and old_long_conf[-1])
                short_pred = (old_y_class[-1] == 1 and old_short_conf[-1])
                       
                long_pred = long_pred or (len(old_y_class) >= 2 and old_y_class[-2] == -1 and old_y_class[-1] == 0 and old_long_conf[-1] and old_long_conf[-2]) 
                short_pred = short_pred or (len(old_y_class) >= 2 and old_y_class[-2] == 1 and old_y_class[-1] == 0 and old_short_conf[-1] and old_short_conf[-2])
                    
            if not self.use_latest_pivot and not long_pred and not short_pred: 
                new_y_class = y_class[origin_size:]
                new_long_conf = long_conf[origin_size:]
                new_short_conf = short_conf[origin_size:]
                new_pred = pred[origin_size:]
                long_pred = long_pred or (new_y_class[-1] == -1 and new_long_conf[-1])
                short_pred = short_pred or (new_y_class[-1] == 1 and new_short_conf[-1])             
                if self.isDebug and (long_pred or short_pred):
                    print("gapped pivots for prediction")
                    print(new_pred)
                    print(new_y_class)
            else:
                if self.isDebug:
                    print(old_pred)
                    print(old_y_class)
            
            if check_status and not long_pred and not short_pred: # model not deterministic, we use past pivot point with passive logic
                if self.isDebug:
                    print("check status use past pivot: {0}".format(past_pivot_status))
                long_pred = long_pred or (past_pivot_status == -1 and
                                        ((old_y_class[-1] == 0 and old_long_conf[-1]) or
                                        (not self.use_latest_pivot and len(new_y_class) >= 1 and new_y_class[-1] == 0 and new_long_conf[-1])))
                                        
                short_pred = short_pred or past_pivot_status == 1
        except Exception as e:
            print("unexpected error: {0}".format(str(e)))
            long_pred = short_pred = False
        return (long_pred, short_pred)
    
        
    def model_predict(self, stock, today_date=None):
        if self.isDebug:
            print("ML working on {0} at date {1}".format(stock, str(today_date) if today_date else ""))
        mld = MLDataPrep(isAnal=self.isAnal, 
                         rq=self.rq, ts=self.ts, 
                         isDebug=self.isDebug, 
                         use_standardized_sub_df=self.use_standardized_sub_df, 
                         monitor_level=self.check_level,
                         max_length_for_pad=self.sub_level_max_length)
        data_set, origin_data_length, past_pivot_status = mld.prepare_stock_data_predict(stock, today_date=today_date, period_count=100, predict_extra=self.use_cnn_lstm) # 500 sample period
        if data_set is None: # can't predict
            print("None dataset, return [0],[[0]], 0")
            return (([0],[[0]]), 0)
        try:
            if self.extra_training:
                tmp_data, tmp_label = mld.retrieve_stocks_data([stock], period_count=self.extra_training_period, filename=self.extra_training_file, today_date=today_date)
                x_train, x_test, y_train, y_test = mld.prepare_stock_data_set(tmp_data, tmp_label)
                x_train, x_test, _ = self.mdp.define_conv_lstm_dimension(x_train, x_test)
                self.mdp.process_model(self.mdp.model, x_train, x_test, y_train, y_test, batch_size = 30,epochs =3)
            
            unique_index = np.array([-1, 0, 1])
            
            if self.use_cnn_lstm:
                return self.mdp.model_predict_cnn_lstm(data_set, unique_index), origin_data_length, past_pivot_status
            elif self.use_cnn:
                return self.mdp.model_predict_cnn(data_set, unique_index), origin_data_length, past_pivot_status
            else:
                return self.mdp.model_predict_rcnn(data_set, unique_index), origin_data_length, past_pivot_status
        except Exception as e: 
            print(e)
            return (([0],[[0]]), 0, 0)
    
    def interpret(self, pred):
        """Our confidence level must be above the threthold"""
        max_val = np.max(pred, axis=1)
        return max_val >= self.long_threthold, max_val >= self.short_threthold