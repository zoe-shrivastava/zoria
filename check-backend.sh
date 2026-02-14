#!/bin/bash
# Quick diagnostic script for Zoria backend

echo "=========================================="
echo "Zoria Backend Diagnostics"
echo "=========================================="
echo ""

# Check container status
echo "[1] Container Status:"
cd /mnt/c/Krishna/projects/zbot/zoria
docker-compose ps backend
echo ""

# Check backend logs
echo "[2] Backend Logs (last 30 lines):"
docker-compose logs backend --tail=30
echo ""

# Test health endpoint
echo "[3] Testing Health Endpoint:"
if curl -s -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "  ✓ Backend is responding"
    curl -s http://localhost:8000/health | python3 -m json.tool 2>/dev/null || curl -s http://localhost:8000/health
else
    echo "  ✗ Backend is NOT responding"
    echo "  Error: Backend container may have crashed"
fi
echo ""

# Test root endpoint
echo "[4] Testing Root Endpoint:"
if curl -s -f http://localhost:8000/ > /dev/null 2>&1; then
    echo "  ✓ Root endpoint working"
    curl -s http://localhost:8000/ | python3 -m json.tool 2>/dev/null || curl -s http://localhost:8000/
else
    echo "  ✗ Root endpoint failed"
fi
echo ""

# Check for common errors
echo "[5] Recent Errors:"
docker-compose logs backend --tail=100 | grep -i "error\|exception\|traceback\|failed\|not found" | tail -10 || echo "  No recent errors found"
echo ""

echo "=========================================="
echo "Recommendations:"
echo "=========================================="
echo ""
echo "If backend is not running or showing errors:"
echo "1. Rebuild backend container:"
echo "   cd /mnt/c/Krishna/projects/zbot/zoria"
echo "   docker-compose build --no-cache backend"
echo ""
echo "2. Restart backend:"
echo "   docker-compose up -d backend"
echo ""
echo "3. Check logs again:"
echo "   docker-compose logs backend --tail=50"
echo ""
