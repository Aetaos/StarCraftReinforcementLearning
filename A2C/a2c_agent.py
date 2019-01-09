import math
import numpy as np
#from pysc2.agents import base_agent
from pysc2.lib import actions
from pysc2.lib import features
from pysc2.env import sc2_env, run_loop, available_actions_printer
from pysc2 import maps
from absl import flags
#from collections import deque

import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))



class A2CAgent:
    """This class implements the A2C agent using the network model"""

    def __init__(self, model, categorical_actions,spatial_actions, id_from_actions,action_from_id):
        self.states = []
        self.rewards = []
        self.actions = []
        self.points = []
        self.gamma = 0.95  # discount rate
        self.categorical_actions = categorical_actions
        self.spatial_actions = spatial_actions
        self.model = model
        self.epsilon = 0.5
        self.id_from_actions = id_from_actions
        self.action_from_id = action_from_id

    def update_epsilon(self):
        if self.epsilon > 0.05:
            self.epsilon = 0.95 * self.epsilon

    def append_sample(self, state, action, reward,point):
        self.states.append(state)
        self.rewards.append(reward)
        self.actions.append(self.id_from_actions[action])
        self.points.append(point)

    def discount_rewards(self, rewards):
        discounted_rewards = np.zeros_like(rewards)
        running_add = 0
        for t in reversed(range(0, len(rewards))):
            running_add = running_add * self.gamma + rewards[t]
            discounted_rewards[t] = running_add
        return discounted_rewards

    def act(self, state, init=False):
        policy = (self.model.predict(state)[1]).flatten()
        
        if init or np.random.random() < self.epsilon:
            return self.action_from_id[np.random.choice(len(self.action_from_id), 1)[0]],np.random.randint(4096)
        else:
            preds=self.model.predict(state)
            return self.action_from_id[np.random.choice(len(self.action_from_id),1,p=preds[1][0])[0]],preds[2][0].argmax()

    def train(self):
        episode_length = len(self.states)
        discounted_rewards = self.discount_rewards(self.rewards)
        # Standardized discounted rewards
        """discounted_rewards -= np.mean(discounted_rewards) 
        if np.std(discounted_rewards):
            discounted_rewards /= np.std(discounted_rewards)
        else:
            self.states, self.actions, self.rewards = [], [], []
            #print ('std = 0!')
            return 0"""

        update_inputs = [np.zeros((episode_length, 17, 64, 64)),
                         np.zeros((episode_length, 7, 64, 64))]  # Episode_lengthx64x64x4

        # Episode length is like the minibatch size in DQN
        for i in range(episode_length):
            update_inputs[0][i, :, :, :] = self.states[i][0][0, :, :, :]
            update_inputs[1][i, :, :, :] = self.states[i][1][0, :, :, :]
           
        values = self.model.predict(update_inputs)[0]

        advantages_actions = np.zeros((episode_length, len(self.id_from_actions)))
        advantages_space = np.zeros((episode_length, 4096))

        for i in range(episode_length):
            advantages_actions[i][self.actions[i]] = discounted_rewards[i] - values[i]
            advantages_space[i][self.points[i]]= discounted_rewards[i] - values[i]
        self.model.fit(update_inputs, [discounted_rewards, advantages_actions,advantages_space], nb_epoch=1, verbose=0)

        self.states, self.actions, self.rewards = [], [], []

        self.update_epsilon()

    def load(self, name):
        self.model.load_weights(name)

    def save(self, name):
        self.model.save_weights(name)
    def run(self):
        FLAGS = flags.FLAGS
        FLAGS(['run_sc2'])
        viz = False
        save_replay = False
        steps_per_episode = 0 # 0 actually means unlimited
        MAX_EPISODES =100
        MAX_STEPS = 400
        steps = 0

        # create a map
        beacon_map = maps.get('MoveToBeacon')


    #run trajectories and train
    with sc2_env.SC2Env(agent_race=None,
                        bot_race=None,
                        difficulty=None,
                        map_name=beacon_map,
                        visualize=viz, agent_interface_format=sc2_env.AgentInterfaceFormat(
                feature_dimensions=sc2_env.Dimensions(
                    screen=64,
                    minimap=64))) as env:
        # agent.load("./save/move_2_beacon-dqn.h5")
    
        done = False
        # batch_size = 5
    
        for e in range(MAX_EPISODES):
            obs = env.reset()
            score = 0
            state = get_state(obs[0])
            for time in range(MAX_STEPS):
                # env.render()
                init = False
                if e == 0 and time == 0:
                    init = True
                a,point = agent.act(state, init)
                if not a in obs[0].observation.available_actions:
                    a = _NO_OP
                func = get_action(a, point)
                next_obs = env.step([func])
                next_state = get_state(next_obs[0])
                reward = float(next_obs[0].reward)
                score += reward
                done = next_obs[0].last()
                agent.append_sample(state, a, reward,point)
                state = next_state
                obs = next_obs
                if done:
                    print("episode: {}/{}, score: {}"
                          .format(e, MAX_EPISODES, score))
                    break
            agent.train()
            agent.save("./save/move_2_beacon-dqn.h5")