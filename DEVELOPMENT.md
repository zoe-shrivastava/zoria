# Zoria Development Guide

## Phase 1: Core Infrastructure ✅ COMPLETE

### What's Been Created

1. **Project Structure**
   - Complete directory structure with modular organization
   - Docker configuration
   - Environment variable setup

2. **Core Modules**
   - `core/database.py` - PostgreSQL + pgvector connection management
   - `core/config.py` - Configuration from environment variables
   - `core/security.py` - JWT tokens, password/PIN hashing

3. **OpenAI Agents Integration**
   - `agents/workflow.py` - Document processing workflow
   - Supports PDF input via base64 encoding
   - Extracts markdown and concepts

4. **Main Application**
   - `main.py` - FastAPI app with lifespan management
   - Health check endpoints
   - CORS middleware

5. **Database Schema**
   - `database/migrations/001_initial_schema.sql`
   - Tables: parents, children, documents, chunks, quizzes, quiz_results
   - pgvector support for embeddings

## Next Steps: Phase 2

### 1. Create API Endpoints

**Files to create:**
- `api/v1/__init__.py`
- `api/v1/auth.py` - Authentication endpoints
- `api/v1/admin.py` - Admin endpoints
- `api/v1/parent.py` - Parent endpoints
- `api/v1/child.py` - Child endpoints
- `api/v1/documents.py` - Document upload/management
- `api/v1/quizzes.py` - Quiz endpoints

### 2. Create Service Layer

**Files to create:**
- `services/auth_service.py` - Authentication logic
- `services/user_service.py` - User management (parent/child CRUD)
- `services/document_service.py` - Document processing with OpenAI Agents
- `services/quiz_service.py` - Quiz generation and scoring

### 3. Create Database Repositories

**Files to create:**
- `database/repositories/user_repository.py`
- `database/repositories/document_repository.py`
- `database/repositories/quiz_repository.py`

### 4. Create Pydantic Schemas

**Files to create:**
- `schemas/auth.py` - Login, register requests/responses
- `schemas/user.py` - User models
- `schemas/document.py` - Document models
- `schemas/quiz.py` - Quiz models

### 5. Create Dependencies

**File to create:**
- `core/dependencies.py` - FastAPI dependencies for auth, database

## Running the Application

### Development Mode

```bash
cd zoria/backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set up .env file
cp ../.env.example ../.env
# Edit .env with your values

# Start database (Docker)
docker-compose up -d postgres

# Run migrations (manual for now)
psql -U zoria -d zoria -f database/migrations/001_initial_schema.sql

# Start backend
uvicorn main:app --reload --port 8000
```

### Docker Compose

```bash
docker-compose up
```

## Testing

```bash
# Health check
curl http://localhost:8000/health

# API docs
open http://localhost:8000/docs
```

## Code Structure Guidelines

1. **Services** contain business logic
2. **Repositories** contain database queries
3. **API endpoints** are thin - validate input, call services, return responses
4. **Schemas** define request/response models
5. **Core** contains shared utilities

## Environment Variables

See `.env.example` for all required variables.

Key variables:
- `DATABASE_URL` or individual DB_* variables
- `OPENAI_API_KEY` - Required for document processing
- `JWT_SECRET_KEY` - Must be at least 32 characters
