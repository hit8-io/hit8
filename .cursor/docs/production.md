# Production

## Deployment Targets

### Backend: Google Cloud Run

The backend is deployed to **Google Cloud Run** via the [GitHub Actions workflow](cicd.md): **hit8-api-stg** (staging) and **hit8-api-prd** (production).

**Service Details:**
- **Project**: `hit8-poc`
- **Services**: `hit8-api-stg` (staging), `hit8-api-prd` (production)
- **Region**: `europe-west1`
- **Platform**: Managed (fully managed by Google)
- **Image registry**: Artifact Registry `europe-west1-docker.pkg.dev/hit8-poc/backend/api`; tag format `{VERSION}-{SHORT_SHA}` (e.g. `0.4.0-a1b2c3d`)

**Resource Configuration:**
- Memory: 2Gi
- CPU: 2 vCPU
- Timeout: 300 seconds (5 minutes)
- Min Instances: 0 (scales to zero)
- Max Instances: 10

**API URLs:**
- Staging: `https://api-stg.hit8.io`
- Production: `https://api-prd.hit8.io`

**Deployment Process:**
- Driven by [deploy.yaml](.github/workflows/deploy.yaml): build → deploy staging (auto) → deploy production (manual approval in GitHub `environment: production`). Triggers on push to `main` with changes in `backend/**`, `frontend/**`, or the workflow file.
- See [CI/CD documentation](cicd.md) for the full pipeline and manual deploy steps.

### Frontend: Cloudflare Pages

The frontend is deployed to **Cloudflare Pages** via the [GitHub Actions workflow](cicd.md) using Wrangler `pages deploy`.

**Deployment Configuration:**
- **Build Command**: `npm run build` (`tsc && vite build`)
- **Build Output**: `frontend/dist`
- **Node Version**: 20

**Deployments (from [deploy.yaml](.github/workflows/deploy.yaml)):**
- **Staging (Preview)**: `dist-stg` (built with `VITE_API_URL=https://api-stg.hit8.io`) → `pages deploy ... --branch=main-staging`
- **Production**: `dist-prd` (built with `VITE_API_URL=https://api-prd.hit8.io`) → `pages deploy ... --branch=main`

**Domains:**
- Primary: `https://www.hit8.io`
- Secondary: `https://hit8.io`
- Fallback: `https://hit8.pages.dev`

## Deployment Process

### Backend Deployment

**Automated (via [deploy.yaml](.github/workflows/deploy.yaml)):**
1. **Build**: `docker build` from `./backend` with `VERSION` from repo root; push to Artifact Registry `europe-west1-docker.pkg.dev/hit8-poc/backend/api:{VERSION}-{SHORT_SHA}`.
2. **Staging**: `gcloud run services update hit8-api-stg --image ... --region europe-west1` (auto after build).
3. **Production**: `gcloud run services update hit8-api-prd --image ... --region europe-west1` (after manual approval). Service config (env, secrets, VPC, scaling) is managed by Terraform in `infra/`; the workflow only updates the container image.

**Manual Deployment (image-only; for full steps see [cicd.md](cicd.md)):**
```bash
# From repo root: build and push image
VERSION=$(cat VERSION | tr -d '[:space:]')
TAG="${VERSION}-$(git rev-parse --short HEAD)"
docker build --tag europe-west1-docker.pkg.dev/hit8-poc/backend/api:"$TAG" --build-arg VERSION="$VERSION" ./backend
gcloud auth configure-docker europe-west1-docker.pkg.dev
docker push europe-west1-docker.pkg.dev/hit8-poc/backend/api:"$TAG"

# Update Cloud Run (staging or production)
gcloud run services update hit8-api-stg --image europe-west1-docker.pkg.dev/hit8-poc/backend/api:"$TAG" --region europe-west1
# or
gcloud run services update hit8-api-prd --image europe-west1-docker.pkg.dev/hit8-poc/backend/api:"$TAG" --region europe-west1
```
To change env, secrets, VPC, or scaling: use Terraform in `infra/`, not `gcloud run deploy`.

### Frontend Deployment

**Automatic (via [deploy.yaml](.github/workflows/deploy.yaml)):**
- **Staging**: `npm run build` with `VITE_API_URL=https://api-stg.hit8.io` → `wrangler pages deploy dist-stg --project-name=hit8 --branch=main-staging` (Preview).
- **Production**: `npm run build` with `VITE_API_URL=https://api-prd.hit8.io` → `wrangler pages deploy dist-prd --project-name=hit8 --branch=main` (Production). Production runs after manual approval.

**Manual (see [cicd.md](cicd.md) for full steps):**
```bash
cd frontend
npm ci && npm run build
# Set VITE_API_URL and other VITE_* for the target (stg or prd), then:
npx wrangler pages deploy dist --project-name=hit8 --branch=main-staging   # staging
# or
npx wrangler pages deploy dist --project-name=hit8 --branch=main           # production
```

### Frontend Build

**Build command**: `npm run build` (`tsc && vite build`). Output: `frontend/dist`.

**SPA Routing:**
The `_redirects` file in `public/` ensures all routes redirect to `index.html`:
```
/favicon.ico    /favicon.svg    200
/*    /index.html   200
```

## Environment Configuration

### Production Configuration

**Backend Environment Variables:**
- `ENVIRONMENT=prod`: Sets production mode
- `DOPPLER_TOKEN`: Injected from GCP Secret Manager; process runs under `doppler run` so all secrets come from Doppler at runtime

**Frontend Environment Variables:**
Configured in Cloudflare Pages dashboard:
- `VITE_GOOGLE_IDENTITY_PLATFORM_KEY`: Firebase API key
- `VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN`: Firebase Auth domain
- `VITE_GCP_PROJECT`: Google Cloud Project ID
- `VITE_API_URL`: Backend API URL

**Configuration Sources:**
1. Environment variables (highest priority)
2. YAML config (`prod` section in `config.yaml`)
3. YAML defaults (lowest priority)

### Secrets Management

Production secrets are managed via:
- **Doppler**: Secret source of truth
- **GCP Secret Manager**: Stores Doppler secrets JSON
- **Cloud Run**: Injects secrets at runtime

See [Secrets Management documentation](secrets-management.md) for details.

## Monitoring & Logging

### Cloud Run Logs

**Accessing Logs (production; for staging use `hit8-api-stg`):**
```bash
# View recent logs
gcloud run services logs read hit8-api-prd --region=europe-west1

# Follow logs in real-time
gcloud run services logs tail hit8-api-prd --region=europe-west1

# Filter logs
gcloud run services logs read hit8-api-prd --region=europe-west1 --filter="severity>=ERROR"
```

**Log Levels:**
- Application logs: Standard output/error
- Request logs: Automatic (method, path, status, latency)
- Error logs: Stack traces and error details

### Cloudflare Pages Analytics

**Available Metrics:**
- Page views
- Bandwidth usage
- Request count
- Error rates
- Build status and history

**Access:**
- Cloudflare Dashboard → Pages → Analytics
- Real-time and historical data

### Error Tracking

**Backend Errors:**
- Logged to Cloud Run logs
- Stack traces included
- Request context preserved

**Frontend Errors:**
- Browser console errors
- Cloudflare error pages (for build/runtime errors)
- Consider integrating error tracking service (e.g., Sentry) for production

## Scaling

### Backend Auto-scaling

**Configuration:**
- **Min Instances**: 0 (scales to zero when idle)
- **Max Instances**: 10
- **Concurrency**: Default (80 requests per instance)

**Scaling Behavior:**
- Scales up when request volume increases
- Scales down to zero after idle period
- Each instance handles multiple concurrent requests
- Cold start time: ~5-10 seconds (when scaling from zero)

**Monitoring Scaling (production; for staging use `hit8-api-stg`):**
```bash
# View service metrics
gcloud run services describe hit8-api-prd --region=europe-west1

# View instance count
gcloud run services describe hit8-api-prd --region=europe-west1 --format="value(status.conditions)"
```

### Frontend Scaling

**CDN Distribution:**
- Automatic global distribution via Cloudflare edge network
- No scaling limits
- Handles unlimited traffic

**Caching:**
- Static assets cached at edge locations
- Cache invalidation on new deployments
- Browser caching via cache headers

## Health Checks

### Health Check Endpoint

**Endpoint**: `GET /health`

**Response:**
```json
{
  "status": "healthy"
}
```

**Usage:**
- Cloud Run health checks (if configured)
- Monitoring services
- Load balancer health checks
- Manual verification

**Testing:**
```bash
# Local
curl http://localhost:8000/health

# Production
curl https://api-prd.hit8.io/health
```

### Monitoring Health

**Recommended:**
- Set up uptime monitoring (e.g., UptimeRobot, Pingdom)
- Monitor `/health` endpoint
- Alert on failures
- Track response times

## Rollback Procedures

### Backend Rollback

Use **hit8-api-prd** for production; for staging use **hit8-api-stg**.

**Via Cloud Run Console:**
1. Go to Cloud Run → hit8-api-prd (or hit8-api-stg) → Revisions
2. Select previous revision
3. Click "Manage Traffic"
4. Set traffic to 100% for previous revision

**Via CLI:**
```bash
# List revisions
gcloud run revisions list --service=hit8-api-prd --region=europe-west1

# Rollback to specific revision
gcloud run services update-traffic hit8-api-prd \
  --to-revisions=REVISION_NAME=100 \
  --region=europe-west1
```

### Frontend Rollback

**Via Cloudflare Pages:**
1. Go to Cloudflare Pages → hit8 → Deployments
2. Find previous successful deployment
3. Click "Retry deployment" or "Create deployment"
4. Or restore from previous build

**Via Git:**
```bash
# Revert to previous commit
git revert HEAD
git push origin main

# Or checkout previous commit
git checkout <previous-commit-sha>
git push origin main --force  # Use with caution
```













