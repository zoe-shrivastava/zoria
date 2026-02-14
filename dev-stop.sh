#!/bin/bash
# Stop development environment

echo "=========================================="
echo "Stopping Zoria Development Environment"
echo "=========================================="
echo ""

cd /mnt/c/Krishna/projects/zbot/zoria

docker-compose -f docker-compose.yml -f frontend/docker-compose.dev.yml down

echo ""
echo "Development environment stopped."
echo ""
echo "To start production environment:"
echo "  docker-compose up -d"
echo ""
