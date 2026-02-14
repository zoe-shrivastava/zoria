#!/bin/bash
# Start development mode - ensures only dev frontend runs

echo "=========================================="
echo "Starting Development Mode"
echo "=========================================="
echo ""

cd /mnt/c/Krishna/projects/zbot/zoria

echo "[1] Stopping ALL containers..."
docker-compose down 2>/dev/null || true

echo ""
echo "[2] Force removing any remaining frontend containers..."
docker stop zoria-frontend zoria-frontend-dev 2>/dev/null || true
docker rm zoria-frontend zoria-frontend-dev 2>/dev/null || true

echo ""
echo "[3] Starting backend and postgres..."
docker-compose up -d postgres backend

echo ""
echo "[4] Waiting for backend to be ready..."
sleep 5

echo ""
echo "[5] Starting dev frontend (Vite) with override..."
docker-compose -f docker-compose.yml -f frontend/docker-compose.dev.yml up -d frontend

echo ""
echo "[6] Waiting for Vite to start..."
sleep 8

echo ""
echo "[7] Checking containers..."
docker ps --filter "name=frontend" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "[8] Frontend logs:"
echo "=========================================="
docker-compose -f docker-compose.yml -f frontend/docker-compose.dev.yml logs frontend --tail=30

echo ""
echo "=========================================="
echo "Development mode should be active!"
echo "=========================================="
echo ""
echo "Frontend: http://localhost:3000 (Vite dev server)"
echo "Backend:  http://localhost:8001"
echo ""
echo "Edit JS files and see changes instantly!"
echo ""
