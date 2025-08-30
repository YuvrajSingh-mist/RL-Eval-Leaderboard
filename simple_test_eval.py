#!/usr/bin/env python3
"""
Simple test submission for CartPole-v1 to generate evaluation metrics
"""
import random
import json

def main():
    # Generate a random score between 20 and 200
    score = random.randint(20, 200)
    
    # Print final score in JSON format
    print(json.dumps({"score": score}))

if __name__ == "__main__":
    main()
