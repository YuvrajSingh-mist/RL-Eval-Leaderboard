#!/bin/bash
# Complete visitor metrics automation setup script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Setting up complete visitor metrics automation...${NC}"

# Get the current directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo -e "${YELLOW}📁 Project directory: $PROJECT_DIR${NC}"

# Make all scripts executable
echo -e "${YELLOW}🔧 Making scripts executable...${NC}"
chmod +x "$SCRIPT_DIR"/*.sh
chmod +x "$SCRIPT_DIR"/*.py

# Test all scripts
echo -e "${YELLOW}🧪 Testing all automation scripts...${NC}"

echo -e "${BLUE}Testing visitor metrics refresh...${NC}"
if python "$SCRIPT_DIR/refresh_visitor_metrics.py"; then
    echo -e "${GREEN}✅ Refresh script working${NC}"
else
    echo -e "${RED}❌ Refresh script failed${NC}"
    exit 1
fi

echo -e "${BLUE}Testing automation script...${NC}"
if "$SCRIPT_DIR/automate_visitor_metrics.sh"; then
    echo -e "${GREEN}✅ Automation script working${NC}"
else
    echo -e "${RED}❌ Automation script failed${NC}"
    exit 1
fi

echo -e "${BLUE}Testing monitoring script...${NC}"
if "$SCRIPT_DIR/monitor_visitor_metrics.sh"; then
    echo -e "${GREEN}✅ Monitoring script working${NC}"
else
    echo -e "${RED}❌ Monitoring script failed${NC}"
    exit 1
fi

# Setup cron job
echo -e "${YELLOW}📅 Setting up cron job for automatic refresh...${NC}"

# Create a temporary file for the cron job
TEMP_CRON=$(mktemp)

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "monitor_visitor_metrics.sh"; then
    echo -e "${YELLOW}⚠️  Cron job already exists. Removing old entry...${NC}"
    crontab -l 2>/dev/null | grep -v "monitor_visitor_metrics.sh" > "$TEMP_CRON"
fi

# Add the new cron job (every 2 minutes)
echo "*/2 * * * * cd $PROJECT_DIR && $SCRIPT_DIR/monitor_visitor_metrics.sh >> /tmp/visitor_automation.log 2>&1" >> "$TEMP_CRON"

# Install the new cron job
crontab "$TEMP_CRON"

# Clean up
rm "$TEMP_CRON"

echo -e "${GREEN}✅ Cron job installed successfully!${NC}"
echo -e "${GREEN}📅 Visitor metrics will be monitored every 2 minutes${NC}"
echo -e "${GREEN}📝 Logs will be written to /tmp/visitor_automation.log${NC}"

# Show current cron jobs
echo -e "${YELLOW}📋 Current cron jobs:${NC}"
crontab -l 2>/dev/null | grep -E "(visitor|monitor)" || echo "No visitor-related cron jobs found"

# Create a status script
echo -e "${YELLOW}📝 Creating status script...${NC}"

cat > "$SCRIPT_DIR/visitor_status.sh" << 'EOF'
#!/bin/bash
# Quick status check for visitor metrics

echo "🔍 Visitor Metrics Status"
echo "========================"
echo ""

# Check current counts
echo "📊 Current Counts:"
ALLTIME=$(curl -s http://localhost:8000/metrics | grep "unique_visitors_alltime" | grep -o '[0-9]\+\.0' | head -1)
TODAY=$(curl -s http://localhost:8000/metrics | grep "unique_visitors_today" | grep -o '[0-9]\+\.0' | head -1)
API_REQUESTS=$(curl -s "http://localhost:9090/api/v1/query?query=sum(http_request_size_bytes_count)" | jq -r '.data.result[0].value[1] // "0"')

echo "   All-time visitors: $ALLTIME"
echo "   Today's visitors: $TODAY"
echo "   Total API requests: $API_REQUESTS"
echo ""

# Check services
echo "🔧 Service Status:"
if curl -s http://localhost:8000/health > /dev/null; then
    echo "   ✅ API: Running"
else
    echo "   ❌ API: Down"
fi

if curl -s http://localhost:9090/-/healthy > /dev/null; then
    echo "   ✅ Prometheus: Running"
else
    echo "   ❌ Prometheus: Down"
fi

if curl -s http://localhost:3000/api/health > /dev/null; then
    echo "   ✅ Grafana: Running"
else
    echo "   ❌ Grafana: Down"
fi

echo ""
echo "📅 Last cron run:"
if [ -f /tmp/visitor_automation.log ]; then
    tail -1 /tmp/visitor_automation.log
else
    echo "   No log file found"
fi
EOF

chmod +x "$SCRIPT_DIR/visitor_status.sh"

echo -e "${GREEN}✅ Status script created: $SCRIPT_DIR/visitor_status.sh${NC}"

# Final test
echo -e "${YELLOW}🎯 Running final comprehensive test...${NC}"
if "$SCRIPT_DIR/monitor_visitor_metrics.sh"; then
    echo -e "${GREEN}✅ All systems operational!${NC}"
else
    echo -e "${RED}❌ Some issues detected${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}🎉 Visitor metrics automation setup completed!${NC}"
echo ""
echo -e "${BLUE}📋 Available commands:${NC}"
echo -e "   ${YELLOW}./scripts/visitor_status.sh${NC}     - Quick status check"
echo -e "   ${YELLOW}./scripts/monitor_visitor_metrics.sh${NC} - Comprehensive monitoring"
echo -e "   ${YELLOW}./scripts/automate_visitor_metrics.sh${NC} - Manual refresh"
echo -e "   ${YELLOW}crontab -l${NC}                    - View cron jobs"
echo -e "   ${YELLOW}tail -f /tmp/visitor_automation.log${NC} - Monitor logs"
echo ""
echo -e "${BLUE}🌐 Access URLs:${NC}"
echo -e "   ${YELLOW}Grafana Dashboard:${NC} http://localhost:3000"
echo -e "   ${YELLOW}Prometheus:${NC} http://localhost:9090"
echo -e "   ${YELLOW}API Metrics:${NC} http://localhost:8000/metrics"
