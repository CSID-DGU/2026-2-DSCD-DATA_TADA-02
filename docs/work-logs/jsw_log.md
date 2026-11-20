# JSW 작업 로그

## 2026-11-20 개인 브랜치와 커밋 규칙 추가

- 팀원의 작업을 백업하고 병합 전 충돌을 확인하도록 개인 이니셜 브랜치, 커밋 전 `git pull origin main`, 작업별 커밋과 푸시, GitHub 웹에서 `main`으로 PR을 여는 절차를 정리했다.
- [협업 규칙](../../CONTRIBUTING.md)과 함께 [Codex 지침](../../AGENTS.md), [Claude Code 지침](../../CLAUDE.md)을 추가했다.
- `jsw`에 `origin/main`을 반영했고 충돌 없이 동기화했다. 기존 개인용 지침은 로컬 파일에 보존했다.

## 2026-11-20 협업 규칙 및 서버 문서 추가

- 팀원이 함께 수정할 수 있도록 개인별 `<이니셜>_log.md` 기록 규칙과 공유 흐름을 [협업 규칙](../../CONTRIBUTING.md)에 정리했다.
- Git에 등록된 서비스 코드를 기준으로 [서버 구조](../server.md)와 [DB 스키마](../database.md)를 문서화하고 [README](../../README.md)에서 연결했다.
- [Supabase 연결 안내](../supabase-api.md)에 FastAPI를 통한 조회, 연결 환경 변수, Data REST API의 요청과 권한 예시를 추가했다.
- Supabase 테이블 11개와 문서의 컬럼 90개를 대조했다. 문서 링크와 운영 FastAPI의 준비 상태, 상권 목록, 상세 응답을 확인했다. Data REST API는 별도 개발 대상에 적용하는 요청 예시다.
- 이 변경의 범위는 문서와 협업 규칙이다. 운영 배포와 DB 변경은 작업 범위에 포함되지 않는다.
