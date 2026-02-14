#!/bin/bash
# Switch from production to development mode

echo "=========================================="
echo "Switching to Development Mode"
echo "=========================================="
echo ""

cd /mnt/c/Krishna/projects/zbot/zoria

echo "[1] Stopping production frontend..."
docker-compose stop frontend
docker-compose rm -f frontend

echo ""
echo "[2] Starting development frontend (Vite dev server)..."
docker-compose -f docker-compose.yml -f frontend/docker-compose.dev.yml up -d frontend

echo ""
echo "[3] Waiting for Vite to start..."
sleep 5

echo ""
echo "[4] Checking frontend logs..."
docker-compose -f docker-compose.yml -f frontend/docker-compose.dev.yml logs frontend --tail=20

echo ""
echo "=========================================="
echo "Development mode active!"
echo "=========================================="
echo ""
echo "Frontend: http://localhost:3000 (Vite dev server with hot reload)"
echo "Backend:  http://localhost:8001"
echo ""
echo "Now you can edit JS files and see changes instantly!"
echo "View logs: docker-compose -f docker-compose.yml -f frontend/docker-compose.dev.yml logs -f frontend"
echo ""
