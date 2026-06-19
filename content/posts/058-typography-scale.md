---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "058. 타이포그래피 스케일 — 폰트 크기 체계와 가독성"
date: 2026-06-13
tags: [ui, ux, typography, font-size, line-height, font-weight, readability, scale, design-token]
summary: "타이포그래피는 텍스트가 어떻게 보이는지를 결정한다. 폰트 크기, 행간, 자간, 굵기를 체계 없이 쓰면 화면마다 느낌이 달라지고 위계가 흐려진다. 타이포그래피 스케일로 크기 체계를 정하고, 가독성 좋은 line-height를 설정하고, 웹에서 반응형 타이포그래피를 구현하는 방법을 설명한다."
slug: "058-typography-scale"
categories: ["디자인 시스템"]
---

텍스트는 UI에서 대부분의 정보를 전달한다. 타이포그래피가 일관되지 않으면 사용자는 무엇이 제목이고 무엇이 본문인지 직관적으로 파악하기 어렵다. 폰트 크기를 12, 13, 14, 15, 16px처럼 비슷하게 쓰면 위계가 없어 보인다. 반대로 체계적인 스케일은 정보 구조를 시각적으로 명확하게 전달한다.

## 타이포그래피 스케일

일정한 비율로 증가하는 크기 단계를 정의한다. 흔히 쓰는 비율은 **1.25(Major Third)** 와 **1.333(Perfect Fourth)** 다.

```
# Major Third (×1.25) 스케일
xs:   12px
sm:   14px
base: 16px   ← 기준점
lg:   18px
xl:   20px
2xl:  24px
3xl:  30px
4xl:  36px
5xl:  48px
6xl:  60px
```

각 단계가 뚜렷하게 차이 나므로 시각적 위계가 자연스럽게 생긴다. 14px와 15px는 너무 비슷해서 구분이 어렵지만, 14px와 18px는 명확히 다르다.

Tailwind CSS의 기본 타이포그래피 스케일이 이 방식을 따른다.

## 사용처 매핑

스케일을 정했으면 각 크기가 어디에 쓰이는지 의미를 부여한다.

```
xs   (12px): 캡션, 레이블, 법적 고지
sm   (14px): 보조 텍스트, 메타 정보, 폼 힌트
base (16px): 본문, 기본 UI 텍스트
lg   (18px): 서브타이틀, 강조 본문
xl   (20px): 소제목 (H3)
2xl  (24px): 제목 (H2)
3xl  (30px): 대제목 (H1, 모바일)
4xl  (36px): 히어로 제목 (데스크탑)
5xl+ (48px~): 랜딩 페이지 대형 헤드라인
```

"이 텍스트는 24px를 써야지"가 아니라 "이건 H2니까 `text-2xl`을 쓰면 된다"로 생각하게 된다.

## Line-height — 행간

가독성에서 font-size만큼 중요한 것이 line-height다. 행간이 너무 좁으면 글이 답답하고, 너무 넓으면 연결성이 끊긴다.

```css
/* 일반적인 가이드라인 */
제목 (큰 텍스트):  line-height: 1.1 ~ 1.25   /* 타이트하게 */
소제목:            line-height: 1.25 ~ 1.375
본문:              line-height: 1.5 ~ 1.75    /* 여유롭게 */
UI 레이블/버튼:    line-height: 1.0 ~ 1.25   /* 딱 맞게 */
```

큰 텍스트는 행간을 좁게 잡아야 자연스럽다. 48px 제목에 line-height: 1.5를 주면 줄 간격이 너무 벌어진다. 반대로 16px 본문에 line-height: 1.2는 너무 촘촘하다.

```css
/* Tailwind 기준 */
.text-4xl { font-size: 2.25rem; line-height: 2.5rem; }   /* leading-10 */
.text-base { font-size: 1rem;   line-height: 1.5rem; }    /* leading-6 */
```

## Font Weight — 굵기로 위계 표현

크기와 함께 굵기도 위계를 만드는 데 중요하다.

```
400 (Regular):  본문, 일반 UI 텍스트
500 (Medium):   강조 본문, 네비게이션 아이템
600 (Semibold): 소제목, 버튼 레이블
700 (Bold):     제목, 주요 강조
800+ (Extrabold): 히어로 헤드라인
```

크기와 굵기를 함께 조정하면 위계가 더 명확해진다.

```css
/* H1: 크고 굵게 */
h1 { font-size: 2.25rem; font-weight: 700; line-height: 1.2; }

/* H2: 중간 크기, 세미볼드 */
h2 { font-size: 1.5rem;  font-weight: 600; line-height: 1.3; }

/* 본문: 기본 크기, 레귤러 */
p  { font-size: 1rem;    font-weight: 400; line-height: 1.6; }
```

## 반응형 타이포그래피

모바일에서 데스크탑 크기의 제목을 그대로 쓰면 너무 작거나 너무 크다. 두 가지 방법이 있다.

### Breakpoint 기반

```css
h1 {
  font-size: 1.875rem;  /* 모바일: 30px */
}

@media (min-width: 768px) {
  h1 {
    font-size: 2.25rem;  /* 태블릿: 36px */
  }
}

@media (min-width: 1024px) {
  h1 {
    font-size: 3rem;     /* 데스크탑: 48px */
  }
}
```

### Fluid Typography — clamp()

뷰포트 너비에 따라 부드럽게 변하는 폰트 크기다. 특정 breakpoint에서 갑자기 바뀌지 않는다.

```css
h1 {
  /* 뷰포트 320px에서 30px, 1200px에서 48px 사이를 부드럽게 변환 */
  font-size: clamp(1.875rem, 4vw + 0.5rem, 3rem);
}
```

`clamp(최솟값, 이상적인값, 최댓값)` — 뷰포트가 좁으면 최솟값, 넓으면 최댓값, 그 사이는 비율에 따라 유동적으로 결정된다.

## 가독성 — 한 줄 너비

타이포그래피에서 자주 간과되는 것이 텍스트 너비다. 한 줄이 너무 길면 다음 줄 시작점을 찾기 어렵다.

```
이상적인 한 줄 길이: 45~75자 (한국어는 약 25~40자)
CSS: max-width: 65ch   /* ch = 해당 폰트의 '0' 글자 너비 */
```

```css
article p {
  max-width: 65ch;
}
```

전체 레이아웃을 넓게 잡더라도 본문 텍스트는 `max-width`로 읽기 편한 너비로 제한한다.

## 트레이드오프

스케일 단계가 너무 많으면 "어떤 크기를 써야 하지" 고민이 늘어난다. 10개보다 6~7개 단계가 일반적으로 충분하다. 스케일 밖의 크기가 필요하다고 느껴지면, 스케일을 무시하는 것이 아니라 스케일을 보완할지를 먼저 논의한다.

시스템 폰트(San Francisco, Segoe UI)와 커스텀 웹폰트는 같은 크기여도 실제 보이는 크기가 다를 수 있다. 폰트를 바꿀 때 스케일 전체를 다시 검토해야 할 수 있다.
