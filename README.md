# Payroll Platform (FastAPI + Jinja)

통합 급여 포털/관리자 애플리케이션입니다. FastAPI를 중심으로 포털(HTML)과 JSON API를 제공하며, 공통 도메인 로직은 `core/` 패키지에 위치합니다.

## 구성 개요

- `app/`: FastAPI 애플리케이션 엔트리(`app.main:create_app`)와 포털/관리자 라우터
- `payroll_api/`: JSON API (원천징수, 급여 저장 등) 및 Pydantic 스키마
- `core/`: ORM 모델, 서비스, DB 유틸리티, 엑셀/인증 등 도메인 로직
- `templates/`, `static/`: 포털 UI 자산 (Jinja2 + vanilla JS)
- `tests/`: in-memory SQLite와 openpyxl을 활용한 단위 테스트 초안
- `docs/QA_CHECKLIST.md`: 수동 QA 체크리스트

## 빠른 시작

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.lock --require-hashes  # 또는 개발용: -r requirements-dev.txt

# 관리자 비밀번호는 해시 문자열을 사용합니다. (아래 예시는 1234를 해시한 값)
export ADMIN_PASSWORD=$(python - <<'PY'
from werkzeug.security import generate_password_hash
print(generate_password_hash('1234'))
PY
)
export SECRET_KEY=dev-secret       # 선택 (추천)
# 로컬 개발 DB는 프로젝트 내 SQLite를 사용(WAL 모드 자동 적용)
# 레이트리밋 Redis 사용 시 (선택)
# export ADMIN_RATE_LIMIT_REDIS_URL=redis://127.0.0.1:6379/0
uvicorn app.main:app --reload
```

> **Windows (CMD/PowerShell) 예시**
>
> ```cmd
> .venv\Scripts\activate
> set ADMIN_PASSWORD=scrypt:32768:8:1$dsWbqeMFENgkHHg5$4b77cbcd7abd34169fee626783c7c542e8efa3f67f3acb930d842bfa5bf191ef61d98508c650c08655885eac7945dc7df4970b704f7e9a9d50fa6a7284eafcef
> set SECRET_KEY=dev-secret
> uvicorn app.main:app --reload
> ```
>
> PowerShell에서는 `set` 대신 `$env:ADMIN_PASSWORD='scrypt:32768:8:1$dsWbqeMFENgkHHg5$4b77cbcd7abd34169fee626783c7c542e8efa3f67f3acb930d842bfa5bf191ef61d98508c650c08655885eac7945dc7df4970b704f7e9a9d50fa6a7284eafcef'` 형식을 사용하세요.

브라우저에서 <http://127.0.0.1:8000> 접속 후:
1. `/admin/login`에서 관리자 로그인
2. 새 회사 생성 → 발급받은 접속코드로 `/portal/{slug}/login` 접속
3. 급여표 입력/저장, 엑셀 다운로드, 마감 테스트 진행

## 테스트

현재 저장소에는 핵심 계산/엑셀 로직에 대한 기본 테스트가 포함됩니다.

```bash
python3 -m compileall app core gateway payroll_api tests   # 최소 문법 검증
# pytest 실행 시에는 requirements-dev.txt 설치 필요
PYTHONPATH=. pytest tests/test_payroll_service.py tests/test_excel_export.py
```

### 데이터베이스 구성

- 개발 환경에서는 `DATABASE_URL`을 지정하지 않으면 저장소 내부 SQLite(`payroll_portal/app.db`)를 사용합니다.
- SQLite 사용 시 WAL 모드/`foreign_keys=ON`이 자동 적용되지만, 운영 환경에서는 PostgreSQL 등 외부 DB를 `DATABASE_URL`로 지정하는 것을 권장합니다.
- 레이트리밋은 기본적으로 Redis 연결이 설정되어 있으면 자동으로 Redis 백엔드를 사용합니다. 운영 환경에서는 `ADMIN_RATE_LIMIT_REDIS_URL`을 반드시 설정하세요.

## QA 체크리스트

수동 점검이 필요한 주요 흐름(관리자 회사 생성, 포털 급여 저장/마감, 토큰 검증 등)은 `docs/QA_CHECKLIST.md`를 참고하세요. 점검 시 발견된 사항은 문서에 주석으로 남기고, 필요한 경우 테스트 추가를 권장합니다.

## 배포(Docker)

아래 Dockerfile이 포함되어 있어 컨테이너로 쉽게 배포할 수 있습니다.

빌드 (잠금파일 사용)
```bash
docker build -t traum0123/payroll-portal:latest .
```

실행(개발 예시)
```bash
# 필수 환경변수: ADMIN_PASSWORD, SECRET_KEY (운영 환경에서 전달 권장)
docker run --rm -p 8000:8000 \
  -e ADMIN_PASSWORD="<해시 문자열>" \
  -e SECRET_KEY="<임의의-비밀값>" \
  -e DATABASE_URL="sqlite:///./payroll_portal/app.db" \
  traum0123/payroll-portal:latest

# 브라우저에서 http://127.0.0.1:8000 접속
```

참고
- 컨테이너는 `PORT`, `UVICORN_WORKERS` 환경변수를 지원합니다.
- 지정되지 않으면 8000 포트, 워커 2개로 구동됩니다.
- 운영 환경에서는 `.env`를 이미지에 포함하지 말고, 배포 플랫폼의 시크릿/환경변수 기능을 사용하세요.
- 헬스체크 엔드포인트: `/api/healthz` (200 응답 기대)

## 개발 편의(선택)

Makefile 제공
```bash
make install-dev   # 개발 의존성 설치
make lint          # ruff 린트
make type          # mypy 타입체크
make migrate       # SQLite로 Alembic 적용
make test          # pytest 실행
```

.env 템플릿: `.env.example` 참고

### 패키징/에디터블 설치

PEP 621 기반 `pyproject.toml` 메타데이터가 포함되어 있어 에디터블 설치가 가능합니다.

```bash
pip install -e .
python -c "import core, app, payroll_api; print('editable ok')"
```

### Docker Compose(dev) 라이브 리로드

개발 편의용으로 코드 마운트 + 리로드를 제공하는 오버라이드 파일을 제공합니다.

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

### 샘플 데이터 시드

```bash
PYTHONPATH=. python scripts/dev_seed.py
# 출력된 포털 로그인 URL/코드로 테스트
```

## 마이그레이션(Alembic)

개발 초기에는 자동 DDL 생성이 가능하지만(설정에 따라), 운영에서는 Alembic으로 스키마를 관리하세요.

기본 명령
```bash
# 최신으로 적용
alembic upgrade head

# 새 리비전 생성(모델 변경 후)
alembic revision -m "<message>"
```

환경 변수
- `DATABASE_URL`이 지정되지 않으면 `sqlite:///./payroll_portal/app.db`로 동작합니다.

## Docker Compose(개발용)

PostgreSQL + Redis와 함께 로컬에서 구동할 수 있는 `docker-compose.yml`을 제공합니다.

```bash
# .env에 ADMIN_PASSWORD/SECRET_KEY 설정 후
docker compose up --build

# 앱: http://127.0.0.1:8000
# DB 연결: postgresql+psycopg://postgres:postgres@db:5432/payroll
# Redis: redis://redis:6379/0
```

메모
- Postgres 드라이버로 `psycopg[binary]`를 사용합니다(잠금파일에 포함).
- CI/도커 모두 Python 3.12를 사용해 잠금파일과 일치합니다.
