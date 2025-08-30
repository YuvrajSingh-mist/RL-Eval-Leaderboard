#!/usr/bin/env python3
"""
Simple test submission for CartPole-v1 to generate evaluation metrics
"""
import gymnasium as gym
import numpy as np

def main():
    env = gym.make('CartPole-v1', render_mode=None)
    observation, info = env.reset()
    
    total_reward = 0
    for _ in range(1000):
        # Simple random policy
        action = env.action_space.sample()
        observation, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        
        if terminated or truncated:
            break
    
    env.close()
    
    # Print final score in JSON format
    print(f'{{"score": {total_reward}}}')

if __name__ == "__main__":
    main()
