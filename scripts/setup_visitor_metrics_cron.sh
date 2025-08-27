#!/bin/bash
# Setup cron job for automatic visitor metrics refresh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🔄 Setting up automatic visitor metrics refresh...${NC}"

# Get the current directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
AUTOMATION_SCRIPT="$SCRIPT_DIR/automate_visitor_metrics.sh"

# Make sure the automation script is executable
chmod +x "$AUTOMATION_SCRIPT"

# Create a temporary file for the cron job
TEMP_CRON=$(mktemp)

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "automate_visitor_metrics.sh"; then
    echo -e "${YELLOW}⚠️  Cron job already exists. Removing old entry...${NC}"
    crontab -l 2>/dev/null | grep -v "automate_visitor_metrics.sh" > "$TEMP_CRON"
fi

# Add the new cron job (every 5 minutes)
echo "*/5 * * * * cd $PROJECT_DIR && $AUTOMATION_SCRIPT >> /tmp/visitor_metrics.log 2>&1" >> "$TEMP_CRON"

# Install the new cron job
crontab "$TEMP_CRON"

# Clean up
rm "$TEMP_CRON"

echo -e "${GREEN}✅ Cron job installed successfully!${NC}"
echo -e "${GREEN}📅 Visitor metrics will be refreshed every 5 minutes${NC}"
echo -e "${GREEN}📝 Logs will be written to /tmp/visitor_metrics.log${NC}"

# Show current cron jobs
echo -e "${YELLOW}📋 Current cron jobs:${NC}"
crontab -l 2>/dev/null | grep -E "(visitor|automate)" || echo "No visitor-related cron jobs found"

# Test the automation script
echo -e "${YELLOW}🧪 Testing automation script...${NC}"
if "$AUTOMATION_SCRIPT"; then
    echo -e "${GREEN}✅ Automation script test successful!${NC}"
else
    echo -e "${RED}❌ Automation script test failed!${NC}"
    exit 1
fi

echo -e "${GREEN}🎉 Visitor metrics automation setup completed!${NC}"
