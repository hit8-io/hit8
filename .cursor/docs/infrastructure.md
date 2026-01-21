# Infrastructure

## Production Infrastructure

### Backend: Google Cloud Run

The backend API is deployed on **Google Cloud Run** as two serverless containerized services: **hit8-api-stg** (staging) and **hit8-api-prd** (production).

**Configuration:**
- **Region**: `europe-west1`
- **Memory**: 2Gi
- **CPU**: 2 vCPU
- **Timeout**: 300 seconds (5 minutes)
- **Scaling**: Min 0, max 10 instances; auto-scaling enabled
- **Platform**: Managed (fully managed by Google)
- **Authentication**: Unauthenticated (public API with token-based auth)

**Container Registry:**
- **Artifact Registry**: `europe-west1-docker.pkg.dev/hit8-poc/backend/api`
- **Tag format**: `{VERSION}-{SHORT_SHA}` (e.g. `0.4.0-a1b2c3d`)

**Deployment:**
- Automated via [GitHub Actions](cicd.md): `docker build` + push to Artifact Registry; `gcloud run services update` for image only. Service config (env, secrets, VPC, scaling) is in Terraform (`infra/`).
- Secrets injected via GCP Secret Manager (`doppler-hit8-stg`, `doppler-hit8-prd`)

### Frontend: Cloudflare Pages

The frontend is deployed on **Cloudflare Pages** as a static site via the [GitHub Actions workflow](cicd.md) (Wrangler `pages deploy`).

**Configuration:**
- **Build Command**: `npm run build` (`tsc && vite build`)
- **Build Output**: `dist/`
- **Node Version**: 20+

**Routing:**
- SPA routing via `_redirects` in `public/`: `/*` → `/index.html` (200)

**Domains:**
- Production: `https://www.hit8.io`, `https://hit8.io`
- Fallback: `https://hit8.pages.dev`

### Database: Supabase

**Production Instance:**
- URL: `https://dxwwmmhfhsljkhftnzke.supabase.co`
- Type: Managed PostgreSQL
- Access: Via Supabase client library with service role key

### Networking

**VPC Configuration:**
- **VPC Network**: `production-vpc`
- **Subnet**: `production-subnet` (10.0.0.0/24)
- **Cloud Router**: `production-router`
- **NAT Gateway**: `production-nat-gateway`
- **Static Egress IP**: `production-static-egress-ip`
- **Cloud Run**: Connected to VPC with all traffic egressing through NAT gateway for static IP

**CORS Configuration:**
- **Allowed Origins** (Production):
  - `https://www.hit8.io`
  - `https://hit8.io`
  - `https://hit8.pages.dev`
- **Credentials**: Allowed
- **Methods**: All (`*`)
- **Headers**: All (`*`)

**API URLs:**
- **Staging**: `https://api-stg.hit8.io`
- **Production**: `https://api-prd.hit8.io`
- Health: `GET /health`; Chat: `POST /chat` (see [api-reference](api-reference.md))

## Development Infrastructure

### Docker Compose

Local development uses **Docker Compose**. Run with **Doppler** for secrets: `doppler run -- docker-compose up`. See [Secrets Management](secrets-management.md) and [development](development.md).

**Services:**
- **api** — Backend (FastAPI/Uvicorn). Port `8000`; `depends_on: langfuse`. Env (e.g. `DATABASE_CONNECTION_STRING`, `GCP_PROJECT`, `VERTEX_SERVICE_ACCOUNT`, etc.) from Doppler. The app database is **not** in this Compose stack: use `DATABASE_CONNECTION_STRING` pointing to Supabase (cloud) or a separate Postgres.
- **web** — Frontend (Vite). Port `5173`.
- **langfuse**, **langfuse-worker** — Observability; depend on clickhouse, redis, minio.
- **clickhouse**, **redis**, **minio** — Backing services for Langfuse. Langfuse DB: `host.docker.internal:54325` (external Postgres).

There is **no `supabase` or Postgres container** in `docker-compose.yml` for the app. Migrations live in `supabase/migrations/`; apply via Supabase tooling.

**Configuration:** [`docker-compose.yaml`](docker-compose.yaml). Environment variables: Doppler; `DATABASE_CONNECTION_STRING` must be supplied for the API.

### Local Development Servers

- **Backend**: `http://localhost:8000` (Uvicorn, hot reload)
- **Frontend**: `http://localhost:5173` (Vite, HMR)
- **Database**: App uses `DATABASE_CONNECTION_STRING` (Supabase or external Postgres). Langfuse uses its own DB at `host.docker.internal:54325`.

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
- Managed by Supabase; URL in `DATABASE_CONNECTION_STRING` / Doppler
- Resource limits depend on Supabase plan

**Development:**
- App uses `DATABASE_CONNECTION_STRING` (Supabase cloud or external Postgres). Docker Compose does not include an app DB container.

## Service URLs

### Production

- **Frontend**: `https://www.hit8.io` / `https://hit8.io`
- **Backend API (staging)**: `https://api-stg.hit8.io`
- **Backend API (production)**: `https://api-prd.hit8.io`
- **Database**: `https://dxwwmmhfhsljkhftnzke.supabase.co` (or as in `DATABASE_CONNECTION_STRING`)

### Development

- **Frontend**: `http://localhost:5173`
- **Backend API**: `http://localhost:8000`
- **Database**: per `DATABASE_CONNECTION_STRING` (e.g. Supabase or local Postgres)

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





