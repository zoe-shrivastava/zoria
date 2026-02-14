#!/bin/bash
# Properly switch to development mode

echo "=========================================="
echo "Switching to Development Mode"
echo "=========================================="
echo ""

cd /mnt/c/Krishna/projects/zbot/zoria

echo "[1] Stopping and removing ALL frontend containers..."
docker-compose stop frontend 2>/dev/null || true
docker-compose rm -f frontend 2>/dev/null || true
docker stop zoria-frontend zoria-frontend-dev 2>/dev/null || true
docker rm zoria-frontend zoria-frontend-dev 2>/dev/null || true

echo ""
echo "[2] Starting ONLY dev frontend (Vite)..."
# Use --no-deps to avoid starting other services if they're already running
docker-compose -f docker-compose.yml -f frontend/docker-compose.dev.yml up -d --no-deps frontend

echo ""
echo "[3] Waiting for Vite to start..."
sleep 8

echo ""
echo "[4] Checking what's running on port 3000..."
docker ps --filter "publish=3000" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "[5] Frontend logs (should show Vite, not nginx):"
echo "=========================================="
docker-compose -f docker-compose.yml -f frontend/docker-compose.dev.yml logs frontend --tail=20

echo ""
echo "=========================================="
echo "Done!"
echo "=========================================="
echo ""
echo "If you see Vite output above, dev mode is active!"
echo "If you see nginx logs, something went wrong."
echo ""
