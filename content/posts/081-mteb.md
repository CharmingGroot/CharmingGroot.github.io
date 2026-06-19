---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "081. MTEB — 임베딩 모델 벤치마크 읽는 법"
date: 2026-06-14
tags: [ai, mteb, embedding, benchmark, evaluation, semantic-search, clustering, sts, huggingface]
summary: "MTEB(Massive Text Embedding Benchmark)는 56개 데이터셋, 8개 태스크로 임베딩 모델을 종합 평가하는 벤치마크다. 모델 선택 시 전체 평균이 아니라 실제 사용 태스크와 언어에 맞는 점수를 봐야 한다."
slug: "081-mteb"
categories: ["AI · ML"]
---

임베딩 모델을 선택할 때 "어떤 게 좋은가요?"라는 질문에 단순한 답은 없다. 코사인 유사도로 문장 쌍의 유사도를 측정하는 태스크와, 수백만 문서에서 관련 문서를 검색하는 태스크, 그리고 문서를 클러스터링하는 태스크는 모두 다른 모델이 잘할 수 있다.

MTEB(Massive Text Embedding Benchmark)는 이 다양한 측면을 표준화된 방식으로 측정한다.

## 8가지 평가 태스크

**Retrieval**: 쿼리에 관련된 문서를 찾는다. RAG의 핵심 태스크다. BEIR 데이터셋 기반. nDCG@10으로 평가한다.

**STS (Semantic Textual Similarity)**: 두 문장의 의미 유사도를 0~5 점수로 예측한다. 예측값과 정답의 피어슨/스피어만 상관관계로 평가한다.

**Classification**: 임베딩 벡터를 특징으로 텍스트를 분류한다. 로지스틱 회귀를 사용해 임베딩 자체의 품질을 측정한다.

**Clustering**: 임베딩으로 텍스트를 군집화한다. V-measure로 평가한다.

**Pair Classification**: 두 텍스트가 같은 의미인지 이진 분류한다.

**Reranking**: 주어진 후보 목록을 재정렬해 관련 문서를 상위에 놓는다.

**Summarization**: 요약이 원문을 잘 반영하는지 평가한다.

**Bitext Mining**: 두 언어에서 서로 번역 관계인 문장 쌍을 찾는다. 다국어 모델 평가에 중요하다.

## MTEB 리더보드 읽는 법

허깅페이스 MTEB 리더보드에서 모델을 비교할 때 전체 평균(Average)만 보면 안 된다.

**실제 사용 태스크를 확인한다**

RAG를 구축한다면 Retrieval 열을 본다. 문장 유사도를 계산한다면 STS 열을 본다. 전체 평균이 높아도 해당 태스크 점수가 낮을 수 있다.

**언어를 확인한다**

대부분의 벤치마크는 영어 기준이다. 한국어가 필요하다면 MTEB의 다국어 버전(MTEB Multilingual) 또는 한국어 특화 벤치마크(KoMTEB, KLUE 등)를 참고한다. `bge-m3`나 `multilingual-e5-large`가 영어 단일 모델보다 전체 평균이 낮더라도 한국어에서는 우위일 수 있다.

**모델 크기와 속도**

임베딩 속도는 추론 지연과 비용에 직결된다. MTEB 리더보드에 파라미터 수와 임베딩 차원이 함께 표시된다. `all-MiniLM-L6-v2`(22M 파라미터, 384차원)는 `text-embedding-3-large`(1536차원)보다 수십 배 빠르지만 점수가 낮다.

**2024년 기준 주요 모델 비교**

| 모델 | MTEB Avg | Retrieval | 차원 | 속도 |
|---|---|---|---|---|
| text-embedding-3-large | 64.6 | 55.4 | 3072 | 느림(API) |
| text-embedding-3-small | 62.3 | 52.8 | 1536 | 느림(API) |
| bge-large-en-v1.5 | 64.2 | 54.3 | 1024 | 중간 |
| bge-m3 | 62.8 | 59.0 | 1024 | 중간 |
| all-mpnet-base-v2 | 57.8 | 43.8 | 768 | 빠름 |
| all-MiniLM-L6-v2 | 56.3 | 41.9 | 384 | 매우 빠름 |

## 모델 선택 프레임워크

1. **언어**: 영어만 → 영어 특화 모델. 한국어 포함 → 다국어 모델
2. **태스크**: RAG → Retrieval 점수 우선. 유사도 → STS 우선
3. **규모**: 수백만 문서 → 차원 낮은 모델로 인덱스 크기 절약
4. **지연**: 실시간 임베딩 필요 → 작은 모델
5. **비용**: self-hosted → 오픈소스. 관리 최소화 → API

## 벤치마크의 한계

MTEB 점수가 높다고 실제 서비스에서 반드시 좋은 것은 아니다. MTEB 데이터셋과 실제 도메인이 다를 수 있다. 법률 문서, 의료 기록, 코드 검색은 MTEB에 잘 반영되지 않는다.

도메인 특화 태스크에서는 범용 모델보다 도메인 데이터로 파인튜닝한 모델이 MTEB 점수는 낮아도 실제 성능이 높을 수 있다. 최종 판단은 실제 데이터로 직접 평가해야 한다.
