# Development

## Local Setup

### Prerequisites

Before setting up the development environment, ensure you have the following installed:

- **Python 3.11+**: Required for backend development
- **Node.js 20+**: Required for frontend development
- **Docker & Docker Compose**: For running local services
- **Doppler CLI**: For secret management (see [Secrets Management](secrets-management.md))
- **Git**: For version control

### Environment Setup with Doppler

The project uses Doppler for secret management. Set up Doppler before running the application:

1. **Install Doppler CLI**:
   ```bash
   # macOS
   brew install dopplerhq/cli/doppler
   
   # Or via install script
   curl -Ls --tlsv1.2 --proto "=https" --retry 3 https://cli.doppler.com/install.sh | sh
   ```

2. **Authenticate with Doppler**:
   ```bash
   doppler login
   ```

3. **Configure Doppler for the project**:
   ```bash
   doppler setup --project hit8 --config dev
   ```

### Running with Docker Compose

The easiest way to run the entire application locally is using Docker Compose:

```bash
# Start all services with Doppler secrets
doppler run -- docker-compose up

# Or run in detached mode
doppler run -- docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

**Services Started:**
- **API**: `http://localhost:8000`
- **Frontend**: `http://localhost:5173`
- **Database**: `localhost:5432`

### Manual Setup (Without Docker)

If you prefer to run services manually without Docker:

#### Backend Setup

1. **Navigate to backend directory**:
   ```bash
   cd backend
   ```

2. **Install dependencies with uv**:
   ```bash
   # Install uv if not already installed
   curl -LsSf https://astral.sh/uv/install.sh | sh
   
   # Install project dependencies
   uv pip install -e .
   ```

3. **Set up environment variables** (via Doppler):
   ```bash
   doppler run -- uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

#### Frontend Setup

1. **Navigate to frontend directory**:
   ```bash
   cd frontend
   ```

2. **Install dependencies**:
   ```bash
   npm install
   ```

3. **Set up environment variables** (via Doppler):
   ```bash
   doppler run -- npm run dev
   ```

4. **Access the application**:
   - Frontend: `http://localhost:5173`
   - Backend API: `http://localhost:8000`

#### Database Setup

For local development, you can either:

1. **Use Docker Compose Supabase service** (recommended):
   ```bash
   docker-compose up supabase
   ```

2. **Use local PostgreSQL**:
   - Install PostgreSQL 15+
   - Create database: `postgres`
   - Update connection string in configuration

## Project Structure

```
hit8/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI application entrypoint
│   │   ├── graph.py         # LangGraph orchestration
│   │   ├── config.py        # Configuration management
│   │   ├── config.yaml      # Environment-specific config
│   │   ├── deps.py          # Authentication dependencies
│   │   └── database.py      # Supabase client
│   ├── tests/
│   │   ├── conftest.py      # Test configuration
│   │   ├── unit/            # Unit tests
│   │   └── integration/     # Integration tests
│   ├── Dockerfile           # Backend container definition
│   ├── cloudbuild.yaml      # Cloud Build configuration
│   └── pyproject.toml        # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # Main application component
│   │   ├── components/
│   │   │   ├── ChatInterface.tsx
│   │   │   └── ui/          # UI components
│   │   └── lib/             # Utility functions
│   ├── public/
│   │   └── _redirects       # Cloudflare Pages routing
│   ├── Dockerfile           # Frontend container definition
│   ├── package.json         # Node dependencies
│   └── vite.config.ts       # Vite configuration
├── docker-compose.yml       # Local development services
└── .cursor/
    └── docs/                # Documentation
```

## Development Workflow

### Backend Development

The backend uses **FastAPI** with **Uvicorn** for the development server.

**Key Features:**
- **Hot Reload**: Enabled via `--reload` flag
- **Auto-reload on file changes**: Changes to Python files trigger automatic server restart
- **API Documentation**: Available at `http://localhost:8000/docs` (Swagger UI)

**Running the Backend:**
```bash
# With Docker Compose (recommended)
doppler run -- docker-compose up api

# Manual
cd backend
doppler run -- uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Making Changes:**
- Edit files in `backend/app/`
- Server automatically reloads on save
- Check logs for errors

### Frontend Development

The frontend uses **Vite** as the build tool and dev server.

**Key Features:**
- **Hot Module Replacement (HMR)**: Instant updates without page refresh
- **Fast Refresh**: React components update in real-time
- **TypeScript**: Type checking and IntelliSense support

**Running the Frontend:**
```bash
# With Docker Compose (recommended)
doppler run -- docker-compose up web

# Manual
cd frontend
doppler run -- npm run dev
```

**Making Changes:**
- Edit files in `frontend/src/`
- Changes appear instantly in the browser
- TypeScript errors shown in terminal and browser console

### Hot Reload Configuration

**Backend:**
- Configured in `docker-compose.yml` with `--reload` flag
- Volume mount: `./backend:/app` enables file watching
- Restarts on Python file changes

**Frontend:**
- Configured in `vite.config.ts`
- Automatic HMR for React components
- No manual restart needed

## Configuration

### Environment Variables

The application uses environment variables for configuration. These are managed via Doppler in development.

**Backend Variables:**
- `GCP_PROJECT`: Google Cloud Project ID
- `GOOGLE_IDENTITY_PLATFORM_DOMAIN`: Firebase Auth domain
- `VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM`: Service account JSON (for Vertex AI)
- `SUPABASE_SERVICE_ROLE_KEY`: Supabase service role key
- `ENVIRONMENT`: Set to `dev` or `prod` (defaults to `dev`)

**Frontend Variables:**
- `VITE_GOOGLE_IDENTITY_PLATFORM_KEY`: Firebase API key
- `VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN`: Firebase Auth domain
- `VITE_GCP_PROJECT`: Google Cloud Project ID
- `VITE_API_URL`: Backend API URL

### Config.yaml Structure

The backend uses a YAML configuration file for environment-specific settings:

**File**: [`backend/app/config.yaml`](backend/app/config.yaml)

**Structure:**
```yaml
defaults:
  app_name: "Hit8 Chat API"
  app_version: "1.0.0"
  debug_mode: false
  vertex_ai_model_name: "gemini-3-flash-preview"
  vertex_ai_location: "global"
  cors_allow_credentials: true

dev:
  debug_mode: true
  cors_allow_origins:
    - "http://localhost:5173"
    - "http://127.0.0.1:5173"
  supabase_url: "http://localhost:5432"

prod:
  debug_mode: false
  cors_allow_origins:
    - "https://www.hit8.io"
    - "https://hit8.io"
    - "https://hit8.pages.dev"
  supabase_url: "https://dxwwmmhfhsljkhftnzke.supabase.co"
```

**Configuration Priority:**
1. Environment variables (highest priority)
2. YAML config (environment-specific)
3. YAML defaults (lowest priority)

## Database Setup

### Local Supabase Instance

The Docker Compose setup includes a local Supabase PostgreSQL container:

**Configuration:**
- Image: `supabase/postgres:15.1.0.147`
- Port: `5432`
- Database: `postgres`
- User: `postgres`
- Password: `postgres` (development only)

**Connection:**
- Host: `localhost`
- Port: `5432`
- Database: `postgres`

**Accessing the Database:**
```bash
# Via Docker
docker-compose exec supabase psql -U postgres -d postgres

# Via local psql client
psql -h localhost -p 5432 -U postgres -d postgres
```

### Migrations

Currently, the application does not use database migrations. If migrations are added in the future:

1. Create migration files in `backend/migrations/`
2. Use a migration tool (e.g., Alembic, Supabase migrations)
3. Run migrations on startup or via CLI

## Development Tips

### Debugging

**Backend:**
- Use Python debugger (`pdb`) or IDE debugger
- Check logs in terminal or Docker logs: `docker-compose logs api`
- API errors return detailed error messages

**Frontend:**
- Use browser DevTools (F12)
- React DevTools extension for component inspection
- Vite error overlay shows compilation errors

### Testing

Run tests during development:

```bash
# Backend tests
cd backend
pytest

# With coverage
pytest --cov=app

# Watch mode (requires pytest-watch)
ptw
```

See [Testing documentation](testing.md) for more details.

### Code Quality

**Backend:**
- Use type hints (Python 3.11+ features)
- Follow PEP 8 style guide
- Run linters: `ruff check .` or `black .`

**Frontend:**
- Use TypeScript for type safety
- Follow ESLint rules: `npm run lint`
- Format code: `npm run format` (if configured)














