#!/bin/bash
# Force rebuild frontend with latest code

echo "=========================================="
echo "Force Rebuilding Zoria Frontend"
echo "=========================================="
echo ""

cd /mnt/c/Krishna/projects/zbot/zoria

echo "[1] Stopping frontend container..."
docker-compose stop frontend

echo ""
echo "[2] Removing old frontend container and image..."
docker-compose rm -f frontend
docker rmi zoria-frontend 2>/dev/null || echo "  (Image already removed or doesn't exist)"

echo ""
echo "[3] Rebuilding frontend (this may take a few minutes)..."
docker-compose build --no-cache --pull frontend

echo ""
echo "[4] Starting frontend..."
docker-compose up -d frontend

echo ""
echo "[5] Waiting for frontend to be ready..."
sleep 3

echo ""
echo "[6] Checking frontend logs..."
docker-compose logs frontend --tail=30

echo ""
echo "=========================================="
echo "Frontend rebuild complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Open http://localhost:3000"
echo "2. Press Ctrl+Shift+R (or Cmd+Shift+R on Mac) to hard refresh"
echo "3. Open browser console (F12) and check for:"
echo "   - Debug box showing tab info"
echo "   - Simple tabs with purple border"
echo "   - TabNavigation component tabs"
echo ""
