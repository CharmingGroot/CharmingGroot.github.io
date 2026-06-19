---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "066. Sentence Transformers — 문장 임베딩과 의미 검색"
date: 2026-06-14
tags: [ai, sentence-transformers, sbert, embedding, semantic-search, nlp, bert, siamese-network, rag, cosine-similarity]
summary: "Sentence Transformers(SBERT)는 문장을 고정 크기 벡터로 변환해 의미적 유사도를 빠르게 계산할 수 있게 한다. 2019년 Reimers와 Gurevych가 제안했으며, BERT의 O(n²) 연산 문제를 샴 네트워크 구조로 해결했다. RAG, 의미 검색, 문장 클러스터링의 기반 기술이다."
slug: "066-sentence-transformers"
categories: ["AI · ML"]
---

BERT가 등장한 후 자연어 이해 성능이 크게 향상됐다. 그런데 "이 두 문장이 얼마나 비슷한가"를 BERT로 계산하려면 두 문장을 쌍으로 묶어 함께 입력해야 한다. 10,000개 문장 데이터베이스에서 가장 유사한 문장을 찾으려면 쿼리와 10,000개 문장의 조합 50,000,000쌍을 전부 BERT에 통과시켜야 한다. 현실적으로 불가능한 방식이다.

2019년 Reimers와 Gurevych의 "Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks"가 이 문제를 해결했다.

## 핵심 아이디어

문장을 미리 고정 크기 벡터(임베딩)로 변환해 저장해 둔다. 유사도 계산은 벡터 간 코사인 유사도로 끝낸다.

```
문장 A → SBERT → 벡터 A (768차원)
문장 B → SBERT → 벡터 B (768차원)

유사도 = cosine_similarity(벡터 A, 벡터 B)
```

10,000개 문장의 임베딩을 미리 계산해두면, 이후 검색은 벡터 연산 한 번이다. BERT 방식 대비 속도가 수천~수만 배 빠르다.

## 샴 네트워크 (Siamese Network)

SBERT는 같은 BERT 가중치를 공유하는 두 개의 인코더로 구성된 샴 네트워크(Siamese Network) 구조로 학습한다. 샴 쌍둥이처럼 동일한 가중치를 가진 두 경로가 나란히 실행된다.

```
문장 A ─→ [공유 BERT] ─→ 풀링 ─→ 벡터 A ──┐
                                             ├→ 손실 함수
문장 B ─→ [공유 BERT] ─→ 풀링 ─→ 벡터 B ──┘
```

레이블이 "두 문장은 같은 의미다"이면 두 벡터가 가까워지도록, "다른 의미다"이면 멀어지도록 가중치를 업데이트한다.

## 풀링 전략

BERT의 출력은 토큰별 벡터 시퀀스다. 문장을 하나의 벡터로 만들려면 시퀀스를 합산해야 한다. 이것이 풀링(pooling)이다.

**CLS 토큰 풀링**: BERT는 문장 시작에 `[CLS]` 토큰을 추가하고, 이 토큰의 출력이 문장 전체의 표현을 담도록 학습한다. 이 벡터 하나를 사용하는 방식이다.

**Mean 풀링**: 모든 토큰 벡터의 평균을 낸다. SBERT 논문에서 실험 결과 CLS 풀링보다 Mean 풀링이 더 좋은 성능을 보였다. 현재 대부분의 모델이 Mean 풀링을 기본으로 사용한다.

**Max 풀링**: 각 차원에서 최댓값을 취한다. 특정 특징의 존재 여부를 포착하는 데 유리하다.

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')

sentences = [
    "오늘 날씨가 맑다",
    "오늘은 화창한 날씨다",
    "파이썬으로 웹 서버를 만들었다",
]

embeddings = model.encode(sentences)
# embeddings.shape: (3, 384)
```

## 학습 방식

### NLI 기반 학습 (원 논문)

자연어 추론(NLI) 데이터셋을 사용한다. 두 문장의 관계가 "함의(entailment)", "중립(neutral)", "모순(contradiction)" 세 가지로 레이블돼 있다.

소프트맥스 손실(Softmax Loss)로 학습한다. 두 벡터의 차이(|u-v|)와 원소별 곱(u×v)을 이어 붙여 분류기에 통과시킨다.

### Triplet Loss

앵커(anchor), 포지티브(positive, 유사한 문장), 네거티브(negative, 다른 문장) 세 가지를 동시에 사용한다.

```
L = max(||s_a - s_p||² - ||s_a - s_n||² + ε, 0)
```

앵커와 포지티브의 거리가 앵커와 네거티브의 거리보다 ε만큼 작아지도록 학습한다. 검색 태스크에서 효과적이다.

### Contrastive Learning (현대적 접근)

SimCSE, E5, BGE 등 현재 널리 쓰이는 모델들은 대조 학습(contrastive learning)을 사용한다. 같은 문장을 드롭아웃을 다르게 적용해 두 번 인코딩하면 포지티브 쌍이 되고, 배치 내 다른 문장들이 자동으로 네거티브가 된다(in-batch negatives). 레이블 없이도 고품질 임베딩을 학습할 수 있다.

## 의미 검색 구현

```python
from sentence_transformers import SentenceTransformer, util

model = SentenceTransformer('all-MiniLM-L6-v2')

# 문서 데이터베이스 (미리 계산)
docs = [
    "k8s에서 HPA는 CPU 사용률 기반으로 Pod을 자동 스케일아웃한다",
    "Crossplane은 k8s에서 AWS 인프라를 관리하는 도구다",
    "Stable Diffusion은 잠재 확산 모델 기반 이미지 생성 모델이다",
]
doc_embeddings = model.encode(docs, convert_to_tensor=True)

# 쿼리
query = "파드 자동 확장 방법"
query_embedding = model.encode(query, convert_to_tensor=True)

# 코사인 유사도 검색
scores = util.cos_sim(query_embedding, doc_embeddings)[0]
top_result = scores.argmax()

print(docs[top_result])
# "k8s에서 HPA는 CPU 사용률 기반으로 Pod을 자동 스케일아웃한다"
```

## Bi-Encoder vs Cross-Encoder

Sentence Transformers 생태계에서 자주 나오는 두 가지 아키텍처다.

**Bi-Encoder** (SBERT가 여기에 해당)

두 문장을 각자 독립적으로 인코딩해 벡터를 만든다. 벡터를 미리 계산해 저장할 수 있어 검색 속도가 빠르다. 대규모 검색의 첫 번째 단계(retrieval)에 사용한다.

**Cross-Encoder**

두 문장을 쌍으로 묶어 BERT에 함께 입력한다. 두 문장이 서로 영향을 미치면서 인코딩되므로 정확도가 더 높다. 하지만 미리 계산이 불가능하고 쌍마다 인코딩해야 하므로 느리다. Bi-Encoder가 추린 상위 후보를 다시 정렬하는 두 번째 단계(reranking)에 사용한다.

```
쿼리 → Bi-Encoder → 상위 100개 후보
          ↓
상위 100개 → Cross-Encoder → 최종 상위 10개 (정확도 높음)
```

이 두 단계 파이프라인이 현재 RAG(Retrieval-Augmented Generation) 시스템의 기본 구조다.

## 주요 모델

| 모델 | 차원 | 특징 |
|---|---|---|
| `all-MiniLM-L6-v2` | 384 | 빠르고 작음, 범용 |
| `all-mpnet-base-v2` | 768 | 균형 잡힌 성능 |
| `bge-m3` | 1024 | 다국어, 한국어 포함 |
| `text-embedding-3-small` | 1536 | OpenAI API |
| `intfloat/multilingual-e5-large` | 1024 | 다국어 강점 |

한국어를 포함한 다국어 검색이 필요하면 `bge-m3`나 `multilingual-e5`가 현실적인 선택이다.

## RAG에서의 역할

Sentence Transformers는 RAG 파이프라인의 핵심 컴포넌트다.

```
문서 수집
    ↓ 청킹 (chunk)
텍스트 조각들
    ↓ Sentence Transformers
벡터 임베딩들
    ↓ 벡터 DB 저장 (Pinecone, Qdrant, pgvector)

─── 쿼리 시 ───

사용자 질문
    ↓ Sentence Transformers
쿼리 벡터
    ↓ 벡터 DB 유사도 검색
관련 문서 조각들
    ↓ LLM에 컨텍스트로 주입
최종 답변
```

임베딩 품질이 RAG 전체의 검색 성능을 결정한다. 좋은 임베딩 모델은 "k8s Pod 스케일링 방법"이라는 쿼리가 "HPA를 이용한 수평적 자동 확장"이라는 문서 조각과 매핑될 수 있도록 의미적 유사성을 포착한다.

## 트레이드오프

임베딩 차원이 높을수록 표현력이 좋지만 저장 공간과 검색 속도가 나빠진다. 384차원과 1536차원은 메모리 사용량이 4배 차이 난다. 수백만 개의 문서를 인덱싱하면 이 차이가 의미 있어진다.

Bi-Encoder는 두 문장을 독립적으로 인코딩하므로 두 문장 사이의 미묘한 관계를 놓칠 수 있다. "A가 B보다 크다"와 "B가 A보다 크다"는 단어 구성이 같아도 의미가 반대지만, Bi-Encoder는 두 문장의 임베딩을 비슷하게 만들 수 있다. 정밀도가 중요한 최종 랭킹 단계에서는 Cross-Encoder가 필요하다.
