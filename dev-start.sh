#!/bin/bash
# Start development environment with hot reload

echo "=========================================="
echo "Starting Zoria Development Environment"
echo "=========================================="
echo ""

cd /mnt/c/Krishna/projects/zbot/zoria

echo "Stopping production frontend (if running)..."
docker-compose stop frontend 2>/dev/null || echo "  (No production frontend running)"
docker-compose rm -f frontend 2>/dev/null || echo "  (No production frontend to remove)"

echo ""
echo "Starting services with hot reload..."
echo "  - Backend: http://localhost:8001 (auto-reload on Python changes)"
echo "  - Frontend: http://localhost:3000 (hot reload on JS changes)"
echo ""

# Use the existing frontend dev override
docker-compose -f docker-compose.yml -f frontend/docker-compose.dev.yml up -d

echo ""
echo "Waiting for services to start..."
sleep 3

echo ""
echo "View logs with:"
echo "  docker-compose -f docker-compose.yml -f frontend/docker-compose.dev.yml logs -f frontend"

echo ""
echo "Services started!"
echo ""
echo "To view logs:"
echo "  docker-compose -f docker-compose.yml -f frontend/docker-compose.dev.yml logs -f"
echo ""
echo "To stop:"
echo "  docker-compose -f docker-compose.yml -f frontend/docker-compose.dev.yml down"
echo ""
