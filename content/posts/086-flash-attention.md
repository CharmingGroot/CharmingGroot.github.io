---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "086. FlashAttention — 어텐션 메모리 최적화"
date: 2026-06-14
tags: [ai, flash-attention, transformer, memory-optimization, cuda, io-aware, tiling, long-context, gpu]
summary: "FlashAttention(2022)은 트랜스포머 어텐션의 메모리 병목을 IO-Aware 타일링으로 해결한다. 어텐션 행렬을 HBM에 저장하지 않고 SRAM에서 직접 계산해 메모리 사용량을 O(n)으로 줄이고 속도를 2~4배 높인다."
slug: "086-flash-attention"
categories: ["AI · ML"]
---

트랜스포머의 가장 큰 병목은 어텐션이다. 시퀀스 길이 n에 대해 n×n 어텐션 행렬을 만들어야 한다. n=1024면 1M 원소, n=16384(16K 컨텍스트)면 256M 원소다. 이 행렬을 GPU 메모리(HBM)에 읽고 쓰는 것이 병목이다.

Stanford의 Dao 등이 2022년 발표한 FlashAttention은 이 문제를 알고리즘 수준에서 해결했다.

## GPU 메모리 계층

GPU에는 두 종류의 메모리가 있다.

**HBM (High Bandwidth Memory)**: GPU 메모리라고 부르는 것. A100 기준 80GB, 대역폭 2TB/s. 크지만 느리다.

**SRAM (Static RAM)**: GPU 코어 내부의 공유 메모리(shared memory). A100 기준 192KB/SM, 대역폭 19TB/s. 작지만 10배 빠르다.

기존 어텐션은 HBM에서 Q, K, V를 읽어 n×n 어텐션 행렬을 계산하고 다시 HBM에 쓴다. HBM 접근이 병목이다.

## IO-Aware 타일링

FlashAttention의 핵심은 어텐션 행렬을 HBM에 쓰지 않는 것이다.

Q, K, V를 작은 블록(tile)으로 나눠 SRAM에 올려놓고 한 번에 계산한다. 어텐션 행렬을 전체 생성하지 않고 블록 단위로 처리하면서 최종 출력만 HBM에 쓴다.

```
기존 어텐션:
HBM → Q,K,V 로드 → S = QK^T 계산 → HBM 저장
HBM → S 로드 → P = softmax(S) 계산 → HBM 저장
HBM → P,V 로드 → O = PV 계산 → HBM 저장

FlashAttention:
HBM → Q_block, K_block, V_block 로드 (작은 블록) → SRAM
SRAM → 블록 단위 어텐션 계산 (HBM 저장 없음)
최종 출력만 HBM에 저장
```

수학적으로 정확히 같은 결과를 내면서 HBM 접근 횟수를 줄인다. 온라인 소프트맥스(online softmax)로 소프트맥스를 블록 단위로 점진적으로 계산한다.

## 성능

| 항목 | 기존 어텐션 | FlashAttention |
|---|---|---|
| 메모리 복잡도 | O(n²) | O(n) |
| 속도 | 기준 | 2~4배 빠름 |
| 수치 정확도 | 기준 | 동일 |
| 역전파 지원 | O | O |

메모리 O(n)이 핵심이다. 16K 컨텍스트에서 기존 어텐션은 256M×4바이트 = 1GB가 어텐션 행렬에만 필요하다. FlashAttention은 이 행렬을 저장하지 않아 수십 배 적은 메모리로 같은 컨텍스트 길이를 처리한다.

## 긴 컨텍스트를 가능하게 하다

FlashAttention이 없었다면 현재의 100K+ 컨텍스트 LLM은 불가능했다. 컨텍스트 길이가 늘어날수록 FlashAttention의 메모리 절약 효과가 커진다.

GPT-4, Claude, LLaMA 2 이후 대부분의 대형 모델이 FlashAttention을 기본으로 사용한다.

## FlashAttention-2 (2023)

작업 분할 방식을 개선해 FlashAttention 대비 2배 추가 속도 향상을 달성했다. 시퀀스 길이 방향으로 병렬화해 GPU 점유율을 높였다.

## FlashAttention-3 (2024)

H100 GPU의 비동기 실행(async warpgroups)과 FP8 저정밀도를 활용한다. A100 대비 H100에서 1.5~2배 추가 속도 향상.

## PagedAttention과의 차이

086이 학습/추론 효율화라면, PagedAttention(vLLM, 092에서 다룸)은 서빙 효율화다. FlashAttention은 단일 요청의 어텐션 계산을 빠르게 하고, PagedAttention은 다수 요청의 KV 캐시를 효율적으로 관리한다. 두 기술은 상호 보완적이다.

## 트레이드오프

CUDA 커널을 직접 작성해야 해 구현이 복잡하다. PyTorch 기본 연산으로는 구현할 수 없고, 하드웨어(NVIDIA GPU)에 종속적이다. AMD GPU나 Apple Silicon에서는 별도 구현이 필요하다. 그러나 PyTorch 2.0부터 `scaled_dot_product_attention` 함수가 FlashAttention을 내부적으로 사용해 사용자가 직접 신경 쓸 필요가 없어졌다.
