#!/bin/bash
# Force switch to development mode

echo "=========================================="
echo "Force Switching to Development Mode"
echo "=========================================="
echo ""

cd /mnt/c/Krishna/projects/zbot/zoria

echo "[1] Stopping ALL frontend containers..."
docker stop zoria-frontend zoria-frontend-dev 2>/dev/null || true
docker rm zoria-frontend zoria-frontend-dev 2>/dev/null || true

echo ""
echo "[2] Stopping via docker-compose..."
docker-compose stop frontend 2>/dev/null || true
docker-compose rm -f frontend 2>/dev/null || true

echo ""
echo "[3] Starting development frontend (Vite dev server)..."
docker-compose -f docker-compose.yml -f frontend/docker-compose.dev.yml up -d frontend

echo ""
echo "[4] Waiting for Vite to start (10 seconds)..."
sleep 10

echo ""
echo "[5] Checking container status..."
docker ps | grep frontend || echo "  No frontend containers found"

echo ""
echo "[6] Checking frontend logs..."
echo "=========================================="
docker-compose -f docker-compose.yml -f frontend/docker-compose.dev.yml logs frontend --tail=30

echo ""
echo "=========================================="
echo "Check the logs above!"
echo "=========================================="
echo ""
echo "You should see Vite dev server output like:"
echo "  VITE v5.x.x  ready in xxx ms"
echo ""
echo "If you see nginx logs, the switch didn't work."
echo "Try: docker-compose -f docker-compose.yml -f frontend/docker-compose.dev.yml down"
echo "Then: docker-compose -f docker-compose.yml -f frontend/docker-compose.dev.yml up -d"
echo ""
