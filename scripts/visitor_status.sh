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
