#!/bin/bash
# Script to rebuild frontend with updated code

echo "=========================================="
echo "Rebuilding Zoria Frontend"
echo "=========================================="
echo ""

cd /mnt/c/Krishna/projects/zbot/zoria

echo "Stopping frontend..."
docker-compose stop frontend

echo ""
echo "Rebuilding frontend (this may take a few minutes)..."
docker-compose build --no-cache frontend

echo ""
echo "Starting frontend..."
docker-compose up -d frontend

echo ""
echo "Checking frontend logs..."
docker-compose logs frontend --tail=20

echo ""
echo "=========================================="
echo "Frontend rebuild complete!"
echo "=========================================="
echo ""
echo "Frontend should now be available at: http://localhost:3000"
echo "The old tabs and cards have been removed."
echo ""
