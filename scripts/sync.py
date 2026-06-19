#!/usr/bin/env python3
"""볼트(/Users/hg/Documents/정리)의 노트를 Hugo content/posts/로 동기화한다.

- 한글 파일명 → 깔끔한 영문 slug 주입 (URL이 percent-encoding 되는 것 방지)
- 번호 범위로 카테고리 자동 부여 (볼트 원본은 안 건드림)
- frontmatter는 원본 그대로 두고 slug / categories 줄만 추가
- draft: true 인 글은 건너뜀
- 매 실행마다 생성물(GENERATED 마커가 붙은 파일)을 지우고 다시 만들어 idempotent

확장: SOURCES에 (glob, category) 추가. 한글 파일명이면 SLUG_MAP에 영문 slug를 넣고,
영문 파일명이면 파일명을 그대로 slug로 쓴다. 특정 파일은 EXCLUDE로 뺀다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

VAULT = Path("/Users/hg/Documents/정리")
POSTS = Path(__file__).resolve().parent.parent / "content" / "posts"

# 올릴 대상: (볼트 기준 glob, 카테고리).
# 카테고리가 "by_range" 면 파일명 앞 번호를 CATEGORY_RANGES로 매핑한다.
SOURCES = [
    ("보안/*.md", "보안"),
    ("[0-9]*.md", "by_range"),
]

# 발행에서 제외할 파일 (stem 기준)
EXCLUDE = {
    "037-skillspector",
}

# 번호 범위 → 카테고리 (by_range 소스에 적용)
CATEGORY_RANGES = [
    (6, 10, "네트워크 기초"),
    (11, 33, "쿠버네티스"),
    (34, 47, "클라우드 인프라"),
    (48, 55, "IaC · 플랫폼"),
    (56, 62, "디자인 시스템"),
    (63, 63, "쿠버네티스"),  # k8s 부하 테스트
    (64, 95, "AI · ML"),
]

# 한글 파일명 → 영문 slug (영문 파일명은 파일명을 그대로 slug로 씀)
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


def leading_number(stem: str) -> int | None:
    m = re.match(r"(\d{1,3})", stem)
    return int(m.group(1)) if m else None


def derive_slug(stem: str) -> str:
    if stem in SLUG_MAP:
        return SLUG_MAP[stem]
    if stem.isascii():  # 영문 파일명(006-json-rpc 등)은 그대로 slug
        return stem
    n = leading_number(stem)
    return f"post-{n}" if n is not None else stem


def resolve_category(stem: str, source_category: str) -> str | None:
    if source_category != "by_range":
        return source_category
    n = leading_number(stem)
    if n is None:
        return None
    for lo, hi, cat in CATEGORY_RANGES:
        if lo <= n <= hi:
            return cat
    return None


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


def inject(fm: str, slug: str, category: str | None) -> str:
    drop = ("slug:", "categories:")
    lines = [ln for ln in fm.splitlines() if not ln.startswith(drop)]
    lines.append(f'slug: "{slug}"')
    if category:
        lines.append(f'categories: ["{category}"]')
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
    seen: set[str] = set()
    for glob, source_category in SOURCES:
        for src in sorted(VAULT.glob(glob)):
            if src.stem in EXCLUDE:
                print(f"  건너뜀(제외): {src.name}", file=sys.stderr)
                continue
            raw = src.read_text(encoding="utf-8")
            sp = split_frontmatter(raw)
            if sp is None:
                print(f"  건너뜀(frontmatter 없음): {src.name}", file=sys.stderr)
                continue
            fm, body = sp
            if re.search(r"^draft:\s*true\b", fm, re.MULTILINE):
                print(f"  건너뜀(draft): {src.name}", file=sys.stderr)
                continue
            slug = derive_slug(src.stem)
            if slug in seen:
                print(f"  경고: slug 충돌 '{slug}' ({src.name}) — 건너뜀", file=sys.stderr)
                continue
            seen.add(slug)
            category = resolve_category(src.stem, source_category)
            new_fm = inject(fm, slug, category)
            out = f"---\n{GENERATED_MARK}\n{new_fm}\n---\n\n{body}"
            (POSTS / f"{slug}.md").write_text(out, encoding="utf-8")
            cat_label = f"[{category}]" if category else "[미분류]"
            print(f"  {cat_label} {src.name}  ->  posts/{slug}.md")
            count += 1

    print(f"\n동기화 완료: {count}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
