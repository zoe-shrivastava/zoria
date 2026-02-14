# Troubleshooting Child Login "Failed to fetch" Error

## Quick Checks

### 1. Verify Backend is Running

```bash
# Check if containers are running
cd /mnt/c/Krishna/projects/zbot/zoria
docker-compose ps

# Check backend logs
docker-compose logs backend | tail -20

# Check if backend is accessible
curl http://localhost:8001/health
```

### 2. Verify Backend Health

The backend should return:
```json
{
  "status": "healthy",
  "database": "connected"
}
```

### 3. Test Child Login Endpoint Directly

```bash
# Test the child login endpoint
curl -X POST http://localhost:8001/api/v1/auth/child/login \
  -H "Content-Type: application/json" \
  -d '{"child_id": "YOUR_CHILD_ID", "pin": "YOUR_PIN"}'
```

### 4. Check Browser Console

Open browser DevTools (F12) and check:
- **Console tab**: Look for detailed error messages
- **Network tab**: Check if the request is being made and what the response is

### 5. Verify Frontend API Configuration

The frontend should be using `http://localhost:8001` in development mode. Check:
- Browser console for the actual URL being called
- Network tab to see the full request URL

## Common Issues and Solutions

### Issue 1: Backend Container Not Running

**Solution:**
```bash
cd /mnt/c/Krishna/projects/zbot/zoria
docker-compose up -d backend
```

### Issue 2: Backend Port Not Accessible

**Check:**
```bash
# Check if port 8001 is in use
netstat -tuln | grep 8001
# or
lsof -i :8001
```

**Solution:** Make sure nothing else is using port 8001, or change the port in docker-compose.yml

### Issue 3: Database Connection Issue

**Check backend logs:**
```bash
docker-compose logs backend | grep -i "database\|error"
```

**Solution:** Make sure postgres container is running:
```bash
docker-compose up -d postgres
```

### Issue 4: CORS Issues

The backend already allows all origins (`allow_origins=["*"]`), but if you're still having issues:

1. Check browser console for CORS errors
2. Verify the request is going to the correct origin

### Issue 5: Invalid Child ID or PIN

Make sure:
- Child ID is in the correct format (e.g., `CHD123ABC` or UUID)
- PIN is set for the child in the database
- Child record exists and is active

## Debug Steps

1. **Check Backend Status:**
   ```bash
   curl http://localhost:8001/health
   ```

2. **Check Backend Logs:**
   ```bash
   docker-compose logs -f backend
   ```

3. **Test API Endpoint:**
   ```bash
   curl -X POST http://localhost:8001/api/v1/auth/child/login \
     -H "Content-Type: application/json" \
     -d '{"child_id": "CHD123ABC", "pin": "1234"}'
   ```

4. **Check Frontend Console:**
   - Open browser DevTools (F12)
   - Go to Console tab
   - Look for error messages
   - Go to Network tab
   - Try login again and check the request/response

5. **Verify Database:**
   ```bash
   docker-compose exec postgres psql -U zoria -d zoria -c "SELECT id, name, child_code, pin_hash IS NOT NULL as has_pin FROM children LIMIT 5;"
   ```

## Expected Behavior

When login works correctly:
1. Frontend sends POST to `http://localhost:8001/api/v1/auth/child/login`
2. Backend validates child_id and PIN
3. Backend returns JWT token and user info
4. Frontend stores token and redirects to dashboard

## Still Having Issues?

1. Check all container logs:
   ```bash
   docker-compose logs
   ```

2. Restart all services:
   ```bash
   docker-compose down
   docker-compose up -d
   ```

3. Check if there are any environment variable issues:
   ```bash
   docker-compose exec backend env | grep -E "DATABASE|JWT|OPENAI"
   ```
