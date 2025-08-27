#!/usr/bin/env python3
"""
Script to refresh visitor metrics manually using Docker.
This can be used for testing or as a backup to the automatic refresh.
"""

import subprocess
import sys

def refresh_visitor_metrics():
    """Refresh visitor metrics using docker exec"""
    try:
        result = subprocess.run([
            'docker', 'exec', 'rl-eval-leaderboard-api-1', 
            'python', '-c', 
            'from app.api import visitor; visitor.refresh_unique_visitor_metrics(); print("Visitor metrics refreshed")'
        ], capture_output=True, text=True, check=True)
        print("✅ Visitor metrics refreshed successfully")
        print(result.stdout.strip())
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to refresh visitor metrics: {e}")
        print(f"Error output: {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = refresh_visitor_metrics()
    sys.exit(0 if success else 1)
