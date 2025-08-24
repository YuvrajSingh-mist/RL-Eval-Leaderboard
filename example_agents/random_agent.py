import sys
import json
import logging
import gymnasium as gym

logger = logging.getLogger(__name__)


def run_random_policy(env_id: str, episodes: int = 10, max_steps: int = 500) -> None:
    """Run a random policy for a few episodes and report average reward.

    Works for both discrete and continuous action spaces by sampling from
    env.action_space each step.
    """
    env = gym.make(env_id)
    metrics: list[float] = []

    for _ in range(episodes):
        reset_out = env.reset()
        observation = reset_out[0] if isinstance(reset_out, tuple) else reset_out
        done = False
        episode_reward = 0.0

        for _ in range(max_steps):
            action = env.action_space.sample()
            step_out = env.step(action)
            if len(step_out) >= 5:
                next_obs, reward, terminated, truncated, _info = step_out
                done = bool(terminated or truncated)
            else:
                # Gym pre-0.26 style
                next_obs, reward, done, _info = step_out
            observation = next_obs
            episode_reward += float(reward)
            if done:
                break

        metrics.append(episode_reward)

    env.close()

    result = {
        "score": (sum(metrics) / len(metrics)) if metrics else 0.0,
        "metrics": metrics,
        "episodes": episodes,
    }
    print(json.dumps(result))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing environment ID"}))
        sys.exit(1)
    env_id = sys.argv[1]
    logger.info(f"Running random policy for env_id={env_id}")
    run_random_policy(env_id)


