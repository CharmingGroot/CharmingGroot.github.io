# CharmingGroot.github.io

Hugo + PaperMod 기반 학습 노트 블로그. https://charminggroot.github.io

## 글 쓰는 법

글 원본은 이 레포가 아니라 로컬 볼트(`~/Documents/정리`)에 있다. 거기서 마크다운을 쓰고,
동기화 스크립트로 블로그 `content/posts/`에 복사한 뒤 push 하면 GitHub Actions가 빌드·배포한다.

```bash
# 1. 볼트에서 글 작성/수정 (~/Documents/정리/보안/*.md 등)
#    아직 미완성이면 frontmatter에 draft: true → 발행에서 제외됨

# 2. 로컬 미리보기 (선택)
python3 scripts/sync.py && hugo server

# 3. 발행 — sync + commit + push 한 번에 (GitHub Actions가 배포)
scripts/publish.sh "post: 제목"
```

Claude Code에서는 "블로그 올려줘"라고 하면 `publish-blog` 스킬이 위 발행을 실행한다.

## 공개 범위 늘리기

`scripts/sync.py`의 `SOURCES`에 볼트 glob을 추가하고, 필요하면 `SLUG_MAP`에 영문 slug를 넣는다.
매핑이 없으면 파일명 숫자로 자동 slug가 생성된다.

## 구조

- `content/posts/` — sync.py가 생성 (frontmatter에 `generated-by` 마커, 직접 수정 금지)
- `hugo.toml` — 사이트 설정
- `themes/PaperMod` — 테마 (git submodule)
- `.github/workflows/hugo.yml` — 빌드·배포
