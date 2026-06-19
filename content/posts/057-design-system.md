---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "057. Design System — 컴포넌트 라이브러리와 원자 디자인"
date: 2026-06-13
tags: [ui, ux, design-system, atomic-design, component, storybook, figma, consistency]
summary: "Design System은 토큰, 컴포넌트, 패턴, 가이드라인을 하나의 시스템으로 묶어 제품 전체의 일관성을 유지하는 체계다. 원자 디자인 방법론으로 컴포넌트를 계층화하고, Storybook으로 문서화하는 방법, 그리고 Design System을 도입할 때의 현실적인 트레이드오프를 설명한다."
slug: "057-design-system"
categories: ["디자인 시스템"]
---

팀이 커지고 제품 화면이 늘어나면 일관성이 무너지기 시작한다. 개발자마다 버튼을 다르게 만들고, 같은 기능을 하는 모달이 세 가지 스타일로 존재한다. 신규 개발자가 어떤 컴포넌트를 써야 하는지 파악하는 데 시간이 걸린다.

Design System은 이 문제를 해결하는 체계다. "우리 제품에서 버튼은 이렇게 생겼고, 이런 상황에서 쓴다"를 정의하고 공유한다. 컴포넌트를 매번 새로 만들지 않고 시스템에서 가져다 쓴다.

## 원자 디자인 (Atomic Design)

Brad Frost가 제안한 컴포넌트 계층화 방법론이다. 화학의 원자→분자→유기체 비유로 UI를 계층화한다.

```
Atom (원자)
  가장 작은 단위. 더 이상 분해할 수 없는 UI 요소.
  Button, Input, Label, Icon, Badge

Molecule (분자)
  Atom 여러 개가 결합해 하나의 기능 단위를 이루는 것.
  SearchBar = Input + Button
  FormField = Label + Input + ErrorMessage

Organism (유기체)
  Molecule과 Atom이 결합한 복잡한 UI 섹션.
  Header = Logo + Navigation + SearchBar + UserMenu
  ProductCard = Image + Title + Price + AddToCartButton

Template (템플릿)
  Organism들로 구성된 페이지 레이아웃. 실제 콘텐츠 없이 구조만.

Page (페이지)
  Template에 실제 데이터를 채운 최종 화면.
```

### 실제 적용

```tsx
// Atom: Button
const Button = ({ variant, size, children, onClick }) => (
  <button
    className={cn(
      styles.base,
      styles.variants[variant],
      styles.sizes[size]
    )}
    onClick={onClick}
  >
    {children}
  </button>
)

// Atom: Input
const Input = ({ placeholder, value, onChange }) => (
  <input className={styles.input} ... />
)

// Molecule: SearchBar = Input + Button
const SearchBar = ({ onSearch }) => {
  const [query, setQuery] = useState('')
  return (
    <div className={styles.searchBar}>
      <Input value={query} onChange={setQuery} placeholder="검색" />
      <Button variant="primary" onClick={() => onSearch(query)}>
        검색
      </Button>
    </div>
  )
}
```

계층이 명확하면 컴포넌트가 어디에 있는지, 어떻게 조합해야 하는지 팀원 누구나 예측할 수 있다.

## 컴포넌트 설계 원칙

### 변형(Variant)을 명시적으로 정의한다

버튼 하나에 여러 변형이 있을 수 있다. 이걸 prop으로 명시하면 사용처에서 임의로 스타일을 덮어쓰지 않아도 된다.

```tsx
type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
type ButtonSize = 'sm' | 'md' | 'lg'

interface ButtonProps {
  variant?: ButtonVariant
  size?: ButtonSize
  disabled?: boolean
  loading?: boolean
  fullWidth?: boolean
}
```

컴포넌트가 지원하는 변형이 명시돼 있으면, 디자이너도 "이 버튼에는 danger 변형이 있다"는 것을 알고 Figma에서 같은 이름으로 설계한다.

### 합성(Composition)을 선호한다

컴포넌트가 너무 많은 것을 알면 유연성이 떨어진다.

```tsx
// 나쁜 예: Modal이 타이틀과 버튼을 직접 소유
<Modal title="삭제 확인" onConfirm={...} onCancel={...} />

// 좋은 예: 합성으로 구조를 외부에서 결정
<Modal>
  <Modal.Header>삭제 확인</Modal.Header>
  <Modal.Body>이 항목을 삭제하시겠습니까?</Modal.Body>
  <Modal.Footer>
    <Button variant="ghost" onClick={onCancel}>취소</Button>
    <Button variant="danger" onClick={onConfirm}>삭제</Button>
  </Modal.Footer>
</Modal>
```

합성 패턴은 컴포넌트의 내부 구조를 열어두어 다양한 케이스를 수용한다.

## Storybook — 컴포넌트 문서화

Storybook은 컴포넌트를 실제 앱과 분리된 환경에서 독립적으로 개발하고 문서화하는 도구다.

```tsx
// Button.stories.tsx
export default {
  title: 'Components/Button',
  component: Button,
}

export const Primary = {
  args: {
    variant: 'primary',
    children: '저장하기',
  }
}

export const Danger = {
  args: {
    variant: 'danger',
    children: '삭제하기',
  }
}

export const Loading = {
  args: {
    variant: 'primary',
    loading: true,
    children: '저장 중...',
  }
}

export const AllVariants = () => (
  <div style={{ display: 'flex', gap: 8 }}>
    <Button variant="primary">Primary</Button>
    <Button variant="secondary">Secondary</Button>
    <Button variant="ghost">Ghost</Button>
    <Button variant="danger">Danger</Button>
  </div>
)
```

Storybook을 빌드해 배포하면 디자이너, 기획자, QA가 브라우저에서 컴포넌트를 직접 확인하고 props를 바꿔볼 수 있다. "버튼 disabled 상태가 어떻게 생겼더라"를 코드를 뒤지지 않고 Storybook에서 확인한다.

## Design System의 범위

모든 것을 Design System에 넣으려 하면 오히려 유지보수 부담이 커진다. 범위를 현실적으로 정하는 것이 중요하다.

```
반드시 포함:
  - Design Token (색상, 타이포그래피, 간격, 그림자)
  - 기본 컴포넌트 (Button, Input, Modal, Toast, Badge 등)
  - 레이아웃 컴포넌트 (Grid, Stack, Container)

상황에 따라:
  - 복잡한 Organism (Header, Sidebar, DataTable)
  - 아이콘 시스템
  - 애니메이션 토큰

제품 코드에 두는 것:
  - 페이지 단위 컴포넌트
  - 도메인 특화 컴포넌트 (주문 폼, 결제 위젯 등)
```

## 트레이드오프

Design System은 초기 투자 비용이 크다. 버튼 하나 만드는 데 모든 변형, 접근성, 문서화를 갖추려면 시간이 걸린다. 제품이 작거나 팀이 혼자일 때는 오버엔지니어링이 될 수 있다.

버전 관리가 필요해진다. Design System을 npm 패키지로 분리하면 여러 제품이 공유할 수 있지만, 버전 업그레이드와 하위 호환성을 관리해야 한다. 제품이 하나뿐이라면 모노레포 안에서 패키지로 관리하는 것이 더 단순하다.

Design System은 "만들어두면 끝"이 아니다. 계속 사용되고 발전하려면 누군가 유지보수와 전파(교육, 문서 업데이트)를 담당해야 한다. 전담 팀이나 명확한 오너가 없으면 시간이 지나면서 방치된다.
