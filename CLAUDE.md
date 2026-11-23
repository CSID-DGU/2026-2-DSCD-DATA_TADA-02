# DATA TADA Claude Code 작업 규칙

@AGENTS.md

저장소 파일을 변경하면 사용자의 별도 요청 없이 현재 담당자의 개인 브랜치 이름으로 `docs/work-logs/<이니셜>_log.md`를 작성하거나 갱신한다. 예를 들어 `lsg` 브랜치에서는 `docs/work-logs/lsg_log.md`를 사용한다. 파일이 없으면 직접 생성한다. `claude_log.md`나 `codex_log.md`로 대신하지 않는다. 커밋 전에 이번 작업의 로그 항목이 변경 파일과 함께 스테이징됐는지 확인한다.

변경 작업마다 담당자의 이니셜 브랜치에서 `git pull origin main`으로 최신 변경을 반영한다. 충돌을 해결하고 검증한 뒤 작업 로그와 변경 사항을 커밋하고 해당 브랜치에 푸시한다. `main`을 대상으로 하는 PR은 작업자가 GitHub 웹에서 직접 연다.
