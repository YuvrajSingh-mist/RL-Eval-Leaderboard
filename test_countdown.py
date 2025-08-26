#!/usr/bin/env python3
"""
Test script to verify countdown timer logic
"""

from datetime import datetime, timezone, timedelta
import time

def test_countdown_logic():
    """Test the countdown timer calculation logic"""
    
    # Simulate a submission created 2 minutes ago
    created_time = datetime.now(timezone.utc) - timedelta(minutes=2)
    elapsed_seconds = int((datetime.now(timezone.utc) - created_time).total_seconds())
    
    print(f"Submission created: {created_time}")
    print(f"Current time: {datetime.now(timezone.utc)}")
    print(f"Elapsed seconds: {elapsed_seconds}")
    
    # Calculate remaining time (300s timeout)
    remaining_seconds = max(0, 300 - elapsed_seconds)
    minutes = remaining_seconds // 60
    seconds = remaining_seconds % 60
    
    print(f"Remaining time: {minutes:02d}:{seconds:02d}")
    
    # Test different scenarios
    scenarios = [
        ("Just started", 0),
        ("1 minute elapsed", 60),
        ("2 minutes elapsed", 120),
        ("4 minutes elapsed", 240),
        ("5 minutes elapsed", 300),
        ("6 minutes elapsed", 360),
    ]
    
    print("\nTesting different scenarios:")
    for desc, elapsed in scenarios:
        remaining = max(0, 300 - elapsed)
        mins = remaining // 60
        secs = remaining % 60
        status = "🟢 Normal" if remaining > 60 else "🟡 Warning" if remaining > 30 else "🔴 Danger"
        print(f"{desc:20} -> {mins:02d}:{secs:02d} {status}")

if __name__ == "__main__":
    test_countdown_logic()
