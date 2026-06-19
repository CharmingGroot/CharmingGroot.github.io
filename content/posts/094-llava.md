---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "094. LLaVA — 오픈소스 멀티모달 LLM"
date: 2026-06-14
tags: [ai, llava, multimodal, vision-language, instruction-tuning, llama, clip, open-source, gpt4-generated]
summary: "LLaVA(2023)는 CLIP 비전 인코더와 LLaMA를 선형 투영 레이어 하나로 연결한 오픈소스 멀티모달 모델이다. GPT-4가 생성한 158K 시각 지시 데이터로 학습해 GPT-4V에 가까운 시각 추론 능력을 보인다."
slug: "094-llava"
categories: ["AI · ML"]
---

GPT-4V가 멀티모달 능력을 보여준 직후, 오픈소스 커뮤니티는 같은 능력을 재현하려 했다. 그러나 학습 데이터가 문제였다. 이미지와 자연어 지시를 함께 포함한 데이터셋이 없었다.

Wisconsin-Madison의 Liu 등이 2023년 발표한 LLaVA(Large Language and Vision Assistant)는 이 문제를 GPT-4로 해결했다.

## GPT-4로 학습 데이터 생성

이미지를 직접 GPT-4에 보낼 수는 없었다(당시 GPT-4V가 아직 없었다). 대신 이미지의 캡션과 바운딩 박스 정보를 텍스트로 변환해 GPT-4에 주고, 이 이미지에 대한 다양한 질의응답을 생성하도록 했다.

```
GPT-4 입력:
"다음 이미지에 대한 설명: 해변에서 두 아이가 모래성을 쌓고 있다.
바운딩 박스: [아이1: (120,80,200,300)], [모래성: (250,200,400,350)]

이 이미지에 대한 상세한 질의응답 5쌍을 만들어라."

GPT-4 출력:
Q: 아이들은 무엇을 하고 있나요?
A: 두 아이가 해변 모래사장에서 함께 모래성을 쌓고 있습니다.
...
```

이 방식으로 158K 개의 이미지-지시 쌍을 생성했다. 세 가지 유형: 상세 설명, 복잡한 추론, 대화.

## 단순하지만 효과적인 아키텍처

LLaVA의 아키텍처는 의도적으로 단순하다.

```
이미지 → CLIP ViT-L/14 → 패치 특징 (256×1024)
                              ↓ 선형 투영 W (1024×4096)
                         시각 토큰 (256×4096)
                              ↓
              [시각 토큰] + [텍스트 토큰] → LLaMA 7B → 답변
```

BLIP-2의 Q-Former 같은 복잡한 구조 없이 선형 투영 레이어 하나다. 시각 토큰을 텍스트 토큰과 같은 차원으로 변환해 LLM 앞에 붙이는 것이 전부다.

2단계 학습:
1. **특징 정렬**: 선형 투영만 학습 (595K 이미지-캡션 쌍)
2. **End-to-End 파인튜닝**: 선형 투영 + LLaMA 전체 학습 (158K 지시 데이터)

## 성능

당시 공개 모델 중 최고 수준의 시각 추론을 보였다. ScienceQA 벤치마크에서 GPT-4에 가까운 성능을 달성했다.

단순한 아키텍처임에도 GPT-4 생성 지시 데이터의 품질이 성능을 결정했다는 것을 보여줬다.

## LLaVA-1.5 (2023)

LLaVA의 개선판이다. 선형 투영을 2층 MLP로 교체하고, 더 해상도 높은 이미지 처리를 추가했다. BLIP-2보다 전반적으로 좋은 성능을 냈다.

## LLaVA-NeXT (LLaVA 1.6, 2024)

동적 고해상도를 도입했다. 이미지를 여러 타일로 나눠 각각 처리해 세밀한 시각 정보를 보존한다.

```
1024×768 이미지 → 4개 타일 (512×384) + 썸네일 1개
각 타일을 독립적으로 CLIP 인코딩
LLM에 순서대로 입력
```

고해상도 이미지에서 OCR(이미지 내 텍스트 읽기), 세밀한 시각 추론 성능이 크게 향상됐다.

## 오픈소스 생태계

LLaVA의 오픈소스 공개는 멀티모달 연구를 민주화했다. 이후 InternVL, Phi-3-Vision, MiniCPM-V, Idefics 등 수십 개의 오픈소스 멀티모달 모델이 LLaVA의 설계를 따랐다.

베이스 LLM을 바꾸면 성능이 올라간다. LLaMA 7B → Mistral 7B → LLaMA 3 8B로 교체하면서 같은 아키텍처에서 성능이 계속 향상됐다.

```python
from transformers import LlavaNextProcessor, LlavaNextForConditionalGeneration
from PIL import Image
import torch

processor = LlavaNextProcessor.from_pretrained("llava-hf/llava-v1.6-mistral-7b-hf")
model = LlavaNextForConditionalGeneration.from_pretrained(
    "llava-hf/llava-v1.6-mistral-7b-hf",
    torch_dtype=torch.float16,
    device_map="auto"
)

image = Image.open("chart.png")
prompt = "[INST] <image>\n이 차트에서 가장 높은 값은 얼마인가요? [/INST]"

inputs = processor(prompt, image, return_tensors="pt").to("cuda")
output = model.generate(**inputs, max_new_tokens=200)
print(processor.decode(output[0], skip_special_tokens=True))
```

## 트레이드오프

LLaVA의 선형 투영 방식은 256개 시각 토큰을 LLM 컨텍스트에 차지한다. LLM의 컨텍스트 윈도우를 줄이는 것이 단점이다. 타일 방식(LLaVA-NeXT)은 더 많은 토큰(1024개 이상)을 사용해 컨텍스트 소비가 크다.

또한 LLaVA는 시각 인코더가 고정(CLIP 또는 DINOv2)이다. 매우 특수한 도메인(예: 의료 X-ray, 병리 슬라이드)에서는 특화된 비전 인코더로 교체하거나 파인튜닝이 필요하다.
