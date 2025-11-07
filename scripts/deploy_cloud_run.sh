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
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:${TS}"

echo "\n[1/2] Building image via Cloud Build -> ${IMAGE}"
gcloud builds submit --project "${PROJECT_ID}" --tag "${IMAGE}" .

echo "\n[2/2] Deploying to Cloud Run"

DEPLOY_ARGS=(
  --project "${PROJECT_ID}"
  --region "${REGION}"
  --image "${IMAGE}"
  --platform managed
  --allow-unauthenticated
  --port 8000
)

# Attach Cloud SQL if provided
if [[ -n "${CLOUDSQL_INSTANCE:-}" ]]; then
  DEPLOY_ARGS+=(--add-cloudsql-instances "${CLOUDSQL_INSTANCE}")
fi

# Build env var list (only include if present)
ENV_VARS=(
  SECRET_KEY
  ADMIN_PASSWORD
  DATABASE_URL
  ADMIN_RATE_LIMIT_BACKEND
  ADMIN_RATE_LIMIT_REDIS_URL
  API_CORS_ORIGINS
  UVICORN_WORKERS
  COOKIE_SECURE
  PAYROLL_AUTO_APPLY_DDL
  PAYROLL_ENFORCE_ALEMBIC
)

ENV_STR=""
for key in "${ENV_VARS[@]}"; do
  val=${!key-}
  if [[ -n "${val}" ]]; then
    if [[ -n "${ENV_STR}" ]]; then ENV_STR+="","; fi
    # shellcheck disable=SC2001
    clean=$(echo -n "${val}" | sed 's/[,]/\\,/g')
    ENV_STR+="${key}=${clean}"
  fi
done

if [[ -z "${ENV_STR}" ]]; then
  echo "WARNING: No env vars passed. You likely need at least ADMIN_PASSWORD and SECRET_KEY." >&2
else
  DEPLOY_ARGS+=(--set-env-vars "${ENV_STR}")
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
    --set-env-vars "${ENV_STR}"
    --command bash --args -lc,"alembic upgrade head"
  )
  if [[ -n "${CLOUDSQL_INSTANCE:-}" ]]; then
    JOB_ARGS+=(--add-cloudsql-instances "${CLOUDSQL_INSTANCE}")
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
