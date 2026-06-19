#!/usr/bin/env python3
"""볼트(/Users/hg/Documents/정리)의 노트를 Hugo content/posts/로 동기화한다.

- 한글 파일명 → 깔끔한 영문 slug 주입 (URL이 percent-encoding 되는 것 방지)
- frontmatter는 원본 그대로 두고 slug 한 줄만 추가
- 매 실행마다 생성물(GENERATED 마커가 붙은 파일)을 지우고 다시 만들어 idempotent

확장: 다른 폴더/노트도 올리려면 SOURCES에 (glob, slug_prefix)를 추가하고
필요하면 SLUG_MAP에 파일별 영문 slug를 넣는다. 매핑이 없으면 prefix-번호로 자동 생성.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

VAULT = Path("/Users/hg/Documents/정리")
POSTS = Path(__file__).resolve().parent.parent / "content" / "posts"

# (볼트 기준 glob, slug prefix) — 올릴 대상
SOURCES = [
    ("보안/*.md", "security"),
]

# 파일 stem → 영문 slug. 없으면 prefix + 숫자로 자동 생성.
SLUG_MAP = {
    "보안-00-런타임보안-생태계": "runtime-security-ecosystem",
    "보안-01-falco-기초": "falco-basics",
    "보안-02-falco-심화": "falco-advanced",
    "보안-03-sigma-기초": "sigma-basics",
    "보안-04-sigma-심화": "sigma-advanced",
    "보안-05-정적분석-ai보안-기초": "static-analysis-ai-security",
    "보안-06-sql-injection": "sql-injection",
}

# frontmatter 안에 넣는 YAML 주석. Hugo는 무시하고, clean_generated()가 이 줄로 생성물을 식별한다.
GENERATED_MARK = "# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요"


def derive_slug(stem: str, prefix: str) -> str:
    if stem in SLUG_MAP:
        return SLUG_MAP[stem]
    m = re.search(r"(\d{1,3})", stem)
    return f"{prefix}-{m.group(1)}" if m else f"{prefix}-{stem}"


def split_frontmatter(text: str) -> tuple[str, str] | None:
    """--- ... --- 블록과 본문을 분리. 실패 시 None."""
    if not text.startswith("---"):
        return None
    parts = text.split("\n---", 1)
    if len(parts) != 2:
        return None
    fm = parts[0][3:].lstrip("\n")  # 첫 '---' 제거
    body = parts[1].lstrip("\n")
    return fm, body


def inject_slug(fm: str, slug: str) -> str:
    lines = [ln for ln in fm.splitlines() if not ln.startswith("slug:")]
    lines.append(f'slug: "{slug}"')
    return "\n".join(lines)


def clean_generated() -> None:
    if not POSTS.exists():
        return
    for f in POSTS.glob("*.md"):
        if f.name == "_index.md":
            continue
        if GENERATED_MARK in f.read_text(encoding="utf-8"):
            f.unlink()


def main() -> int:
    POSTS.mkdir(parents=True, exist_ok=True)
    clean_generated()

    count = 0
    for glob, prefix in SOURCES:
        for src in sorted(VAULT.glob(glob)):
            raw = src.read_text(encoding="utf-8")
            sp = split_frontmatter(raw)
            if sp is None:
                print(f"  건너뜀(frontmatter 없음): {src.name}", file=sys.stderr)
                continue
            fm, body = sp
            slug = derive_slug(src.stem, prefix)
            new_fm = inject_slug(fm, slug)
            out = f"---\n{GENERATED_MARK}\n{new_fm}\n---\n\n{body}"
            dest = POSTS / f"{slug}.md"
            dest.write_text(out, encoding="utf-8")
            print(f"  {src.name}  ->  posts/{slug}.md")
            count += 1

    print(f"\n동기화 완료: {count}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
