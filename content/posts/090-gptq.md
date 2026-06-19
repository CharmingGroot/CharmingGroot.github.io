---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "090. GPTQ — 사후 학습 양자화"
date: 2026-06-14
tags: [ai, gptq, quantization, post-training-quantization, int4, weight-compression, inference-optimization, llm]
summary: "GPTQ(2022)는 LLM 가중치를 4비트로 압축하는 사후 학습 양자화 방법이다. 재학습 없이 보정 데이터만으로 FP16 대비 4배 작은 모델을 만들고, 성능 손실을 최소화한다. 소비자 GPU에서 대형 모델을 실행하는 실용적인 방법이다."
slug: "090-gptq"
categories: ["AI · ML"]
---

LLaMA-65B를 FP16으로 올리려면 130GB VRAM이 필요하다. A100 80GB 두 장이 있어야 한다. 대부분의 환경에서는 불가능하다.

양자화(quantization)는 가중치를 낮은 정밀도로 저장해 메모리를 줄인다. FP16(16비트) → INT4(4비트)면 4배 작아진다. 65B 모델이 32.5GB로 줄어 단일 A100에 올라간다.

문제는 품질 손실이다. 단순히 반올림하면 정보가 손실돼 성능이 크게 떨어진다.

## GPTQ의 접근

Frantar 등이 2022년 발표한 GPTQ는 **2차 정보(Hessian)**를 활용해 양자화 오차를 최소화한다.

핵심 아이디어: 한 가중치를 양자화해 오차가 생기면, 나머지 가중치를 조정해 전체 레이어 출력이 원래와 같아지도록 보상한다.

```
원본 레이어 출력 = W × X
양자화 후:       Q(W) × X + 오차

GPTQ: Q(W) + 보정항 ≈ W
보정항은 남은 가중치들이 흡수
```

이 과정에서 2차 미분(Hessian)으로 각 가중치가 출력에 미치는 영향을 정량화해 보정 우선순위를 정한다.

## 적용 과정

재학습이 필요 없다. 소량의 보정 데이터(calibration data, 128~512 샘플)만 필요하다.

```python
from transformers import AutoModelForCausalLM, AutoTokenizer, GPTQConfig

quantization_config = GPTQConfig(
    bits=4,                     # 4비트 양자화
    group_size=128,             # 128개 가중치마다 독립 양자화
    dataset="wikitext2",        # 보정 데이터
)

model = AutoModelForCausalLM.from_pretrained(
    "meta-llama/Llama-2-7b-hf",
    quantization_config=quantization_config,
    device_map="auto",
)
```

`group_size`는 몇 개의 가중치를 하나의 양자화 그룹으로 묶는지다. 작을수록 정밀도가 높지만 오버헤드가 커진다.

## 성능 비교

LLaMA-7B 기준:

| 정밀도 | 메모리 | Perplexity | 비고 |
|---|---|---|---|
| FP16 | 14GB | 5.68 | 기준 |
| INT8 | 7GB | 5.72 | 거의 동일 |
| INT4 (GPTQ) | 3.5GB | 5.85 | 약간 하락 |
| INT3 | 2.6GB | 6.34 | 눈에 띄는 하락 |

INT4가 FP16 대비 성능 손실이 작아 실용적인 선택이다.

## Hugging Face 생태계

TheBloke 같은 커뮤니티 기여자들이 수천 개의 모델을 미리 GPTQ로 양자화해 Hugging Face Hub에 올려뒀다. 직접 양자화할 필요 없이 다운로드해서 바로 쓸 수 있다.

```python
# 미리 양자화된 모델 사용
model = AutoModelForCausalLM.from_pretrained(
    "TheBloke/Llama-2-7B-GPTQ",
    device_map="auto",
)
```

## AWQ, GGUF와의 비교

세 가지 모두 LLM 양자화 방법이지만 설계 목표가 다르다.

**GPTQ**: GPU 추론 최적화. 배치 처리에 유리. 서버 배포에 적합.

**AWQ (Activation-aware Weight Quantization, 2023)**: 중요한 가중치를 선별적으로 보호해 GPTQ보다 품질이 좋다. 실용적으로 비슷한 용도.

**GGUF (llama.cpp 포맷, 2023)**: CPU 추론 최적화. 맥북 같은 소비자 하드웨어에서 실행. 레이어를 VRAM과 RAM에 나눠 올릴 수 있어 VRAM이 부족한 환경에서 유리하다.

GPU 서버 배포라면 GPTQ나 AWQ, 로컬 실행이라면 GGUF가 적합하다. 091에서 AWQ와 GGUF를 자세히 다룬다.

## 트레이드오프

양자화는 불가역적이다. 4비트로 압축하면 원본 FP16 정밀도로 복원할 수 없다. 또한 양자화 비율이 높아질수록(3비트 이하) 특정 태스크에서 성능이 급격히 떨어질 수 있다. 수학 추론, 코딩 같이 정밀한 작업이 일반 대화보다 양자화에 더 민감하다.

추론 속도는 하드웨어에 따라 다르다. INT4 연산이 FP16보다 처리량이 높지만, 역양자화(dequantization) 오버헤드가 있어 단순히 4배 빠르지는 않다. 실제로는 1.5~3배 속도 향상 정도다.
