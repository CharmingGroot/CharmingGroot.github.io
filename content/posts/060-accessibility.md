---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "060. 접근성(a11y) — 색상 대비, 키보드 내비게이션, ARIA"
date: 2026-06-13
tags: [ui, ux, accessibility, a11y, wcag, aria, keyboard, color-contrast, screen-reader, inclusive-design]
summary: "접근성은 장애가 있는 사용자를 위한 것이기도 하지만, 동시에 모든 사용자의 경험을 개선한다. 색상 대비 기준, 키보드만으로 이동 가능한 UI, 스크린 리더를 위한 ARIA 속성, 그리고 실무에서 가장 자주 놓치는 접근성 체크포인트를 설명한다."
slug: "060-accessibility"
categories: ["디자인 시스템"]
---

접근성(Accessibility, a11y)은 시각, 청각, 운동, 인지 장애가 있는 사용자가 제품을 쓸 수 있게 하는 설계다. 하지만 접근성을 높이면 장애가 없는 사용자도 혜택을 받는다. 고대비 모드는 밝은 햇빛 아래서 화면을 보는 사람에게도 도움이 되고, 키보드 내비게이션은 파워 유저의 생산성을 높인다.

WCAG(Web Content Accessibility Guidelines) 2.1이 국제 표준이다. A(최소), AA(표준), AAA(최고) 세 등급이 있고, 대부분의 서비스는 AA를 목표로 한다.

## 색상 대비

시각 장애나 색맹이 있는 사용자는 대비가 낮은 텍스트를 읽기 어렵다. WCAG AA 기준:

```
일반 텍스트 (18px 미만 또는 Bold 14px 미만):  대비율 4.5:1 이상
큰 텍스트 (18px 이상 또는 Bold 14px 이상):    대비율 3:1 이상
UI 컴포넌트, 그래픽:                           대비율 3:1 이상
```

대비율은 밝기(luminance)의 비율이다. 흰 배경(1.0)에 순수 검정(0.0)은 21:1로 최고 대비다.

```
# 흔히 실패하는 사례
배경: #FFFFFF (흰색)
텍스트: #9CA3AF (회색) → 대비율 2.85:1 ← AA 실패

배경: #FFFFFF
텍스트: #6B7280 (더 진한 회색) → 대비율 4.61:1 ← AA 통과

# 브랜드 컬러 사용 시
배경: #3B82F6 (파란색)
텍스트: #FFFFFF (흰색) → 대비율 3.07:1 ← 큰 텍스트만 AA 통과
텍스트: #1E3A8A (진한 파란색) → 대비율 4.73:1 ← AA 통과
```

Figma, Chrome DevTools, axe 같은 도구로 자동으로 확인할 수 있다. 디자인 단계에서 잡는 것이 개발 후 수정보다 훨씬 쉽다.

색상만으로 정보를 전달하면 안 된다. 오류 상태를 빨간색으로만 표시하면 적녹 색맹 사용자는 알 수 없다. 아이콘이나 텍스트를 함께 쓴다.

```tsx
// 나쁜 예: 색상만으로 오류 표시
<Input style={{ borderColor: 'red' }} />

// 좋은 예: 색상 + 아이콘 + 텍스트
<Input
  error
  style={{ borderColor: 'var(--color-danger)' }}
/>
<span>
  <ErrorIcon aria-hidden="true" />
  이메일 형식이 올바르지 않습니다
</span>
```

## 키보드 내비게이션

마우스를 쓸 수 없는 사용자는 키보드만으로 모든 기능에 접근할 수 있어야 한다.

**Tab 순서**: Tab 키로 포커스가 이동하는 순서가 시각적 레이아웃과 일치해야 한다. CSS로 시각적 순서를 바꿔도 DOM 순서가 논리적이어야 한다.

**포커스 표시**: 포커스된 요소가 시각적으로 명확히 보여야 한다. 브라우저 기본 outline을 `outline: none`으로 없애는 경우가 많은데, 반드시 대체 스타일을 제공해야 한다.

```css
/* 나쁜 예: 포커스 표시 제거 */
*:focus { outline: none; }

/* 좋은 예: 대체 포커스 스타일 */
*:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
  border-radius: 4px;
}
/* :focus-visible은 마우스 클릭 시에는 적용 안 되고 키보드 포커스 시에만 적용됨 */
```

**키보드 트랩**: 모달이 열렸을 때 Tab이 모달 밖으로 나가면 안 된다. 모달 내부에서 Tab이 순환해야 한다. 반대로 모달을 닫으면 포커스가 모달을 열었던 버튼으로 돌아와야 한다.

**Escape 키**: 모달, 드롭다운, 팝오버는 Escape로 닫혀야 한다.

## ARIA

HTML 기본 요소가 의미를 충분히 전달하지 못할 때 ARIA(Accessible Rich Internet Applications) 속성으로 보완한다.

```tsx
// 커스텀 버튼처럼 동작하는 div
<div
  role="button"
  tabIndex={0}
  aria-pressed={isActive}
  onClick={handleClick}
  onKeyDown={(e) => e.key === 'Enter' && handleClick()}
>
  좋아요
</div>

// 아이콘만 있는 버튼 — 스크린 리더에게 의미 전달
<button aria-label="검색">
  <SearchIcon aria-hidden="true" />
</button>

// 로딩 상태 알림
<button aria-busy={isLoading} disabled={isLoading}>
  {isLoading ? '저장 중...' : '저장'}
</button>

// 오류 메시지 연결
<input
  id="email"
  aria-describedby="email-error"
  aria-invalid={hasError}
/>
<p id="email-error" role="alert">
  이메일 형식이 올바르지 않습니다
</p>
```

`role="alert"`는 스크린 리더가 즉시 읽어준다. 폼 제출 오류나 토스트 알림에 적합하다.

**ARIA 사용 원칙**: 가능하면 HTML 기본 요소를 쓰는 것이 낫다. `<button>`이 `<div role="button">`보다 기본 동작(키보드 포커스, Enter/Space 작동)을 다 해준다. ARIA는 기본 HTML로 표현할 수 없는 경우에만 쓴다.

## 실무에서 자주 놓치는 항목

**이미지 alt 텍스트**: 의미 있는 이미지는 내용을 설명하는 alt를 쓴다. 장식용 이미지는 `alt=""`로 스크린 리더가 건너뛰게 한다.

```tsx
// 의미 있는 이미지
<img src="profile.jpg" alt="홍길동 프로필 사진" />

// 장식용 이미지 (건너뜀)
<img src="decoration.svg" alt="" aria-hidden="true" />
```

**폼 레이블**: 모든 input에 label이 연결돼야 한다. placeholder만 쓰면 안 된다. placeholder는 타이핑을 시작하면 사라져 무엇을 입력하는지 잊게 만든다.

```tsx
// 나쁜 예
<input placeholder="이메일을 입력하세요" />

// 좋은 예
<label htmlFor="email">이메일</label>
<input id="email" placeholder="example@email.com" />
```

**동적 콘텐츠 알림**: 페이지 이동 없이 콘텐츠가 바뀌면 스크린 리더가 모른다. `aria-live` 영역으로 변경을 알린다.

```tsx
<div aria-live="polite" aria-atomic="true">
  {statusMessage}  {/* 장바구니에 추가됐습니다 등 */}
</div>
```

## 트레이드오프

접근성은 나중에 추가하기 어렵다. DOM 구조, 포커스 관리, 색상 시스템에 영향을 미치므로 처음부터 고려해야 한다. 시맨틱 HTML(`<button>`, `<nav>`, `<main>`, `<h1>~<h6>`)을 올바르게 쓰는 것만으로도 기본 접근성의 80%가 해결된다.

자동화 도구(axe, Lighthouse)로 접근성 이슈를 찾을 수 있지만, 자동으로 발견할 수 있는 이슈는 전체의 30~40%에 불과하다. 실제 스크린 리더(VoiceOver, NVDA)로 직접 테스트하는 과정이 필요하다.
