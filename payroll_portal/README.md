급여 요청 포털 (간이)

개요
- 세무사가 고객사별 월별 급여 입력을 요청하고, 입력 데이터를 엑셀로 다운로드하는 간단한 포털입니다.
- 회사별 전용 접속코드로만 접근 가능하도록 분리되어 있습니다.

구성
- Python + Flask + SQLite + SQLAlchemy + openpyxl
- DB 파일: `payroll_portal/app.db`

설치
1) 가상환경(선택):
   python -m venv .venv
   source .venv/bin/activate  (Windows: .venv\\Scripts\\activate)

2) 패키지 설치:
   pip install -r requirements.txt

3) 환경변수 설정:
   - 관리자 로그인 비밀번호
     Linux/macOS: export ADMIN_PASSWORD=원하는비번
     Windows(PowerShell): $env:ADMIN_PASSWORD="원하는비번"
   - 세션 키(선택): export SECRET_KEY=임의의랜덤문자열
   - 스키마 자동생성(개발용): 기본값 1. 운영에서는 `export PAYROLL_AUTO_APPLY_DDL=0`

실행
   python -m flask --app payroll_portal.app run --debug
   브라우저에서 http://127.0.0.1:5000 접속

사용 흐름
1) 관리자 로그인 후 회사 생성(회사명, 슬러그)
   - 생성 시 표시되는 접속코드를 해당 회사에 전달합니다(1회 표시).
   - 재발급 가능: 회사 상세 > 접속코드 재발급
2) 회사는 /portal/{slug}/login 에서 접속코드로 로그인
3) 해당 월 선택 후 급여표 입력/저장
4) 엑셀 다운로드로 제출용 파일 저장

보안/운영 주의사항
- 접속코드는 안전한 방식(예: 별도 채널)으로 전달하세요.
- 운영 환경에서는 충분히 긴 `SECRET_KEY` 설정, HTTPS, 리버스 프록시, 백업 등을 권장합니다.
