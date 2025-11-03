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

권장:
- `DATABASE_URL`: 운영 DB(PostgreSQL) 접속 정보. 예: `postgresql+psycopg://user:pass@host:5432/db`
- HTTPS 환경: `COOKIE_SECURE=1`
- CORS: `API_CORS_ORIGINS=https://example.com`
- 마이그레이션 정책: `PAYROLL_AUTO_APPLY_DDL=0`, `PAYROLL_ENFORCE_ALEMBIC=1`

## 자동 배포 스크립트

```bash
# 빌드 + 배포(Cloud Build + Cloud Run)
PROJECT_ID=<YOUR_PROJECT>
REGION=asia-northeast3
SERVICE_NAME=payroll-portal

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

배포 후 헬스 확인:

```bash
curl -s https://<RUN_URL>/api/healthz
```

## 수동 커맨드(대안)

```bash
gcloud builds submit --tag gcr.io/<PROJECT_ID>/payroll-portal:$(date +%Y%m%d-%H%M%S)
gcloud run deploy payroll-portal \
  --image gcr.io/<PROJECT_ID>/payroll-portal:LATEST \
  --region <REGION> --allow-unauthenticated --port 8000 \
  --set-env-vars ADMIN_PASSWORD=$ADMIN_PASSWORD,SECRET_KEY=$SECRET_KEY,DATABASE_URL=$DATABASE_URL
```

## 주의 사항

- 업로드는 XLSX만 지원합니다. 템플릿 및 백엔드가 .xlsx만 허용하도록 구성되어 있습니다.
- 운영 환경에서는 PostgreSQL 사용과 Alembic 강제(`PAYROLL_ENFORCE_ALEMBIC=1`)를 권장합니다.
