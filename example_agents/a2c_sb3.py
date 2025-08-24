import sys
import json
import logging
import gymnasium as gym
import numpy as np

from stable_baselines3 import A2C  # type: ignore

logger = logging.getLogger(__name__)


def run_a2c(env_id: str, timesteps: int = 10_000) -> None:
    env = gym.make(env_id)
    model = A2C("MlpPolicy", env, verbose=0)
    model.learn(total_timesteps=timesteps)

    metrics: list[float] = []
    for _ in range(10):
        obs, _ = env.reset()
        done = False
        ep_ret = 0.0
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, _ = env.step(action)
            done = bool(terminated or truncated)
            ep_ret += float(reward)
        metrics.append(ep_ret)
    env.close()

    result = {"score": float(np.mean(metrics)) if metrics else 0.0, "metrics": metrics, "episodes": len(metrics)}
    print(json.dumps(result))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing environment ID"}))
        sys.exit(1)
    env_id = sys.argv[1]
    logger.info(f"Training A2C (SB3) for env_id={env_id}")
    run_a2c(env_id)


