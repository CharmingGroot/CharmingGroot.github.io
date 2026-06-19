---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "059. 간격 시스템 — 8pt Grid와 공간으로 위계 만들기"
date: 2026-06-13
tags: [ui, ux, spacing, grid, 8pt, layout, padding, margin, design-token, visual-hierarchy]
summary: "간격이 일관되지 않으면 화면이 어수선해 보인다. 8pt 그리드 시스템은 모든 간격을 8의 배수로 정의해 시각적 일관성을 만든다. 간격이 정보 구조를 표현하는 방식, 컴포넌트 내부와 외부 간격의 차이, 그리고 레이아웃 컴포넌트로 간격을 관리하는 방법을 설명한다."
slug: "059-spacing-system"
categories: ["디자인 시스템"]
---

두 요소가 얼마나 가까이 있는가는 그 둘이 얼마나 관련 있는가를 암시한다. 제목과 그 아래 본문은 가깝고, 다음 섹션과는 멀어야 한다. 이 **근접의 원칙(Law of Proximity)** 이 간격 시스템의 기반이다.

간격을 임의로 정하면 화면마다 다른 느낌이 나고 위계가 흐려진다. 14px, 15px, 16px, 18px처럼 비슷한 값들이 섞이면 보는 사람은 구분을 못 한다.

## 8pt 그리드

모든 간격을 **8의 배수**로 정의하는 시스템이다. 대부분의 기기가 8로 나눠지는 해상도를 가져 픽셀이 깔끔하게 떨어지고, 디자이너와 개발자가 같은 기준으로 소통할 수 있다.

```
spacing-1:  4px   (8의 절반, 아주 좁은 간격)
spacing-2:  8px
spacing-3:  12px
spacing-4:  16px
spacing-5:  20px
spacing-6:  24px
spacing-8:  32px
spacing-10: 40px
spacing-12: 48px
spacing-16: 64px
spacing-20: 80px
spacing-24: 96px
```

4px는 8의 절반으로, 아이콘과 텍스트 사이처럼 아주 좁은 간격에 쓴다. Tailwind가 이 체계를 그대로 따른다.

## 간격으로 위계 표현

간격의 크기가 관계의 강도를 나타낸다. 가까울수록 관련 있고, 멀수록 독립적이다.

```
[섹션 제목]        ← 위 섹션과 32px 떨어짐
                   ← 아래 내용과 8px 붙어있음
[섹션 내용 1]
                   ← 같은 섹션 내 항목 간격 16px
[섹션 내용 2]
                   ← 다음 섹션과 32px 떨어짐
[다음 섹션 제목]
```

제목 위는 크게, 제목 아래는 작게 → 제목이 아래 내용과 묶여 보인다. 이것이 여백으로 그룹을 만드는 방식이다.

## 컴포넌트 내부 간격 (Padding)

컴포넌트 안의 여백은 컴포넌트의 밀도를 결정한다. 버튼, 카드, 인풋처럼 상호작용 가능한 요소는 충분한 padding이 필요하다.

```css
/* 버튼 크기별 padding */
.btn-sm  { padding: 6px 12px;  }   /* 4+8, 8+4 */
.btn-md  { padding: 8px 16px;  }   /* 8, 16 */
.btn-lg  { padding: 12px 24px; }   /* 12, 24 */

/* 카드 */
.card { padding: 16px; }           /* 내부 여백 */
.card-header { padding: 16px 16px 12px; }
.card-body   { padding: 0 16px 16px;   }
```

모바일에서 터치 타깃은 최소 44×44px 이상이 권장된다(Apple HIG 기준). 텍스트가 작아도 padding을 충분히 줘서 터치 영역을 확보한다.

## 컴포넌트 외부 간격 (Margin)

컴포넌트 외부 여백은 레이아웃에서 다른 요소와의 관계를 정의한다. 하지만 컴포넌트에 margin을 직접 넣으면 재사용이 어려워진다.

```tsx
// 나쁜 예: 컴포넌트에 margin이 박힘
const Button = () => (
  <button style={{ marginTop: 16 }}>저장</button>
)

// 좋은 예: 컴포넌트는 margin 없이, 레이아웃 컴포넌트가 간격 담당
const Form = () => (
  <Stack gap={16}>
    <Input />
    <Button>저장</Button>
  </Stack>
)
```

## 레이아웃 컴포넌트

간격을 직접 margin으로 주는 대신, 간격을 담당하는 레이아웃 컴포넌트를 만든다.

```tsx
// Stack: 세로 방향 간격
const Stack = ({ gap, children }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap }}>
    {children}
  </div>
)

// Inline: 가로 방향 간격
const Inline = ({ gap, align, children }) => (
  <div style={{ display: 'flex', alignItems: align, gap }}>
    {children}
  </div>
)

// Grid: 그리드 레이아웃
const Grid = ({ columns, gap, children }) => (
  <div style={{
    display: 'grid',
    gridTemplateColumns: `repeat(${columns}, 1fr)`,
    gap
  }}>
    {children}
  </div>
)
```

```tsx
// 사용
<Stack gap={24}>
  <Inline gap={8} align="center">
    <Icon name="user" />
    <Text>홍길동</Text>
  </Inline>
  <Grid columns={3} gap={16}>
    <Card />
    <Card />
    <Card />
  </Grid>
</Stack>
```

컴포넌트는 margin 없이 만들고, 배치는 레이아웃 컴포넌트가 담당한다. 같은 컴포넌트를 다른 간격으로 배치하고 싶을 때 컴포넌트를 바꾸지 않아도 된다.

## 페이지 레이아웃 간격

페이지 전체에서 반복되는 간격 패턴도 정의해둔다.

```
섹션 간격 (section-gap):      64px ~ 96px
컨텐츠 그룹 간격:              32px ~ 48px
관련 요소 간격:                16px ~ 24px
인라인 요소 간격:              8px ~ 12px
아이콘-텍스트 간격:            4px ~ 8px

페이지 좌우 여백 (mobile):     16px
페이지 좌우 여백 (tablet):     32px
페이지 좌우 여백 (desktop):    64px~
최대 콘텐츠 너비:              1280px
```

## 트레이드오프

8pt 시스템은 규칙이지 법칙이 아니다. 아이콘과 텍스트 사이를 6px로 하면 조금 더 자연스러운 경우가 있다. 5px나 6px 같은 예외가 생겨도 대부분의 간격이 8의 배수이면 시스템이 무너지지 않는다.

간격 토큰을 픽셀로 정의하면 고해상도(Retina) 디스플레이나 폰트 크기 설정 변경에 대응이 어렵다. `rem` 단위로 정의하면 사용자가 브라우저 폰트 크기를 바꿔도 비율이 유지된다.

```css
/* 픽셀 기반 */
--spacing-4: 16px;

/* rem 기반 (접근성 측면에서 더 좋음) */
--spacing-4: 1rem;   /* 기본 폰트 16px 기준 */
```
