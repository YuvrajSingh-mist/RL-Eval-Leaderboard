import sys
import json
import logging
import numpy as np
import gymnasium as gym

logger = logging.getLogger(__name__)


def run_sarsa(env_id: str, episodes: int = 400, max_steps: int = 200) -> None:
    env_kwargs = {}
    if str(env_id).startswith("FrozenLake"):
        env_kwargs["is_slippery"] = False
    env = gym.make(env_id, **env_kwargs)

    if not hasattr(env.action_space, "n") or not hasattr(env.observation_space, "n"):
        print(json.dumps({"error": "SARSA example supports discrete observation and action spaces"}))
        return

    n_obs = int(env.observation_space.n)
    n_act = int(env.action_space.n)
    Q = np.zeros((n_obs, n_act), dtype=np.float32)

    alpha = 0.1
    gamma = 0.99
    epsilon = 1.0
    epsilon_min = 0.05
    epsilon_decay = 0.995

    metrics: list[float] = []
    for _ in range(episodes):
        s0 = env.reset()
        s = s0[0] if isinstance(s0, tuple) else s0
        s = int(s)
        # Choose initial action
        if np.random.rand() < epsilon:
            a = env.action_space.sample()
        else:
            a = int(np.argmax(Q[s]))

        ep_ret = 0.0
        for _ in range(max_steps):
            step_out = env.step(a)
            if len(step_out) >= 5:
                s_next, r, terminated, truncated, _info = step_out
                done = bool(terminated or truncated)
            else:
                s_next, r, done, _info = step_out
            s_next = int(s_next if not isinstance(s_next, tuple) else s_next[0])
            ep_ret += float(r)

            # Next action (epsilon greedy)
            if np.random.rand() < epsilon:
                a_next = env.action_space.sample()
            else:
                a_next = int(np.argmax(Q[s_next]))

            # SARSA update
            td_target = float(r) + gamma * Q[s_next, a_next] * (0.0 if done else 1.0)
            Q[s, a] += alpha * (td_target - Q[s, a])

            s, a = s_next, a_next
            if done:
                break

        epsilon = max(epsilon_min, epsilon * epsilon_decay)
        metrics.append(ep_ret)

    env.close()
    result = {
        "score": float(np.mean(metrics)) if metrics else 0.0,
        "metrics": metrics,
        "episodes": episodes,
    }
    print(json.dumps(result))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing environment ID"}))
        sys.exit(1)
    env_id = sys.argv[1]
    logger.info(f"Running SARSA for env_id={env_id}")
    run_sarsa(env_id)


