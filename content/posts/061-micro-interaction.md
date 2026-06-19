---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "061. 마이크로인터랙션 — 피드백, 애니메이션, 트랜지션"
date: 2026-06-13
tags: [ui, ux, micro-interaction, animation, transition, feedback, motion, framer-motion, css]
summary: "마이크로인터랙션은 사용자가 행동을 취했을 때 인터페이스가 반응하는 작은 순간이다. 버튼을 눌렀을 때 눌리는 느낌, 저장이 완료됐을 때 체크마크, 에러가 발생했을 때 흔들림. 이 작은 피드백들이 쌓여 제품의 완성도를 결정한다. 트리거, 규칙, 피드백, 루프 4단계 구조와 실제 구현 방법을 설명한다."
slug: "061-micro-interaction"
categories: ["디자인 시스템"]
---

버튼을 눌렀는데 아무 반응이 없으면 눌린 건지 모른다. 폼을 제출했는데 화면이 그대로면 처리 중인지 오류인지 모른다. 마이크로인터랙션은 "지금 무슨 일이 일어나고 있는지"를 사용자에게 즉각 알려주는 피드백 시스템이다.

## 4단계 구조

Dan Saffer의 프레임워크다.

**Trigger (트리거)**: 인터랙션을 시작하는 것. 버튼 클릭, 폼 제출, 스크롤, 시간 경과.

**Rules (규칙)**: 트리거 이후 무슨 일이 일어나는지. "버튼을 클릭하면 API를 호출한다."

**Feedback (피드백)**: 사용자에게 무슨 일이 일어났는지 알리는 것. 로딩 스피너, 색상 변화, 애니메이션.

**Loops & Modes (루프)**: 인터랙션이 반복되거나 상태가 바뀌는 경우. 완료 후 원래 상태로 돌아오기, 토글 상태 유지.

## 주요 패턴

### 버튼 상태 피드백

버튼은 네 가지 상태가 시각적으로 구분돼야 한다.

```css
/* 기본 */
.btn {
  background: var(--color-primary);
  transform: scale(1);
  transition: all 150ms ease;
}

/* hover: 살짝 밝아지거나 그림자 추가 */
.btn:hover {
  background: var(--color-primary-hover);
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

/* active: 눌리는 느낌 */
.btn:active {
  transform: scale(0.97);
  box-shadow: none;
}

/* disabled: 비활성화 */
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}
```

`scale(0.97)`이 미묘하지만 "눌림"을 전달하는 중요한 디테일이다.

### 로딩 상태

비동기 작업은 진행 중임을 반드시 알려야 한다.

```tsx
const Button = ({ loading, children, onClick }) => (
  <button
    disabled={loading}
    onClick={onClick}
    className={cn(styles.btn, loading && styles.loading)}
  >
    {loading ? (
      <>
        <Spinner className={styles.spinner} aria-hidden="true" />
        <span>처리 중...</span>
      </>
    ) : children}
  </button>
)
```

```css
@keyframes spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}

.spinner {
  animation: spin 0.8s linear infinite;
}
```

버튼 텍스트를 "저장 중..."으로 바꾸면 스크린 리더도 상태 변화를 인지한다.

### 성공/실패 피드백

```tsx
// 저장 성공 시 체크마크로 전환 후 원래 상태로 복귀
const SaveButton = () => {
  const [state, setState] = useState<'idle' | 'loading' | 'success'>('idle')

  const handleSave = async () => {
    setState('loading')
    await save()
    setState('success')
    setTimeout(() => setState('idle'), 2000)  // 2초 후 원래로
  }

  return (
    <button onClick={handleSave}>
      {state === 'loading' && <Spinner />}
      {state === 'success' && <CheckIcon />}
      {state === 'idle' && '저장'}
      {state === 'loading' && '저장 중...'}
      {state === 'success' && '저장됨'}
    </button>
  )
}
```

### 오류 흔들림 (Shake)

잘못된 입력이나 오류 시 요소를 잠깐 흔들면 "뭔가 잘못됐다"는 신호를 직관적으로 전달한다.

```css
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  20%       { transform: translateX(-8px); }
  40%       { transform: translateX(8px); }
  60%       { transform: translateX(-6px); }
  80%       { transform: translateX(6px); }
}

.input--error {
  animation: shake 0.4s ease;
  border-color: var(--color-danger);
}
```

### 페이지 트랜지션

페이지 이동이 뚝뚝 끊기면 어수선하다. 부드러운 트랜지션이 맥락의 연속성을 유지한다.

```tsx
// Framer Motion 예시
import { AnimatePresence, motion } from 'framer-motion'

const Page = ({ children }) => (
  <motion.div
    initial={{ opacity: 0, y: 8 }}
    animate={{ opacity: 1, y: 0 }}
    exit={{ opacity: 0, y: -8 }}
    transition={{ duration: 0.2, ease: 'easeOut' }}
  >
    {children}
  </motion.div>
)
```

이동 방향이 의미를 갖는다. 다음 단계로 가면 오른쪽에서 들어오고, 뒤로 가면 왼쪽에서 들어온다. 사용자가 공간적 위치를 파악하도록 돕는다.

### 스켈레톤 로딩

콘텐츠가 로딩 중일 때 빈 화면 대신 콘텐츠의 형태를 흉내 낸 회색 블록을 보여준다. 실제 레이아웃 이동(Layout Shift)을 줄이고 기다리는 느낌을 줄인다.

```css
@keyframes shimmer {
  0%   { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

.skeleton {
  background: linear-gradient(
    90deg,
    #f0f0f0 25%,
    #e0e0e0 50%,
    #f0f0f0 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
}
```

## 애니메이션 원칙

**목적이 있어야 한다.** 애니메이션은 상태 변화를 명확히 하거나, 요소 간 관계를 보여주거나, 다음 동작을 안내하는 목적을 가져야 한다. 그냥 멋있어 보이려는 애니메이션은 오히려 방해가 된다.

**빠르게.** UI 애니메이션은 대부분 100~300ms가 적당하다. 500ms 이상은 느려 보인다. 입력 피드백(hover, active)은 100~150ms, 콘텐츠 전환은 200~300ms, 복잡한 레이아웃 변화는 300~500ms.

**easing을 신경 쓴다.** `linear`는 기계적으로 보인다. `ease-out`(빠르게 시작해 천천히 끝남)이 자연스러운 물리 운동을 모방한다. 들어오는 것은 `ease-out`, 나가는 것은 `ease-in`이 자연스럽다.

**prefers-reduced-motion 존중.** 전정 장애나 간질이 있는 사용자는 과도한 모션이 불편하거나 위험할 수 있다.

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

## 트레이드오프

애니메이션이 많으면 성능에 영향을 준다. `transform`과 `opacity`는 GPU 가속이 돼 성능이 좋다. `width`, `height`, `padding`, `margin`은 레이아웃을 다시 계산하므로 비싸다. 가능하면 `transform`으로 대체한다.

```css
/* 느림: 레이아웃 변경 */
.btn:hover { width: 120px; }

/* 빠름: transform */
.btn:hover { transform: scaleX(1.1); }
```
