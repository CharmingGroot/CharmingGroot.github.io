---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "084. BLIP — 이미지 캡셔닝과 VQA"
date: 2026-06-14
tags: [ai, blip, multimodal, image-captioning, vqa, bootstrapping, noisy-data, salesforce]
summary: "BLIP(2022)은 노이즈가 많은 웹 이미지-텍스트 쌍을 정제해 학습하는 부트스트래핑 방식을 도입했다. 이미지 이해(Image-Text Matching)와 이미지-텍스트 생성(Captioning)을 통합 모델 안에서 처리한다."
slug: "084-blip"
categories: ["AI · ML"]
---

CLIP은 이미지와 텍스트를 같은 공간에 정렬하는 데 뛰어나지만, 텍스트를 생성하지는 못한다. "이 이미지를 설명하세요"나 "이미지에 대한 질문에 답하세요" 같은 생성 태스크에는 적합하지 않다.

Salesforce Research의 Li 등이 2022년 발표한 BLIP(Bootstrapping Language-Image Pre-training)은 이해와 생성을 모두 처리하는 통합 비전-언어 모델이다.

## 세 가지 사전학습 목표

BLIP은 하나의 모델을 세 가지 목표로 동시에 학습한다.

**ITC (Image-Text Contrastive)**: CLIP처럼 이미지와 텍스트 임베딩을 정렬한다. 대조 학습으로 올바른 쌍의 유사도를 높인다.

**ITM (Image-Text Matching)**: 이미지-텍스트 쌍이 매칭되는지 이진 분류한다. 단순한 임베딩 유사도가 아니라 크로스 어텐션으로 두 모달리티를 함께 처리해 더 정밀한 판단을 한다.

**LM (Language Modeling)**: 이미지를 조건으로 텍스트를 자기회귀 방식으로 생성한다. 이미지 캡셔닝, VQA의 답변 생성에 사용된다.

## 아키텍처

이미지 인코더(ViT)와 텍스트 인코더-디코더(BERT 기반)로 구성된다.

텍스트 모듈은 태스크에 따라 세 가지 모드로 동작한다.

```
ITC용:  [텍스트 인코더]  — 이미지 특징과 독립적으로 인코딩
ITM용:  [크로스 어텐션 인코더] — 이미지 특징을 크로스 어텐션으로 참조
LM용:   [인과 마스킹 디코더] — 자기회귀로 텍스트 생성
```

가중치 일부를 세 모드가 공유해 효율적으로 학습한다.

## CapFilt: 노이즈 데이터 정제

웹에서 수집한 이미지-텍스트 쌍은 노이즈가 많다. alt 텍스트가 이미지와 무관하거나("click here", 광고 문구 등) 너무 부정확한 경우가 흔하다.

BLIP의 핵심 기여가 **CapFilt(Captioning and Filtering)**다.

**1단계 (Captioner)**: 깨끗한 데이터(COCO 캡션)로 파인튜닝된 캡셔너가 웹 이미지에 대한 합성 캡션을 생성한다.

**2단계 (Filter)**: ITM 모델이 원본 텍스트와 합성 캡션 모두를 평가해 이미지와 매칭되지 않는 것을 제거한다.

이렇게 정제된 데이터로 재학습하는 과정이 부트스트래핑(bootstrapping)이다. 처음에는 불완전한 데이터로 모델을 학습하고, 학습된 모델로 데이터를 정제해 더 좋은 모델을 만든다.

## 다운스트림 태스크

**Image Captioning (이미지 설명 생성)**
```python
# BLIP으로 이미지 캡션 생성
from transformers import BlipProcessor, BlipForConditionalGeneration
from PIL import Image

processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")

image = Image.open("dog.jpg")
inputs = processor(image, return_tensors="pt")
output = model.generate(**inputs)
caption = processor.decode(output[0], skip_special_tokens=True)
# "a dog playing with a ball in the park"
```

**VQA (Visual Question Answering)**
```python
# 이미지에 대한 질문 답변
question = "이 사진에서 개가 몇 마리인가?"
inputs = processor(image, question, return_tensors="pt")
output = model.generate(**inputs)
answer = processor.decode(output[0], skip_special_tokens=True)
```

## 이후 발전

BLIP의 한계는 이미지 인코더와 언어 모델이 강하게 결합돼 있어 더 강력한 LLM으로 교체하기 어렵다는 것이다. BLIP-2(2023, 093에서 다룸)는 Q-Former라는 중간 모듈로 이 문제를 해결해 Flan-T5, OPT 같은 대형 LLM을 비전 모델과 연결했다.

## 트레이드오프

세 가지 목표를 동시에 학습하는 것은 각 목표의 성능이 단일 목표 모델보다 약간 낮을 수 있다. 그러나 하나의 모델로 다양한 태스크를 처리한다는 실용적 장점이 크다. 용도가 명확하게 캡셔닝이나 VQA 하나라면 전용 모델이 유리하고, 여러 태스크를 단일 모델로 처리해야 한다면 BLIP이 적합하다.
