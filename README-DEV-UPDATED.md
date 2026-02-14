# Zoria Development Setup

## Default Mode: Development (Hot Reload)

The main `docker-compose.yml` now starts in **development mode** by default with hot reload!

### Quick Start

```bash
cd /mnt/c/Krishna/projects/zbot/zoria
docker-compose up -d
```

That's it! The frontend runs Vite dev server with hot reload.

### What This Means

- ✅ **No rebuilds needed** - Edit JS files and see changes instantly
- ✅ **Hot Module Replacement** - Changes appear automatically in browser
- ✅ **Faster development** - No waiting for Docker builds
- ✅ **Better error messages** - Vite shows clear errors

### Access

- **Frontend**: http://localhost:3000 (Vite dev server)
- **Backend**: http://localhost:8001 (FastAPI with auto-reload)

### Development Workflow

1. Start services:
   ```bash
   docker-compose up -d
   ```

2. Edit code in `frontend/src/` - changes appear instantly!

3. View logs:
   ```bash
   docker-compose logs -f frontend
   ```

4. Stop services:
   ```bash
   docker-compose down
   ```

## Production Mode (Optional)

If you need to test the production build:

```bash
# Start production build
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Rebuild after code changes
docker-compose -f docker-compose.yml -f docker-compose.prod.yml build frontend
docker-compose -f docker-compose.yml -f docker-compose.prod.yml restart frontend
```

## Summary

- **Default**: Development mode (hot reload) ✅
- **Production**: Use `docker-compose.prod.yml` override

No more rebuilds during development! 🎉
