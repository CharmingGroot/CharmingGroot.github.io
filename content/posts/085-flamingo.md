---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "085. Flamingo — Few-Shot 멀티모달 LLM"
date: 2026-06-14
tags: [ai, flamingo, multimodal, few-shot, deepmind, vision-language, gated-attention, in-context-learning]
summary: "Flamingo(2022)는 사전학습된 비전 모델과 LLM을 고정하고 중간 연결 레이어만 학습해 강력한 멀티모달 Few-Shot 능력을 보여준다. 프롬프트에 이미지-텍스트 예시를 몇 개 제공하면 새로운 비전 태스크에 즉시 적응한다."
slug: "085-flamingo"
categories: ["AI · ML"]
---

GPT-3의 In-Context Learning은 충격적이었다. 프롬프트에 예시 몇 개를 넣으면 학습 없이 새로운 태스크를 수행한다. 이 능력을 이미지-텍스트 태스크에도 적용할 수 없을까?

DeepMind가 2022년 발표한 Flamingo는 멀티모달 In-Context Learning을 처음으로 강력하게 구현했다.

## 핵심 설계: 기존 모델을 고정

Flamingo는 두 개의 사전학습된 모델에서 출발한다.

- **NFNet (비전 모델)**: 이미지 → 시각적 특징
- **Chinchilla (70B LLM)**: 텍스트 → 텍스트

중요한 점은 두 모델의 **가중치를 고정**한다는 것이다. 학습하는 것은 중간에 추가하는 연결 레이어뿐이다.

## Perceiver Resampler

ViT의 출력은 이미지 해상도에 따라 크기가 달라지는 가변 길이 시퀀스다. LLM에 넣으려면 고정 크기 토큰이 필요하다.

Perceiver Resampler가 가변 길이 시각 특징을 고정 64개 토큰으로 압축한다. 크로스 어텐션으로 시각 특징 전체를 보면서 핵심 정보를 64개 학습 가능한 쿼리 벡터로 집약한다.

```
이미지 → NFNet → 가변 크기 시각 특징
                      ↓ Perceiver Resampler
                  고정 64개 시각 토큰
                      ↓ LLM에 삽입
```

## Gated Cross-Attention

LLM의 각 레이어 사이에 Cross-Attention Dense Layer를 삽입한다. 이 레이어가 텍스트 토큰이 시각 토큰에 어텐션하도록 한다.

게이팅 메커니즘(tanh gate)으로 시각 정보의 영향도를 조절한다. 초기에는 게이트가 거의 닫혀 LLM의 순수 텍스트 동작을 유지하고, 학습하면서 시각 정보를 점진적으로 통합한다.

```
텍스트 레이어 출력
    ↓
Gated Cross-Attention (시각 토큰에 어텐션)
    ↓
FFN Layer
    ↓
다음 텍스트 레이어
```

LLM 가중치는 고정이므로 기존 텍스트 능력이 보존된다. Cross-Attention 레이어만 학습해 시각 이해를 추가한다.

## Few-Shot 멀티모달 In-Context Learning

```
[이미지1] 설명: 해변에서 파도를 타는 사람. [이미지2] 설명: 
```

이런 프롬프트를 넣으면 모델이 두 번째 이미지를 보고 같은 형식의 설명을 생성한다. 파인튜닝 없이 예시 몇 개만으로 새로운 태스크에 적응한다.

Few-Shot 예시가 많을수록 성능이 오른다. 4-shot이 0-shot보다, 8-shot이 4-shot보다 좋다.

## 학습 데이터

- ALIGN: 18억 개 이미지-텍스트 쌍
- LTIP: 3억 1200만 개 이미지-텍스트 쌍
- VTP: 2700만 개 비디오-텍스트 쌍
- M3W: 웹에서 추출한 이미지가 삽입된 문서

특히 M3W(Multimodal MassiveWeb)가 중요하다. 텍스트 사이에 이미지가 삽입된 웹 문서를 그대로 학습해 멀티모달 인터리빙을 자연스럽게 학습한다.

## 의의와 한계

Flamingo는 "사전학습된 강력한 단일 모달 모델을 최소한의 학습으로 연결한다"는 설계 철학을 보여줬다. 이 철학이 이후 LLaVA, InstructBLIP 등 오픈소스 멀티모달 모델들의 기반이 됐다.

단점은 Flamingo 자체가 비공개 모델이라 직접 사용할 수 없다. 또한 비전 모델과 LLM을 고정하므로 두 모달리티의 깊은 통합이 제한된다. 같은 레이어에서 함께 학습하는 GPT-4V 같은 통합 학습 방식이 더 깊은 이해를 보인다.

## 트레이드오프

기존 모델을 고정하는 방식은 학습 효율이 좋다. 연결 레이어만 학습하므로 계산 비용이 적다. 그러나 두 모달리티 간의 정렬이 통합 학습 방식만큼 깊지 않다. 텍스트에 강하게 의존하는 태스크에서 좋지만, 이미지의 세밀한 디테일이 중요한 태스크에서는 한계가 있다.
