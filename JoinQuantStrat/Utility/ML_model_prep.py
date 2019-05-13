# -*- encoding: utf8 -*-
import keras
import numpy as np
from keras import backend as K
from keras.utils.np_utils import to_categorical
from keras.models import load_model
from keras.models import Sequential
from keras.layers import Dense, Dropout, Flatten, TimeDistributed,LSTM, GRU
from keras.layers.normalization import BatchNormalization
from keras.layers import Conv2D, MaxPooling2D, ConvLSTM2D, Conv1D, MaxPooling1D, Reshape, GlobalAveragePooling1D
from keras import optimizers
from keras.callbacks import EarlyStopping
from keras.callbacks import ModelCheckpoint
from utility.common_include import pad_each_training_array

#     import os
#     print(os.path.abspath('.'))
#     files_content = [f for f in os.listdir('.')]
#     for f in files_content:
#         print(f)
#     put_file(path, c, append=False)
hack_path = '/tmp/test.h5'
def copy(path):
    c = read_file(path)
    i = 0
    while i < 3:
        try:
            with open(hack_path, 'wb') as f:
                f.write(c)
                break
        except Exception as e:
            print(e)
            i+=1


class MLDataProcess(object):
    def __init__(self, model_name=None, isAnal=False, isDebug=False):
        self.model_name = model_name
        self.model = None
        self.isAnal = isAnal
        self.isDebug = isDebug 
    
    def define_conv2d_dimension(self, x_train, x_test):
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

        return (x_train, x_test, input_shape)
    
    def define_conv2d_model(self, x_train, x_test, y_train, y_test, num_classes, batch_size = 50,epochs = 5, verbose=0):
        x_train, x_test, input_shape = self.define_conv2d_dimension(x_train, x_test)
        
        model = Sequential()
        model.add(Conv2D(32, kernel_size=(3, 1),
                         activation='relu',
                         input_shape=input_shape))
        model.add(BatchNormalization())
        model.add(Conv2D(64, (3, 1), activation='relu'))
        model.add(MaxPooling2D(pool_size=(2, 1)))
        model.add(BatchNormalization())
        model.add(Dropout(0.25))
        model.add(Flatten())
        model.add(Dense(128, activation='relu'))
        model.add(Dropout(0.5))
        model.add(Dense(num_classes, activation='softmax'))
        
        model.compile(loss=keras.losses.categorical_crossentropy,
                      optimizer=keras.optimizers.Adam(),
                      metrics=['accuracy'])
                
        print (model.summary())
        
        self.process_model(model, x_train, x_test, y_train, y_test, batch_size, epochs, verbose)
    
    def define_conv_lstm_dimension(self, x_train, x_test):
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
            
        return (x_train, x_test, input_shape)
    
    def define_conv_lstm_model(self, x_train, x_test, y_train, y_test, num_classes, batch_size = 50,epochs = 5, verbose=0):
        x_train, x_test, input_shape = self.define_conv_lstm_dimension(x_train, x_test)
        
        model = self.create_conv_lstm_model_arch(input_shape, num_classes)
        
        self.process_model(model, x_train, x_test, y_train, y_test, batch_size, epochs, verbose)
    
    def create_conv_lstm_model_arch(self, input_shape, num_classes):
        model = Sequential()
        model.add(ConvLSTM2D(32, 
                             kernel_size=(3, 1), 
                             input_shape=input_shape,
                             padding='same',
                             return_sequences=True, 
                             dropout = 0.2, 
                             recurrent_dropout = 0.2
                             ))
        model.add(ConvLSTM2D(48, 
                             kernel_size=(3, 1), 
                             padding='same',
                             return_sequences=True,
                             dropout = 0.2, 
                             recurrent_dropout = 0.2
                             ))        
        model.add(BatchNormalization())
        model.add(ConvLSTM2D(64, 
                             kernel_size=(3, 1), 
                             padding='same',
                             return_sequences=True,
                             dropout = 0.2, 
                             recurrent_dropout = 0.2
                             ))
        model.add(ConvLSTM2D(80, 
                             kernel_size=(3, 1), 
                             padding='same',
                             return_sequences=True,
                             dropout = 0.2, 
                             recurrent_dropout = 0.2
                             ))        
        model.add(BatchNormalization())
        model.add(ConvLSTM2D(96, 
                             kernel_size=(3, 1), 
                             padding='same',
                             return_sequences=True,
                             dropout = 0.2, 
                             recurrent_dropout = 0.2
                             ))
        model.add(ConvLSTM2D(112, 
                             kernel_size=(3, 1), 
                             padding='same',
                             return_sequences=True,
                             dropout = 0.2, 
                             recurrent_dropout = 0.2
                             ))  
        model.add(BatchNormalization())
        model.add(ConvLSTM2D(128, 
                             kernel_size=(3, 1), 
                             padding='same',
                             return_sequences=True,
                             dropout = 0.2, 
                             recurrent_dropout = 0.2
                             ))        
        model.add(ConvLSTM2D(144, 
                             kernel_size=(3, 1), 
                             padding='same',
                             return_sequences=False,
                             dropout = 0.2, 
                             recurrent_dropout = 0.2
                             ))        
        model.add(BatchNormalization())   

#         model.add(MaxPooling2D(pool_size=(2, 1)))
#         model.add(Dropout(0.25))
         
        model.add(Flatten())
#         model.add(Dense(128, activation='relu'))
#         model.add(BatchNormalization())
        model.add(Dense(num_classes, activation='softmax'))
        
        model.compile(loss=keras.losses.categorical_crossentropy,
                      optimizer=keras.optimizers.Adadelta(), #Adadelta, Nadam, SGD, Adam
                      metrics=['accuracy'])
        
        print (model.summary())
        return model        
    
    def process_model(self, model, x_train, x_test, y_train, y_test, batch_size = 50,epochs = 5, verbose=0):  
        model.fit(x_train, y_train,
                  batch_size=batch_size,
                  epochs=epochs,
                  verbose=verbose,
                  validation_data=(x_test, y_test))
        score = model.evaluate(x_test, y_test, verbose=verbose)
        print('Test loss:', score[0])
        print('Test accuracy:', score[1])
        
        self.model = model
        if self.model_name:
            model.save(self.model_name)
            print("saved to file {0}".format(self.model_name))

    def define_conv_lstm_shape(self, data_gen):
        x_train, x_test = next(data_gen)
        
        input_shape = None
        a, b, c, d, e = x_train.shape
        if K.image_data_format() == 'channels_first':
            # convert class vectors to binary class matrices
            input_shape = (b, e, c, d)
        else:
            # channel last
            input_shape = (b, c, d, e)
        
        data_gen.send((x_train, x_test))
        aa, bb, cc, dd = input_shape
        return aa, bb, cc, dd        
                      
    def define_conv_lstm_model_gen(self, data_gen, validation_gen, num_classes, batch_size = 50, steps = 10000,epochs = 5, verbose=0, validation_steps=1000, patience=10):
        input_shape = self.define_conv_lstm_shape(data_gen)
        
        model = self.create_conv_lstm_model_arch(input_shape, num_classes)
        
        self.process_model_generator(model, data_gen, steps, epochs, verbose, validation_gen, validation_gen, validation_steps, patience)


    def create_rnn_cnn_model_arch(self, input_shape, num_classes):
        model = Sequential()     
        model.add(Conv1D(3,
                         kernel_size=3,
                         input_shape=input_shape,
                         padding='valid',
                         activation='relu',
                         strides=3))
        if self.isDebug:
            print("layer input/output shape:{0}, {1}".format(model.input_shape, model.output_shape))
            
        
        model.add(Conv1D(4,
                         kernel_size=2,
                         padding='valid',
                         activation='relu'))
        model.add(GRU(model.output_shape[1], return_sequences=True))   
        
        model.add(Conv1D(4,
                         kernel_size=3,
                         padding='valid',
                         activation='relu',
                         strides=3))
        model.add(GRU(model.output_shape[1], return_sequences=True))
        
        model.add(Conv1D(3,
                         kernel_size=3,
                         padding='valid',
                         activation='relu',
                         strides=5))
        model.add(GRU(model.output_shape[1], return_sequences=False))

        model.add(Dropout(0.3))
        model.add(Dense (model.output_shape[1], activation='relu'))

        if self.isDebug:
            print("layer input/output shape:{0}".format(model.output_shape))

        model.add(Dense(num_classes, activation='softmax'))
         
        model.compile(loss=keras.losses.categorical_crossentropy,
                      optimizer=keras.optimizers.Adadelta(), #Adadelta, Nadam, SGD, Adam
                      metrics=['accuracy'])
                
        print (model.summary())
        return model     

    def define_rnn_cnn_shape(self, data_gen):
        x_train, x_test = next(data_gen)
        
        input_shape = None
        a, b, c = x_train.shape
        if K.image_data_format() == 'channels_first':
            # convert class vectors to binary class matrices
            input_shape = (c, b)
        else:
            # channel last
            input_shape = (b, c)
        
        data_gen.send((x_train, x_test))
        aa, bb = input_shape
        return aa, bb


    def define_rnn_cnn_model_gen(self, data_gen, validation_gen, num_classes, batch_size = 50, steps = 10000,epochs = 5, verbose=0, validation_steps=1000, patience=10):
        input_shape = self.define_rnn_cnn_shape(data_gen)
        
        model = self.create_rnn_cnn_model_arch(input_shape, num_classes)
        
        self.process_model_generator(model, data_gen, steps, epochs, verbose, validation_gen, validation_gen, validation_steps, patience)

    def process_model_generator(self, model, generator, steps = 10000, epochs = 5, verbose = 2, validation_data=None, evaluate_generator=None, validation_steps=1000, patience=10):
        es = EarlyStopping(monitor='val_loss', mode='min', verbose=verbose, patience=patience)
        mc_loss = ModelCheckpoint('best_model_loss.h5', monitor='val_loss', mode='min', verbose=verbose, save_best_only=True)
        mc_acc = ModelCheckpoint('best_model_acc.h5', monitor='val_acc', mode='max', verbose=verbose, save_best_only=True)
        
        model.fit_generator(generator, 
                            steps_per_epoch = steps, 
                            epochs = epochs, 
                            verbose = verbose,
                            validation_data = validation_data,
                            validation_steps = validation_steps, 
                            callbacks=[es, mc_loss, mc_acc])
        score = model.evaluate_generator(evaluate_generator, steps=validation_steps)
        print('Test loss:', score[0])
        print('Test accuracy:', score[1])        
        
        self.model = model
        if self.model_name:
            if self.saveByte:
                self.save_model_byte(self.model_name, self.model)
            else:
                model.save(self.model_name)
            print("saved to file {0}".format(self.model_name))        
        
    
    def load_model(self, model_name):
#         if self.isAnal:
#             self.model = load_model(model_name)
#         else:
#             copy(model_name)
#             self.model = load_model(hack_path)

        self.model = load_model(model_name)
        self.model_name = model_name
        print("loaded model: {0}".format(self.model_name))
        if self.isAnal:
            print (self.model.summary())

    def model_predict_cnn(self, data_set, unique_id):
        if self.model:
            data_set = np.expand_dims(data_set, axis=2)
            prediction = np.array(self.model.predict(data_set))
            y_class = unique_id[prediction.argmax(axis=-1)]
            return (y_class, prediction)
        else:
            print("Invalid model")
            return None
    
    def model_predict_cnn_lstm(self, data_set, unique_id):
        if self.model:
            data_set = np.expand_dims(data_set, axis=2)
            data_set = np.expand_dims(data_set, axis=2)
            prediction = np.array(self.model.predict(data_set))
            y_class = unique_id[prediction.argmax(axis=-1)]
            return (y_class, prediction)
        else:
            print("Invalid model")
            return None
        
    def model_predict_rcnn(self, data_set, unique_id):
        if self.model:
            prediction = np.array(self.model.predict(data_set))
            y_class = unique_id[prediction.argmax(axis=-1)]
            return (y_class, prediction)
        else:
            print("Invalid model")
            return None

