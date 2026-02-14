#!/bin/bash
# Script to diagnose and fix port 8000 conflict

echo "=========================================="
echo "Port 8000 Conflict Diagnosis"
echo "=========================================="
echo ""

# Check what's running on port 8000
echo "[1] Checking what's using port 8000:"
if command -v lsof &> /dev/null; then
    lsof -i :8000 2>/dev/null || echo "  No process found with lsof"
elif command -v netstat &> /dev/null; then
    netstat -tulpn 2>/dev/null | grep :8000 || echo "  No process found with netstat"
elif command -v ss &> /dev/null; then
    ss -tulpn 2>/dev/null | grep :8000 || echo "  No process found with ss"
else
    echo "  Cannot check port (install lsof, netstat, or ss)"
fi
echo ""

# Check for marker_service
echo "[2] Checking for PDF Parsing Service (marker_service):"
if [ -d "/mnt/c/Krishna/projects/zbot/marker_service" ]; then
    PID_FILE="/mnt/c/Krishna/projects/zbot/marker_service/logs/service.pid"
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE" 2>/dev/null)
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "  ⚠️  PDF Parsing Service is RUNNING (PID: $PID)"
            echo "  This service also uses port 8000!"
            echo ""
            echo "  To stop it:"
            echo "    cd /mnt/c/Krishna/projects/zbot/marker_service"
            echo "    ./stop.sh"
        else
            echo "  ✓ PDF Parsing Service is not running (stale PID file)"
        fi
    else
        echo "  ✓ PDF Parsing Service is not running"
    fi
else
    echo "  ✓ marker_service directory not found"
fi
echo ""

# Check Docker container
echo "[3] Checking Zoria backend container:"
cd /mnt/c/Krishna/projects/zbot/zoria
docker-compose ps backend 2>/dev/null || echo "  Cannot check Docker (permission issue)"
echo ""

# Test endpoints
echo "[4] Testing endpoints:"
echo "  Testing http://localhost:8000/ ..."
ROOT_RESPONSE=$(curl -s http://localhost:8000/ 2>/dev/null)
if echo "$ROOT_RESPONSE" | grep -q "PDF Parsing Service\|Zoria API"; then
    if echo "$ROOT_RESPONSE" | grep -q "PDF Parsing Service"; then
        echo "  ⚠️  Port 8000 is serving PDF Parsing Service (not Zoria)"
    else
        echo "  ✓ Port 8000 is serving Zoria API"
    fi
else
    echo "  ? Unknown service on port 8000"
    echo "  Response: $ROOT_RESPONSE"
fi
echo ""

echo "=========================================="
echo "Solutions"
echo "=========================================="
echo ""
echo "Option 1: Stop PDF Parsing Service (if running)"
echo "  cd /mnt/c/Krishna/projects/zbot/marker_service"
echo "  ./stop.sh"
echo ""
echo "Option 2: Change Zoria backend port"
echo "  Edit docker-compose.yml and change:"
echo "    ports:"
echo "      - \"8001:8000\"  # Use 8001 instead of 8000"
echo "  Then update frontend API base URL to http://localhost:8001"
echo ""
echo "Option 3: Change PDF Parsing Service port"
echo "  Edit marker_service/start.sh and change --port 8000 to --port 8001"
echo ""
