#!/usr/bin/env python3
"""
Script to manually generate test evaluation metrics for testing the Grafana dashboard
"""
import requests
import time
import random
from datetime import datetime, timedelta

def generate_test_metrics():
    """Generate test evaluation metrics by making API calls"""
    
    print("Generating test evaluation metrics...")
    
    # Test script that will be submitted multiple times
    test_script = '''#!/usr/bin/env python3
import gymnasium as gym
import random
import time

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
'''
    
    # Write test script to file
    with open('test_script.py', 'w') as f:
        f.write(test_script)
    
    # Submit multiple test submissions to generate metrics
    submissions = []
    
    for i in range(5):
        try:
            with open('test_script.py', 'rb') as f:
                files = {'file': ('test_script.py', f, 'text/plain')}
                data = {
                    'env_id': 'CartPole-v1',
                    'algorithm': f'TestMetrics{i}',
                    'name': f'test_user_{i}'
                }
                
                response = requests.post(
                    'http://localhost:8000/api/submit',
                    files=files,
                    data=data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    submission_id = result['id']
                    submissions.append(submission_id)
                    print(f"✅ Submitted test {i+1}: {submission_id}")
                else:
                    print(f"❌ Failed to submit test {i+1}: {response.status_code}")
                    
        except Exception as e:
            print(f"❌ Error submitting test {i+1}: {e}")
        
        # Wait a bit between submissions
        time.sleep(2)
    
    print(f"\nSubmitted {len(submissions)} test submissions")
    print("Waiting for evaluations to complete...")
    
    # Wait for evaluations to complete
    time.sleep(60)
    
    # Check metrics
    print("\nChecking evaluation metrics...")
    
    try:
        response = requests.get("http://localhost:9090/api/v1/query?query=evaluation_started_total", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('data', {}).get('result'):
                print("✅ Evaluation metrics available in Prometheus:")
                for result in data['data']['result']:
                    print(f"   {result['metric']}: {result['value'][1]}")
            else:
                print("❌ No evaluation metrics in Prometheus")
        else:
            print(f"❌ Prometheus query failed: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error querying Prometheus: {e}")
    
    # Check completed metrics
    try:
        response = requests.get("http://localhost:9090/api/v1/query?query=evaluation_completed_total", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('data', {}).get('result'):
                print("✅ Evaluation completed metrics:")
                for result in data['data']['result']:
                    print(f"   {result['metric']}: {result['value'][1]}")
            else:
                print("❌ No evaluation completed metrics")
        else:
            print(f"❌ Prometheus query failed: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error querying Prometheus: {e}")
    
    # Check failed metrics
    try:
        response = requests.get("http://localhost:9090/api/v1/query?query=evaluation_failed_total", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('data', {}).get('result'):
                print("✅ Evaluation failed metrics:")
                for result in data['data']['result']:
                    print(f"   {result['metric']}: {result['value'][1]}")
            else:
                print("❌ No evaluation failed metrics")
        else:
            print(f"❌ Prometheus query failed: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error querying Prometheus: {e}")

if __name__ == "__main__":
    generate_test_metrics()
