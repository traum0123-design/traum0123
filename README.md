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
pip install -r payroll_portal/requirements.txt
export ADMIN_PASSWORD=changeme     # 필수
export SECRET_KEY=dev-secret       # 선택 (추천)
uvicorn app.main:app --reload
```

브라우저에서 <http://127.0.0.1:8000> 접속 후:
1. `/admin/login`에서 관리자 로그인
2. 새 회사 생성 → 발급받은 접속코드로 `/portal/{slug}/login` 접속
3. 급여표 입력/저장, 엑셀 다운로드, 마감 테스트 진행

## 테스트

현재 저장소에는 핵심 계산/엑셀 로직에 대한 기본 테스트가 포함됩니다.

```bash
python3 -m compileall app core gateway payroll_api tests   # 최소 문법 검증
# pytest 실행 시에는 openpyxl, sqlalchemy 등 의존성 설치 필요
pytest tests/test_payroll_service.py tests/test_excel_export.py
```

## QA 체크리스트

수동 점검이 필요한 주요 흐름(관리자 회사 생성, 포털 급여 저장/마감, 토큰 검증 등)은 `docs/QA_CHECKLIST.md`를 참고하세요. 점검 시 발견된 사항은 문서에 주석으로 남기고, 필요한 경우 테스트 추가를 권장합니다.
