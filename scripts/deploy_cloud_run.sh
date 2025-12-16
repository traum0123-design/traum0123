#!/usr/bin/env bash
set -euo pipefail

# Deploy the Payroll Portal to Google Cloud Run using Cloud Build.
#
# Usage:
#   scripts/deploy_cloud_run.sh [PROJECT_ID] [REGION] [SERVICE_NAME]
#
# Or set env vars and run without args:
#   PROJECT_ID=your-project REGION=asia-northeast3 SERVICE_NAME=payroll-portal \
#   ADMIN_PASSWORD=... SECRET_KEY=... \
#   DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db \
#   ./scripts/deploy_cloud_run.sh
#
# Optional env:
#   UVICORN_WORKERS (default: 2)
#   API_CORS_ORIGINS (comma-separated)
#   COOKIE_SECURE (1 recommended in prod)
#   CLOUDSQL_INSTANCE (PROJECT:REGION:INSTANCE to attach Cloud SQL)
#   AR_REPO (Artifact Registry repository name; default: SERVICE_NAME)
#   AR_LOCATION (Artifact Registry location; default: REGION)
#   IMAGE_TAG (override image tag; default: timestamp)
#   CLOUD_RUN_PORT (container port; default: 8000, or "default" to unset and use Cloud Run default)
#   CLOUD_RUN_SECRETS (comma-separated KEY=SECRET:VERSION mappings for Secret Manager)
#   CREATE_AR_REPO=1 (create Artifact Registry repo if missing)

PROJECT_ID=${1:-${PROJECT_ID:-}}
REGION=${2:-${REGION:-asia-northeast3}}
SERVICE_NAME=${3:-${SERVICE_NAME:-payroll-portal}}

if [[ -z "${PROJECT_ID}" ]]; then
  echo "ERROR: PROJECT_ID not set. Pass as arg or env." >&2
  exit 1
fi

echo "Project: ${PROJECT_ID}"
echo "Region : ${REGION}"
echo "Service: ${SERVICE_NAME}"

TS=$(date +%Y%m%d-%H%M%S)
TAG=${IMAGE_TAG:-${TS}}
AR_LOCATION=${AR_LOCATION:-${REGION}}
AR_REPO=${AR_REPO:-${SERVICE_NAME}}
IMAGE="${AR_LOCATION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${SERVICE_NAME}:${TAG}"

if ! gcloud artifacts repositories describe "${AR_REPO}" --project "${PROJECT_ID}" --location "${AR_LOCATION}" >/dev/null 2>&1; then
  if [[ "${CREATE_AR_REPO:-0}" == "1" ]]; then
    echo "\nCreating Artifact Registry repo: ${AR_REPO} (${AR_LOCATION})"
    gcloud artifacts repositories create "${AR_REPO}" \
      --project "${PROJECT_ID}" \
      --location "${AR_LOCATION}" \
      --repository-format docker
  else
    echo "ERROR: Artifact Registry repo not found: ${AR_REPO} (location: ${AR_LOCATION})" >&2
    echo "Create it with:" >&2
    echo "  gcloud artifacts repositories create \"${AR_REPO}\" --repository-format=docker --location \"${AR_LOCATION}\" --project \"${PROJECT_ID}\"" >&2
    echo "Or rerun with CREATE_AR_REPO=1 to auto-create." >&2
    exit 1
  fi
fi

echo "\n[1/2] Building image via Cloud Build -> ${IMAGE}"
gcloud builds submit --project "${PROJECT_ID}" --tag "${IMAGE}" .

echo "\n[2/2] Deploying to Cloud Run"

CLOUD_RUN_PORT=${CLOUD_RUN_PORT:-8000}
DEPLOY_ARGS=(
  --project "${PROJECT_ID}"
  --region "${REGION}"
  --image "${IMAGE}"
  --platform managed
  --allow-unauthenticated
  --port "${CLOUD_RUN_PORT}"
)

# Attach Cloud SQL if provided
if [[ -n "${CLOUDSQL_INSTANCE:-}" ]]; then
  DEPLOY_ARGS+=(--add-cloudsql-instances "${CLOUDSQL_INSTANCE}")
fi

# Parse Secret Manager mappings, and avoid also setting those keys via env vars.
declare -A _SECRET_ENV_KEYS=()
if [[ -n "${CLOUD_RUN_SECRETS:-}" ]]; then
  IFS=',' read -ra _secret_pairs <<< "${CLOUD_RUN_SECRETS}"
  for _pair in "${_secret_pairs[@]}"; do
    _key="${_pair%%=*}"
    if [[ -n "${_key}" && "${_key}" != /* ]]; then
      _SECRET_ENV_KEYS["${_key}"]=1
    fi
  done
  DEPLOY_ARGS+=(--update-secrets "${CLOUD_RUN_SECRETS}")
fi

# Build env var list (only include if present)
ENV_VARS=(
  SECRET_KEY
  ADMIN_PASSWORD
  DATABASE_URL
  PAYROLL_ALLOW_SQLITE_IN_CLOUD_RUN
  ADMIN_RATE_LIMIT_BACKEND
  ADMIN_RATE_LIMIT_REDIS_URL
  API_CORS_ORIGINS
  UVICORN_WORKERS
  COOKIE_SECURE
  PAYROLL_AUTO_APPLY_DDL
  PAYROLL_ENFORCE_ALEMBIC
  PORTAL_PUBLIC_BASE_URL
)

ENV_STR=""
for key in "${ENV_VARS[@]}"; do
  if [[ -n "${_SECRET_ENV_KEYS[$key]:-}" ]]; then
    continue
  fi
  val=${!key-}
  if [[ -n "${val}" ]]; then
    if [[ -n "${ENV_STR}" ]]; then ENV_STR+=","; fi
    # shellcheck disable=SC2001
    clean=$(echo -n "${val}" | sed 's/[,]/\\,/g')
    ENV_STR+="${key}=${clean}"
  fi
done

if [[ -n "${ENV_STR}" ]]; then
  DEPLOY_ARGS+=(--update-env-vars "${ENV_STR}")
elif [[ -z "${CLOUD_RUN_SECRETS:-}" ]]; then
  echo "WARNING: No env vars/secrets passed. You likely need at least ADMIN_PASSWORD and SECRET_KEY." >&2
fi

gcloud run deploy "${SERVICE_NAME}" "${DEPLOY_ARGS[@]}"

echo "\nDeployed. Fetching URL:"
gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)'

SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --project "${PROJECT_ID}" --region "${REGION}" --format='value(status.url)')
echo "\nHealth check (once running): curl -s ${SERVICE_URL}/api/healthz"

# Optionally run DB migrations via Cloud Run Job if requested
if [[ "${RUN_MIGRATIONS:-0}" == "1" ]]; then
  echo "\nCreating/Updating Cloud Run Job for migrations"
  JOB_NAME="${SERVICE_NAME}-migrate"
  JOB_ARGS=(
    --project "${PROJECT_ID}"
    --region "${REGION}"
    --image "${IMAGE}"
    --execute-now
    --command bash --args -lc,"alembic upgrade head"
  )
  if [[ -n "${CLOUDSQL_INSTANCE:-}" ]]; then
    JOB_ARGS+=(--add-cloudsql-instances "${CLOUDSQL_INSTANCE}")
  fi
  if [[ -n "${CLOUD_RUN_SECRETS:-}" ]]; then
    JOB_ARGS+=(--update-secrets "${CLOUD_RUN_SECRETS}")
  fi
  if [[ -n "${ENV_STR}" ]]; then
    JOB_ARGS+=(--update-env-vars "${ENV_STR}")
  fi

  # Create or update then execute
  if gcloud run jobs describe "${JOB_NAME}" --project "${PROJECT_ID}" --region "${REGION}" >/dev/null 2>&1; then
    gcloud run jobs update "${JOB_NAME}" "${JOB_ARGS[@]}"
  else
    gcloud run jobs create "${JOB_NAME}" "${JOB_ARGS[@]}"
  fi
  echo "\nExecuting migration job: ${JOB_NAME}"
  gcloud run jobs execute "${JOB_NAME}" --project "${PROJECT_ID}" --region "${REGION}"
fi
