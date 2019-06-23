# -*- encoding: utf8 -*-
import keras
import numpy as np
from keras import backend as K
from keras.utils.np_utils import to_categorical
from keras.models import load_model
from keras.models import Sequential
from keras.layers import Dense, Dropout, Flatten, TimeDistributed,LSTM, GRU, Bidirectional
from keras.layers.normalization import BatchNormalization
from keras.layers import Conv2D, MaxPooling2D, ConvLSTM2D, Conv1D, MaxPooling1D, Reshape, GlobalAveragePooling2D, GlobalMaxPooling2D
from keras import optimizers
from keras.callbacks import EarlyStopping
from keras.callbacks import ModelCheckpoint
from keras.callbacks import CSVLogger
from keras.callbacks import Callback
from common_include import pad_each_training_array
from attentionWithContext import AttentionWithContext
from keras.layers.pooling import GlobalMaxPool1D

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
    
        
    def define_conv1d_shape(self, data_gen):
        x_train, x_test = next(data_gen)
        
        input_shape = None
        a, b, c = x_train.shape
        if K.image_data_format() == 'channels_first':
            input_shape = (a, c, b)
        else:
            input_shape = (a, b, c)

        return (input_shape[1], input_shape[2])
    
        
    def create_conv1d_model_arch(self, input_shape, num_classes, hp):
        model = Sequential()
        model.add(Conv1D(hp.hidden_neurons, kernel_size=3, strides=2,
                         activation=hp.activation_func,
                         input_shape=input_shape,
                         kernel_initializer=hp.weight_init))
        model.add(Conv1D(hp.hidden_neurons, 3, strides=2, activation=hp.activation_func))
        if hp.network_topology == "deep": #add two extra layers
            model.add(Conv1D(hp.hidden_neurons, 3, strides=2, activation=hp.activation_func))
            model.add(Conv1D(hp.hidden_neurons, 3, strides=2, activation=hp.activation_func))
        model.add(Conv1D(hp.hidden_neurons, 3, strides=2, activation=hp.activation_func))
        model.add(GlobalAveragePooling1D())
        model.add(Dense(hp.hidden_neurons, activation=hp.activation_func))
        model.add(Dropout(hp.drop_out_rate))
        model.add(Dense(num_classes, activation='softmax'))
        
        model.compile(loss=keras.losses.categorical_crossentropy,
                      optimizer=hp.get_optimizer(),
                      metrics=['accuracy'])
                
        print (model.summary())
        return model
        
    
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
    
    def create_conv_lstm_model_arch(self, input_shape, num_classes, hp):
        model = Sequential()
        model.add(ConvLSTM2D(hp.hidden_neurons, 
                             kernel_initializer = hp.weight_init,
                             kernel_size=(1, 1), 
                             data_format='channels_last',
                             input_shape=input_shape,
                             padding='valid',
                             return_sequences=True, 
                             dropout = hp.drop_out_rate, 
                             recurrent_dropout = hp.drop_out_rate,
                             activation = hp.activation_func
                             ))
        if hp.network_topology == "deep":
            model.add(ConvLSTM2D(hp.hidden_neurons, 
                                 kernel_size=(1, 1), 
                                 padding='valid',
                                 return_sequences=True,
                                 dropout = hp.drop_out_rate, 
                                 recurrent_dropout = hp.drop_out_rate,
                                 activation = hp.activation_func
                             ))        
            model.add(ConvLSTM2D(hp.hidden_neurons, 
                                 kernel_size=(1, 1), 
                                 padding='valid',
                                 return_sequences=True,
                                 dropout = hp.drop_out_rate, 
                                 recurrent_dropout = hp.drop_out_rate,
                                 activation = hp.activation_func
                             ))
        model.add(ConvLSTM2D(hp.hidden_neurons, 
                             kernel_size=(1, 1), 
                             padding='valid',
                             return_sequences=False,
                             dropout = hp.drop_out_rate, 
                             recurrent_dropout = hp.drop_out_rate,
                             activation = hp.activation_func
                             ))        
        model.add(GlobalMaxPooling2D())
        model.add(Dropout(hp.drop_out_rate))

#         model.add(Flatten())
         
#         model.add(Dense(128, activation='relu'))
#         model.add(BatchNormalization())
        model.add(Dense(num_classes, activation='softmax')) # softmax sigmoid
        
        model.compile(loss=keras.losses.categorical_crossentropy, #categorical_crossentropy
                      optimizer=hp.get_optimizer(), #Adadelta, Nadam, SGD, Adam
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
                      
        
    def create_lstm_model_arch(self, input_shape, num_classes, hp):
        model = Sequential()    
#         print(input_shape)
#         model.add(Flatten(input_shape=input_shape))
#         model.add(Dense (144, activation='relu'))
        
        model.add(LSTM(64, return_sequences=True, 
                       input_shape=input_shape, dropout=0.191, recurrent_dropout = 0.191)) 

        model.add(Dense (model.output_shape[2], activation='relu'))

        if self.isDebug:
            print("layer input/output shape:{0}, {1}".format(model.input_shape, model.output_shape))
            
        model.add(Dense(num_classes, activation='softmax')) #softmax sigmoid
        
        model.compile(loss=keras.losses.categorical_crossentropy, #categorical_crossentropy
                      optimizer=keras.optimizers.Adadelta(), #Adadelta, Nadam, SGD, Adam,SGD(lr=0.01, decay=1e-6, momentum=0.9, nesterov=True)
                      metrics=['accuracy'])
        
        print (model.summary())
        return model         
        
    def create_rnn_cnn_model_arch(self, input_shape, num_classes, hp):
        model = Sequential()     
        model.add(Conv1D(hp.hidden_neurons,
                         kernel_size=3,
                         input_shape=input_shape,
                         padding='valid',
                         activation=hp.activation_func,
                         kernel_initializer=hp.weight_init))
        model.add(MaxPooling1D(pool_size=3, strides=2))

        model.add(Bidirectional(LSTM(model.output_shape[2], return_sequences=True, 
                                     activation = hp.activation_func,
                                     dropout = hp.drop_out_rate, 
                                     recurrent_dropout = hp.drop_out_rate), merge_mode='concat'))

        if hp.network_topology == 'deep':
#             model.add(Bidirectional(LSTM(model.output_shape[2], return_sequences=True, 
#                              activation = hp.activation_func,
#                              dropout = hp.drop_out_rate, 
#                              recurrent_dropout = hp.drop_out_rate), merge_mode='concat'))
            model.add(TimeDistributed(Dense (num_classes, activation=hp.activation_func)))
            model.add(AttentionWithContext())
        if self.isDebug:
            print("layer input/output shape:{0}, {1}".format(model.input_shape, model.output_shape))
#         model.add(GlobalMaxPool1D())
        model.add(Flatten())

        model.add(Dense(num_classes, activation='softmax' if num_classes>2 else 'sigmoid')) #softmax, sigmoid
        model.compile(loss=keras.losses.categorical_crossentropy if num_classes>2 else keras.losses.binary_crossentropy,
                      optimizer=hp.get_optimizer(), #Adadelta, Nadam, SGD, Adam,SGD(lr=0.01, decay=1e-6, momentum=0.9, nesterov=True)
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

    def define_cnn_model_gen(self, data_gen, validation_gen, num_classes, batch_size = 50, steps = 10000,epochs = 5, verbose=0, validation_steps=1000, patience=10, hyper_param=None):
        input_shape = self.define_conv1d_shape(data_gen)

        model = self.create_conv1d_model_arch(input_shape, num_classes, hyper_param)
        
        return self.process_model_generator(model, data_gen, steps, epochs, verbose, validation_gen, validation_gen, validation_steps, patience)    


    def define_conv_lstm_model_gen(self, data_gen, validation_gen, num_classes, batch_size = 50, steps = 10000,epochs = 5, verbose=0, validation_steps=1000, patience=10, hyper_param=None):
        input_shape = self.define_conv_lstm_shape(data_gen)
        
        model = self.create_conv_lstm_model_arch(input_shape, num_classes, hyper_param)
        
        return self.process_model_generator(model, data_gen, steps, epochs, verbose, validation_gen, validation_gen, validation_steps, patience)


    def define_rnn_cnn_model_gen(self, data_gen, validation_gen, num_classes, batch_size = 50, steps = 10000,epochs = 5, verbose=0, validation_steps=1000, patience=10, hyper_param=None):
        input_shape = self.define_rnn_cnn_shape(data_gen)
        
        model = self.create_rnn_cnn_model_arch(input_shape, num_classes, hyper_param)
#         model = self.create_lstm_model_arch(input_shape, num_classes, hyper_param)
        
        return self.process_model_generator(model, data_gen, steps, epochs, verbose, validation_gen, validation_gen, validation_steps, patience)

    def process_model_generator(self, model, generator, steps = 10000, epochs = 5, verbose = 2, validation_data=None, evaluate_generator=None, validation_steps=1000, patience=10):
        es_loss = EarlyStopping(monitor='val_loss', mode='min', verbose=verbose, patience=patience)
#         es_acc = EarlyStopping(monitor='val_acc', mode='max', verbose=verbose, patience=patience, baseline=0.5)
        mc_loss = ModelCheckpoint('training_model/bl.{epoch:003d}-{val_acc:.4f}-{val_loss:.4f}-{acc:.4f}-{loss:.4f}.h5', monitor='val_loss', mode='min', verbose=verbose, save_best_only=True)
        mc_acc = ModelCheckpoint('training_model/ba.{epoch:003d}-{val_acc:.4f}-{val_loss:.4f}-{acc:.4f}-{loss:.4f}.h5', monitor='val_acc', mode='max', verbose=verbose, save_best_only=True)
#         cvs_logger = CSVLogger('log/training.log', append=True)
#         acclosshistory = LossAccHistory()
        
        record = model.fit_generator(generator, 
                            steps_per_epoch = steps, 
                            epochs = epochs, 
                            verbose = verbose,
                            validation_data = validation_data,
                            validation_steps = validation_steps, 
                            callbacks=[es_loss, mc_loss, mc_acc]) # , mc_loss, mc_acc cvs_logger,  mc_loss, mc_acc
#         score = model.evaluate_generator(evaluate_generator, steps=validation_steps)
#         print('Test loss:', score[0])
#         print('Test accuracy:', score[1])          
        self.model = model
        
#         if self.model_name:
#             if self.saveByte:
#                 self.save_model_byte(self.model_name, self.model)
#             else:
#                 model.save(self.model_name)
#             print("saved to file {0}".format(self.model_name))       
        
        return min(record.history['val_loss']), max(record.history['val_acc'])
        
    
    def load_model(self, model_name):
        self.model = load_model(model_name, custom_objects={'AttentionWithContext': AttentionWithContext})
        self.model_name = model_name
        
        if self.isDebug:
            print("loaded model: {0}".format(self.model_name))
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

class LossAccHistory(Callback):
    def on_train_begin(self, logs={}):
        self.losses = []
        self.accs = []

    def on_batch_end(self, batch, logs={}):
        self.losses.append(logs.get('val_loss'))
        self.accs.append(logs.get('val_acc'))
        
    def get_highest_acc(self):
        return max(self.accs)

    def get_lowest_loss(self):
        return min(self.losses)
      
    
class HyperParam():
    def __init__(self, nt, hn, wi, lr, m, af, dor, om):
        self.network_topology = nt
        self.hidden_neurons = hn
        self.weight_init = wi
        self.learning_rate = lr
        self.momentum = m
        self.activation_func = af
        self.optimization_method = om
        self.drop_out_rate = dor
    
    def get_optimizer(self):
        if self.optimization_method == "SGD":
            return keras.optimizers.SGD(lr = self.learning_rate, momentum=self.momentum, nesterov=False)
        elif self.optimization_method == "RMSprop":
            return keras.optimizers.RMSprop(lr = self.learning_rate)
        elif self.optimization_method == "Adagrad":
            return keras.optimizers.Adagrad(lr = self.learning_rate)
        elif self.optimization_method == "Adadelta":
            return keras.optimizers.Adadelta(lr = self.learning_rate)
        elif self.optimization_method == "Adam":
            return keras.optimizers.Adam(lr = self.learning_rate)      
        elif self.optimization_method == "Adamax":
            return keras.optimizers.Adamax(lr = self.learning_rate)  
        elif self.optimization_method == "Nadam":
            return keras.optimizers.Nadam(lr = self.learning_rate)           
