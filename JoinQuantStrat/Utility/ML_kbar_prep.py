from kBarProcessor import *
from jqdata import *
from biaoLiStatus import TopBotType
from pickle import dump
from pickle import load
import pandas as pd
import numpy as np
import talib
import keras
from keras.utils.np_utils import to_categorical
from keras.models import load_model
from keras.models import Sequential
from keras.layers import Dense, Dropout, Flatten
from keras.layers import Conv2D, MaxPooling2D
from sklearn.model_selection import train_test_split

# pd.options.mode.chained_assignment = None 

class MLKbarPrep(object):
    '''
    Turn multiple level of kbar data into Chan Biaoli status,
    return a dataframe with combined biaoli status
    data types:
    biaoli status, high/low prices, volume/turnover ratio/money, MACD, sequence index
    '''

    monitor_level = ['1d', '30m']
    def __init__(self, count=100, isAnal=False, isNormalize=True, manual_select=False, useMinMax=True):
        self.isAnal = isAnal
        self.count = count
        self.isNormalize = isNormalize
        self.useMinMax = useMinMax
        self.manual_select = manual_select
        self.stock_df_dict = {}
        self.sub_level_min_count = 2
        self.sub_max_count = 21 * 8
        self.data_set = []
        self.label_set = []
    
    def retrieve_stock_data(self, stock):
        for level in MLKbarPrep.monitor_level:
            local_count = self.count if level == '1d' else self.count * 8
            stock_df = None
            if not self.isAnal:
                stock_df = attribute_history(stock, local_count, level, fields = ['open','close','high','low', 'money'], skip_paused=True, df=True)  
            else:
                latest_trading_day = get_trade_days(count=1)[-1]
                stock_df = get_price(stock, count=local_count, end_date=latest_trading_day, frequency=level, fields = ['open','close','high','low', 'money'], skip_paused=True)          
            stock_df = self.prepare_df_data(stock_df)
            self.stock_df_dict[level] = stock_df
    
    def prepare_df_data(self, stock_df):
        # MACD
        stock_df.loc[:,'macd_raw'], _, stock_df.loc[:,'macd']  = talib.MACD(stock_df['close'].values)
        # BiaoLi
        stock_df = self.prepare_biaoli(stock_df)
        return stock_df
        
    
    def prepare_biaoli(self, stock_df):
        kb = KBarProcessor(stock_df)
        kb_marked = kb.getMarkedBL()
        stock_df = stock_df.join(kb_marked[['new_index', 'tb']])
        return stock_df
    
    def prepare_training_data(self):
        higher_df = self.stock_df_dict[MLKbarPrep.monitor_level[0]]
        lower_df = self.stock_df_dict[MLKbarPrep.monitor_level[1]]
        high_df_tb = higher_df.dropna(subset=['new_index'])
        high_dates = high_df_tb.index
        for i in range(0, len(high_dates)-1):
            first_date = high_dates[i]
            second_date = high_dates[i+1]
            trunk_lower_df = lower_df.loc[first_date:second_date,:]
            self.create_ml_data_set(trunk_lower_df, high_df_tb.ix[i+1, 'tb'].value)
        return self.data_set, self.label_set
        
    def create_ml_data_set(self, trunk_df, label): 
        # at least 3 parts in the sub level
        sub_level_count = len(trunk_df['tb']) - trunk_df['tb'].isnull().sum()
        if sub_level_count < self.sub_level_min_count:
            return
        
        if trunk_df.shape[0] > self.sub_max_count: # truncate
            trunk_df = trunk_df.iloc[-self.sub_max_count:,:]
        
        if self.manual_select:
            trunk_df = self.manual_select(trunk_df)
        else:
            trunk_df = self.manual_wash(trunk_df)  
        if self.isNormalize:
            trunk_df = self.normalize(trunk_df)
        
        self.data_set.append(trunk_df.values)
        self.label_set.append(label)
        
        
    def manual_select(self, df):
        df = df.dropna()
        df['new_index'] = df['new_index'].shift(-1) - df['new_index'] 
        df['tb'] = df.apply(lambda row: row['tb'].value, axis = 1)
        df['price'] = df.apply(lambda row: row['high'] if row['tb'] == 1 else row['low'])
        df.drop(['open', 'high', 'low'], 1)
        return df
        
    def manual_wash(self, df):
        df = df.drop(['new_index','tb'], 1)
        return df
        
    def normalize(self, df):
        for column in df: 
            if column == 'new_index' or column == 'tb':
                continue
            if self.useMinMax:
                # min-max
                col_min = df[column].min()
                col_max = df[column].max()
                df[column]=(df[column]-col_min)/(col_max-col_min)
            else:
                # mean std
                col_mean = df[column].mean()
                col_std = df[column].std()
                df[column] = (df[column] - col_mean) / col_std
        return df
    
    
class MLDataPrep(object):
    def __init__(self, isAnal=False):
        self.isAnal = isAnal
    
    def retrieve_stocks_data(self, stocks, period_count=60, filename='cnn_training.pkl'):
        data_list = label_list = []
        for stock in stocks:
            print ("working on stock: {0}".format(stock))
            mlk = MLKbarPrep(isAnal=self.isAnal, count=period_count, isNormalize=True)
            mlk.retrieve_stock_data(stock)
            dl, ll = mlk.prepare_training_data()
            data_list = data_list + dl
            label_list = label_list + ll   
        
        self.save_dataset((np.array(data_list), np.array(label_list)), filename)
        
    def prepare_stock_data_cnn(self, filename, padData=True, test_portion=0.1, random_seed=42):
        A, B = self.load_dataset(filename)

        if padData:
            A = self.pad_each_training_array(A)
        A = np.expand_dims(A, axis=2) # reshape (36, 168, 7) to (36, 168, 1, 7)
        
        x_train, x_test, y_train, y_test = train_test_split(A, B, test_size=test_portion, random_state=random_seed)
        
        if self.isAnal:
            print (x_train.shape)
            for i in range(x_train.shape[0]):
                print (x_train[i].shape)
        
        return x_train, x_test, y_train, y_test
    
        # save a dataset to file
    def save_dataset(self, dataset, filename):
        dump(dataset, open(filename, 'wb'))
        print('Saved: %s' % filename)
        
    # load a clean dataset
    def load_dataset(self, filename):
        return load(open(filename, 'rb'))

    def pad_each_training_array(self, data_list):
        new_shape = self.findmaxshape(data_list)
        new_data_list = self.fillwithzeros(data_list, new_shape)
        return new_data_list
    
    def fillwithzeros(self, inputarray, outputshape):
        """
        Fills input array with dtype 'object' so that all arrays have the same shape as 'outputshape'
        inputarray: input numpy array
        outputshape: max dimensions in inputarray (obtained with the function 'findmaxshape')
    
        output: inputarray filled with zeros
        """
        length = len(inputarray)
        output = np.zeros((length,)+outputshape)
        for i in range(length):
            output[i][:inputarray[i].shape[0],:inputarray[i].shape[1]] = inputarray[i]
        return output
    
    def findmaxshape(self, inputarray):
        """
        Finds maximum x and y in an inputarray with dtype 'object' and 3 dimensions
        inputarray: input numpy array
    
        output: detected maximum shape
        """
        max_x, max_y = 0, 0
        for array in inputarray:
            x, y = array.shape
            if x > max_x:
                max_x = x
            if y > max_y:
                max_y = y
        return(max_x, max_y)


class MLDataProcess(object):
    def __init__(self, model_name='ml_model.h5'):
        self.model_name = model_name
        self.model = None
     
    def define_conv2d_model(self, x_train, x_test, y_train, y_test, num_classes, batch_size = 50,epochs = 5):
        # convert class vectors to binary class matrices
        a, b, c, d = x_train.shape
        input_shape = (b, c, d)
        
        y_train = to_categorical(y_train, num_classes)
        y_test = to_categorical(y_test, num_classes)
        
        model = Sequential()
        model.add(Conv2D(32, kernel_size=(3, 1),
                         activation='relu',
                         input_shape=input_shape))
        model.add(Conv2D(64, (3, 1), activation='relu'))
        model.add(MaxPooling2D(pool_size=(2, 1)))
        model.add(Dropout(0.25))
        model.add(Flatten())
        model.add(Dense(128, activation='relu'))
        model.add(Dropout(0.5))
        model.add(Dense(num_classes, activation='softmax'))
        
        model.compile(loss=keras.losses.categorical_crossentropy,
                      optimizer=keras.optimizers.Adadelta(),
                      metrics=['accuracy'])
        
        model.fit(x_train, y_train,
                  batch_size=batch_size,
                  epochs=epochs,
                  verbose=1,
                  validation_data=(x_test, y_test))
        score = model.evaluate(x_test, y_test, verbose=1)
        print('Test loss:', score[0])
        print('Test accuracy:', score[1])
        
        self.model = model
        if self.model_name:
            model.save(self.model_name)
    
    def load_model(self, model_name):
        self.model = load_model(model_name)
        self.model_name = model_name

#     def define_model(self):
#         x_train, x_test, y_train, y_test = train_test_split(A, B, test_size=0.2, random_state=42)
#          
#         #####################################################################################################
#          
#         # convert class vectors to binary class matrices
#         num_classes = 3
#         y_train = keras.utils.to_categorical(y_train, num_classes)
#         y_test = keras.utils.to_categorical(y_test, num_classes)
#          
#          
#         model = Sequential()
#          
#         # we add a Convolution1D, which will learn filters
#         # word group filters of size filter_length:
#         model.add(Conv1D(250,
#                          3,
#                          padding='valid',
#                          activation='relu',
#                          strides=1,
#                          input_shape=(None, 7)))
#         # we use max pooling:
#         model.add(GlobalMaxPooling1D())
#          
#         # We add a vanilla hidden layer:
#         model.add(Dense(250))
#         model.add(Dropout(0.2))
#         model.add(Activation('relu'))
#          
#         # We project onto a single unit output layer, and squash it with a sigmoid:
#         model.add(Dense(3))
#         model.add(Activation('sigmoid'))
#          
#         model.compile(loss='binary_crossentropy',
#                       optimizer='adam',
#                       metrics=['accuracy'])
#         model.fit(x_train, y_train,
#                   batch_size=20,
#                   epochs=2,
#                   validation_data=(x_test, y_test))
#          
#         score = model.evaluate(x_test, y_test, verbose=0)
#         print('Test loss:', score[0])
#         print('Test accuracy:', score[1])        
        





#                           open      close       high        low        money  \
# 2017-11-14 10:00:00  3446.5500  3436.1400  3450.3400  3436.1400  60749246464   
# 2017-11-14 10:30:00  3436.7000  3433.1700  3438.7300  3431.2600  39968927744   
# 2017-11-14 11:00:00  3433.3600  3437.7500  3439.4100  3429.8200  28573523968   

# 
#                       macd_raw      macd  new_index              tb  
# 2017-11-14 10:00:00   9.480639 -0.786244        NaN             NaN  
# 2017-11-14 10:30:00   8.310828 -1.564845        NaN             NaN  
# 2017-11-14 11:00:00   7.664954 -1.768575        NaN             NaN  
# 2017-11-14 11:30:00   6.671123 -2.209925        NaN             NaN  
# 2017-11-14 13:30:00   6.626142 -1.803925        NaN             NaN  
# 2017-11-14 14:00:00   6.067070 -1.890397        NaN             NaN  
# 2017-11-14 14:30:00   4.368913 -2.870843        NaN             NaN  
# 2017-11-14 15:00:00   3.564614 -2.940114        NaN             NaN  
# 2017-11-15 10:00:00   1.701251 -3.842782        NaN             NaN  
# 2017-11-15 10:30:00  -0.326071 -4.696083        NaN             NaN  
# 2017-11-15 11:00:00  -1.975328 -5.076272        NaN             NaN  
# 2017-11-15 11:30:00  -3.382178 -5.186497        NaN             NaN  
# 2017-11-15 13:30:00  -4.234472 -4.831033        NaN             NaN  
# 2017-11-15 14:00:00  -4.859551 -4.364890        NaN             NaN  
# 2017-11-15 14:30:00  -5.841940 -4.277823        NaN             NaN  
# 2017-11-15 15:00:00  -6.416611 -3.881995        NaN             NaN  
# 2017-11-16 10:00:00  -6.918969 -3.507483         51  TopBotType.bot  
# 2017-11-16 10:30:00  -7.690800 -3.423451        NaN             NaN  
# 2017-11-16 11:00:00  -7.859263 -2.873531        NaN             NaN  
# 2017-11-16 11:30:00  -7.935189 -2.359566        NaN             NaN  
# 2017-11-16 13:30:00  -8.347779 -2.217725        NaN             NaN  
# 2017-11-16 14:00:00  -7.629007 -1.199162        NaN             NaN  
# 2017-11-16 14:30:00  -7.446391 -0.813237         57  TopBotType.top  
# 2017-11-16 15:00:00  -7.247972 -0.491854        NaN             NaN  
# 2017-11-17 10:00:00  -7.885018 -0.903120        NaN             NaN  



