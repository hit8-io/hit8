# Secrets Management

## Doppler Integration

Hit8 uses **Doppler** as the primary secret management system, with integration into Google Cloud Platform for production deployments.

## Development: Doppler CLI

### Setup

**Install Doppler CLI:**
```bash
# macOS
brew install dopplerhq/cli/doppler

# Or via install script
curl -Ls --tlsv1.2 --proto "=https" --retry 3 https://cli.doppler.com/install.sh | sh
```

**Authenticate:**
```bash
doppler login
```

**Configure Project:**
```bash
doppler setup --project hit8 --config dev
```

### Running with Doppler

**Docker Compose:**
```bash
doppler run -- docker-compose up
```

**Individual Services:**
```bash
# Backend
doppler run -- uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
doppler run -- npm run dev
```

**What Doppler Does:**
- Injects environment variables from Doppler secrets
- Overrides local environment variables
- Provides secure secret access without hardcoding

## Production: GCP Secret Manager

### Secret Storage

**Secret Name**: `doppler-hit8-prod`

**Storage Location**: Google Cloud Secret Manager
- Project: `hit8-poc`
- Project Number: `617962194338`
- Secret Path: `projects/617962194338/secrets/doppler-hit8-prod`

**Format**: JSON string containing all secrets

### Secret Injection

**Cloud Run Configuration:**
```yaml
--set-secrets="DOPPLER_SECRETS_JSON=projects/617962194338/secrets/doppler-hit8-prod:latest"
```

**Runtime Parsing:**
The backend parses the Doppler secrets JSON at startup in [`main.py`](backend/app/main.py):

```python
if doppler_secrets_json := os.getenv("DOPPLER_SECRETS_JSON"):
    try:
        secrets = json.loads(doppler_secrets_json)
        # Set individual environment variables from Doppler secrets
        for key, value in secrets.items():
            if key not in os.environ:  # Don't override existing env vars
                os.environ[key] = str(value)
    except json.JSONDecodeError:
        pass  # Invalid JSON, continue with existing env vars
```

**Process:**
1. Cloud Run injects `DOPPLER_SECRETS_JSON` from Secret Manager
2. Backend parses JSON at application startup
3. Individual secrets set as environment variables
4. Existing environment variables not overridden (allows local overrides)

## Secret Injection

### Backend Secret Injection

**Location**: [`backend/app/main.py`](backend/app/main.py)

**Process:**
1. Check for `DOPPLER_SECRETS_JSON` environment variable
2. Parse JSON string to dictionary
3. Set each secret as environment variable
4. Continue with normal application startup

**Code:**
```python
# Parse Doppler secrets JSON if provided (for Cloud Run)
if doppler_secrets_json := os.getenv("DOPPLER_SECRETS_JSON"):
    try:
        secrets = json.loads(doppler_secrets_json)
        # Set individual environment variables from Doppler secrets
        for key, value in secrets.items():
            if key not in os.environ:  # Don't override existing env vars
                os.environ[key] = str(value)
    except json.JSONDecodeError:
        pass  # Invalid JSON, continue with existing env vars
```

**Benefits:**
- Single secret (JSON) instead of multiple individual secrets
- Centralized secret management via Doppler
- Easy secret rotation (update JSON in Secret Manager)

### Frontend Secret Injection

**Method**: Environment variables via Vite

**Configuration**: Cloudflare Pages dashboard

**Environment Variables:**
- `VITE_GOOGLE_IDENTITY_PLATFORM_KEY`
- `VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN`
- `VITE_GCP_PROJECT`
- `VITE_API_URL`

**Build-time Injection:**
- Variables prefixed with `VITE_` are available at build time
- Injected into JavaScript bundle during build
- Accessible via `import.meta.env.VITE_*`

**Vite Configuration:**
The [`vite.config.ts`](frontend/vite.config.ts) handles environment variable mapping:

```typescript
process.env.VITE_GOOGLE_IDENTITY_PLATFORM_KEY = 
  process.env.VITE_GOOGLE_IDENTITY_PLATFORM_KEY || 
  process.env.GOOGLE_IDENTITY_PLATFORM_KEY || 
  env.GOOGLE_IDENTITY_PLATFORM_KEY
```

**Priority:**
1. `VITE_*` prefixed variables (highest)
2. Non-prefixed variables (for Docker/Doppler)
3. `.env` file variables (lowest)

## Required Secrets

### Backend Secrets

**GCP Project:**
- `GCP_PROJECT`: Google Cloud Project ID (`hit8-poc`)

**Google Identity Platform:**
- `GOOGLE_IDENTITY_PLATFORM_DOMAIN`: Firebase Auth domain

**Vertex AI:**
- `VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM`: Service account JSON (for Vertex AI access)

**Supabase:**
- `SUPABASE_SERVICE_ROLE_KEY`: Supabase service role key for database access

**Optional:**
- `ENVIRONMENT`: Set to `prod` or `dev` (defaults to `dev` if not set)

### Frontend Secrets

**Firebase Configuration:**
- `VITE_GOOGLE_IDENTITY_PLATFORM_KEY`: Firebase API key
- `VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN`: Firebase Auth domain
- `VITE_GCP_PROJECT`: Google Cloud Project ID

**API Configuration:**
- `VITE_API_URL`: Backend API URL (e.g., `https://hit8-api-xxx.run.app`)

### Secret Naming Conventions

**Backend:**
- Uppercase with underscores
- No `VITE_` prefix (not needed for backend)
- Example: `GCP_PROJECT`, `GOOGLE_IDENTITY_PLATFORM_DOMAIN`

**Frontend:**
- Must be prefixed with `VITE_` to be available in build
- Example: `VITE_GOOGLE_IDENTITY_PLATFORM_KEY`

## Secret Rotation

### Updating Secrets in Doppler

1. **Update in Doppler Dashboard:**
   - Go to Doppler project
   - Select config (e.g., `prod`)
   - Update secret value
   - Save changes

2. **Sync to GCP Secret Manager:**
   - Export secrets from Doppler:
     ```bash
     doppler secrets download --project hit8 --config prod --format json --no-file
     ```
   - Update GCP Secret Manager:
     ```bash
     echo "$SECRETS_JSON" | gcloud secrets versions add doppler-hit8-prod \
       --data-file=- \
       --project=hit8-poc
     ```

3. **Redeploy Backend:**
   - Secrets are injected at runtime
   - New deployments automatically use latest secret version
   - Or manually trigger deployment to pick up new secrets

### Frontend Secret Updates

1. **Update in Cloudflare Pages:**
   - Go to Cloudflare Pages dashboard
   - Select project → Settings → Environment variables
   - Update variable values
   - Save changes

2. **Redeploy:**
   - Trigger new deployment (push to `main` or manual)
   - New build uses updated environment variables

### Best Practices

1. **Rotate Regularly**: Update secrets periodically
2. **Version Control**: Use Secret Manager versions for rollback
3. **Test Changes**: Test secret updates in development first
4. **Monitor**: Check logs after secret rotation for errors
5. **Document**: Keep track of which secrets were updated and when

## Local Development

### Doppler CLI Setup

**Initial Setup:**
```bash
# Install Doppler CLI
brew install dopplerhq/cli/doppler

# Login
doppler login

# Setup project
doppler setup --project hit8 --config dev
```

**Verify Setup:**
```bash
# Test secret access
doppler secrets get GCP_PROJECT

# Run command with secrets
doppler run -- echo $GCP_PROJECT
```

### Docker Compose with Doppler

**Running Services:**
```bash
# Start all services with Doppler secrets
doppler run -- docker-compose up

# Start specific service
doppler run -- docker-compose up api

# Run in background
doppler run -- docker-compose up -d
```

**Environment Variables:**
- Injected by Doppler before Docker Compose starts
- Available to all services in `docker-compose.yml`
- Override local environment variables

### Manual Secret Setup (Alternative)

If Doppler is not available, you can set environment variables manually:

**Backend:**
```bash
export GCP_PROJECT="hit8-poc"
export GOOGLE_IDENTITY_PLATFORM_DOMAIN="your-domain.firebaseapp.com"
export VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM='{"type":"service_account",...}'
export SUPABASE_SERVICE_ROLE_KEY="your-key"
```

**Frontend:**
```bash
export VITE_GOOGLE_IDENTITY_PLATFORM_KEY="your-key"
export VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN="your-domain.firebaseapp.com"
export VITE_GCP_PROJECT="hit8-poc"
export VITE_API_URL="http://localhost:8000"
```

**Note**: Manual setup is not recommended for production and should only be used for local development when Doppler is unavailable.

## Security Considerations

### Secret Storage

1. **Never Commit Secrets**: Secrets should never be committed to version control
2. **Use Doppler**: Always use Doppler for secret management
3. **Rotate Regularly**: Update secrets periodically
4. **Least Privilege**: Only grant necessary permissions
5. **Audit Access**: Monitor who has access to secrets

### Secret Access

1. **Development**: Use Doppler CLI with appropriate config
2. **Production**: Use GCP Secret Manager with Cloud Run integration
3. **CI/CD**: Use service account with minimal permissions
4. **Local Overrides**: Allowed for development (via environment variables)

### Error Handling

**Invalid JSON:**
- Backend silently continues if `DOPPLER_SECRETS_JSON` is invalid
- Falls back to existing environment variables
- Logs should be checked for secret-related errors

**Missing Secrets:**
- Application will fail to start if required secrets are missing
- Error messages indicate which secrets are required
- Check Doppler/GCP Secret Manager for missing secrets



