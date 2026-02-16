# Zoria - Educational Learning Platform

A modern learning platform with AI-powered document processing, concept extraction, and personalized learning experiences.

## Features

- **Role-Based Access**: Admin, Parent, and Child roles
- **Document Processing**: Upload PDFs with automatic concept extraction using OpenAI Agents
- **Child Management**: Parents can create and manage child profiles
- **Document Management**: Upload, view, and manage educational documents
- **Modern UI**: Clean, responsive React frontend
- **Vector Storage**: PostgreSQL with pgvector for semantic search (coming soon)

## Tech Stack

### Backend
- **FastAPI** - Modern Python web framework
- **PostgreSQL** - Database with pgvector extension
- **OpenAI Agents SDK** - Document processing and concept extraction
- **JWT** - Authentication
- **Bcrypt** - Password/PIN hashing

### Frontend
- **React 18** - UI framework
- **Vite** - Build tool
- **Modern CSS** - Design system with CSS variables

### Infrastructure
- **Docker & Docker Compose** - Containerization
- **Nginx** - Frontend web server (production)
- **PostgreSQL** - Database with pgvector

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Node.js 18+ (for local frontend development)
- Python 3.10+ (for local backend development)
- OpenAI API key

### 1. Clone and Setup

```bash
cd zoria
cp .env.example .env
# Edit .env with your OpenAI API key and other settings
```

### 2. Start with Docker Compose

```bash
docker-compose up --build
```

This will start:
- **PostgreSQL** on port 5432
- **Backend API** on port 8000
- **Frontend** on port 3000

### 3. Access the Application

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### 4. Initial Setup

1. Register a parent account via the frontend
2. Create child profiles
3. Upload PDF documents
4. Documents will be automatically processed with concept extraction

## Development

### Backend Development

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r ../requirements.txt

# Set up .env file
cp ../.env.example ../.env
# Edit .env with your settings

# Start database
docker-compose up -d postgres

# Run migrations (manual for now)
psql -U zoria -d zoria -f database/migrations/001_initial_schema.sql

# Start backend
uvicorn main:app --reload --port 8000
```

### Frontend Development

```bash
cd frontend
npm install

# Create .env file
echo "VITE_API_BASE=http://localhost:8000" > .env

# Start dev server
npm run dev
```

## Environment Variables

See `.env.example` for all required environment variables. Key variables:

- `OPENAI_API_KEY` - Required for document processing
- `JWT_SECRET_KEY` - Must be at least 32 characters (generate with `openssl rand -hex 32`)
- `DB_PASSWORD` - Database password
- `FRONTEND_PORT` - Frontend port (default: 3000)
- `API_PORT` - Backend API port (default: 8000)

## Project Structure

```
zoria/
├── backend/           # FastAPI backend
│   ├── api/v1/       # API endpoints
│   ├── core/         # Core utilities (config, database, security)
│   ├── services/     # Business logic
│   ├── agents/       # OpenAI Agents workflow
│   ├── database/     # Database repositories and migrations
│   └── schemas/      # Pydantic models
├── frontend/          # React frontend
│   ├── src/
│   │   ├── components/  # UI components
│   │   ├── pages/       # Page components
│   │   ├── services/    # API client
│   │   └── styles/      # CSS
│   └── Dockerfile
├── docker-compose.yml  # Docker services
├── .env.example        # Environment variables template
└── README.md
```

## API Endpoints

### Authentication
- `POST /api/v1/auth/register` - Register parent
- `POST /api/v1/auth/login` - Login parent/admin
- `POST /api/v1/auth/child/login` - Login child with PIN
- `GET /api/v1/auth/me` - Get current user

### Admin
- `POST /api/v1/admin/parents` - Create parent
- `GET /api/v1/admin/parents` - List parents
- `DELETE /api/v1/admin/parents/{id}` - Deactivate parent

### Parent
- `POST /api/v1/parent/children` - Create child
- `GET /api/v1/parent/children` - List children
- `GET /api/v1/parent/children/{id}` - Get child
- `PUT /api/v1/parent/children/{id}` - Update child
- `DELETE /api/v1/parent/children/{id}` - Delete child

### Documents
- `POST /api/v1/documents/upload` - Upload PDF
- `GET /api/v1/documents` - List documents
- `GET /api/v1/documents/{id}` - Get document
- `DELETE /api/v1/documents/{id}` - Delete document

## Documentation

- [Architecture & Features (Business)](docs/ARCHITECTURE_AND_FEATURES_BUSINESS.md) - High-level overview for product and business users
- [Architecture & Features (Technical)](docs/ARCHITECTURE_AND_FEATURES_TECHNICAL.md) - High-level technical architecture and feature map
- [Architecture Diagrams](docs/ARCHITECTURE_DIAGRAM.md) - Mermaid diagrams (system context, deployment, components, flows)
- [Detailed Flows](docs/DETAILED_FLOWS.md) - Document ingestion, test generation & evaluation, and reports (end-to-end)
- [Development Guide](DEVELOPMENT.md) - Development setup and guidelines
- [Phase 2 Complete](PHASE2_COMPLETE.md) - Backend implementation details
- [Frontend Complete](FRONTEND_COMPLETE.md) - Frontend implementation details

## License

[Your License Here]

## Contributing

[Contributing Guidelines Here]
