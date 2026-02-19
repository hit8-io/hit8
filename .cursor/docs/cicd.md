# CI/CD

## Overview

A single GitHub Actions workflow builds and deploys both backend and frontend, deploys to **staging** automatically, then to **production** after **manual approval**. Cloud Run services and related infra (VPC, secrets) are managed by **Terraform** in `infra/`; the workflow only updates the **container image** for existing services.

**Workflow**: [`.github/workflows/deploy.yaml`](.github/workflows/deploy.yaml)

**Trigger Conditions:**
- Push to `main` with changes in `backend/**`, `frontend/**`, or `.github/workflows/deploy.yaml`
- Manual: `workflow_dispatch` (GitHub Actions tab)

**Concurrency:** One run per workflow/ref; newer runs cancel in‑progress ones.

**Environments:**
- Staging: auto-deploy after build
- Production: requires manual approval (GitHub `environment: production`)

---

## Workflow Configuration

```yaml
env:
  REGION: europe-west1
  IMAGE_BASE: europe-west1-docker.pkg.dev/hit8-poc/backend/api
  CLOUDFLARE_PROJECT: hit8
  API_URL_PRD: https://api-prd.hit8.io
  API_URL_STG: https://api-stg.hit8.io
```

---

## Jobs

### 0. Apply Database Schema

- **Name**: `apply-schema`
- **Runs**: When `database/schema.hcl` changes, or on manual trigger
- **Steps**:
  1. Install Atlas CLI
  2. Install Doppler CLI
  3. Validate schema files exist
  4. Show schema diff (dry-run) for staging
  5. Apply schema to staging automatically
  6. Show schema diff (dry-run) for production
  7. Apply schema to production (requires manual approval)

**Schema Management:**
- Schema is defined declaratively in `database/schema.hcl`
- Atlas automatically generates and applies migrations
- Staging: Applied automatically
- Production: Applied after manual approval in GitHub Actions

See [supabase/migrate.md](../supabase/migrate.md) for local development workflow.

---

### 1. Build Backend

- **Checkout** → **Authenticate to GCP** (`google-github-actions/auth`, `GCP_SA_KEY`) → **Set up Cloud SDK** → **Configure Docker** for Artifact Registry (`gcloud auth configure-docker europe-west1-docker.pkg.dev`)
- **Determine tag:** `VERSION` from repo root + 7-char `github.sha` → `{VERSION}-{SHORT_SHA}` (e.g. `0.4.0-a1b2c3d`)
- **Build and push:** `docker build` (from `./apps/api`, `--build-arg VERSION`), `docker push` to `europe-west1-docker.pkg.dev/hit8-poc/backend/api:{tag}`
- **Outputs:** `image_tag`, `version` for deploy jobs

**Image:** Artifact Registry (not GCR). Tag: `{VERSION}-{SHORT_SHA}`.

**Note:** Database schema changes are automatically applied via Atlas in the `apply-schema` job (see below).

---

### 2. Build Frontend & Site

- **Checkout** → **Node 20** → **Install pnpm** → **`pnpm install`** (at root for monorepo)
- **Build SaaS App (apps/web):**
  - **Staging:** `pnpm turbo build --filter=web` with `VITE_API_URL=https://api-stg.hit8.io` → upload artifact `dist-stg`
  - **Production (GCP):** `pnpm turbo build --filter=web` with `VITE_API_URL=https://api-prd.hit8.io` → upload artifact `dist-prd`
  - **Production (Scaleway):** `pnpm turbo build --filter=web` with `VITE_API_URL=https://scw-prd.hit8.io` → upload artifact `dist-scw`
- **Build Marketing Site (apps/site):**
  - `pnpm turbo build --filter=site` → upload artifact `dist-site`

**Build command:** `pnpm turbo build --filter=<app>` (`tsc && vite build`). Output: `apps/<app>/dist`.

**Environment variables (from GitHub secrets):**
- `VITE_API_URL` — stg: `https://api-stg.hit8.io`, prd: `https://api-prd.hit8.io`, scw: `https://scw-prd.hit8.io`
- `VITE_GOOGLE_IDENTITY_PLATFORM_KEY`
- `VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN`
- `VITE_GCP_PROJECT`
- `VITE_API_TOKEN`
- `VITE_SENTRY_DSN`

---

### 3. Deploy Staging

**Needs:** `build` (backend + frontend + site)

**Backend:**
- `gcloud run services update hit8-api-stg --image {IMAGE_BASE}:{image_tag} --region europe-west1`
- Service, env, secrets, and VPC are defined in Terraform; only the image is updated.

**SaaS App Frontend:**
- Download `dist-stg` → **Wrangler** `pages deploy dist-stg --project-name=hit8 --branch=main-staging` (Cloudflare Pages **Preview**, iter8.hit8.io)

**Marketing Site:**
- Download `dist-site` → **Wrangler** `pages deploy dist-site --project-name=hit8-site --branch=main-staging` (Cloudflare Pages **Preview**, www.hit8.io)

---

### 4. Deploy Production

**Needs:** `build`, `deploy-staging`. Uses `environment: production` (manual approval in GitHub).

**Backend:**
- `gcloud run services update hit8-api-prd --image {IMAGE_BASE}:{image_tag} --region europe-west1`

**SaaS App Frontend:**
- Download `dist-prd` → **Wrangler** `pages deploy dist-prd --project-name=hit8 --branch=main --commit-dirty=true` (Cloudflare Pages **Production**, iter8.hit8.io)
- Download `dist-scw` → **Wrangler** `pages deploy dist-scw --project-name=hit8 --branch=scaleway --commit-dirty=true` (Cloudflare Pages **Production**, scw.hit8.io)

**Marketing Site:**
- Download `dist-site` → **Wrangler** `pages deploy dist-site --project-name=hit8-site --branch=main --commit-dirty=true` (Cloudflare Pages **Production**, www.hit8.io)

---

## Terraform and Cloud Run

Cloud Run services **hit8-api-stg** and **hit8-api-prd** are created and configured in [infra/gcp.tf](infra/gcp.tf):

- Image (placeholder), ENVIRONMENT (`stg` / `prd`), `DOPPLER_TOKEN` (from Secret Manager), VPC, scaling (0–10), resources (2 CPU, 2Gi), timeout 300s

To change env vars, secrets, VPC, or scaling: update Terraform and run `terraform apply`. The CI workflow only runs `gcloud run services update ... --image`, so it does not override Terraform-managed settings.

---

## Version Sync Workflow

**File**: [`.github/workflows/sync-version.yaml`](.github/workflows/sync-version.yaml)

**Trigger:** Push to `main` or `develop` that changes `VERSION`, or `workflow_dispatch`.

**Behavior:**
- Reads `VERSION` from repo root
- Updates `frontend/package.json`, `backend/pyproject.toml`, `backend/app/constants.py`
- Commits and pushes if there are changes
- On `main`: creates tag `v{VERSION}`, GitHub Release, and triggers `deploy.yaml` via `workflow_dispatch`

---

## SPA Routing

**File**: [frontend/public/_redirects](frontend/public/_redirects)

```
/favicon.ico    /favicon.svg    200
/*    /index.html   200
```

All routes go to `index.html` for client-side routing.

---

## Deployment Flow (Summary)

1. Push to `main` (with backend/frontend, schema, or workflow changes)
2. **Schema:** If `database/schema.hcl` or `database/atlas.hcl` changed, apply schema to staging (auto) and production (manual approval)
3. Workflow: build backend image (Docker → Artifact Registry) and frontend (two builds: stg, prd)
4. **Staging:** `hit8-api-stg` image update + Cloudflare Pages `main-staging` (Preview)
5. **Production:** after manual approval → `hit8-api-prd` image update + Cloudflare Pages `main` (Production)

---

## Manual Deployment

### Backend (image-only update)

Cloud Run is managed by Terraform. To deploy a new image without re-running the workflow:

```bash
# 1. Build and push image (from repo root)
VERSION=$(cat VERSION | tr -d '[:space:]')
TAG="${VERSION}-$(git rev-parse --short HEAD)"
docker build --tag europe-west1-docker.pkg.dev/hit8-poc/backend/api:"$TAG" --build-arg VERSION="$VERSION" ./backend
gcloud auth configure-docker europe-west1-docker.pkg.dev
docker push europe-west1-docker.pkg.dev/hit8-poc/backend/api:"$TAG"

# 2. Update Cloud Run (staging or production)
gcloud run services update hit8-api-stg --image europe-west1-docker.pkg.dev/hit8-poc/backend/api:"$TAG" --region europe-west1
# or
gcloud run services update hit8-api-prd --image europe-west1-docker.pkg.dev/hit8-poc/backend/api:"$TAG" --region europe-west1
```

**Alternative:** Run the workflow via `workflow_dispatch` in the GitHub Actions tab.

To change service config (env, secrets, VPC, scaling): use Terraform in `infra/`, not `gcloud run deploy`.

### Frontend

**Via Wrangler (staging preview):**
```bash
cd frontend
npm ci && npm run build
# Set VITE_API_URL and other VITE_* for staging, then:
npx wrangler pages deploy dist --project-name=hit8 --branch=main-staging
```

**Via Wrangler (production):**
```bash
cd frontend
npm ci && npm run build
# Set VITE_API_URL=https://api-prd.hit8.io and other VITE_* for production, then:
npx wrangler pages deploy dist --project-name=hit8 --branch=main
```

**Via workflow:** `workflow_dispatch` for [deploy.yaml](.github/workflows/deploy.yaml).

---

## Rollback

### Backend

**Traffic to a previous revision:**
```bash
gcloud run revisions list --service=hit8-api-prd --region=europe-west1
gcloud run services update-traffic hit8-api-prd --to-revisions=REVISION_NAME=100 --region=europe-west1
```

**Deploy a previous image:** Run the workflow from a commit that has the desired `VERSION` and code, or build and push that image tag and run `gcloud run services update hit8-api-prd --image=...:{tag} --region=europe-west1`.

Use `hit8-api-stg` for staging rollback.

### Frontend

**Cloudflare Pages:** Deployments → choose an older deployment → “Rollback to this deployment” (or redeploy that build).

---

## Monitoring

### Backend

- **GitHub Actions:** Workflow runs and logs in the Actions tab
- **Cloud Run:**
  ```bash
  gcloud run services describe hit8-api-prd --region=europe-west1
  gcloud run revisions list --service=hit8-api-prd --region=europe-west1
  ```

### Frontend

- **Cloudflare Pages:** Project → Deployments; build and deploy logs per branch (`main`, `main-staging`).

---

## Troubleshooting

**Backend:**
- **Build failures:** GitHub Actions logs for `build-backend`
- **Deploy / image not found:** Check image in Artifact Registry: `gcloud artifacts docker images list europe-west1-docker.pkg.dev/hit8-poc/backend --include-tags`
- **Runtime / secrets:** Cloud Run logs; Doppler and GCP Secret Manager for `doppler-hit8-prd` / `doppler-hit8-stg`

**Frontend:**
- **Build failures:** GitHub Actions logs for `build-frontend`; run `npm run build` locally with the right `VITE_*`
- **Wrong API in browser:** Confirm `VITE_API_URL` (and build) used for stg vs prd
- **Routing:** Check [frontend/public/_redirects](frontend/public/_redirects)

**Both:**
- **Staging only:** Ensure `deploy-staging` passed; production needs approval for `deploy-production`.
