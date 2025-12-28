# Production Startup Issues - Root Cause Analysis Plan

## Critical Issues Identified

### 1. **Settings Initialization at Module Level** (HIGH PRIORITY)
**Location:** `backend/app/config.py:121`
**Issue:** `settings = Settings()` runs immediately when module is imported
**Risk:** If any required env var is missing or invalid, app crashes before FastAPI can start
**Impact:** App cannot start, no error visibility until logs are checked

### 2. **Complex Startup Sequence** (MEDIUM PRIORITY)
**Location:** `backend/app/main.py`
**Issue:** Multiple try/except blocks, complex dependency chain
**Risk:** Errors can be hidden or swallowed
**Impact:** Hard to debug, unclear failure points

### 3. **YAML File Dependency** (MEDIUM PRIORITY)
**Location:** `backend/app/config.py:19-35`, `backend/app/main.py:163-182`
**Issue:** Reads `config.yaml` at startup
**Risk:** File not found or invalid YAML causes crash
**Impact:** App cannot start if config file is missing

### 4. **Logger Initialization Before Settings** (LOW PRIORITY)
**Location:** `backend/app/main.py:28`, `backend/app/graph.py:19`
**Issue:** Loggers created before settings are validated
**Risk:** Logger might fail if structlog not properly configured
**Impact:** Errors might not be logged

## Simplified Startup Sequence (Proposed)

### Phase 1: Minimal Startup (Must Succeed)
1. Parse Doppler secrets
2. Set environment variables
3. Initialize basic logging (stderr only)
4. Create FastAPI app (minimal)
5. Add health check endpoint (no dependencies)
6. **START LISTENING ON PORT 8080**

### Phase 2: Configuration Loading (Can Fail Gracefully)
1. Load Settings (with fallbacks)
2. Configure structured logging
3. Validate critical settings

### Phase 3: Service Initialization (Lazy - On Demand)
1. Database connection (when graph is created)
2. Firebase (when auth is needed)
3. Langfuse (when tracing is needed)
4. Vertex AI model (when chat is requested)

## Root Cause Finding Plan

### Step 1: Create Minimal Test App
Create a minimal FastAPI app that:
- Only has `/health` endpoint
- No dependencies on settings, database, or external services
- Prints to stderr at each step
- Starts listening immediately

**Goal:** Verify Cloud Run can start a simple Python app

### Step 2: Add Settings Loading
Add Settings loading with:
- Detailed error messages
- Fallback values where possible
- Continue even if some settings fail

**Goal:** Verify Settings can load in production

### Step 3: Add Dependencies One by One
Add dependencies incrementally:
1. Database connection (lazy)
2. Firebase (lazy)
3. Langfuse (lazy)
4. Graph (lazy)

**Goal:** Identify which dependency causes failure

### Step 4: Check Cloud Run Logs
For each deployment, check:
- Last successful print statement
- First error message
- Stack trace
- Environment variables present

**Goal:** Pinpoint exact failure location

## Implementation Steps

1. **Simplify main.py startup** - Remove complex try/except, use simple prints
2. **Make Settings optional where possible** - Use defaults, validate later
3. **Add startup probe endpoint** - Simple endpoint that responds immediately
4. **Improve error messages** - Print to stderr with clear markers
5. **Test incrementally** - Deploy minimal version first, then add features

## Debugging Commands

```bash
# Check Cloud Run logs
gcloud run services logs read hit8-api --region=europe-west1 --limit=100

# Check if service is running
gcloud run services describe hit8-api --region=europe-west1

# Test health endpoint locally
curl https://hit8-api-617962194338.europe-west1.run.app/health

# Check environment variables in Cloud Run
gcloud run services describe hit8-api --region=europe-west1 --format="value(spec.template.spec.containers[0].env)"
```

## Expected Outcomes

After simplification:
- App should start even if database is unavailable
- App should start even if Langfuse is unavailable
- App should start even if Firebase is unavailable
- Health check should respond immediately
- Detailed errors in logs for any failures

