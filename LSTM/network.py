import math
import numpy as np
from pysc2.agents import base_agent
from pysc2.lib import actions
from pysc2.lib import features
from pysc2.env import sc2_env, run_loop, available_actions_printer
from pysc2 import maps
from absl import flags
from collections import deque
import keras
from keras import backend as K
from keras.models import Sequential
from keras.layers import Dense,Conv1D,Conv2D,Dropout,Flatten,Activation,MaxPool1D,MaxPooling2D,Lambda, ConvLSTM2D, TimeDistributed
from keras.optimizers import Adam, RMSprop


class FullyConvLSTM:
    """This class implements the fullyconvLSTM agent network from DeepMind paper, that trains on 4 consecutive slides.

        Args
        ----
        eta : the entropy regularization hyperparameter
        expl_rate : the multiplication factor for the policy output Dense layer, used to favorise exploration. Set to 0 if
            not exploring but exploiting
        model (Keras.model): the actual keras model"""

    def __init__(self, eta, expl_rate, categorical_actions, spatial_actions):
        self.eta = eta
        self.expl_rate = expl_rate
        self.categorical_actions = categorical_actions
        self.spatial_actions = spatial_actions
        self.model = None
        self.initialize_layers(eta, expl_rate)

    def initialize_layers(self, eta, expl_rate):
        """Initializes the keras model"""

        def entropy_reg(weight_matrix):
            """Entropy regularization to promote exploration"""
            return - self.eta * K.sum(weight_matrix * K.log(weight_matrix))
        cnn_map = Sequential()
        cnn_map.add(Conv2D(16, kernel_size=(5,5), data_format='channels_first', input_shape=(17,64,64), kernel_initializer='he_uniform'))
        cnn_map.add(Activation('relu'))
        cnn_map.add(MaxPooling2D(pool_size=(2, 2), strides=None, padding='valid', data_format='channels_first'))

        model_view_map= Sequential()
        model_view_map.add(TimeDistributed(cnn_map))
        model_view_map.add(ConvLSTM2D(filters=32, kernel_size=(3,3), strides=(1,1), activation='relu'))

        model_view_map.add(MaxPooling2D(pool_size=(2,2), strides=None, padding='valid', data_format='channels_first'))
        model_view_map.add(Flatten())

        cnn_mini = Sequential()
        cnn_mini.add(Conv2D(16, kernel_size=(5, 5), data_format='channels_first', input_shape=(17, 64, 64),
                           kernel_initializer='he_uniform'))
        cnn_mini.add(Activation('relu'))
        cnn_mini.add(MaxPooling2D(pool_size=(2, 2), strides=None, padding='valid', data_format='channels_first'))

        model_view_mini = Sequential()
        model_view_mini.add(TimeDistributed(cnn_mini))
        model_view_mini.add(ConvLSTM2D(filters=32, kernel_size=(3, 3), strides=(1,1), activation='relu'))

        model_view_mini.add(MaxPooling2D(pool_size=(2,2), strides=None, padding='valid', data_format='channels_first'))
        model_view_mini.add(Flatten())

        concat = 
        # map conv
        input_map = keras.layers.Input(shape=(17, 64, 64), name='input_map')
        model_view_map = TimeDistributed(Conv2D(16, kernel_size=(5, 5), data_format='channels_first', input_shape=(17, 64, 64),kernel_initializer="he_uniform"))(input_map)
        model_view_map = TimeDistributed(Activation('relu'))(model_view_map)
        model_view_map = TimeDistributed(MaxPooling2D(pool_size=(2, 2), strides=None, padding='valid', data_format='channels_first'))(
            model_view_map)
        """model_view_map = Conv2D(32, kernel_size=(3, 3), data_format='channels_first', kernel_initializer="he_uniform")(
            model_view_map)
        model_view_map = Activation('relu')(model_view_map)
        model_view_map = MaxPooling2D(pool_size=(2, 2), strides=None, padding='valid', data_format='channels_first')(
            model_view_map)"""
        model_view_map = ConvLSTM2D(filters=32, kernel_size=(3,3), strides=1, activation='relu')(model_view_map)

        # minimap conv
        input_mini = keras.layers.Input(shape=(7, 64, 64), name='input_mini')
        model_view_mini = TimeDistributed(Conv2D(16, kernel_size=(5, 5), data_format='channels_first', input_shape=(7, 64, 64),
                                 kernel_initializer="he_uniform"))(input_mini)
        model_view_mini = TimeDistributed(Activation('relu'))(model_view_mini)
        model_view_mini = TimeDistributed(MaxPooling2D(pool_size=(2, 2), strides=None, padding='valid', data_format='channels_first'))(
            model_view_mini)
        """model_view_mini = Conv2D(32, kernel_size=(3, 3), data_format='channels_first', kernel_initializer="he_uniform")(
            model_view_mini)
        model_view_mini = Activation('relu')(model_view_mini)
        model_view_mini = MaxPooling2D(pool_size=(2, 2), strides=None, padding='valid', data_format='channels_first')(
            model_view_mini)"""
        model_view_mini = ConvLSTM2D(filters=32, kernel_size=(3,3), strides=1, activation='relu')(model_view_mini)

        # concatenate
        concat = TimeDistributed(keras.layers.concatenate([model_view_map, model_view_mini]))

        # value estimate and Action policy
        intermediate = TimeDistributed(Flatten())(concat)
        intermediate = TimeDistributed(keras.layers.Dense(256, activation='relu', kernel_initializer="he_uniform"))(intermediate)

        out_value = TimeDistributed(keras.layers.Dense(1))(intermediate)
        out_value = TimeDistributed(Activation('linear', name='value_output'))(out_value)

        out_non_spatial = TimeDistributed(keras.layers.Dense(len(self.categorical_actions) + len(self.spatial_actions),
                                             kernel_initializer="he_uniform",
                                             kernel_regularizer=entropy_reg))(intermediate)
        out_non_spatial = TimeDistributed(Lambda(lambda x: self.expl_rate * x))(out_non_spatial)
        out_non_spatial = TimeDistributed(Activation('softmax', name='non_spatial_output'))(out_non_spatial)

        # spatial policy output
        out_spatial = TimeDistributed(Conv2D(1, kernel_size=(1, 1), data_format='channels_first', kernel_initializer="he_uniform",
                             name='out_spatial'))(concat)
        out_spatial = TimeDistributed(Flatten())(out_spatial)
        out_spatial = TimeDistributed(Dense(4096, activation='softmax', kernel_initializer="he_uniform"))(out_spatial)
        out_spatial = TimeDistributed(Activation('softmax', name='spatial_output'))(out_spatial)

        # compile
        model = keras.models.Model(inputs=[input_map, input_mini], outputs=[out_value, out_non_spatial, out_spatial])
        model.summary()
        losses = {
            "value_output": "mse",
            "non_spatial_output": "categorical_crossentropy",
            "spatial_output": "categorical_crossentropy"
        }

        lossWeights = {"value_output": 1.0, "non_spatial_output": 1.0, "spatial_output": 1.0}
        model.compile(loss=losses, loss_weights=lossWeights, optimizer=RMSprop(lr=0.1))
        self.model = model

    def predict(self, *args, **kwargs):
        """wrapper for keras model predict function"""
        return self.model.predict(*args, **kwargs)

    def fit(self, *args, **kwargs):
        """wrapper for keras model fit function"""
        return self.model.fit(*args, **kwargs)

    def load_weights(self, *args, **kwargs):
        """wrapper for keras model load_weights function"""
        return self.model.load_weights(*args, **kwargs)

    def save_weights(self, *args, **kwargs):
        """wrapper for keras model save_weights function"""
        return self.model.save_weights(*args, **kwargs)