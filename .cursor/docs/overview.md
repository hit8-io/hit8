# Hit8 Documentation Overview

## Project Summary

Hit8 is an AI-powered conversational application built with LangGraph orchestration, providing multi-tenant chat capabilities with real-time streaming, graph visualization, and observability. The stack comprises a React TypeScript frontend (Cloudflare Pages), a FastAPI Python backend (GCP Cloud Run), Supabase/PostgreSQL for persistence, and Google Vertex AI for LLM inference.

## Documentation Map

| Document | Description | When to use |
|----------|-------------|-------------|
| [architecture.md](architecture.md) | System design, components, flows, Cloud Run | Understand how the system works, data flows, and design decisions |
| [api-reference.md](api-reference.md) | API endpoints and contracts | Integrate with the API, check request/response formats |
| [authentication.md](authentication.md) | Firebase/Google Identity, token flow | Set up or debug auth, token verification |
| [cicd.md](cicd.md) | GitHub Actions, staging/production, Terraform | Deploy, understand the pipeline, manual deploy steps |
| [dependencies.md](dependencies.md) | Backend (uv) and frontend (npm) deps | Add or update packages, resolve version issues |
| [development.md](development.md) | Local setup, Docker Compose, config | Get started, run locally, configure dev environment |
| [infrastructure.md](infrastructure.md) | Cloud Run, Cloudflare, VPC, Supabase | Understand hosting, networking, and resource config |
| [production.md](production.md) | Deployment targets, rollback, health, scaling | Deploy to prod, roll back, monitor, scale |
| [secrets-management.md](secrets-management.md) | Doppler, GCP Secret Manager | Manage secrets in dev and prod, rotation |
| [technical-debt.md](technical-debt.md) | Known debt and follow-ups | Plan refactors, understand limitations |
| [testing.md](testing.md) | Pytest, mocks, CI | Write or run tests, troubleshoot test failures |
| [troubleshooting.md](troubleshooting.md) | Common failures and fixes | Debug auth, CORS, Vertex AI, secrets, etc. |

## Quick Links

- **Getting started** → [development.md](development.md)
- **Deploy** → [cicd.md](cicd.md)
- **API** → [api-reference.md](api-reference.md)
- **Runbooks** → [production.md](production.md) (rollback, health), [troubleshooting.md](troubleshooting.md)

## Conventions

- **Environment variables and secrets**: [secrets-management.md](secrets-management.md) and backend `config.yaml` / Pydantic settings. Use Doppler in development; GCP Secret Manager (Doppler JSON) in production.
- **Infrastructure as code**: `infra/` (Terraform for GCP: Cloud Run, VPC, Artifact Registry, secrets wiring). The CI workflow updates container images only; Terraform owns service config.
- **Migrations**: `supabase/migrations/`; apply via Supabase tooling or project runbook.
