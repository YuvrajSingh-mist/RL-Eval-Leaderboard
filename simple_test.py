#!/usr/bin/env python3
import gymnasium as gym
import random

env = gym.make('CartPole-v1', render_mode=None)
observation, info = env.reset()

total_reward = 0
for _ in range(1000):
    action = random.choice([0, 1])  # Random actions
    observation, reward, terminated, truncated, info = env.step(action)
    total_reward += reward
    
    if terminated or truncated:
        break

env.close()
print(f'{{"score": {total_reward}}}')
