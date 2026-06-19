---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "088. Prompt Tuning / Prefix Tuning — 소프트 프롬프트 학습"
date: 2026-06-14
tags: [ai, nlp, prompt-tuning, prefix-tuning, peft, fine-tuning, parameter-efficient, soft-prompt, t5, gpt]
summary: "Prompt Tuning과 Prefix Tuning은 모델 가중치를 고정하고 입력 앞에 붙이는 학습 가능한 벡터(소프트 프롬프트)만 학습한다. 전체 파인튜닝의 0.1% 미만 파라미터로 비슷한 성능을 달성한다."
slug: "088-prompt-prefix-tuning"
categories: ["AI · ML"]
---

모델이 커질수록 파인튜닝 비용이 커진다. 175B 파라미터 GPT-3를 태스크마다 완전히 파인튜닝하면 각각 350GB 모델 사본이 필요하다. 1,000개 태스크면 350TB다.

파라미터 효율적 파인튜닝(PEFT)의 출발점 중 하나가 소프트 프롬프트(soft prompt)다.

## Prompt Tuning (2021, Google)

Lester 등이 T5를 대상으로 발표했다. 아이디어는 단순하다.

하드 프롬프트: `"텍스트를 긍정/부정으로 분류하세요: {입력}"`처럼 사람이 작성한 텍스트.

소프트 프롬프트: 텍스트가 아니라 **학습 가능한 임베딩 벡터**를 입력 앞에 붙인다. 이 벡터들이 모델에게 "이렇게 동작하라"는 조건 역할을 한다.

```
일반 입력: [텍스트 토큰들] → 모델 → 출력
Prompt Tuning: [소프트 토큰 k개] + [텍스트 토큰들] → 모델 → 출력
```

모델 가중치는 전혀 건드리지 않는다. 소프트 토큰 임베딩(k × d 파라미터, 보통 k=100, d=768)만 학습한다.

**성능**: 모델이 충분히 크면(11B 이상) 전체 파인튜닝과 비슷한 성능이 나온다. 작은 모델에서는 차이가 있다.

```python
# PEFT 라이브러리로 Prompt Tuning 적용
from peft import PromptTuningConfig, get_peft_model, TaskType

config = PromptTuningConfig(
    task_type=TaskType.CAUSAL_LM,
    num_virtual_tokens=20,    # 소프트 프롬프트 토큰 수
    tokenizer_name_or_path="gpt2",
)
model = get_peft_model(base_model, config)
# 학습 가능한 파라미터: 20 × 768 = 15,360 (전체의 0.002%)
```

## Prefix Tuning (2021, Stanford)

Li와 Liang이 GPT-2와 BART를 대상으로 발표했다. Prompt Tuning과 유사하지만 더 깊이 개입한다.

Prompt Tuning은 입력 임베딩 레이어에만 소프트 프롬프트를 추가한다. Prefix Tuning은 **모든 트랜스포머 레이어의 Key와 Value에 학습 가능한 접두사를 추가**한다.

```
각 레이어에서:
Attention(Q, [Prefix_K; K], [Prefix_V; V])

일반 K, V에 학습된 Prefix_K, Prefix_V를 앞에 이어붙임
```

모든 레이어에서 직접 어텐션을 통해 소프트 프롬프트의 영향을 준다. Prompt Tuning보다 영향력이 강해 작은 모델에서도 효과가 있다.

파라미터 수는 레이어 × 접두사 길이 × 히든 크기 × 2(K, V)다. 전체 파라미터의 0.1~1% 수준.

직접 최적화가 불안정해서 원래 논문에서는 소규모 MLP를 통해 Prefix를 생성하고 추론 시에는 MLP를 제거한다.

## Prompt Tuning vs Prefix Tuning vs 전체 파인튜닝

| 방식 | 학습 파라미터 | 소규모 모델 | 저장 공간 | 병합 가능 |
|---|---|---|---|---|
| 전체 파인튜닝 | 100% | 최고 | 모델 전체 | — |
| Prefix Tuning | 0.1~1% | 좋음 | 접두사만 | 불가 |
| Prompt Tuning | <0.1% | 약함 | 극소 | 불가 |
| LoRA | 0.1~1% | 좋음 | 작음 | 가능 |

LoRA(089)가 나오면서 소프트 프롬프트 방식보다 더 많이 쓰이게 됐다. LoRA는 가중치에 직접 개입하므로 작은 모델에서도 성능이 좋고, 파인튜닝된 가중치를 원본과 병합할 수 있어 추론 오버헤드가 없다.

## 실용적 의미

소프트 프롬프트 방식의 가장 큰 장점은 **동일한 베이스 모델을 여러 태스크에 공유**한다는 것이다.

```
동일한 GPT-3 가중치
    + Prefix_번역 → 번역 모델
    + Prefix_분류 → 분류 모델
    + Prefix_요약 → 요약 모델
```

추론 시 태스크별 접두사만 바꾸면 된다. 서버 한 대에 GPT-3를 한 번만 올려두고 접두사로 태스크를 전환한다. 메모리 효율이 극적으로 좋다.

## 트레이드오프

소프트 프롬프트는 사람이 해석할 수 없다. 어떤 의미를 학습했는지 알 수 없다. 디버깅이 어렵고 특정 도메인 지식을 명시적으로 주입하기 어렵다. 또한 학습에 사용한 모델 버전에 종속된다. 모델이 업데이트되면 소프트 프롬프트를 재학습해야 한다.
