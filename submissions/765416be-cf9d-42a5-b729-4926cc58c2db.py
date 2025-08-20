
import gym
import numpy as np
import sys
import json

def train_dqn(env_id, episodes=50):
    env = gym.make(env_id)
    
    # For discrete action spaces only
    if not hasattr(env.action_space, 'n'):
        print(json.dumps({"error": "Environment must have discrete action space"}))
        return
    
    # Initialize Q-table
    state_size = env.observation_space.n if hasattr(env.observation_space, 'n') else 100
    q_table = np.zeros([state_size, env.action_space.n])
    
    # Hyperparameters
    alpha = 0.1
    gamma = 0.6
    epsilon = 0.1
    
    # Training
    metrics = []
    for i in range(episodes):
        state = env.reset()
        if isinstance(state, tuple):
            state = state[0]
            
        done = False
        total_reward = 0
        
        while not done:
            # Epsilon-greedy action selection
            if np.random.uniform(0, 1) < epsilon:
                action = env.action_space.sample()
            else:
                action = np.argmax(q_table[state])
            
            # Take action
            result = env.step(action)
            next_state, reward, done, info = result[0], result[1], result[2], result[3:]
            if isinstance(next_state, tuple):
                next_state = next_state[0]
                
            total_reward += reward
            
            # Update Q-table
            old_value = q_table[state, action]
            next_max = np.max(q_table[next_state])
            new_value = (1 - alpha) * old_value + alpha * (reward + gamma * next_max)
            q_table[state, action] = new_value
            
            state = next_state
        
        metrics.append(total_reward)
    
    env.close()
    
    # Return results in structured format
    result = {
        "score": float(np.mean(metrics[-10:])),
        "metrics": metrics,
        "episodes": episodes
    }
    print(json.dumps(result))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing environment ID"}))
        sys.exit(1)
        
    env_id = sys.argv[1]
    train_dqn(env_id)
