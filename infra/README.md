# Hit8 Infrastructure

Terraform-managed infrastructure for Hit8: GCP (Cloud Run, Identity Platform, storage), Scaleway (containers, VMs, RDB), and Cloudflare (DNS, Pages, rulesets).

## Architecture Overview

| Provider   | Components |
|-----------|------------|
| **GCP**   | Cloud Run (API), Artifact Registry, Identity Platform, Secret Manager, Cloud Storage (chat/knowledge buckets), Cloud Run Job (scheduled). |
| **Scaleway** | Serverless Containers (api-prd, api-stg) attached to VPC via Private Network; staging VM (Docker Compose: Postgres, Redis, PgBouncer), production RDB (Postgres), Stardust VM (Redis). |
| **Cloudflare** | DNS (hit8.io), Pages (www/scw), redirects, cache rules, rate limiting (API endpoints). |

Secrets and non-default configuration are supplied via **Doppler**; Terraform reads them as `TF_VAR_*` environment variables.

## Prerequisites

- **Terraform** 1.x (tested with 1.5+)
- **Doppler CLI** (`doppler` in PATH), logged in and project/config selected
- Provider credentials:
  - **GCP**: `gcloud auth application-default login` (or service account with required roles)
  - **Scaleway**: `SCW_ACCESS_KEY`, `SCW_SECRET_KEY`, `SCW_PROJECT_ID` (or equivalent in Doppler)
  - **Cloudflare**: `CLOUDFLARE_API_TOKEN` or `CLOUDFLARE_EMAIL` + `CLOUDFLARE_API_KEY` (or in Doppler)

## Doppler Setup

Variables are defined in Terraform with **UPPERCASE** names. Doppler should expose them with the `TF_VAR_` prefix so Terraform picks them up (e.g. `TF_VAR_CLOUDFLARE_ACCOUNT_ID`).

### Suggested project structure

- One Doppler project (e.g. `hit8-infra`) with a config (e.g. `prd` or `ci`) used for Terraform.
- Required secrets and non-defaults set in that config; Terraform defaults are used when not set.

### Required / common variables (UPPERCASE in Terraform)

| Terraform variable           | Description                    | Example / note |
|-----------------------------|--------------------------------|----------------|
| `CLOUDFLARE_ACCOUNT_ID`     | Cloudflare account ID          | Sensitive      |
| `CLOUDFLARE_ZONE_ID`       | Zone ID for hit8.io            | Sensitive      |
| `DOMAIN_NAME`              | Root domain (default: hit8.io) | Optional       |
| `GCP_PROJECT_ID`           | GCP project ID                 | Sensitive      |
| `GCP_REGION` / `GCP_ZONE`  | Region/zone (defaults set)     | Optional       |
| `SERVICE_NAME`, `SECRET_NAME`, `ARTIFACT_*`, `IMAGE_TAG` | GCP service/image config | Optional |
| `SCW_PROJECT_ID`           | Scaleway project ID (UUID)     | Sensitive      |
| `SCW_SECRET_KEY`           | Scaleway API secret key (containers use it to fetch Doppler token from Secret Manager) | Sensitive      |
| `SCW_PRD_DB_PWD`           | Production RDB password       | Sensitive      |
| `DOPPLER_PROJECT`         | Doppler project name (Scaleway; default: hit8) | Optional |
| `DOPPLER_SERVICE_TOKENS`   | Map `prd`/`stg` → Doppler tokens for containers | Sensitive |
| `CONTAINER_IMAGE`          | Container image tag (Scaleway)| Optional       |

**GCP Secret Manager – Doppler tokens:** Cloud Run and the report job use `DOPPLER_TOKEN` (not the full secrets JSON). Terraform creates secrets `doppler-token-prd` and `doppler-token-stg`. Populate them with the Doppler service token string (one per environment), e.g.:

```bash
echo -n "dp.st.prd.xxxx" | gcloud secrets versions add doppler-token-prd --data-file=-
echo -n "dp.st.stg.xxxx" | gcloud secrets versions add doppler-token-stg --data-file=-
```

**Scaleway Secret Manager – Doppler tokens:** Terraform creates secrets `doppler-token-prd` and `doppler-token-stg` in Scaleway Secret Manager (same pattern as GCP). The Doppler token is **not** in Terraform. Populate each secret via Console (Secret Manager → secret → Add version) or CLI after apply:

```bash
# Create a version with the Doppler token (opaque secret: use key "data")
echo -n 'dp.st.prd.xxxx' | base64
# In Console: paste the token as the secret value; or via CLI:
scw secret secret version create <secret-id> data="$(echo -n 'dp.st.prd.xxxx' | base64)" region=fr-par
```

Containers fetch the token at startup via the [Secret Manager API](https://www.scaleway.com/en/developers/api/secret-manager/#path-secrets-allow-a-product-to-use-the-secret) using `SCW_SECRET_KEY` (passed as a secret env var so the container can authenticate). Ensure the API key has Secret Manager read permission.

Set in Doppler (with `TF_VAR_` prefix), e.g.:

```bash
doppler login
doppler setup  # select project/config
doppler secrets set TF_VAR_CLOUDFLARE_ACCOUNT_ID="..." TF_VAR_CLOUDFLARE_ZONE_ID="..." ...
```

Or download and source: `doppler secrets download --no-file --format env | grep TF_VAR_` and export before Terraform.

## Security

- **Secrets**: All sensitive values (Cloudflare IDs, GCP project, DB passwords, Doppler tokens) come from Doppler; no secrets in repo or default values.
- **SSH (Scaleway VMs)**: Staging VM and production Redis VM use cloud-init to install **fail2ban** and harden SSH:
  - `/etc/ssh/sshd_config.d/99-hardening.conf`: `PermitRootLogin prohibit-password`, `PasswordAuthentication no`, `MaxAuthTries 3`, etc.
  - `/etc/fail2ban/jail.local`: `sshd` jail with `maxretry=3`, `findtime=600`, `bantime=3600`.
- **API rate limiting (Cloudflare)**: Zone-level rate limiting rules:
  - General API hosts (api-prd, api-stg, scw-prd, scw-stg): 100 req/min per IP, 10 min mitigation.
  - Sensitive paths (`/auth`, `/admin`): 10 req/min per IP, 30 min mitigation.
  - Responses: HTTP 429 with JSON body.

## Deployment

```bash
cd infra
doppler run -- terraform init
doppler run -- terraform plan
doppler run -- terraform apply
```

Apply specific resources if needed:

```bash
doppler run -- terraform apply -target=module.foo
```

## CI/CD Integration

- Run Terraform (plan/apply) in CI with a Doppler **service token** for the infra project/config.
- Inject env: `doppler run --config ci -- terraform plan` (or use Doppler’s download-and-inject pattern).
- Ensure CI has provider credentials (GCP SA key, Scaleway keys, Cloudflare token) and that Doppler exposes all required `TF_VAR_*` variables.

## Troubleshooting

- **Missing variable errors**: Ensure every required Terraform variable is set in Doppler (with `TF_VAR_` prefix) or passed in the environment.
- **Scaleway “project” errors**: Confirm `SCW_PROJECT_ID` (and optional region/zone) are set and match the Scaleway project used by the CLI.
- **Cloudflare rate limit / ruleset errors**: Check zone-level ruleset limits and that `http_ratelimit` phase is supported for your plan.
- **State**: Backend is configured in `state.tf`. For local state, run `terraform init` and use the same backend config across runs.

## File Structure

| File                | Purpose |
|---------------------|--------|
| `state.tf`          | Terraform backend (GCS or local). |
| `providers.tf`      | GCP, Scaleway, Cloudflare providers. |
| `cf-variables.tf`   | Cloudflare-related variables (UPPERCASE). |
| `gcp-variables.tf`  | GCP-related variables (UPPERCASE). |
| `scw-variables.tf`  | Scaleway-related variables (UPPERCASE). |
| `gcp.tf`            | Cloud Run, Artifact Registry, IAM, storage, Cloud Run Job. |
| `cloudflare.tf`     | DNS, Pages, redirects, cache, rate limiting. |
| `scw.tf`            | Registry, VPC, VM, RDB, containers, domains, outputs. |
| `scripts/`          | Helper scripts (e.g. Stardust). |
| `functions/`        | Firebase/other serverless functions (if any). |
