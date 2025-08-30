#!/usr/bin/env python3
"""
Script to manually test evaluation metrics by incrementing them directly
"""
import requests
import time
import random

def test_evaluation_metrics():
    """Test evaluation metrics by incrementing them directly"""
    
    print("Testing evaluation metrics...")
    
    # Test the metrics endpoint
    try:
        response = requests.get("http://localhost:8000/metrics", timeout=10)
        if response.status_code == 200:
            print("✅ API metrics endpoint is accessible")
            
            # Check if evaluation metrics exist
            metrics_text = response.text
            if "evaluation_started_total" in metrics_text:
                print("✅ evaluation_started_total metric exists")
            else:
                print("❌ evaluation_started_total metric not found")
                
            if "evaluation_completed_total" in metrics_text:
                print("✅ evaluation_completed_total metric exists")
            else:
                print("❌ evaluation_completed_total metric not found")
                
        else:
            print(f"❌ API metrics endpoint returned status {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error accessing API metrics: {e}")
    
    # Test Prometheus query
    try:
        response = requests.get("http://localhost:9090/api/v1/query?query=evaluation_started_total", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('data', {}).get('result'):
                print("✅ Prometheus has evaluation metrics data")
                for result in data['data']['result']:
                    print(f"   {result['metric']}: {result['value'][1]}")
            else:
                print("❌ Prometheus has no evaluation metrics data")
        else:
            print(f"❌ Prometheus query failed with status {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error querying Prometheus: {e}")
    
    # Submit a test submission to generate metrics
    print("\nSubmitting test submission to generate evaluation metrics...")
    
    test_script = '''#!/usr/bin/env python3
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
'''
    
    # Write test script to file
    with open('test_script.py', 'w') as f:
        f.write(test_script)
    
    try:
        with open('test_script.py', 'rb') as f:
            files = {'file': ('test_script.py', f, 'text/plain')}
            data = {
                'env_id': 'CartPole-v1',
                'algorithm': 'TestMetrics',
                'name': 'test_metrics_user'
            }
            
            response = requests.post(
                'http://localhost:8000/api/submit',
                files=files,
                data=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Test submission queued: {result['id']}")
                
                # Wait for evaluation to complete
                print("Waiting for evaluation to complete...")
                time.sleep(30)
                
                # Check metrics again
                print("\nChecking metrics after evaluation...")
                response = requests.get("http://localhost:9090/api/v1/query?query=evaluation_started_total", timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('data', {}).get('result'):
                        print("✅ Evaluation metrics now available in Prometheus")
                        for result in data['data']['result']:
                            print(f"   {result['metric']}: {result['value'][1]}")
                    else:
                        print("❌ Still no evaluation metrics in Prometheus")
                        
            else:
                print(f"❌ Test submission failed: {response.status_code}")
                
    except Exception as e:
        print(f"❌ Error submitting test: {e}")

if __name__ == "__main__":
    test_evaluation_metrics()
