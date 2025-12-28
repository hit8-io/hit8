# Infrastructure

## Production Infrastructure

### Backend: Google Cloud Run

The backend API is deployed on **Google Cloud Run** as a serverless containerized service.

**Configuration:**
- **Region**: `europe-west1`
- **Memory**: 2Gi
- **CPU**: 2 vCPU
- **Timeout**: 300 seconds (5 minutes)
- **Scaling**:
  - Min instances: 0 (scales to zero)
  - Max instances: 10
  - Auto-scaling enabled
- **Platform**: Managed (fully managed by Google)
- **Authentication**: Unauthenticated (public API with token-based auth)

**Container Registry:**
- Images stored in **Google Container Registry (GCR)**
- Image naming: `gcr.io/hit8-poc/hit8-api`
- Tags: Git SHA and `latest`

**Deployment:**
- Automated via GitHub Actions (see [CI/CD documentation](cicd.md))
- Build process uses Google Cloud Build with Kaniko
- Secrets injected via GCP Secret Manager (Doppler secrets JSON)

### Frontend: Cloudflare Pages

The frontend is deployed on **Cloudflare Pages** as a static site.

**Configuration:**
- **Build Command**: `npm run build:cloudflare`
- **Build Directory**: `dist/`
- **Framework Preset**: Vite
- **Node Version**: 20+
- **Deployment**: Automatic via GitHub integration

**Routing:**
- SPA routing handled via `_redirects` file in `public/` directory
- All routes redirect to `index.html` with 200 status code

**Domains:**
- Production: `https://www.hit8.io`, `https://hit8.io`
- Fallback: `https://hit8.pages.dev` (Cloudflare Pages default)

### Database: Supabase

**Production Instance:**
- URL: `https://dxwwmmhfhsljkhftnzke.supabase.co`
- Type: Managed PostgreSQL
- Access: Via Supabase client library with service role key

### Networking

**CORS Configuration:**
- **Allowed Origins** (Production):
  - `https://www.hit8.io`
  - `https://hit8.io`
  - `https://hit8.pages.dev`
- **Credentials**: Allowed
- **Methods**: All (`*`)
- **Headers**: All (`*`)

**API Endpoints:**
- Backend API: Deployed on Cloud Run (URL configured in frontend)
- Health Check: `GET /health`
- Chat Endpoint: `POST /chat`

## Development Infrastructure

### Docker Compose

Local development uses **Docker Compose** to orchestrate multiple services.

**Services:**
1. **API Service** (`api`)
   - Build context: `./backend`
   - Port: `8000:8000`
   - Command: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
   - Volumes: `./backend:/app` (hot reload)
   - Depends on: `supabase`

2. **Supabase Service** (`supabase`)
   - Image: `supabase/postgres:15.1.0.147`
   - Port: `5432:5432`
   - Database: `postgres`
   - Password: `postgres` (development only)

3. **Web Service** (`web`)
   - Build context: `./frontend`
   - Port: `5173:5173`
   - Command: `npm run dev -- --host`
   - Volumes: `./frontend:/app`, `/app/node_modules` (excluded)

**Configuration:**
- File: [`docker-compose.yml`](docker-compose.yml)
- Environment variables: Injected via Doppler (see [Secrets Management](secrets-management.md))

### Local Development Servers

**Backend:**
- Framework: FastAPI with Uvicorn
- Hot Reload: Enabled via `--reload` flag
- Port: `8000`
- Access: `http://localhost:8000`

**Frontend:**
- Framework: Vite dev server
- Hot Reload: Enabled by default
- Port: `5173`
- Access: `http://localhost:5173`

**Database:**
- Type: PostgreSQL 15.1.0
- Port: `5432`
- Access: `localhost:5432`

## Resource Requirements

### Backend (Cloud Run)

**Production:**
- Memory: 2Gi per instance
- CPU: 2 vCPU per instance
- Scaling: 0-10 instances
- Timeout: 300 seconds

**Development:**
- Memory: Minimal (local Docker container)
- CPU: Shared with host
- No scaling limits

### Frontend (Cloudflare Pages)

**Production:**
- Build resources: Provided by Cloudflare
- Bandwidth: Unlimited (Cloudflare CDN)
- Storage: Static files only

**Development:**
- Memory: Minimal (Vite dev server)
- CPU: Shared with host

### Database (Supabase)

**Production:**
- Managed by Supabase
- Resource limits depend on Supabase plan

**Development:**
- Local PostgreSQL container
- Minimal resource usage

## Service URLs

### Production

- **Frontend**: `https://www.hit8.io` / `https://hit8.io`
- **Backend API**: Configured via `VITE_API_URL` environment variable
- **Database**: `https://dxwwmmhfhsljkhftnzke.supabase.co`

### Development

- **Frontend**: `http://localhost:5173`
- **Backend API**: `http://localhost:8000`
- **Database**: `http://localhost:5432`

## Scaling Configuration

### Backend Auto-scaling

The backend automatically scales based on request volume:

- **Min Instances**: 0 (scales to zero when idle)
- **Max Instances**: 10
- **Scaling Behavior**: 
  - Scales up when requests increase
  - Scales down to zero after idle period
  - Each instance handles concurrent requests

### Frontend Scaling

The frontend is a static site served via Cloudflare's CDN:

- **Global Distribution**: Automatic via Cloudflare edge network
- **Caching**: Static assets cached at edge locations
- **No Scaling Limits**: Handles unlimited traffic





