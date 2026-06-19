---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "083. CLIP — 텍스트-이미지 공동 임베딩"
date: 2026-06-14
tags: [ai, clip, multimodal, contrastive-learning, openai, zero-shot, image-text, embedding]
summary: "CLIP(2021)은 4억 개의 이미지-텍스트 쌍으로 텍스트와 이미지를 같은 임베딩 공간에 정렬한다. 별도 파인튜닝 없이 새로운 분류 태스크에 적용하는 Zero-Shot 분류가 가능하고, 텍스트로 이미지를 검색하거나 이미지로 텍스트를 검색하는 크로스 모달 검색의 기반이 된다."
slug: "083-clip"
categories: ["AI · ML"]
---

이미지 분류 모델은 사전 정의된 클래스만 분류할 수 있다. ImageNet 1000개 클래스를 학습한 모델은 1001번째 클래스를 추가하려면 재학습이 필요하다.

OpenAI가 2021년 발표한 CLIP(Contrastive Language-Image Pre-Training)은 다른 접근을 택했다. 분류 레이블 대신 자연어 설명과 이미지를 같은 공간에 맞추는 것이다.

## 학습 방식

인터넷에서 수집한 4억 개의 이미지-텍스트 쌍으로 학습한다. 각 이미지에는 alt 텍스트나 캡션이 있다.

두 개의 인코더를 사용한다.
- **이미지 인코더**: ViT 또는 ResNet으로 이미지 → 벡터
- **텍스트 인코더**: Transformer로 텍스트 → 벡터

**대조 학습(Contrastive Learning)**: 배치 내 N개 이미지-텍스트 쌍에서 올바른 쌍의 유사도는 높이고, 올바르지 않은 쌍의 유사도는 낮춘다.

```
배치: [(이미지1, 텍스트1), (이미지2, 텍스트2), ..., (이미지N, 텍스트N)]

N×N 유사도 행렬:
         텍스트1  텍스트2  ...  텍스트N
이미지1  [높음    낮음         낮음  ]
이미지2  [낮음    높음         낮음  ]
...
이미지N  [낮음    낮음         높음  ]

대각선(올바른 쌍)의 유사도를 높이고, 나머지를 낮추도록 학습
```

N이 클수록(큰 배치) 더 많은 부정 쌍을 보므로 학습이 강해진다. CLIP은 배치 크기 32,768로 학습했다.

## Zero-Shot 분류

학습된 CLIP으로 새로운 분류 태스크를 파인튜닝 없이 수행한다.

```python
import clip
import torch
from PIL import Image

model, preprocess = clip.load("ViT-B/32")

image = preprocess(Image.open("dog.jpg")).unsqueeze(0)
text = clip.tokenize(["a photo of a dog", "a photo of a cat", "a photo of a car"])

with torch.no_grad():
    image_features = model.encode_image(image)
    text_features = model.encode_text(text)
    
    # 코사인 유사도
    similarity = (image_features @ text_features.T).softmax(dim=-1)
    
print(similarity)  # [0.94, 0.05, 0.01]
```

클래스를 "a photo of a {class}"로 표현한다. 이미지 임베딩과 가장 유사한 텍스트 임베딩의 클래스가 예측이다.

ImageNet 1000개 클래스 Zero-Shot 분류에서 76.2% 정확도를 냈다. ResNet-50의 감독 학습(76.1%)과 비슷한 수준이다.

## 크로스 모달 검색

텍스트로 이미지를 검색하거나, 이미지로 텍스트를 검색하는 것이 자연스럽다.

```python
# 이미지 데이터베이스를 미리 임베딩
image_embeddings = [model.encode_image(img) for img in image_database]

# 텍스트 쿼리로 이미지 검색
query = "빨간 사과가 있는 정물화"
text_embedding = model.encode_text(query)

similarities = [cosine_similarity(text_embedding, img_emb) for img_emb in image_embeddings]
top_images = sorted(zip(similarities, images), reverse=True)[:5]
```

## Stable Diffusion과의 관계

064에서 다룬 Stable Diffusion이 CLIP 텍스트 인코더를 사용한다. 프롬프트를 CLIP으로 임베딩해 U-Net의 크로스 어텐션에 주입한다. CLIP이 텍스트와 이미지를 같은 공간에 정렬했기 때문에, 텍스트 임베딩이 이미지 생성에 의미 있는 조건이 될 수 있다.

## 한계

4억 개 데이터로 학습했지만 특정 도메인(의료 영상, 위성 이미지, 전문 도메인)에서는 일반화가 약하다. "CT 스캔에서 폐 결절"을 Zero-Shot으로 잘 분류하지 못한다.

또한 세밀한 구분에 약하다. "두 마리 개가 공을 쫓는" 같은 복잡한 공간 관계나 속성 구분(빨간 큰 컵 vs 파란 작은 컵)에서 성능이 떨어진다.

OpenCLIP은 CLIP을 오픈소스로 재현한 프로젝트다. Stable Diffusion 2.x와 SDXL이 OpenCLIP ViT-H/G를 텍스트 인코더로 사용한다.

## 트레이드오프

CLIP은 학습 비용이 막대하다. 4억 쌍의 데이터를 대규모 GPU로 수백 GPU-일 학습한다. 이미 학습된 CLIP을 백본으로 사용하고 특정 도메인에 파인튜닝하는 것이 실용적이다. BLIP, LLaVA 같은 후속 모델들이 이 방식을 취했다.
