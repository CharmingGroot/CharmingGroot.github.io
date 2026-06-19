---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "056. Design Token — 디자인 결정을 변수로 관리하기"
date: 2026-06-13
tags: [ui, ux, design-system, design-token, color, typography, figma, style-dictionary, tailwind]
summary: "Design Token은 색상, 타이포그래피, 간격, 그림자 같은 디자인 결정을 이름 있는 변수로 추상화한 것이다. 컴포넌트가 직접 헥스코드를 박지 않고 토큰을 참조하면, 브랜드 변경이나 다크모드 구현이 토큰 수정 하나로 전체에 반영된다. 토큰 계층 구조, 실제 구현 방법, 그리고 Design System과의 관계를 설명한다."
slug: "056-design-token"
categories: ["디자인 시스템"]
---

버튼 컴포넌트에 `color: #3B82F6`을 직접 쓰고, 카드에도 같은 코드를 복사하고, 헤더에도 넣었다. 브랜드 컬러를 바꾸기로 했다. 이제 모든 파일을 찾아서 고쳐야 한다.

Design Token은 이 문제를 해결한다. `#3B82F6`에 `color-primary`라는 이름을 붙이고, 모든 컴포넌트가 그 이름을 참조한다. 브랜드 컬러를 바꿀 때 토큰 하나만 수정하면 전체에 반영된다.

## 토큰 계층 구조

토큰은 보통 두 계층으로 나눈다.

### Primitive Token (Global Token)

원시값에 의미 없는 이름을 붙인 것이다. 팔레트 전체를 정의한다.

```js
// 색상 팔레트
color-blue-50:  #EFF6FF
color-blue-100: #DBEAFE
color-blue-400: #60A5FA
color-blue-500: #3B82F6
color-blue-600: #2563EB
color-blue-900: #1E3A8A

color-gray-50:  #F9FAFB
color-gray-500: #6B7280
color-gray-900: #111827

// 간격
spacing-1: 4px
spacing-2: 8px
spacing-4: 16px
spacing-8: 32px

// 폰트 크기
font-size-sm:   14px
font-size-base: 16px
font-size-xl:   20px
font-size-3xl:  30px
```

이 계층은 "무엇이 있는지"만 정의한다. "언제 쓰는지"는 다음 계층이다.

### Semantic Token (Alias Token)

Primitive Token에 **의미**를 부여한다. 컴포넌트는 이 계층의 토큰을 참조한다.

```js
// 의미 기반 색상
color-primary:          color-blue-500
color-primary-hover:    color-blue-600
color-text-default:     color-gray-900
color-text-muted:       color-gray-500
color-background:       color-gray-50
color-border:           color-gray-200
color-danger:           color-red-500
color-success:          color-green-500

// 컴포넌트 특화 토큰 (필요 시)
button-bg-primary:      color-primary
button-bg-hover:        color-primary-hover
button-text:            color-white
```

버튼이 `color-blue-500`을 직접 참조하지 않고 `color-primary`를 참조한다. 나중에 브랜드 컬러를 보라색으로 바꾸면 `color-primary: color-purple-500`으로만 바꾸면 된다.

## 다크모드 구현

Semantic Token이 있으면 다크모드가 자연스럽게 구현된다.

```css
/* 라이트 모드 */
:root {
  --color-background: #F9FAFB;
  --color-text-default: #111827;
  --color-primary: #3B82F6;
  --color-border: #E5E7EB;
}

/* 다크 모드 */
[data-theme="dark"] {
  --color-background: #111827;
  --color-text-default: #F9FAFB;
  --color-primary: #60A5FA;    /* 다크에서 더 밝은 파란색 */
  --color-border: #374151;
}
```

컴포넌트 코드는 `var(--color-background)` 하나만 쓴다. 테마가 바뀌면 CSS 변수값만 교체되므로 컴포넌트를 건드리지 않아도 된다.

## 구현 도구

### Style Dictionary

Amazon이 만든 오픈소스 토큰 변환 도구다. JSON으로 토큰을 정의하면 CSS Variables, iOS Swift, Android Kotlin, JS 상수 등 여러 플랫폼용 파일을 자동으로 생성한다.

```json
// tokens.json
{
  "color": {
    "primary": { "value": "#3B82F6" },
    "text": {
      "default": { "value": "#111827" },
      "muted": { "value": "#6B7280" }
    }
  },
  "spacing": {
    "4": { "value": "16px" }
  }
}
```

```bash
style-dictionary build
```

```css
/* 자동 생성: variables.css */
:root {
  --color-primary: #3B82F6;
  --color-text-default: #111827;
  --color-text-muted: #6B7280;
  --spacing-4: 16px;
}
```

```swift
// 자동 생성: StyleDictionary.swift
public enum StyleDictionary {
  public static let colorPrimary = UIColor(red: 0.23, green: 0.51, blue: 0.96, alpha: 1)
}
```

웹, iOS, Android가 같은 토큰 파일에서 각자 필요한 형식으로 코드를 생성하므로 플랫폼 간 디자인 일관성이 유지된다.

### Figma Variables

Figma 안에서 직접 토큰을 정의하고 컴포넌트에 연결하는 기능이다. 디자이너가 Figma에서 변수를 정의하면 개발자가 그 값을 받아 Style Dictionary나 CSS 변수로 내보낸다.

Figma Variables와 Style Dictionary를 연결하는 플러그인(Token Studio 등)을 쓰면 디자이너의 변경이 자동으로 코드로 흘러가는 파이프라인을 만들 수 있다.

### Tailwind CSS

Tailwind는 설정 파일이 사실상 Design Token이다.

```js
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#3B82F6',
          hover: '#2563EB',
        },
        text: {
          muted: '#6B7280',
        }
      },
      spacing: {
        '18': '72px',
      }
    }
  }
}
```

`bg-primary`, `text-text-muted` 같은 유틸리티 클래스로 토큰을 참조한다. 별도 Design Token 시스템 없이 Tailwind 설정만으로 브랜드 일관성을 관리하는 팀이 많다.

## Design System과의 관계

Design Token이 "값"을 정의한다면, Design System은 그 위에 쌓인 더 큰 개념이다.

```
Design System
  ├── Design Token   (값: 색상, 간격, 타이포그래피)
  ├── Component      (Button, Input, Modal 등 — 토큰을 참조)
  ├── Pattern        (컴포넌트 조합 방식)
  └── Guideline      (언제 무엇을 쓸지 규칙)
```

토큰 없이 컴포넌트만 만들면 컴포넌트 안에 하드코딩된 값들이 분산돼 일관성을 유지하기 어렵다. 토큰이 Design System의 토대가 된다.

## 트레이드오프

토큰 계층을 너무 세분화하면 오히려 복잡해진다. `button-primary-bg-color-default-state`처럼 과도하게 구체적인 토큰은 유지하기 어렵다. Primitive → Semantic 두 계층이면 대부분 충분하다.

디자이너와 개발자가 같은 토큰 이름을 쓰는 것이 핵심이다. Figma에서 `Primary/500`이라고 부르는 것을 개발 코드에서 `color-blue-500`이라고 다르게 부르면 소통 비용이 생긴다. 토큰 정의 단계에서 디자이너와 개발자가 함께 이름을 정하는 것이 중요하다.
