# CI/CD

## Backend CI/CD Pipeline

### GitHub Actions Workflow

**File**: [`.github/workflows/deploy-backend.yml`](.github/workflows/deploy-backend.yml)

**Trigger Conditions:**
- Push to `main` branch
- Path filters: Changes in `backend/**` or `.github/workflows/deploy-backend.yml`
- Manual trigger: `workflow_dispatch` (available in GitHub UI)

**Configuration:**
```yaml
env:
  PROJECT_ID: hit8-poc
  PROJECT_NUMBER: 617962194338
  SERVICE_NAME: hit8-api
  REGION: europe-west1
  SECRET_NAME: doppler-hit8-prod
```

### Build Process

**Step 1: Checkout Code**
```yaml
- name: Checkout
  uses: actions/checkout@v4
```

**Step 2: Authenticate to Google Cloud**
```yaml
- name: Authenticate to Google Cloud
  uses: google-github-actions/auth@v2
  with:
    credentials_json: ${{ secrets.GCP_SA_KEY }}
```

**Step 3: Set up Cloud SDK**
```yaml
- name: Set up Cloud SDK
  uses: google-github-actions/setup-gcloud@v2
```

**Step 4: Configure Docker for GCR**
```yaml
- name: Configure Docker for GCR
  run: gcloud auth configure-docker
```

**Step 5: Build and Push Docker Image**
```yaml
- name: Build and Push Docker Image
  run: |-
    gcloud builds submit \
      --config cloudbuild.yaml \
      --region=europe-west1 \
      --machine-type=e2-medium \
      --substitutions=_IMAGE_NAME=gcr.io/$PROJECT_ID/$SERVICE_NAME,_TAG=$GITHUB_SHA,_PROJECT_ID=$PROJECT_ID \
      . || {
        # Check if the image was actually created
        if gcloud container images describe gcr.io/$PROJECT_ID/$SERVICE_NAME:$GITHUB_SHA --format="value(image_summary.fully_qualified_digest)" 2>/dev/null; then
          echo "Build succeeded (image exists), ignoring log streaming error"
          exit 0
        else
          echo "Build failed - image not found"
          exit 1
        fi
      }
```

**Build Configuration**: [`cloudbuild.yaml`](cloudbuild.yaml)

**Build Process:**
- Uses Kaniko executor for container builds
- Builds Docker image from `Dockerfile`
- Pushes to Google Container Registry (GCR)
- Tags: Git SHA and `latest`
- Enables caching for faster builds

**Step 6: Deploy to Cloud Run**
```yaml
- name: Deploy to Cloud Run
  run: |-
    gcloud run deploy $SERVICE_NAME \
      --image gcr.io/$PROJECT_ID/$SERVICE_NAME:$GITHUB_SHA \
      --platform managed \
      --region $REGION \
      --allow-unauthenticated \
      --set-env-vars="ENVIRONMENT=prod" \
      --set-secrets="DOPPLER_SECRETS_JSON=projects/$PROJECT_NUMBER/secrets/$SECRET_NAME:latest" \
      --memory=2Gi \
      --cpu=2 \
      --timeout=300 \
      --max-instances=10 \
      --min-instances=0
```

**Deployment Configuration:**
- Image: Tagged with Git SHA
- Environment: `ENVIRONMENT=prod`
- Secrets: Injected from GCP Secret Manager
- Resources: 2Gi memory, 2 CPU
- Scaling: 0-10 instances

### Build Configuration

**File**: [`cloudbuild.yaml`](cloudbuild.yaml)

**Configuration:**
```yaml
steps:
  - name: 'gcr.io/kaniko-project/executor:latest'
    args:
      - '--dockerfile=Dockerfile'
      - '--context=dir://.'
      - '--destination=${_IMAGE_NAME}:${_TAG}'
      - '--destination=${_IMAGE_NAME}:latest'
      - '--build-arg=PRODUCTION=true'
      - '--cache=true'
      - '--cache-ttl=24h'
      - '--cache-repo=gcr.io/${_PROJECT_ID}/cache'
```

**Features:**
- Kaniko executor (no Docker daemon needed)
- Multi-stage caching for faster builds
- Builds and pushes in single step
- Tags with both SHA and `latest`

## Frontend CI/CD Pipeline

### Cloudflare Pages GitHub Integration

**Deployment Method**: Automatic via Cloudflare Pages GitHub integration

**Trigger Conditions:**
- Push to `main` branch
- Automatic preview deployments for pull requests
- Manual deployments via Cloudflare dashboard

### Build Configuration

**Build Command**: `npm run build:cloudflare`

**What it does:**
1. `npm ci`: Clean install of dependencies
2. `tsc`: TypeScript compilation
3. `vite build`: Production build

**Build Directory**: `dist/`

**Node Version**: 20

**Framework Preset**: Vite

### Environment Variables

**Configuration Location**: Cloudflare Pages dashboard

**Required Variables:**
- `VITE_GOOGLE_IDENTITY_PLATFORM_KEY`
- `VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN`
- `VITE_GCP_PROJECT`
- `VITE_API_URL`

**Setup:**
1. Go to Cloudflare Pages dashboard
2. Select project → Settings → Environment variables
3. Add variables for production environment
4. Save changes

### SPA Routing

**File**: [`frontend/public/_redirects`](frontend/public/_redirects)

**Configuration:**
```
/favicon.ico    /favicon.svg    200
/*    /index.html   200
```

**Purpose:**
- Ensures all routes redirect to `index.html`
- Required for single-page application routing
- Handles client-side routing

## Deployment Steps

### Automated Deployment Flow

**Backend:**
1. Developer pushes to `main` branch
2. GitHub Actions workflow triggered
3. Code checked out
4. Authenticated to Google Cloud
5. Docker image built and pushed to GCR
6. Cloud Run service updated with new image
7. Secrets injected from GCP Secret Manager
8. Service deployed and ready

**Frontend:**
1. Developer pushes to `main` branch
2. Cloudflare Pages detects changes
3. Build process starts
4. Dependencies installed (`npm ci`)
5. TypeScript compiled (`tsc`)
6. Production build created (`vite build`)
7. Static files deployed to Cloudflare CDN
8. Site live and accessible

### Deployment Timeline

**Backend:**
- Build time: ~5-10 minutes
- Deployment time: ~1-2 minutes
- Total: ~6-12 minutes

**Frontend:**
- Build time: ~2-5 minutes
- Deployment time: ~1 minute
- Total: ~3-6 minutes

## Manual Deployment

### Backend Manual Deployment

**Prerequisites:**
- Google Cloud SDK installed
- Authenticated to GCP
- Project set: `gcloud config set project hit8-poc`

**Steps:**
```bash
# 1. Build and push image
cd backend
gcloud builds submit \
  --config cloudbuild.yaml \
  --region=europe-west1 \
  --substitutions=_IMAGE_NAME=gcr.io/hit8-poc/hit8-api,_TAG=manual-$(date +%s),_PROJECT_ID=hit8-poc

# 2. Deploy to Cloud Run
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

### Frontend Manual Deployment

**Option 1: Via Cloudflare Dashboard**
1. Go to Cloudflare Pages dashboard
2. Select project
3. Click "Create deployment"
4. Upload `dist/` directory
5. Deploy

**Option 2: Via Wrangler CLI**
```bash
# Build locally
cd frontend
npm ci
npm run build:cloudflare

# Deploy
npx wrangler pages deploy dist --project-name=hit8
```

**Option 3: Via Git**
```bash
# Push to main branch
git push origin main

# Cloudflare Pages automatically deploys
```

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

**Via GitHub Actions:**
1. Revert commit: `git revert HEAD`
2. Push to `main` branch
3. GitHub Actions automatically deploys previous version

### Frontend Rollback

**Via Cloudflare Pages:**
1. Go to Cloudflare Pages → hit8 → Deployments
2. Find previous successful deployment
3. Click "Retry deployment" or "Create deployment"
4. Previous build restored

**Via Git:**
```bash
# Revert to previous commit
git revert HEAD
git push origin main

# Cloudflare Pages automatically deploys previous version
```

## Monitoring Deployments

### Backend Deployment Status

**GitHub Actions:**
- View workflow runs in GitHub Actions tab
- Check build logs for errors
- Monitor deployment status

**Cloud Run:**
```bash
# View service status
gcloud run services describe hit8-api --region=europe-west1

# View recent revisions
gcloud run revisions list --service=hit8-api --region=europe-west1
```

### Frontend Deployment Status

**Cloudflare Pages:**
- View deployments in Cloudflare Pages dashboard
- Check build logs for errors
- Monitor deployment status

**Build History:**
- All deployments visible in dashboard
- Build logs available for each deployment
- Success/failure status shown

## Troubleshooting Deployments

### Common Issues

**Backend:**
1. **Build Failures**: Check Cloud Build logs
2. **Deployment Failures**: Check Cloud Run logs
3. **Secret Issues**: Verify GCP Secret Manager configuration
4. **Image Not Found**: Verify image exists in GCR

**Frontend:**
1. **Build Failures**: Check Cloudflare Pages build logs
2. **Environment Variables**: Verify variables set in dashboard
3. **Routing Issues**: Check `_redirects` file
4. **Build Errors**: Check TypeScript/Vite errors

### Debugging

**Backend:**
```bash
# View build logs
gcloud builds list --limit=5

# View deployment logs
gcloud run services logs read hit8-api --region=europe-west1
```

**Frontend:**
- Check Cloudflare Pages build logs
- Verify environment variables
- Test build locally: `npm run build:cloudflare`













