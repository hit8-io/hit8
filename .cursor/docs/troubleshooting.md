# Troubleshooting

## Common Issues

### Authentication Failures

#### Issue: 401 Unauthorized on API Requests

**Symptoms:**
- API requests return 401 Unauthorized
- Frontend shows authentication errors
- User cannot send chat messages

**Possible Causes:**
1. Missing or invalid ID token
2. Expired token
3. Token not sent in Authorization header
4. Firebase configuration incorrect

**Solutions:**

**Check Token Generation:**
```typescript
// In frontend, verify token is generated
const token = await firebaseUser.getIdToken(false)
console.log('Token:', token)  // Should not be null
```

**Verify Token Format:**
- Token should be a JWT string
- Check that token is included in request headers:
  ```typescript
  headers: {
    Authorization: `Bearer ${token}`,  // Note: "Bearer " prefix required
  }
  ```

**Check Firebase Configuration:**
- Verify environment variables are set:
  - `VITE_GOOGLE_IDENTITY_PLATFORM_KEY`
  - `VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN`
  - `VITE_GCP_PROJECT`
- Check Firebase console for correct values

**Backend Token Verification:**
- Verify service account credentials are correct
- Check Firebase Admin SDK initialization
- Review backend logs for token verification errors

#### Issue: Firebase Admin SDK Initialization Fails

**Symptoms:**
- Backend fails to start
- Error: "Failed to initialize Firebase Admin SDK"
- Service account JSON parsing errors

**Solutions:**

**Verify Service Account JSON:**
```python
# Check that service account JSON is valid
import json
service_account_info = json.loads(settings.vertex_service_account_json)
# Should not raise JSONDecodeError
```

**Check Environment Variable:**
- Verify `VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM` is set
- Ensure JSON is properly formatted
- Check for special characters that need escaping

**Verify Project ID:**
- Ensure `GCP_PROJECT` matches service account project
- Check service account has necessary permissions

### Secret Injection Problems

#### Issue: Secrets Not Available at Runtime

**Symptoms:**
- Application fails to start
- Missing configuration errors
- Environment variables not set

**Solutions:**

**Development (Doppler):**
```bash
# Verify Doppler is configured
doppler secrets get GCP_PROJECT

# Check Doppler setup
doppler setup --project hit8 --config dev

# Verify secrets are injected
doppler run -- env | grep GCP_PROJECT
```

**Production (GCP Secret Manager):**
```bash
# Verify secret exists
gcloud secrets describe doppler-hit8-prod --project=hit8-poc

# Check secret version
gcloud secrets versions list doppler-hit8-prod --project=hit8-poc

# Verify Cloud Run secret configuration
gcloud run services describe hit8-api --region=europe-west1 \
  --format="value(spec.template.spec.containers[0].env)"
```

**Backend Secret Parsing:**
- Check `DOPPLER_SECRETS_JSON` is set in Cloud Run
- Verify JSON parsing in [`main.py`](backend/app/main.py)
- Check logs for JSON parsing errors

#### Issue: Invalid JSON in DOPPLER_SECRETS_JSON

**Symptoms:**
- Backend starts but secrets not available
- Configuration errors
- Silent failure in secret parsing

**Solutions:**

**Verify JSON Format:**
```bash
# Check secret JSON is valid
gcloud secrets versions access latest \
  --secret=doppler-hit8-prod \
  --project=hit8-poc | jq .
```

**Check Secret Parsing:**
- Review [`main.py`](backend/app/main.py) secret parsing logic
- Add logging to debug JSON parsing
- Verify JSON structure matches expected format

### CORS Errors

#### Issue: CORS Policy Blocks Requests

**Symptoms:**
- Browser console shows CORS errors
- Requests fail with CORS policy errors
- "Access-Control-Allow-Origin" header missing

**Solutions:**

**Check CORS Configuration:**
- Verify `cors_allow_origins` in [`config.yaml`](backend/app/config.yaml)
- Ensure frontend URL is in allowed origins list
- Check environment-specific configuration (dev vs prod)

**Development:**
```yaml
dev:
  cors_allow_origins:
    - "http://localhost:5173"
    - "http://127.0.0.1:5173"
```

**Production:**
```yaml
prod:
  cors_allow_origins:
    - "https://www.hit8.io"
    - "https://hit8.io"
    - "https://hit8.pages.dev"
```

**Verify CORS Middleware:**
- Check CORS middleware is configured in [`main.py`](backend/app/main.py)
- Ensure `allow_credentials=True` if needed
- Verify `allow_methods=["*"]` and `allow_headers=["*"]`

**Browser-Specific Issues:**
- Clear browser cache
- Check browser console for specific CORS error
- Verify request includes proper headers

### Vertex AI Connection Issues

#### Issue: Vertex AI API Calls Fail

**Symptoms:**
- Chat requests fail
- Error: "Failed to connect to Vertex AI"
- Timeout errors

**Solutions:**

**Verify Service Account:**
- Check service account has Vertex AI permissions
- Verify service account JSON is correct
- Ensure service account is enabled

**Check Project Configuration:**
```python
# Verify project ID matches
project=service_account_info.get("project_id") or settings.gcp_project
```

**Verify Model Configuration:**
- Check `vertex_ai_model_name` is correct
- Verify `vertex_ai_location` is valid
- Ensure model is available in specified location

**Network Issues:**
- Check Cloud Run has internet access
- Verify firewall rules allow outbound connections
- Check for VPC restrictions

**Check Logs:**
```bash
# View Cloud Run logs
gcloud run services logs read hit8-api --region=europe-west1 \
  --filter="severity>=ERROR"
```

#### Issue: Vertex AI Response Timeout

**Symptoms:**
- Requests timeout after 5 minutes
- Error: "Request timeout"
- Long response times

**Solutions:**

**Increase Timeout:**
- Cloud Run timeout is set to 300 seconds (5 minutes)
- Consider increasing if needed:
  ```bash
  gcloud run services update hit8-api \
    --timeout=600 \
    --region=europe-west1
  ```

**Optimize Requests:**
- Reduce message length
- Simplify prompts
- Consider using faster model variant

**Monitor Performance:**
- Check Vertex AI response times
- Monitor Cloud Run request latency
- Review logs for slow requests

## Debugging

### Log Locations

#### Backend Logs

**Cloud Run Logs:**
```bash
# View recent logs
gcloud run services logs read hit8-api --region=europe-west1

# Follow logs in real-time
gcloud run services logs tail hit8-api --region=europe-west1

# Filter by severity
gcloud run services logs read hit8-api --region=europe-west1 \
  --filter="severity>=ERROR"
```

**Local Development:**
- Logs appear in terminal where uvicorn is running
- Docker Compose: `docker-compose logs api`

#### Frontend Logs

**Browser Console:**
- Open browser DevTools (F12)
- Check Console tab for errors
- Check Network tab for failed requests

**Cloudflare Pages:**
- View build logs in Cloudflare Pages dashboard
- Check deployment logs for build errors

### Debugging Procedures

#### Backend Debugging

**Enable Debug Mode:**
```yaml
# In config.yaml
dev:
  debug_mode: true
```

**Add Logging:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

logger.debug("Debug message")
logger.info("Info message")
logger.error("Error message")
```

**Test Endpoints:**
```bash
# Health check
curl http://localhost:8000/health

# Chat endpoint (with token)
curl -X POST http://localhost:8000/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'
```

#### Frontend Debugging

**Enable Debug Logging:**
```typescript
// Check Firebase config
console.log('Firebase config:', firebaseConfig)

// Check token
console.log('Token:', idToken)

// Check API URL
console.log('API URL:', API_URL)
```

**Network Inspection:**
- Open browser DevTools → Network tab
- Check request/response details
- Verify headers are correct
- Check response status codes

**React DevTools:**
- Install React DevTools browser extension
- Inspect component state
- Check props and hooks

### Environment Issues

#### Local vs Production Differences

**Configuration:**
- Development uses `config.yaml` dev section
- Production uses `config.yaml` prod section
- Environment determined by `ENVIRONMENT` variable or `K_SERVICE`

**Secrets:**
- Development: Doppler CLI
- Production: GCP Secret Manager
- Different secret sources may have different values

**Database:**
- Development: Local Supabase container
- Production: Cloud Supabase instance
- Different connection strings

**CORS:**
- Development: `http://localhost:5173`
- Production: `https://www.hit8.io`
- Different allowed origins

#### Common Environment Issues

**Issue: Wrong Environment Detected**

**Symptoms:**
- Production config used in development
- Development config used in production

**Solutions:**
```bash
# Development: Ensure ENVIRONMENT is not set to "prod"
unset ENVIRONMENT

# Production: Ensure ENVIRONMENT is set to "prod"
export ENVIRONMENT=prod
```

**Issue: Missing Environment Variables**

**Symptoms:**
- Application fails to start
- Configuration errors
- Missing required settings

**Solutions:**
- Check all required environment variables are set
- Verify Doppler configuration
- Check GCP Secret Manager for production

## Getting Help

### Check Documentation

1. Review relevant documentation sections
2. Check API reference for endpoint details
3. Review architecture for system understanding

### Review Logs

1. Check application logs for errors
2. Review deployment logs
3. Check external service logs (Firebase, Vertex AI)

### Common Solutions

1. **Restart Services**: Often resolves transient issues
2. **Clear Cache**: Browser cache, Docker images, etc.
3. **Verify Configuration**: Check all configuration values
4. **Check Dependencies**: Ensure all dependencies are installed
5. **Update Dependencies**: May resolve compatibility issues

### Escalation

If issues persist:
1. Collect relevant logs
2. Document error messages
3. Note steps to reproduce
4. Check for known issues in dependencies
5. Consider opening an issue or seeking support



















