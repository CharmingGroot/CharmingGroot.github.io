---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "073. RoBERTa — BERT 학습 방식 개선"
date: 2026-06-14
tags: [ai, nlp, roberta, bert, pre-training, mlm, dynamic-masking, facebook, training-recipe]
summary: "RoBERTa(2019)는 BERT 아키텍처를 바꾸지 않고 학습 방식만 개선해 성능을 크게 높였다. NSP 제거, 더 많은 데이터, 더 큰 배치, 동적 마스킹이 핵심이다. '좋은 사전학습 레시피'가 아키텍처만큼 중요하다는 것을 보여줬다."
slug: "073-roberta"
categories: ["AI · ML"]
---

BERT가 발표된 지 얼마 지나지 않아 Facebook AI의 Liu 등은 BERT가 충분히 학습되지 않았다는 것을 발견했다. 2019년 발표한 RoBERTa(Robustly Optimized BERT Pretraining Approach)는 아키텍처는 그대로 두고 학습 방식만 바꿔 BERT를 크게 앞섰다.

## BERT의 어디가 문제였나

논문의 핵심 주장은 단순하다. BERT는 학습이 부족했다(undertrained). 더 오래, 더 많은 데이터로, 더 큰 배치로 학습하면 성능이 크게 오른다.

## 주요 변경 사항

### NSP 제거

BERT의 NSP(Next Sentence Prediction) 태스크를 제거했다. 실험 결과 NSP가 오히려 성능을 해친다는 것을 발견했다.

NSP를 위해 두 문장을 이어붙이면 각 문장이 짧아진다. 하나의 긴 문서를 연속으로 처리하는 것이 문맥 학습에 더 유리하다. RoBERTa는 단일 문장이 아닌 문서 단위의 긴 시퀀스(최대 512 토큰)를 그대로 입력한다.

### 동적 마스킹 (Dynamic Masking)

BERT는 데이터 전처리 시 마스킹을 한 번 고정해 학습 내내 같은 마스킹 패턴을 사용한다.

RoBERTa는 매 에폭(epoch)마다 다른 마스킹 패턴을 적용한다. 같은 문장이라도 에폭마다 다른 토큰이 마스킹된다. 40에폭 학습이면 같은 문장을 40가지 다른 마스킹 패턴으로 본다. 더 다양한 학습 신호를 제공한다.

### 더 많은 데이터

BERT: Wikipedia + BookCorpus (16GB)  
RoBERTa: Wikipedia + BookCorpus + CC-News + OpenWebText + Stories (160GB)

10배 더 많은 데이터로 학습했다.

### 더 크고 오래

BERT-base: 배치 256, 100만 스텝  
RoBERTa: 배치 8192, 50만 스텝 (실질적으로 8배 더 많은 토큰)

큰 배치는 더 안정적인 기울기 추정을 제공하고, 학습률을 더 높게 설정할 수 있다.

### 더 큰 BPE 어휘

BERT의 WordPiece 어휘(30,000) 대신 GPT-2의 Byte-level BPE(50,000)를 사용한다. OOV가 없고 다양한 언어와 특수 문자를 처리한다.

## 성능 비교

GLUE 벤치마크(자연어 이해 종합 평가):

| 모델 | GLUE 점수 |
|---|---|
| BERT-large | 80.4 |
| RoBERTa-large | 88.5 |

같은 아키텍처에서 학습 방식만 바꿔 8점이 올랐다.

## 시사점

RoBERTa가 주는 교훈은 아키텍처 혁신만큼 **학습 레시피**가 중요하다는 것이다.

이후 연구들이 동일한 교훈을 반복해서 확인했다. LLaMA가 GPT-3보다 작은 모델로 비슷한 성능을 낸 것도 더 많은 데이터를 더 오래 학습했기 때문이었다. Chinchilla 논문은 모델 크기와 학습 토큰 수의 최적 비율을 제시하며 당시 모델들이 모두 학습 부족 상태였음을 보였다.

"더 큰 모델이 더 좋다"보다 "같은 크기라면 더 잘 학습된 모델이 더 좋다"가 더 정확한 명제다.

## 트레이드오프

RoBERTa는 BERT보다 학습 비용이 훨씬 높다. 160GB 데이터, 배치 8192, 긴 학습 시간은 대기업이나 연구기관이 아니면 처음부터 학습하기 어렵다. 그러나 사전학습된 가중치를 허깅페이스(Hugging Face)에서 다운로드해 파인튜닝하는 것은 누구나 할 수 있다. 실무에서는 사전학습 비용보다 파인튜닝 비용이 중요하고, 이 부분에서 BERT와 RoBERTa의 차이는 크지 않다.
