#!/usr/bin/env bash
# 볼트(~/Documents/정리) 글을 블로그로 발행한다: sync → commit → push.
# 배포는 GitHub Actions가 자동으로 한다.
#
# 사용:
#   scripts/publish.sh                # 변경된 글 제목으로 자동 커밋 메시지
#   scripts/publish.sh "post: ..."    # 커밋 메시지 직접 지정
#
# draft: true 인 글은 sync 단계에서 걸러져 발행되지 않는다.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

echo "[1/4] 볼트 → content 동기화"
python3 scripts/sync.py

echo "[2/4] 변경 확인"
git add -A
if git diff --cached --quiet; then
  echo "변경 없음 — 발행할 글이 없습니다."
  exit 0
fi
git diff --cached --name-status

echo "[3/4] 커밋"
if [ "$#" -ge 1 ] && [ -n "${1:-}" ]; then
  MSG="$1"
else
  CHANGED="$(git diff --cached --name-only -- content/posts \
    | xargs -n1 basename 2>/dev/null | sed 's/\.md$//' | paste -sd', ' - || true)"
  MSG="post: ${CHANGED:-update}"
fi
git commit -q -m "$MSG"
echo "  → $MSG"

echo "[4/4] 푸시"
git push -q origin main
echo "완료. GitHub Actions가 1~2분 내 배포합니다 → https://charminggroot.github.io"
