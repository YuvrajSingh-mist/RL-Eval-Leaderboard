import sys
import json
import logging
import numpy as np
import gymnasium as gym
import torch
import torch.nn as nn
import torch.optim as optim

logger = logging.getLogger(__name__)


class QNet(nn.Module):
    def __init__(self, obs_size: int, n_actions: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(obs_size, 64), nn.ReLU(),
            nn.Linear(64, 64), nn.ReLU(),
            nn.Linear(64, n_actions)
        )

    def forward(self, x):
        return self.net(x)


def dqn_train(env_id: str, episodes: int = 40, max_steps: int = 200) -> None:
    env = gym.make(env_id)
    # Flattened obs for classic control like CartPole/MountainCar
    sample = env.reset()[0] if isinstance(env.reset(), tuple) else env.reset()
    obs_size = int(np.array(sample).size)
    if not hasattr(env.action_space, 'n'):
        print(json.dumps({"error": "DQN example supports discrete actions"}))
        return
    n_actions = int(env.action_space.n)

    q = QNet(obs_size, n_actions)
    tgt = QNet(obs_size, n_actions)
    tgt.load_state_dict(q.state_dict())
    opt = optim.Adam(q.parameters(), lr=1e-3)
    gamma = 0.99
    epsilon, eps_min, eps_decay = 1.0, 0.05, 0.97

    from collections import deque
    buf = deque(maxlen=5000)

    def to_tensor(obs):
        x = np.array(obs, dtype=np.float32).reshape(1, -1)
        return torch.from_numpy(x)

    metrics: list[float] = []
    step_count = 0
    for ep in range(episodes):
        r0 = env.reset()
        obs = r0[0] if isinstance(r0, tuple) else r0
        ep_ret = 0.0
        for _ in range(max_steps):
            step_count += 1
            if np.random.rand() < epsilon:
                act = env.action_space.sample()
            else:
                with torch.no_grad():
                    act = int(torch.argmax(q(to_tensor(obs))).item())
            step_out = env.step(act)
            if len(step_out) >= 5:
                next_obs, rew, terminated, truncated, _info = step_out
                done = bool(terminated or truncated)
            else:
                next_obs, rew, done, _info = step_out
            buf.append((obs, act, rew, next_obs, done))
            ep_ret += float(rew)
            obs = next_obs

            if len(buf) >= 512:
                import random
                batch = random.sample(buf, 64)
                ob, ac, rw, nb, dn = zip(*batch)
                ob_t = torch.from_numpy(np.array(ob, dtype=np.float32))
                nb_t = torch.from_numpy(np.array(nb, dtype=np.float32))
                ac_t = torch.tensor(ac, dtype=torch.long).view(-1, 1)
                rw_t = torch.tensor(rw, dtype=torch.float32).view(-1, 1)
                dn_t = torch.tensor(dn, dtype=torch.float32).view(-1, 1)

                q_pred = q(ob_t).gather(1, ac_t)
                with torch.no_grad():
                    q_next = tgt(nb_t).max(1, keepdim=True)[0]
                    target = rw_t + (1.0 - dn_t) * gamma * q_next
                loss = nn.functional.smooth_l1_loss(q_pred, target)
                opt.zero_grad(); loss.backward(); opt.step()

            if step_count % 200 == 0:
                tgt.load_state_dict(q.state_dict())

            if done:
                break

        epsilon = max(eps_min, epsilon * eps_decay)
        metrics.append(ep_ret)

    env.close()
    result = {"score": float(np.mean(metrics)) if metrics else 0.0, "metrics": metrics, "episodes": episodes}
    print(json.dumps(result))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing environment ID"}))
        sys.exit(1)
    env_id = sys.argv[1]
    logger.info(f"Training minimal DQN for env_id={env_id}")
    dqn_train(env_id)


