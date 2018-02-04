from kBarProcessor import *
from jqdata import *
from biaoLiStatus import TopBotType
from pickle import dump
from pickle import load
import pandas as pd
import numpy as np
import talib

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
#         self.data_set = None
#         self.label_set = None
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
        
        if trunk_df.shape[0] > self.sub_max_count:
            return
        
        if self.manual_select:
            trunk_df = self.manual_select(trunk_df)
        else:
            trunk_df = self.manual_wash(trunk_df)  
        if self.isNormalize:
            trunk_df = self.normalize(trunk_df)
        
#         if self.data_set:
#             self.data_set = np.append(self.data_set, np.array(trunk_df.as_matrix()), axis=0)
#         else:
#             self.data_set = np.array(trunk_df.values)
#         if self.label_set:
#             self.label_set = np.append(self.label_set, np.array(label), axis=0)
#         else:
#             self.label_set = np.array(label)
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
            mlk = MLKbarPrep(isAnal=self.isAnal, count=period_count, isNormalize=True)
            mlk.retrieve_stock_data(stock)
            dl, ll = mlk.prepare_training_data()
            data_list = data_list + dl
            label_list = label_list + ll
#             if data_list:
#                 data_list = np.append(data_list, dl, axis=0)  
#             else:
#                 data_list = dl
#             if label_list:
#                 label_list = np.append(label_list, ll, axis=0)    
#             else:
#                 label_list = ll       
        
        data_list = self.pad_each_training_array(data_list)
        
        self.save_dataset((np.array(data_list), np.array(label_list)), filename)
        
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


# class MLDataProcess(object):
#     def __init__(self):
#         pass
#     
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
        
        
        
    
#     trainLines, trainLabels = load_dataset('train.pkl')

#                           open      close       high        low        money  \
# 2017-11-14 10:00:00  3446.5500  3436.1400  3450.3400  3436.1400  60749246464   
# 2017-11-14 10:30:00  3436.7000  3433.1700  3438.7300  3431.2600  39968927744   
# 2017-11-14 11:00:00  3433.3600  3437.7500  3439.4100  3429.8200  28573523968   
# 2017-11-14 11:30:00  3438.3300  3432.7300  3439.2000  3429.2000  24392908800   
# 2017-11-14 13:30:00  3432.5200  3442.8800  3443.3600  3432.5200  20425834496   
# 2017-11-14 14:00:00  3443.2200  3437.2600  3444.0100  3437.2600  24327323648   
# 2017-11-14 14:30:00  3437.5100  3422.3300  3437.5100  3419.8000  33216167936   
# 2017-11-14 15:00:00  3422.1900  3429.5500  3430.9800  3421.7300  35750559744   
# 2017-11-15 10:00:00  3416.2100  3414.6000  3423.7500  3410.8100  55361372160   
# 2017-11-15 10:30:00  3414.2500  3407.7300  3414.6600  3402.9300  38162980864   
# 2017-11-15 11:00:00  3407.2300  3406.9200  3409.4300  3400.9000  29406961664   
# 2017-11-15 11:30:00  3407.0900  3405.2000  3407.1100  3401.4300  25066242048   
# 2017-11-15 13:30:00  3405.2700  3407.8500  3408.4900  3396.3800  21151498240   
# 2017-11-15 14:00:00  3407.3600  3407.7800  3409.9000  3404.0100  17256185856   
# 2017-11-15 14:30:00  3407.8700  3400.9100  3411.4400  3398.5900  21355659264   
# 2017-11-15 15:00:00  3400.9600  3402.5200  3406.6400  3399.4300  31956697088   
# 2017-11-16 10:00:00  3393.1900  3400.9500  3401.2000  3390.7000  45503774720   
# 2017-11-16 10:30:00  3400.3800  3395.2200  3406.6500  3395.2200  28820635648   
# 2017-11-16 11:00:00  3395.8100  3399.5900  3400.1400  3393.3100  20578672640   
# 2017-11-16 11:30:00  3399.7300  3399.1700  3403.9800  3397.8300  18842411008   
# 2017-11-16 13:30:00  3399.2900  3393.6100  3400.7700  3391.4000  21402566656   
# 2017-11-16 14:00:00  3393.5300  3405.4800  3406.3400  3393.2800  22388572160   
# 2017-11-16 14:30:00  3404.6700  3399.6200  3409.4300  3399.1700  24022908928   
# 2017-11-16 15:00:00  3400.0100  3399.2500  3405.5800  3397.9100  39276363776   
# 2017-11-17 10:00:00  3392.6800  3388.2800  3403.2900  3381.8300  64131162112   
# 2017-11-17 10:30:00  3388.2300  3379.3100  3395.1500  3375.3500  44516007936   
# 2017-11-17 11:00:00  3379.8200  3381.9200  3387.1200  3373.4600  26680705024   
# 2017-11-17 11:30:00  3382.0500  3380.1600  3386.4700  3378.9000  18375770112   
# 2017-11-17 13:30:00  3380.9600  3386.8500  3386.9100  3373.3000  22499377152   
# 2017-11-17 14:00:00  3387.1800  3381.7300  3388.3500  3376.7300  29176512512   
# ...                        ...        ...        ...        ...          ...   
# 2017-12-01 11:00:00  3323.7000  3316.3500  3324.4100  3313.3900  19714468679   
# 2017-12-01 11:30:00  3315.6600  3305.6700  3316.6100  3305.3600  15512355362   
# 2017-12-01 13:30:00  3306.0800  3309.4400  3309.5700  3303.9800  13526109043   
# 2017-12-01 14:00:00  3309.5500  3307.1900  3314.8400  3306.9500  14551911717   
# 2017-12-01 14:30:00  3307.5400  3315.1300  3318.1000  3306.0900  18115189630   
# 2017-12-01 15:00:00  3315.5900  3317.8300  3318.6100  3312.6500  30275395439   
# 2017-12-04 10:00:00  3310.1500  3313.6600  3315.7100  3304.1000  44587786103   
# 2017-12-04 10:30:00  3313.7900  3313.2399  3318.8900  3312.6400  22925770045   
# 2017-12-04 11:00:00  3312.9100  3313.0700  3313.4500  3307.5300  18711267737   
# 2017-12-04 11:30:00  3313.0900  3322.1700  3322.2500  3312.0700  15047088349   
# 2017-12-04 13:30:00  3322.1000  3320.3200  3323.7700  3319.1400  15715596997   
# 2017-12-04 14:00:00  3320.7300  3316.1800  3320.8000  3308.7800  18728029872   
# 2017-12-04 14:30:00  3314.8800  3306.4699  3316.1900  3304.2700  19350906055   
# 2017-12-04 15:00:00  3306.7100  3310.3700  3311.7500  3304.2199  28519034539   
# 2017-12-05 10:00:00  3304.6700  3310.3500  3313.4899  3303.3900  37203142103   
# 2017-12-05 10:30:00  3310.3300  3309.1600  3312.1700  3303.1400  31927064680   
# 2017-12-05 11:00:00  3309.4899  3306.4300  3312.6700  3305.6100  20200039366   
# 2017-12-05 11:30:00  3306.4200  3311.7300  3315.4899  3304.0700  21838222754   
# 2017-12-05 13:30:00  3312.1400  3305.4500  3312.1400  3303.5700  18530595856   
# 2017-12-05 14:00:00  3305.2500  3305.9899  3306.2600  3300.9800  28738386709   
# 2017-12-05 14:30:00  3305.9800  3304.5700  3306.5200  3301.2800  30332461040   
# 2017-12-05 15:00:00  3304.4500  3303.0800  3305.2100  3300.9899  53456211406   
# 2017-12-06 10:00:00  3291.1600  3293.5600  3296.0700  3279.7399  34674733285   
# 2017-12-06 10:30:00  3293.4400  3282.8700  3293.4400  3279.6400  21529561799   
# 2017-12-06 11:00:00  3282.7900  3279.7800  3286.0900  3276.5300  14517425058   
# 2017-12-06 11:30:00  3280.2700  3283.0600  3284.2399  3277.0300  13492312774   
# 2017-12-06 13:30:00  3283.6500  3274.1500  3283.6500  3270.7399  19192852108   
# 2017-12-06 14:00:00  3274.4100  3262.9300  3277.1000  3262.9300  17387902797   
# 2017-12-06 14:30:00  3262.8100  3275.5700  3275.5700  3254.6100  23747889646   
# 2017-12-06 15:00:00  3274.7600  3294.1300  3294.1300  3274.7600  33529829897   
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
# 2017-11-17 10:30:00  -9.009825 -1.622342        NaN             NaN  
# 2017-11-17 11:00:00  -9.580203 -1.754176        NaN             NaN  
# 2017-11-17 11:30:00 -10.058303 -1.785821        NaN             NaN  
# 2017-11-17 13:30:00  -9.784584 -1.209681         61  TopBotType.bot  
# 2017-11-17 14:00:00  -9.867059 -1.033725        NaN             NaN  
# ...                        ...       ...        ...             ...  
# 2017-12-01 11:00:00  -5.191112 -0.168306        NaN             NaN  
# 2017-12-01 11:30:00  -6.074752 -0.841556        NaN             NaN  
# 2017-12-01 13:30:00  -6.397093 -0.931118        NaN             NaN  
# 2017-12-01 14:00:00  -6.756226 -1.032201        NaN             NaN  
# 2017-12-01 14:30:00  -6.327213 -0.482550        NaN             NaN  
# 2017-12-01 15:00:00  -5.703603  0.112848        NaN             NaN  
# 2017-12-04 10:00:00  -5.482670  0.267025        NaN             NaN  
# 2017-12-04 10:30:00  -5.280607  0.375271        NaN             NaN  
# 2017-12-04 11:00:00  -5.075670  0.464166        NaN             NaN  
# 2017-12-04 11:30:00  -4.131339  1.126797        NaN             NaN  
# 2017-12-04 13:30:00  -3.491976  1.412928        132  TopBotType.top  
# 2017-12-04 14:00:00  -3.281512  1.298714        NaN             NaN  
# 2017-12-04 14:30:00  -3.853818  0.581126        NaN             NaN  
# 2017-12-04 15:00:00  -3.947168  0.390221        NaN             NaN  
# 2017-12-05 10:00:00  -3.976919  0.288376        NaN             NaN  
# 2017-12-05 10:30:00  -4.049836  0.172367        NaN             NaN  
# 2017-12-05 11:00:00  -4.278591 -0.045110        NaN             NaN  
# 2017-12-05 11:30:00  -3.986264  0.197774        NaN             NaN  
# 2017-12-05 13:30:00  -4.212774 -0.022989        NaN             NaN  
# 2017-12-05 14:00:00  -4.299161 -0.087501        NaN             NaN  
# 2017-12-05 14:30:00  -4.431118 -0.175567        NaN             NaN  
# 2017-12-05 15:00:00  -4.602867 -0.277852        NaN             NaN  
# 2017-12-06 10:00:00  -5.444404 -0.895511        NaN             NaN  
# 2017-12-06 10:30:00  -6.894447 -1.876443        NaN             NaN  
# 2017-12-06 11:00:00  -8.198447 -2.544355        NaN             NaN  
# 2017-12-06 11:30:00  -8.865017 -2.568740        NaN             NaN  
# 2017-12-06 13:30:00  -9.997002 -2.960580        NaN             NaN  
# 2017-12-06 14:00:00 -11.665002 -3.702864        NaN             NaN  
# 2017-12-06 14:30:00 -11.830586 -3.094758        146  TopBotType.bot  
# 2017-12-06 15:00:00 -10.344925 -1.287278        NaN             NaN  
