---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "062. 반응형 디자인 — 브레이크포인트, 유동 레이아웃, 모바일 우선"
date: 2026-06-13
tags: [ui, ux, responsive, breakpoint, mobile-first, fluid-layout, css-grid, flexbox, viewport, tailwind]
summary: "반응형 디자인은 하나의 코드베이스가 모바일부터 데스크탑까지 다양한 화면 크기에서 잘 동작하도록 하는 접근 방식이다. 모바일 우선 설계 원칙, 브레이크포인트 설정 방법, CSS Grid와 Flexbox로 유동적인 레이아웃을 만드는 방법, 그리고 자주 발생하는 문제들을 설명한다."
slug: "062-responsive-design"
categories: ["디자인 시스템"]
---

전 세계 웹 트래픽의 55% 이상이 모바일에서 발생한다. 데스크탑 기준으로 설계하고 모바일을 나중에 맞추는 방식은 거꾸로다. 반응형 디자인은 다양한 화면 크기에서 동등하게 좋은 경험을 제공하는 것이 목표다.

## 모바일 우선 (Mobile First)

모바일 화면 기준으로 먼저 설계하고, 화면이 넓어질수록 레이아웃을 확장한다.

```css
/* 모바일 우선 (기본값 = 모바일) */
.container {
  padding: 16px;
  font-size: 16px;
}

/* 태블릿 이상 */
@media (min-width: 768px) {
  .container {
    padding: 32px;
  }
}

/* 데스크탑 이상 */
@media (min-width: 1024px) {
  .container {
    padding: 64px;
    max-width: 1280px;
    margin: 0 auto;
  }
}
```

반대 방향(데스크탑 기준, 모바일에서 덮어쓰기)은 `max-width` 미디어 쿼리를 쓴다. 이 방식은 특수 케이스가 많아지고 CSS 구조가 복잡해진다.

## 브레이크포인트

고정된 기기 크기에 맞추는 것보다 **콘텐츠가 깨지는 지점**에 브레이크포인트를 두는 것이 더 나은 접근이다. 하지만 실무에서는 팀 공통 기준이 있는 것이 편하다.

```
xs:   < 480px    (소형 모바일)
sm:   480px+     (모바일)
md:   768px+     (태블릿)
lg:   1024px+    (데스크탑)
xl:   1280px+    (와이드 데스크탑)
2xl:  1536px+    (초대형 화면)
```

Tailwind의 기본 브레이크포인트도 이와 유사하다. `sm:`, `md:`, `lg:`, `xl:`, `2xl:` 프리픽스가 각 브레이크포인트 이상에서 적용된다.

```html
<!-- 모바일: 1열, 태블릿: 2열, 데스크탑: 3열 -->
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
  <Card />
  <Card />
  <Card />
</div>
```

## CSS Grid — 2차원 레이아웃

페이지 전체 레이아웃처럼 행과 열을 동시에 제어해야 할 때 강력하다.

```css
/* 12열 그리드 시스템 */
.grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 24px;
}

/* 모바일: 전체 너비 */
.sidebar  { grid-column: span 12; }
.main     { grid-column: span 12; }

/* 데스크탑: 사이드바 3열, 메인 9열 */
@media (min-width: 1024px) {
  .sidebar { grid-column: span 3; }
  .main    { grid-column: span 9; }
}
```

### Auto-fit과 minmax — 자동 반응형

브레이크포인트 없이 자동으로 열 수를 조정하는 패턴이다.

```css
.card-grid {
  display: grid;
  /* 최소 280px, 가능하면 더 넓게 — 공간에 따라 열 수 자동 결정 */
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 24px;
}
```

컨테이너가 900px면 3열(280+280+280+여백), 600px면 2열, 400px면 1열로 자동 조정된다. 미디어 쿼리 없이 카드 그리드가 반응형이 된다.

## Flexbox — 1차원 레이아웃

단일 행 또는 열 방향 배치에 적합하다. 내비게이션, 버튼 그룹, 카드 내부 레이아웃에 많이 쓴다.

```css
/* 네비게이션: 모바일에서 세로, 데스크탑에서 가로 */
.nav {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

@media (min-width: 768px) {
  .nav {
    flex-direction: row;
    align-items: center;
    gap: 24px;
  }
}
```

### flex-wrap으로 유동적 배치

```css
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
/* 태그가 많으면 자동으로 다음 줄로 넘어감 */
```

## 텍스트와 이미지 반응형

### 유동 타이포그래피

058에서 다룬 `clamp()`로 화면 크기에 따라 자동으로 조절된다.

```css
h1 { font-size: clamp(1.75rem, 4vw, 3rem); }
p  { font-size: clamp(0.9rem, 2vw, 1rem); }
```

### 반응형 이미지

```html
<!-- 뷰포트에 따라 다른 이미지 소스 -->
<picture>
  <source media="(min-width: 1024px)" srcset="hero-large.webp" />
  <source media="(min-width: 768px)"  srcset="hero-medium.webp" />
  <img src="hero-small.webp" alt="히어로 이미지" />
</picture>

<!-- 컨테이너 너비에 맞게 자동 조절 -->
<img src="photo.jpg" style="width: 100%; height: auto;" alt="..." />
```

## 자주 발생하는 문제

### 고정 너비 요소

```css
/* 모바일에서 화면 밖으로 삐져나옴 */
.box { width: 600px; }

/* 반응형 */
.box { width: min(600px, 100%); }
/* 또는 */
.box { max-width: 600px; width: 100%; }
```

### 터치 타깃 너무 작음

데스크탑에서는 8px짜리 링크를 클릭할 수 있지만, 모바일에서는 손가락으로 정확히 누르기 어렵다.

```css
/* 터치 타깃 최소 크기 보장 */
.small-link {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  padding: 8px 12px;
}
```

### 가로 스크롤 발생

```css
/* 전체 페이지 가로 스크롤 방지 */
html, body {
  overflow-x: hidden;
}

/* 컨테이너 너비 제한 */
* {
  box-sizing: border-box;
}
```

### 뷰포트 설정 누락

```html
<!-- HTML head에 반드시 포함 -->
<meta name="viewport" content="width=device-width, initial-scale=1" />
```

이 태그 없이는 모바일 브라우저가 페이지를 데스크탑 크기로 렌더링하고 축소해서 보여준다.

## 트레이드오프

브레이크포인트가 너무 많으면 관리가 복잡해진다. 3~4개 브레이크포인트로 충분한 경우가 대부분이다. 각 브레이크포인트에서 레이아웃이 극적으로 달라지는 것보다, `auto-fit`이나 `flex-wrap`으로 자연스럽게 흘러가도록 설계하면 브레이크포인트가 줄어든다.

반응형 디자인은 "더 작은 화면에 맞추기"가 아니라 "모든 화면에서 콘텐츠를 잘 전달하기"다. 모바일에서 데스크탑 레이아웃을 억지로 압축하는 것보다, 모바일에 맞는 정보 구조와 탐색 방식을 별도로 설계하는 것이 더 좋은 경험을 만든다.
