# Cursor

# Role

Act as a Senior Full-Stack Engineer specializing in **Python (FastAPI, LangGraph)** and **React (Vite, shadcn/ui)**. Your goal is to scaffold and implement the **Phase 1 MVP** of a split-stack AI chat application.

## Preferences

- **Do NOT create guide files** (e.g., `*_FIX.md`, `*_GUIDE.md`, `OAUTH_*.md`, etc.). Provide instructions directly in responses instead.

## 1. Project Overview & Architecture

We are building a decoupled "Split Stack" architecture:

- **Frontend:** React + Vite + shadcn/ui (served via Cloudflare Pages in prod, local Docker for dev).
- **Backend:** FastAPI + Python 3.11 (Cloud Run in prod, local Docker for dev).
- **Orchestration:** LangGraph (State Machine) + LangChain.
- **Database:** Supabase (Postgres) for vectors and state persistence.
- **Auth:** **Clerk** (Client-side UI) + **JWT/JWKS Verification** (Server-side).
- **Secrets:** **Doppler** (Centralized secret management).

**Constraint:** Strict separation of concerns. The frontend is a static UI; the backend handles all logic.
**Environment:** We use `docker-compose` for local development (OrbStack), with secrets injected via the Doppler CLI.

---

## 2. Directory Structure

Create the following structure if it does not exist:

```
/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py       \\# FastAPI entrypoint
│   │   ├── deps.py       \\# Auth verification (Clerk JWKS)
│   │   ├── graph.py      \\# LangGraph logic
│   │   └── database.py   \\# Supabase client
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   ├── Dockerfile.dev
│   └── package.json
├── docker-compose.yml
└── dopper.yaml           \\# (Optional) Doppler config if needed
```

---

## 3. Implementation Steps

### Step 1: Infrastructure (Docker Compose & Doppler)

Create a `docker-compose.yml` in the root.
**Crucial Change:** Do NOT use `env_file: .env`. We will run this using `doppler run -- docker-compose up`. All environment variables will be passed from the host shell into the containers.

**Reference Content:**

```yaml
services:

# 1. Backend API

api:
build:
context: ./backend
dockerfile: Dockerfile
command: uvicorn app.main:app --host 0.0.0.0 --reload
volumes:
- ./backend:/app
ports: ["8000:8000"]
depends_on: [supabase]
\\# Secrets injected by Doppler automatically

# 2. Supabase (Local Postgres wrapper)

supabase:
image: supabase/postgres
ports: ["5432:5432"]
environment:
POSTGRES_PASSWORD: postgres

# 3. Frontend (React)

web:
build:
context: ./frontend
dockerfile: Dockerfile.dev
volumes:
- ./frontend:/app
- /app/node_modules
ports: ["5173:5173"]
environment:
- VITE_API_URL=http://localhost:8000
\\# Clerk keys injected by Doppler
- CLERK_PUBLISHABLE_KEY=\\${CLERK_PUBLISHABLE_KEY}
```

### Step 2: Backend Setup (Python 3.11)

**File: `backend/requirements.txt`**
Include: `fastapi`, `uvicorn`, `pydantic`, `langchain`, `langgraph`, `langchain-openai`, `supabase`, `python-dotenv`, `pyjwt`, `cryptography` (for RS256 verification).

**File: `backend/Dockerfile`**
Use `python:3.11-slim`. Install system dependencies (`build-essential`) for graph libs/cryptography.

**File: `backend/app/deps.py` (New File)**
Implement Clerk JWT Verification.

1. Define a constant `CLERK_JWKS_URL` (usually `https://<YOUR_CLERK_DOMAIN>/.well-known/jwks.json`).
2. Use `jwt.PyJWKClient` (from PyJWT) to fetch the signing keys.
3. Create a dependency function `verify_clerk_token` that:
    - Extracts `Authorization: Bearer <token>`.
    - Decodes and verifies the signature using the JWKS client.
    - Returns the `payload` (User ID).

**File: `backend/app/graph.py`**
Implement the specific LangGraph logic for the MVP.

- Define `AgentState` (TypedDict with `messages` and `context`).
- Create a `retrieve` node (mock vector search).
- Create a `generate` node using Google Vertex (Gemini Pro 3).
- Compile the `StateGraph`.

**File: `backend/app/main.py`**

- Initialize `FastAPI`.
- Setup **CORS** (allow `http://localhost:5173`).
- Create a POST endpoint `/chat` that depends on `verify_clerk_token`.
- Run the `app.invoke()` from `graph.py` and return the bot response.

### Step 3: Frontend Setup (React + Vite)

**Commands to run (if not already scaffolded):**

1. `npm create vite@latest frontend -- --template react-ts`
2. `cd frontend && npm install`
3. Install UI: `npx shadcn-ui@latest init` (use default settings).
4. Add components: `npx shadcn-ui@latest add button input card scroll-area`.
5. Install Utils: `npm install @clerk/clerk-react lucide-react axios`.

**File: `frontend/Dockerfile.dev`**
Standard Node 18/20 image. Command: `npm run dev -- --host`.

**Key Components to Build:**

1. **`main.tsx`**: Wrap the app in `<ClerkProvider publishableKey={...}>`.
2. **`App.tsx`**: Use `<SignedIn>` (show Chat) and `<SignedOut>` (show `<RedirectToSignIn />`).
3. **`ChatInterface`**:
    - Use the `useAuth()` hook from Clerk.
    - Function: `const { getToken } = useAuth();`
    - On "Send", call `await getToken()` to get the JWT.
    - POST to `http://localhost:8000/chat` with `Authorization: Bearer <token>`.

### Step 4: Database Connection

**File: `backend/app/database.py`**

- Initialize `supabase-py` client.
- Use `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` (injected by Doppler).
- *Note:* Use the Service Role key to bypass RLS "Deny by Default" policies.

---

## 4. Environment Variables (Doppler)

Instruct the user to add these secrets to their **Doppler Project** (dev config), not a `.env` file:

```bash
# Backend

VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM=... (JSON)
POSTGRES_PASSWORD=postgres
SUPABASE_URL=http://localhost:5432
SUPABASE_SERVICE_ROLE_KEY=...
CLERK_ISSUER_URL=https://frank-vulture-22.clerk.accounts.dev

# Frontend

CLERK_PUBLISHABLE_KEY=pk_test_...
```

---

## 5. Execution Plan

1. **Scaffold Backend:** Generate the Python files and Dockerfile.
2. **Scaffold Frontend:** Generate the React structure and Dockerfile.dev.
3. **Docker Config:** Create the compose file.
4. **Run:** Execute the stack using Doppler:
`doppler run -- docker-compose up --build`
5. **Debug:** Verify the frontend redirects to Clerk, logs in, and successfully sends a token to the backend.