
import gymnasium as gym
import numpy as np
import sys
import json
import logging

logger = logging.getLogger(__name__)

def train_dqn(env_id=None, episodes=200, max_steps=100):
    # For FrozenLake, use deterministic dynamics for faster convergence
    env_kwargs = {}
    if str(env_id).startswith("FrozenLake"):
        env_kwargs["is_slippery"] = False
    env = gym.make(env_id, **env_kwargs)
    
    # For discrete action spaces only
    if not hasattr(env.action_space, 'n'):
        print(json.dumps({"error": "Environment must have discrete action space"}))
        return
    
    # Initialize Q-table
    state_size = int(env.observation_space.n)
    q_table = np.zeros([state_size, env.action_space.n])
    
    # Hyperparameters
    alpha = 0.1
    gamma = 0.95
    epsilon = 1.0
    min_epsilon = 0.05
    decay = 0.995
    logger.info(f"state_size={state_size} action_space={env.action_space.n} is_slippery={env_kwargs.get('is_slippery', 'default')}")
    # Training
    metrics = []
    for i in range(episodes):
        state = env.reset()
        if isinstance(state, tuple):
            state = state[0]
        state = int(state)

        done = False
        total_reward = 0

        for t in range(max_steps):
            # Epsilon-greedy action selection
            if np.random.uniform(0, 1) < epsilon:
                action = env.action_space.sample()
            else:
                action = np.argmax(q_table[state])
            
            # Take action (Gym 0.26+: obs, reward, terminated, truncated, info)
            step_out = env.step(action)
            next_state, reward, terminated, truncated, info = step_out[0], step_out[1], step_out[2], step_out[3], step_out[4] if len(step_out) > 4 else ({})
            done = bool(terminated or truncated)
            if isinstance(next_state, tuple):
                next_state = next_state[0]
            next_state = int(next_state)

            total_reward += reward
            
            # Update Q-table
            old_value = q_table[state, action]
            next_max = np.max(q_table[next_state])
            new_value = (1 - alpha) * old_value + alpha * (reward + gamma * next_max)
            q_table[state, action] = new_value
            
            state = next_state
            if done:
                break

        epsilon = max(min_epsilon, epsilon * decay)
        logger.info(f"episode={i} reward={total_reward:.2f} epsilon={epsilon:.3f}")
        metrics.append(total_reward)
    
    env.close()
    
    # Return results in structured format
    result = {
        "score": float(np.mean(metrics)),
        "metrics": metrics,
        "episodes": episodes
    }
    # print("Hi")
    print(json.dumps(result))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing environment ID"}))
        sys.exit(1)
        
    env_id = sys.argv[1]
    logger.info(f"Training DQN for env_id: {env_id}")
    train_dqn(env_id)
