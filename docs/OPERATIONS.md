Operations Guide (Payroll Platform)

1) Migrations (Alembic)
- Never run automatic DDL in production. Set PAYROLL_AUTO_APPLY_DDL=0 and PAYROLL_ENFORCE_ALEMBIC=1.
- Apply migrations before rolling out the app:
  - alembic upgrade head
- Rollback (for staging/emergency only):
  - alembic downgrade -1 (or to a specific revision)

Important recent revisions:
- 0004_idempotency_records: adds idempotency records table for safe write deduplication
- 0005_companies_pagination_idx: adds (created_at, id) index for companies listing
- 0006_monthly_payrolls_seek_index: adds (company_id, year, month, id) index for payroll listings

2) Idempotency Store
- Write APIs accept Idempotency-Key; responses are cached keyed by (method, path, key, body_hash).
- To prune old entries (e.g., >7 days):
  - python scripts/manage.py prune-idempotency --days 7

PII at-rest (DB)
- 정규화 테이블의 주민등록번호는 저장 시 마지막 4자리만 남기고 마스킹(***-**-1234)하여 저장됩니다.
- 엑셀 다운로드에서도 동일 마스킹 적용, '메타' 시트에 다운로드 정보가 포함됩니다.
- 선택 암호화: 환경변수 `PII_ENC_KEY`(Fernet key, base64 urlsafe)를 설정하고 `cryptography`가 설치된 경우, 주민등록번호는 `enc:<token>` 형태로 암호화 저장됩니다.
  - 키 생성: `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`
  - 복호화는 내부 유틸로만 사용되며, 화면/엑셀에는 항상 마스킹된 형태만 노출됩니다.
 - 키 회전(무중단): `PII_ENC_KEYS`에 콤마로 구분한 키 목록을 설정하면, 첫 번째 키로 암호화하고 모든 키로 복호화를 시도합니다.
   - 회전 절차: `PII_ENC_KEYS="<new>,<old>"`로 배포 → 신규 데이터는 new로 암호화, 기존 데이터는 old로 복호화 가능 → 데이터 점진 재암호화 후 `PII_ENC_KEYS`에서 old 제거.

3) Security & Tokens
- Cookies: Secure + HttpOnly + SameSite=Lax recommended in production.
- Token revocation:
  - Rotate company token key via API or CLI to revoke all existing tokens for a company:
    * API: POST /api/admin/company/{company_id}/rotate-token-key
    * CLI: python scripts/manage.py rotate-company-token-key --company-id <id|--slug>
- Access code rotation:
  - CLI: python scripts/manage.py rotate-company-access --company-id <id|--slug>
- RBAC roles:
  - Admin tokens include roles=["admin"], company tokens default to roles=["payroll_manager"].
  - Impersonation issues roles=["company_admin"].
  - Write endpoints under /api/portal (e.g., save payroll, field configs) require roles ∈ {payroll_manager, company_admin, admin}.
  - Read endpoints allow viewer.
- Admin token revocation:
  - Revoke specific token: python scripts/manage.py revoke-admin-token --token <token>
  - Revoke all admin tokens issued before now: python scripts/manage.py revoke-admin-all
  - Behavior: tokens include jti (per-token) and are checked against revoked list; a global fence (iat) revokes all issued at/before the fence.

3.1) Admin 레이트리밋(백엔드/장애 정책)
- 백엔드 선택: `ADMIN_RATE_LIMIT_BACKEND=auto|redis|memory` (기본 `auto`)
  - `auto`: `ADMIN_RATE_LIMIT_REDIS_URL`(또는 `REDIS_URL`)이 있으면 Redis, 없으면 메모리
- 장애(fail) 정책: `ADMIN_RATE_LIMIT_REDIS_POLICY=open|closed|memory` (기본 `open`)
  - `open`: Redis 오류 시 요청을 허용(레이트리밋 미적용)
  - `closed`: Redis 오류 시 차단으로 간주(즉시 초과 처리)
  - `memory`: Redis 오류 시 프로세스-로컬 메모리 백엔드로 폴백(멀티 인스턴스 환경에서는 보수적)


4) Observability
- Request ID: all responses include X-Request-ID.
- Metrics: GET /metrics exposes Prometheus text metrics.
- Structured logs: enable with JSON_LOGS=1.
- Sentry: set SENTRY_DSN (optional). PII headers are scrubbed.
 - PII masking in logs: formatter masks 주민등록번호 패턴(######-#######), 13자리 연속 숫자는 마지막 4자리만 남깁니다.

5) API Contract
- Versioned under /api and /api/v1 (same routes for now).
- Errors: if client sends Accept: application/problem+json, RFC7807 payloads are returned.
- Idempotency-Key for write endpoints is documented in OpenAPI components.

6) Deployment
- Container runs as non-root. Prefer running with read-only rootfs and a writable /tmp mount if possible.
- Health endpoints:
  - /api/livez, /api/readyz, /api/healthz
- Recommended runtime flags (example):
  - docker run --read-only -v /tmp -e PORT=8000 -p 8000:8000 <image>
 - Image: multi-stage build is configured in Dockerfile to minimize runtime surface area.
 - Security scans: run Trivy or equivalent in CI on built image.
 - Runtime hardening (examples):
   - Read-only rootfs + tmpfs mounts: `--read-only -v /tmp --tmpfs /run`
   - Drop capabilities: `--cap-drop=ALL`
   - No new privileges: `--security-opt=no-new-privileges:true`
   - Seccomp: `--security-opt seccomp=./docs/docker/seccomp-minimal.json` (adjust as needed)

7) Static Build/Serving/Cache/Compression
- Build static assets (development): `./.venv/bin/python scripts/build_static.py`
- Docker build runs `scripts/build_static.py` automatically. The image includes `payroll_portal/static/dist/*` and `manifest.json`.
- Runtime serves static at `/static` from `payroll_portal/static`. Templates and UI resolve hashed filenames via `resolve_static(...)` and `manifest.json`.
- Cache strategy:
  - Files are fingerprinted by content hash (e.g., `app.97e7f048e0.js`), safe to cache long-term by CDN.
  - Nonce-based CSP is used for scripts to avoid inline JS. Styles are bundled; avoid inline style attributes where possible.
- Verification:
  - After `docker run`, check `GET /static/dist/manifest.json` and that script/style links in HTML point to hashed `dist/*` paths.
  - CI "Build static assets" step runs to prevent regressions.

Notes on Front-end Build (optional):
- You may adopt Vite/Rollup to produce `dist/manifest.json` with the same mapping keys. If so, build in a Node builder stage and copy into the final image.
- Required: code splitting, minify, optional sourcemaps, and hashed filenames compatible with `resolve_static`.

Compression:
- Reverse proxy (recommended): enable gzip/brotli for `text/*`, `application/json`, `application/javascript`, `text/css`.
  - Nginx example:
    - `gzip on; gzip_comp_level 6; gzip_types text/plain text/css application/json application/javascript;`
    - Brotli (if available): `brotli on; brotli_comp_level 5; brotli_types text/plain text/css application/json application/javascript;`
- App-level (fallback): add Starlette GZipMiddleware in `app/main.py` if proxy is not handling it.
  - `from starlette.middleware.gzip import GZipMiddleware`
  - `application.add_middleware(GZipMiddleware, minimum_size=1024)`

Security scans policy (CI):
- Trivy image scanning runs in CI and fails the pipeline on CRITICAL vulnerabilities.

8) Export Links (Signed/Expiring, optional)
- Set `EXPORT_HMAC_SECRET` to enforce signed, expiring links for `/api/portal/{slug}/export/{year}/{month}`.
- Client must add `exp=<unix_epoch>&sig=<hmac>` to the query string, where:
  - `sig = HMAC_SHA256(EXPORT_HMAC_SECRET, f"/api/portal/{slug}/export/{year}/{month}|{exp}|{company_id}")`
  - If `exp` has passed or `sig` mismatches, API returns 403.
- Without `EXPORT_HMAC_SECRET`, existing links continue to work (non-breaking).

9) Policy Settings (Per Company/Year)
- Table: `policy_settings(company_id nullable, year, policy_json, created_at)` with unique (company_id, year).
- Use to override rounding/step/rates per year/company (e.g., local tax rounding or insurance rounding).
- The calculator loads policy and overlays on defaults; history/audit can be added via app logic.

10) UI Preferences (Company scope)
- Company-scoped UI preferences are stored via `/api/portal/{slug}/ui-prefs`.
- Current usage: `table.columnWidths` (map of field -> width px), `table.fixedCols` (number of leftmost sticky columns), `view.mode` (compact/comfortable).
- The frontend loads these on page load and persists changes (예: 컬럼 헤더 드래그/토글 단축키/툴바 버튼 클릭/페이지 이탈).
    - 단축키: Shift+M(간단 보기), Shift+F(고정 열 수 순환). 동일 기능의 툴바 버튼도 제공됩니다.
    - Extendable: additional keys (e.g., `table.fixedCols`, `view.mode`) can be added without backend changes.

11) 성능 측정/목표(p95)
- 목표 예시(내부망 기준):
  - 월 급여 리스트/상세/저장 p95 < 300~500ms
  - 엑셀 내보내기(1~5만 행) 스트리밍으로 OOM/타임아웃 없이 완료
- 방법:
  - 부하: k6 또는 Locust 사용(샘플은 `scripts/loadtest/` 참조)
  - 계측: `/metrics`(Prometheus) 스크랩 후 Grafana 대시보드로 p95 모니터링
  - 로그: 구조화 JSON 로그에서 `X-Request-ID` 기반 트레이싱
