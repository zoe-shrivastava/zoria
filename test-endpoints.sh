#!/bin/bash
# Test script for Zoria API endpoints

BASE_URL="http://localhost:8000"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=========================================="
echo "Zoria API Endpoint Tests"
echo "=========================================="
echo ""

# Test 1: Root endpoint
echo -e "${YELLOW}[Test 1] Root Endpoint (GET /)${NC}"
response=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$BASE_URL/")
http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE/d')

if [ "$http_code" = "200" ]; then
    echo -e "${GREEN}✓ Root endpoint working${NC}"
    echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
else
    echo -e "${RED}✗ Root endpoint failed (HTTP $http_code)${NC}"
    echo "Response: $body"
fi
echo ""

# Test 2: Health endpoint
echo -e "${YELLOW}[Test 2] Health Endpoint (GET /health)${NC}"
response=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$BASE_URL/health")
http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE/d')

if [ "$http_code" = "200" ]; then
    echo -e "${GREEN}✓ Health endpoint working${NC}"
    echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
else
    echo -e "${RED}✗ Health endpoint failed (HTTP $http_code)${NC}"
    echo "Response: $body"
fi
echo ""

# Test 3: Login endpoint with GET (should return 405 or 404)
echo -e "${YELLOW}[Test 3] Login Endpoint with GET (should fail)${NC}"
response=$(curl -s -w "\nHTTP_CODE:%{http_code}" "$BASE_URL/api/v1/auth/login")
http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE/d')

if [ "$http_code" = "405" ]; then
    echo -e "${GREEN}✓ GET method correctly rejected (405 Method Not Allowed)${NC}"
    echo "This means the route exists but requires POST"
elif [ "$http_code" = "404" ]; then
    echo -e "${RED}✗ Route not found (404)${NC}"
    echo "Response: $body"
    echo "This means the route is not registered. Check backend logs for import errors."
else
    echo -e "${YELLOW}? Unexpected response (HTTP $http_code)${NC}"
    echo "Response: $body"
fi
echo ""

# Test 4: Login endpoint with POST (should return 401 or 422)
echo -e "${YELLOW}[Test 4] Login Endpoint with POST (should return 401/422)${NC}"
response=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$BASE_URL/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"email":"test@example.com","password":"test"}')
http_code=$(echo "$response" | grep "HTTP_CODE" | cut -d: -f2)
body=$(echo "$response" | sed '/HTTP_CODE/d')

if [ "$http_code" = "401" ]; then
    echo -e "${GREEN}✓ Login endpoint working (401 Unauthorized - expected)${NC}"
    echo "The endpoint exists and is processing requests correctly"
    echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
elif [ "$http_code" = "422" ]; then
    echo -e "${GREEN}✓ Login endpoint working (422 Validation Error - expected)${NC}"
    echo "The endpoint exists and is validating input"
    echo "$body" | python3 -m json.tool 2>/dev/null || echo "$body"
elif [ "$http_code" = "404" ]; then
    echo -e "${RED}✗ Route not found (404)${NC}"
    echo "Response: $body"
    echo ""
    echo "The route is not registered. This usually means:"
    echo "1. Backend container crashed during startup"
    echo "2. Import error in auth.py (check for missing dependencies)"
    echo "3. Router not included in main.py"
    echo ""
    echo "Check backend logs: docker-compose logs backend --tail=50"
else
    echo -e "${YELLOW}? Unexpected response (HTTP $http_code)${NC}"
    echo "Response: $body"
fi
echo ""

# Test 5: Check available routes
echo -e "${YELLOW}[Test 5] Checking API Documentation${NC}"
if curl -s -f "$BASE_URL/docs" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ API docs available at: $BASE_URL/docs${NC}"
    echo "You can view all available endpoints there"
else
    echo -e "${YELLOW}? API docs not accessible${NC}"
fi
echo ""

echo "=========================================="
echo "Summary"
echo "=========================================="
echo ""
echo "If Test 4 returned 404, the backend needs to be rebuilt:"
echo "  cd /mnt/c/Krishna/projects/zbot/zoria"
echo "  docker-compose build --no-cache backend"
echo "  docker-compose up -d backend"
echo ""
