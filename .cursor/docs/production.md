# Production

## Deployment Targets

### Backend: Google Cloud Run

The backend is deployed to **Google Cloud Run** via GitHub Actions CI/CD pipeline.

**Service Details:**
- **Project**: `hit8-poc`
- **Service Name**: `hit8-api`
- **Region**: `europe-west1`
- **Platform**: Managed (fully managed by Google)

**Resource Configuration:**
- Memory: 2Gi
- CPU: 2 vCPU
- Timeout: 300 seconds (5 minutes)
- Min Instances: 0 (scales to zero)
- Max Instances: 10

**Deployment Process:**
- Automated on push to `main` branch (when `backend/**` files change)
- Manual trigger available via GitHub Actions UI
- See [CI/CD documentation](cicd.md) for detailed deployment steps

### Frontend: Cloudflare Pages

The frontend is deployed to **Cloudflare Pages** via GitHub integration.

**Deployment Configuration:**
- **Build Command**: `npm run build:cloudflare`
- **Build Directory**: `dist/`
- **Node Version**: 20
- **Framework Preset**: Vite

**Automatic Deployments:**
- Triggered on push to `main` branch
- Automatic preview deployments for pull requests
- Production deployments for `main` branch

**Domains:**
- Primary: `https://www.hit8.io`
- Secondary: `https://hit8.io`
- Fallback: `https://hit8.pages.dev`

## Deployment Process

### Backend Deployment

**Automated Deployment (via GitHub Actions):**

1. **Trigger**: Push to `main` branch with changes in `backend/**`
2. **Build**: Google Cloud Build with Kaniko
   - Builds Docker image
   - Pushes to GCR: `gcr.io/hit8-poc/hit8-api`
   - Tags: Git SHA and `latest`
3. **Deploy**: Cloud Run deployment
   - Updates service with new image
   - Injects secrets from GCP Secret Manager
   - Sets environment variables

**Manual Deployment:**

```bash
# Authenticate to Google Cloud
gcloud auth login

# Set project
gcloud config set project hit8-poc

# Build and push image
cd backend
gcloud builds submit \
  --config cloudbuild.yaml \
  --region=europe-west1 \
  --substitutions=_IMAGE_NAME=gcr.io/hit8-poc/hit8-api,_TAG=manual-$(date +%s),_PROJECT_ID=hit8-poc

# Deploy to Cloud Run
gcloud run deploy hit8-api \
  --image gcr.io/hit8-poc/hit8-api:latest \
  --platform managed \
  --region europe-west1 \
  --allow-unauthenticated \
  --set-env-vars="ENVIRONMENT=prod" \
  --set-secrets="DOPPLER_SECRETS_JSON=projects/617962194338/secrets/doppler-hit8-prod:latest" \
  --memory=2Gi \
  --cpu=2 \
  --timeout=300 \
  --max-instances=10 \
  --min-instances=0
```

### Frontend Deployment

**Automatic Deployment (via Cloudflare Pages):**

1. **Trigger**: Push to `main` branch
2. **Build**: Cloudflare Pages build system
   - Runs `npm ci` to install dependencies
   - Runs `tsc` for TypeScript compilation
   - Runs `vite build` to create production bundle
3. **Deploy**: Static files deployed to Cloudflare CDN
   - Files from `dist/` directory
   - `_redirects` file configured for SPA routing

**Manual Deployment:**

1. **Build locally**:
   ```bash
   cd frontend
   npm ci
   npm run build:cloudflare
   ```

2. **Deploy via Cloudflare Dashboard**:
   - Go to Cloudflare Pages dashboard
   - Select project
   - Upload `dist/` directory
   - Or use Wrangler CLI:
     ```bash
     npx wrangler pages deploy dist --project-name=hit8
     ```

### Frontend Build

The frontend uses a specific build script for Cloudflare Pages:

**Build Command**: `npm run build:cloudflare`

**What it does:**
1. `npm ci`: Clean install of dependencies
2. `tsc`: TypeScript type checking and compilation
3. `vite build`: Production build with optimizations

**Build Output:**
- Directory: `dist/`
- Contains: Optimized HTML, CSS, JavaScript bundles
- Includes: `_redirects` file for SPA routing

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
- `DOPPLER_SECRETS_JSON`: Injected from GCP Secret Manager
- Other secrets: Parsed from `DOPPLER_SECRETS_JSON` in [`main.py`](backend/app/main.py)

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

**Accessing Logs:**
```bash
# View recent logs
gcloud run services logs read hit8-api --region=europe-west1

# Follow logs in real-time
gcloud run services logs tail hit8-api --region=europe-west1

# Filter logs
gcloud run services logs read hit8-api --region=europe-west1 --filter="severity>=ERROR"
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

**Monitoring Scaling:**
```bash
# View service metrics
gcloud run services describe hit8-api --region=europe-west1

# View instance count
gcloud run services describe hit8-api --region=europe-west1 --format="value(status.conditions)"
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
curl https://your-api-url.run.app/health
```

### Monitoring Health

**Recommended:**
- Set up uptime monitoring (e.g., UptimeRobot, Pingdom)
- Monitor `/health` endpoint
- Alert on failures
- Track response times

## Rollback Procedures

### Backend Rollback

**Via Cloud Run Console:**
1. Go to Cloud Run → hit8-api → Revisions
2. Select previous revision
3. Click "Manage Traffic"
4. Set traffic to 100% for previous revision

**Via CLI:**
```bash
# List revisions
gcloud run revisions list --service=hit8-api --region=europe-west1

# Rollback to specific revision
gcloud run services update-traffic hit8-api \
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













