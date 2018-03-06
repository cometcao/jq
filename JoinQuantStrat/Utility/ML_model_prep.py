# -*- encoding: utf8 -*-
import keras
import numpy as np
from keras import backend as K
from keras.utils.np_utils import to_categorical
from keras.models import load_model
from keras.models import Sequential
from keras.layers import Dense, Dropout, Flatten, TimeDistributed,LSTM
from keras.layers.normalization import BatchNormalization
from keras.layers import Conv2D, MaxPooling2D, ConvLSTM2D
from keras import optimizers


class MLDataProcess(object):
    def __init__(self, model_name='ml_model.h5'):
        self.model_name = model_name
        self.model = None
     
    def define_conv2d_model(self, x_train, x_test, y_train, y_test, num_classes, batch_size = 50,epochs = 5):
        x_train = np.expand_dims(x_train, axis=2) 
        x_test = np.expand_dims(x_test, axis=2) 
        
        input_shape = None
        if K.image_data_format() == 'channels_first':
            # convert class vectors to binary class matrices
            a, b, c, d = x_train.shape
            input_shape = (d, b, c)
        else:
            # convert class vectors to binary class matrices
            a, b, c, d = x_train.shape
            input_shape = (b, c, d)

        
#         y_train = to_categorical(y_train, num_classes)
#         y_test = to_categorical(y_test, num_classes)
        
        model = Sequential()
        model.add(Conv2D(32, kernel_size=(3, 1),
                         activation='relu',
                         input_shape=input_shape))
        model.add(Conv2D(64, (3, 1), activation='relu'))
        model.add(MaxPooling2D(pool_size=(2, 1)))
#         model.add(BatchNormalization())
        model.add(Dropout(0.25))
        model.add(Flatten())
        model.add(Dense(128, activation='relu'))
        model.add(Dropout(0.5))
        model.add(Dense(num_classes, activation='softmax'))
        
        model.compile(loss=keras.losses.categorical_crossentropy,
                      optimizer=keras.optimizers.Adadelta(),
                      metrics=['accuracy'])
                
        print (model.summary())
        
        self.process_model(model, x_train, x_test, y_train, y_test, batch_size, epochs)
    
    
    def define_conv_lstm_model(self, x_train, x_test, y_train, y_test, num_classes, batch_size = 50,epochs = 5):
        x_train = np.expand_dims(x_train, axis=2) 
        x_test = np.expand_dims(x_test, axis=2) 
        
        x_train = np.expand_dims(x_train, axis=1)
        x_test = np.expand_dims(x_test, axis=1)
        
        input_shape = None
        a, b, c, d, e = x_train.shape
        if K.image_data_format() == 'channels_first':
            # convert class vectors to binary class matrices
            input_shape = (b, e, c, d)
        else:
            # convert class vectors to binary class matrices
            input_shape = (b, c, d, e)
        
#         y_train = to_categorical(y_train, num_classes)
#         y_test = to_categorical(y_test, num_classes)
        
        # define CNN model
        model = Sequential()
        model.add(ConvLSTM2D(32, 
                             kernel_size=(3, 1), 
                             input_shape=input_shape,
                             padding='same',
                             return_sequences=True, 
                             dropout = 0.2, 
                             recurrent_dropout = 0.2
                             ))
        model.add(BatchNormalization())
        model.add(ConvLSTM2D(64, 
                             kernel_size=(3, 1), 
                             padding='same',
                             return_sequences=False,
                             dropout = 0.2, 
                             recurrent_dropout = 0.2
                             ))        
        model.add(BatchNormalization())
        model.add(Flatten())
        model.add(Dense(128, activation='relu'))
        model.add(Dense(num_classes, activation='softmax'))
        
        model.compile(loss=keras.losses.categorical_crossentropy,
                      optimizer=keras.optimizers.Adadelta(),
                      metrics=['accuracy'])        
        
        print (model.summary())
        
        self.process_model(model, x_train, x_test, y_train, y_test, batch_size, epochs)
    
    def process_model(self, model, x_train, x_test, y_train, y_test, batch_size = 50,epochs = 5):  
        model.fit(x_train, y_train,
                  batch_size=batch_size,
                  epochs=epochs,
                  verbose=2,
                  validation_data=(x_test, y_test))
        score = model.evaluate(x_test, y_test, verbose=1)
        print('Test loss:', score[0])
        print('Test accuracy:', score[1])
        
        self.model = model
        if self.model_name:
            model.save(self.model_name)
            print("saved to file {0}".format(self.model_name))
    
    def load_model(self, model_name):
        self.model = load_model(model_name)
        self.model_name = model_name
        print("loaded model: {0}".format(self.model_name))

    def model_predict_cnn(self, data_set, unique_id):
        if self.model:
            data_set = np.expand_dims(data_set, axis=2)
            prediction = np.array(self.model.predict(data_set))
            print(prediction)
            y_class = unique_id[prediction.argmax(axis=-1)]
            print(y_class)
        else:
            print("Invalid model")
    
    def model_predict_cnn_lstm(self, data_set, unique_id):
        if self.model:
            data_set = np.expand_dims(data_set, axis=2)
            data_set = np.expand_dims(data_set, axis=1)
            prediction = np.array(self.model.predict(data_set))
            print(prediction)
            y_class = unique_id[prediction.argmax(axis=-1)]
            print(y_class)
            return (y_class, prediction)
        else:
            print("Invalid model")
            return None

