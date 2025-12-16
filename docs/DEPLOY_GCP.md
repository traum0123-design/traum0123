# GCP 배포 가이드 (Cloud Run)

이 저장소는 Dockerfile이 포함되어 있어 Cloud Run으로 쉽게 배포할 수 있습니다.

## 사전 준비

- gcloud CLI 로그인 및 프로젝트 선택

```bash
gcloud auth login
gcloud config set project <PROJECT_ID>
```

## 필수 환경변수

- `ADMIN_PASSWORD`: 관리자 비밀번호 해시 (예시는 README 참고)
- `SECRET_KEY`: 강한 랜덤 문자열
- `DATABASE_URL`: 운영 DB(PostgreSQL/Cloud SQL) 접속 정보. 예: `postgresql+psycopg://user:pass@host:5432/db`

권장:
- HTTPS 환경: `COOKIE_SECURE=1`
- CORS: `API_CORS_ORIGINS=https://example.com`
- 마이그레이션 정책: `PAYROLL_AUTO_APPLY_DDL=0`, `PAYROLL_ENFORCE_ALEMBIC=1`

## 자동 배포 스크립트

```bash
# 빌드 + 배포(Cloud Build + Cloud Run)
PROJECT_ID=<YOUR_PROJECT>
REGION=asia-northeast3
SERVICE_NAME=payroll-portal

# Artifact Registry (Container Registry(gcr.io) 대신 권장)
# - 스크립트는 기본으로 SERVICE_NAME과 같은 이름의 AR_REPO를 사용합니다.
# - 없으면 먼저 repo를 만들어주세요.
AR_LOCATION=$REGION
AR_REPO=$SERVICE_NAME
gcloud artifacts repositories create "$AR_REPO" \
  --project "$PROJECT_ID" --location "$AR_LOCATION" --repository-format docker

# 필수 비밀은 환경변수로 주입
export ADMIN_PASSWORD=<해시문자열>
export SECRET_KEY=<랜덤값>

# (선택) 운영 DB
export DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db

# 배포 실행
scripts/deploy_cloud_run.sh "$PROJECT_ID" "$REGION" "$SERVICE_NAME"

# (선택) 배포 시 마이그레이션을 Cloud Run Job으로 실행하려면
export RUN_MIGRATIONS=1
scripts/deploy_cloud_run.sh "$PROJECT_ID" "$REGION" "$SERVICE_NAME"
```

Cloud SQL을 사용한다면 인스턴스 연결명을 환경변수로 추가:

```bash
export CLOUDSQL_INSTANCE=<PROJECT>:<REGION>:<INSTANCE>
scripts/deploy_cloud_run.sh "$PROJECT_ID" "$REGION" "$SERVICE_NAME"
```

Secret Manager를 쓰고 싶다면(권장), `--set-env-vars` 대신 `--update-secrets`로 주입할 수 있습니다:

```bash
# 예) ENV_VAR=SECRET_NAME:VERSION (latest 가능)
export CLOUD_RUN_SECRETS="ADMIN_PASSWORD=admin-password:latest,SECRET_KEY=secret-key:latest,DATABASE_URL=database-url:latest"
scripts/deploy_cloud_run.sh "$PROJECT_ID" "$REGION" "$SERVICE_NAME"
```

배포 후 헬스 확인:

```bash
curl -s https://<RUN_URL>/api/healthz
```

## 수동 커맨드(대안)

```bash
REGION=asia-northeast3
PROJECT_ID=<PROJECT_ID>
AR_REPO=payroll-portal
SERVICE=payroll-portal
TAG=$(date +%Y%m%d-%H%M%S)
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${SERVICE}:${TAG}"

gcloud builds submit --tag "${IMAGE}" .
gcloud run deploy payroll-portal \
  --image "${IMAGE}" \
  --region "${REGION}" --allow-unauthenticated --port 8000 \
  --update-env-vars ADMIN_PASSWORD=$ADMIN_PASSWORD,SECRET_KEY=$SECRET_KEY,DATABASE_URL=$DATABASE_URL
```

## 주의 사항

- 업로드는 XLSX만 지원합니다. 템플릿 및 백엔드가 .xlsx만 허용하도록 구성되어 있습니다.
- Cloud Run에서는 `DATABASE_URL` 설정을 강제합니다(운영 안전). 임시 SQLite를 허용하려면 `PAYROLL_ALLOW_SQLITE_IN_CLOUD_RUN=1`(비권장).
- 운영 환경에서는 PostgreSQL 사용과 Alembic 강제(`PAYROLL_ENFORCE_ALEMBIC=1`)를 권장합니다.
