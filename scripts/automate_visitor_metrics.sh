#!/bin/bash
# Automation script for visitor metrics refresh.
# This script can be run manually or as a cron job to ensure visitor metrics are always up to date.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🔄 Refreshing visitor metrics...${NC}"

# Run the Python script to refresh metrics
if python scripts/refresh_visitor_metrics.py; then
    echo -e "${GREEN}✅ Visitor metrics refreshed successfully${NC}"
    
    # Check if metrics are exposed
    if curl -s http://localhost:8000/metrics | grep -q "unique_visitors_alltime"; then
        echo -e "${GREEN}✅ Visitor metrics are exposed on /metrics endpoint${NC}"
        
        # Get the current count
        COUNT=$(curl -s http://localhost:8000/metrics | grep "unique_visitors_alltime" | grep -o '[0-9]\+\.0' | head -1)
        echo -e "${GREEN}📊 Current all-time unique visitors: ${COUNT}${NC}"
    else
        echo -e "${RED}❌ Visitor metrics not found on /metrics endpoint${NC}"
        exit 1
    fi
else
    echo -e "${RED}❌ Failed to refresh visitor metrics${NC}"
    exit 1
fi

echo -e "${GREEN}🎉 Visitor metrics automation completed successfully!${NC}"
