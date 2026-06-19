---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "091. DINOv2 — 범용 비전 특징 추출기"
date: 2026-06-14
tags: [ai, vision, dinov2, self-supervised, meta, feature-extraction, depth-estimation, segmentation, universal]
summary: "DINOv2(2023)는 1억 4200만 장의 정제된 이미지로 학습한 자기지도 비전 모델이다. 파인튜닝 없이 깊이 추정, 세그멘테이션, 분류, 검색 등 다양한 비전 태스크에 직접 사용할 수 있는 범용 비전 특징 추출기다."
slug: "091-dinov2"
categories: ["AI · ML"]
---

DINO(082)는 레이블 없이 의미 있는 비전 표현을 학습할 수 있음을 보였다. 그러나 학습 데이터 규모와 질이 제한적이었다.

Meta AI가 2023년 발표한 DINOv2는 같은 원리를 훨씬 더 큰 스케일로 확장했다. 핵심은 데이터 큐레이션이다.

## 자동 데이터 큐레이션

이전 자기지도 모델들은 인터넷에서 무작위로 수집한 이미지를 그대로 사용했다. DINOv2는 데이터 품질에 집착했다.

**LVD-142M 데이터셋 구축 과정**

1. 인터넷에서 수집한 무제한 이미지 풀
2. ImageNet-22K 같은 큐레이션된 시드 데이터셋과 임베딩 유사도 비교
3. 시드와 너무 가깝거나(중복) 너무 다른(노이즈) 이미지 제거
4. 클래스 균형을 위한 지역 중복 제거(deduplication)

결과: 1억 4200만 장의 정제된 이미지. 규모도 크고 다양성도 높다.

## 학습 방식

DINO + iBOT을 결합했다. DINO는 이미지 수준의 표현을, iBOT은 패치 수준의 표현을 학습한다.

**iBOT (image BERT pre-training with Online Tokenizer)**: BERT의 MLM처럼 이미지 패치를 마스킹하고 복원한다. 패치 수준에서 세밀한 특징을 학습한다.

DINO의 전역 표현 + iBOT의 지역 패치 표현을 함께 학습해 두 가지 추상화 수준에서 모두 좋은 특징을 갖는다.

## 범용성

DINOv2의 핵심 주장은 파인튜닝 없이도 다양한 태스크에 쓸 수 있다는 것이다. 특징 추출기(feature extractor)로만 사용하고 선형 레이어를 얹어도 충분하다.

**분류**: ImageNet에서 선형 프로빙으로 86.5% (ViT-G/14 기준). 파인튜닝된 모델과 비슷한 수준.

**깊이 추정**: 픽셀별 깊이를 예측하는 태스크. 선형 레이어만 추가해도 SOTA에 가까운 성능. DINOv2 특징이 3D 기하학 정보를 암묵적으로 포착하고 있다.

**세그멘테이션**: 어텐션 맵이 객체 경계를 따르는 DINO의 특성이 더 강화됐다.

**이미지 검색**: 특징 벡터의 코사인 유사도만으로 시각적으로 유사한 이미지를 잘 찾는다.

```python
from transformers import AutoImageProcessor, AutoModel
from PIL import Image
import torch

processor = AutoImageProcessor.from_pretrained('facebook/dinov2-base')
model = AutoModel.from_pretrained('facebook/dinov2-base')

image = Image.open("image.jpg")
inputs = processor(images=image, return_tensors="pt")

with torch.no_grad():
    outputs = model(**inputs)

# CLS 토큰: 이미지 전체 표현 (1×768)
cls_features = outputs.last_hidden_state[:, 0, :]

# 패치 토큰: 공간 정보 포함 (256×768, 16×16 그리드)
patch_features = outputs.last_hidden_state[:, 1:, :]
```

## LLM과의 통합

DINOv2는 비전-언어 멀티모달 모델의 비전 인코더로 많이 사용된다. LLaVA 계열 모델들이 DINOv2나 CLIP ViT를 비전 인코더로 선택한다. CLIP은 텍스트와의 정렬이 강하지만 세밀한 시각적 특징이 약한 반면, DINOv2는 순수 비전 표현이 강하다.

## 크기 옵션

| 모델 | 파라미터 | 패치 크기 | 특징 차원 |
|---|---|---|---|
| dinov2-small | 22M | 14×14 | 384 |
| dinov2-base | 86M | 14×14 | 768 |
| dinov2-large | 307M | 14×14 | 1024 |
| dinov2-giant | 1.1B | 14×14 | 1536 |

## 트레이드오프

DINOv2는 레이블 없이 학습했으므로 특정 클래스 분류에서 지도 학습 모델보다 약간 낮을 수 있다. 그러나 다양한 태스크에 즉시 사용 가능한 범용성이 압도적 장점이다. 파인튜닝 없이 특징만 추출해 쓰는 "특징 추출기" 패턴은 빠른 프로토타입 제작에 이상적이다.

`/14` 패치 크기는 `/16`보다 세밀하지만 토큰 수가 1.3배 많아 계산량이 늘어난다. 속도보다 정확도가 중요하다면 giant/14, 속도가 중요하다면 base/14가 현실적인 선택이다.
