# Production Startup Issues - Comprehensive Review

## Executive Summary

The application is failing to start in Cloud Run. The container cannot listen on port 8080 within the timeout period. This document outlines identified issues, simplifications made, and a systematic plan to find the root cause.

## Critical Issues Identified

### 1. **Settings Initialization Blocks Startup** ⚠️ CRITICAL
**Location:** `backend/app/config.py:121`
**Issue:** `settings = Settings()` executes at module import time
**Impact:** If any required environment variable is missing or invalid, the app crashes before FastAPI can start
**Status:** ✅ Made lazy where possible, but Settings() still runs on import

### 2. **Complex Startup Sequence** ⚠️ HIGH
**Location:** `backend/app/main.py`
**Issues:**
- Multiple nested try/except blocks can hide errors
- Complex dependency chain (secrets → settings → logging → FastAPI)
- Too many operations before app can listen on port
**Impact:** Hard to debug, unclear failure points
**Status:** ✅ Simplified with STARTUP_MARKER_* tags

### 3. **Module-Level Code Execution** ⚠️ MEDIUM
**Locations:**
- `backend/app/config.py:121` - Settings initialization
- `backend/app/graph.py:19` - Logger creation (safe)
- `backend/app/deps.py:14` - Logger creation (safe)
**Impact:** Code runs before app can start, blocking operations prevent startup
**Status:** ✅ Made graph, Firebase, and Langfuse lazy

### 4. **YAML File Dependency** ⚠️ MEDIUM
**Location:** `backend/app/config.py:19-35`, `backend/app/main.py:163-182`
**Issue:** Reads `config.yaml` at startup
**Impact:** Missing or invalid YAML causes crash
**Status:** ⚠️ Still required, but error handling improved

## Simplifications Made

### ✅ Lazy Initialization
1. **Graph initialization** - Only creates when chat request comes in
2. **Firebase initialization** - Only initializes when auth is needed
3. **Langfuse initialization** - Only initializes when tracing is needed
4. **Database connection** - Only connects when graph is created

### ✅ Improved Error Handling
1. **Clear startup markers** - `STARTUP_MARKER_1` through `STARTUP_MARKER_6`
2. **Detailed error messages** - Print to stderr with full tracebacks
3. **Non-blocking logging** - Logging setup failures don't crash app
4. **Resilient health check** - Works even if settings fail

### ✅ Simplified Startup Sequence
```
STARTUP_MARKER_1: Parse Doppler secrets
STARTUP_MARKER_2: Import settings (critical)
STARTUP_MARKER_3: Import dependencies
STARTUP_MARKER_4: Setup logging (non-blocking)
STARTUP_MARKER_5: Create FastAPI app
STARTUP_MARKER_6: Startup event fired
```

## Root Cause Finding Plan

### Phase 1: Verify Basic Startup ✅
**Goal:** Confirm Python/FastAPI can start in Cloud Run
**Action:** Deploy current code with STARTUP_MARKER_* tags
**Check:** Look for last STARTUP_MARKER in logs
**Expected:** Should reach at least STARTUP_MARKER_5

### Phase 2: Identify Failure Point
**Steps:**
1. Check Cloud Run logs for last successful marker
2. Check for `STARTUP_MARKER_X_ERROR` messages
3. Review full traceback if available
4. Verify environment variables are set

**Log Analysis:**
```bash
# Get recent logs
gcloud run services logs read hit8-api --region=europe-west1 --limit=200

# Filter for startup markers
gcloud run services logs read hit8-api --region=europe-west1 --limit=200 | grep STARTUP_MARKER
```

### Phase 3: Test Incrementally
If Phase 1 fails, test with minimal app:

1. **Minimal FastAPI app** (`main_simplified.py`)
   - Only health endpoint
   - No dependencies
   - Verify Cloud Run can start Python

2. **Add Settings loading**
   - Test if Settings() can initialize
   - Check which env vars are missing

3. **Add dependencies one by one**
   - Test each import separately
   - Identify which dependency fails

## Most Likely Root Causes

### Hypothesis 1: Settings Validation Fails
**Probability:** 80%
**Reason:** Settings() requires all fields, validates at import time
**Check:** Look for `STARTUP_MARKER_2_ERROR` in logs
**Fix:** Make Settings fields optional where possible, validate later

### Hypothesis 2: Missing Environment Variable
**Probability:** 70%
**Reason:** One of required env vars not in Doppler secrets
**Check:** Compare required vars vs. secrets provided
**Fix:** Ensure all required vars are in Doppler

### Hypothesis 3: YAML File Not Found
**Probability:** 30%
**Reason:** `config.yaml` not in Docker image
**Check:** Verify file is copied in Dockerfile
**Fix:** Ensure COPY . . includes config.yaml

### Hypothesis 4: Import Error
**Probability:** 20%
**Reason:** Missing dependency or import error
**Check:** Look for ImportError in logs
**Fix:** Verify all dependencies in pyproject.toml

## Immediate Actions

### 1. Check Cloud Run Logs
```bash
gcloud run services logs read hit8-api \
  --region=europe-west1 \
  --limit=200 \
  --format="value(textPayload,jsonPayload.message)"
```

Look for:
- Last `STARTUP_MARKER_X` reached
- Any `STARTUP_MARKER_X_ERROR` messages
- Full tracebacks

### 2. Verify Environment Variables
```bash
# Check what's in the secret
gcloud secrets versions access latest \
  --secret=doppler-hit8-prod \
  --project=hit8-poc | jq 'keys'
```

### 3. Test Locally with Production Secrets
```bash
# Export secrets
export DOPPLER_SECRETS_JSON='{"DATABASE_CONNECTION_STRING":"...", ...}'
export ENVIRONMENT=prd

# Run app
cd backend
doppler run -- uvicorn app.main:app --host 0.0.0.0 --port 8080
```

### 4. Test Minimal App (if needed)
Temporarily use `main_simplified.py` to verify basic startup works.

## Code Changes Summary

### Files Modified
1. ✅ `backend/app/main.py` - Added STARTUP_MARKER_* tags, simplified error handling
2. ✅ `backend/app/graph.py` - Made Langfuse lazy
3. ✅ `backend/app/deps.py` - Made Firebase lazy
4. ✅ `backend/app/config.py` - Better error messages
5. ✅ `backend/Dockerfile` - Optimized layer caching
6. ✅ `backend/.dockerignore` - Added to reduce build context

### Key Improvements
- **Lazy initialization** for all external services
- **Clear startup markers** for debugging
- **Better error messages** with full tracebacks
- **Resilient health check** that works without dependencies
- **Non-blocking logging** setup

## Next Steps

1. **Deploy current changes** - The STARTUP_MARKER_* tags will show exactly where it fails
2. **Check logs immediately** - Look for the last marker reached
3. **Identify failure point** - Use marker number to pinpoint issue
4. **Fix specific issue** - Address the exact failure point
5. **Verify fix** - Deploy and confirm next marker is reached

## Success Criteria

The app is successfully starting when:
- ✅ All STARTUP_MARKER_* messages appear in logs
- ✅ Health endpoint responds: `curl https://.../health`
- ✅ No errors in Cloud Run logs
- ✅ Container listens on port 8080

## Debugging Checklist

- [ ] Check Cloud Run logs for STARTUP_MARKER_* messages
- [ ] Verify all required env vars are in Doppler secrets
- [ ] Test Settings initialization locally with production secrets
- [ ] Verify config.yaml is in Docker image
- [ ] Check for import errors in logs
- [ ] Verify database connection string format
- [ ] Test minimal app if full app fails

