# Zoria Development Workflow

## Quick Answer: Do I need to rebuild?

**For Production (current setup):** Yes, rebuild every time
**For Development:** No! Use the dev setup below for hot reload

---

## Development Mode (Hot Reload)

Use this for active development - changes reflect immediately without rebuild:

```bash
# Start dev environment
docker-compose -f docker-compose.dev.yml up -d

# View logs
docker-compose -f docker-compose.dev.yml logs -f frontend-dev

# Stop dev environment
docker-compose -f docker-compose.dev.yml down
```

**Benefits:**
- ✅ Hot Module Replacement (HMR) - changes appear instantly
- ✅ No rebuild needed
- ✅ Faster development cycle
- ✅ Better error messages

**Access:**
- Frontend: http://localhost:3000 (Vite dev server)
- Backend: http://localhost:8001

---

## Production Mode (Current Setup)

Use this for testing production builds:

```bash
# Start production environment
docker-compose up -d

# Rebuild after code changes
docker-compose build --no-cache frontend
docker-compose restart frontend
```

**When to use:**
- Testing production build
- Final testing before deployment
- Performance testing

---

## Recommended Workflow

1. **During Development:**
   ```bash
   docker-compose -f docker-compose.dev.yml up -d
   ```
   Edit code → See changes instantly (no rebuild)

2. **Before Committing:**
   ```bash
   # Test production build
   docker-compose build frontend
   docker-compose up -d
   ```

3. **For Deployment:**
   Use production build (current `docker-compose.yml`)

---

## Switching Between Dev and Prod

**Stop current environment:**
```bash
docker-compose down
# or
docker-compose -f docker-compose.dev.yml down
```

**Start the one you need:**
```bash
# Dev
docker-compose -f docker-compose.dev.yml up -d

# Prod
docker-compose up -d
```
