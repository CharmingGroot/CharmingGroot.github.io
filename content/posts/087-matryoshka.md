---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "087. Matryoshka Representation Learning — 가변 차원 임베딩"
date: 2026-06-14
tags: [ai, matryoshka, mrl, embedding, dimensionality, flexible-embedding, openai, text-embedding-3]
summary: "MRL(Matryoshka Representation Learning, 2022)은 하나의 임베딩 모델이 다양한 차원에서 모두 좋은 성능을 내도록 학습하는 방법이다. 큰 임베딩 벡터의 앞부분만 잘라내도 성능이 유지된다. 저장/속도와 정확도 사이를 동적으로 조절할 수 있다."
slug: "087-matryoshka"
categories: ["AI · ML"]
---

임베딩 차원은 보통 고정이다. 768차원 모델은 항상 768차원 벡터를 반환한다. 정밀도가 필요할 때는 차원이 크면 좋지만, 빠른 검색이나 저장 공간 절약이 필요할 때는 작은 차원이 낫다. 두 요구를 한 모델로 처리할 수 없었다.

Google Research의 Kusupati 등이 2022년 발표한 MRL(Matryoshka Representation Learning)은 이 문제를 해결한다. 러시아 전통 인형 마트료시카처럼, 큰 임베딩 안에 여러 크기의 유효한 임베딩이 중첩된다.

## 학습 방식

MRL은 하나의 학습 과정에서 여러 차원의 임베딩을 동시에 최적화한다.

전체 d차원 임베딩과 그 앞부분 d/2, d/4, d/8... 차원 임베딩이 모두 잘 동작하도록 손실 함수를 설계한다.

```
총 손실 = Σ loss(임베딩[:d]) + loss(임베딩[:d/2]) + ... + loss(임베딩[:8])

임베딩[:d/2]는 d차원 임베딩의 앞 절반만 사용
```

이 학습 방식으로 앞부분 차원들이 가장 중요한 정보를 담도록 정렬된다. 뒤로 갈수록 세밀한 보조 정보를 담는다.

## 실제 사용

```python
from openai import OpenAI
client = OpenAI()

# text-embedding-3 계열이 MRL 방식
response = client.embeddings.create(
    model="text-embedding-3-large",  # 최대 3072차원
    input="k8s에서 HPA 동작 방식",
    dimensions=256    # 256차원으로 잘라내기
)
embedding = response.data[0].embedding
# len(embedding) == 256
```

`dimensions` 파라미터로 원하는 차원을 지정한다. API가 내부적으로 앞부분만 반환한다.

직접 자를 수도 있다.

```python
full_embedding = get_embedding(text)  # 1536차원
small_embedding = full_embedding[:256]  # 앞 256차원만 사용
small_embedding = small_embedding / norm(small_embedding)  # L2 정규화 필수
```

## 차원별 성능

MTEB 기준 `text-embedding-3-large`의 차원별 성능:

| 차원 | MTEB 평균 |
|---|---|
| 3072 (전체) | 64.6 |
| 1536 | 64.1 |
| 512 | 63.0 |
| 256 | 61.6 |
| 64 | 55.4 |

3072차원의 96%를 512차원으로 달성한다. 저장 공간은 6분의 1이다.

## 실용적 활용

**2단계 검색 파이프라인**: 1단계에서 작은 차원(빠른 검색)으로 후보를 넓게 추출하고, 2단계에서 큰 차원으로 재정렬한다. 단일 임베딩 모델로 Bi-Encoder의 역할을 두 스케일에서 수행한다.

**비용-성능 최적화**: 수억 개 벡터를 저장할 때 차원을 절반으로 줄이면 저장 비용도 절반이다. MTEB 점수 손실이 크지 않으면 충분히 가치 있는 트레이드오프다.

**엣지 디바이스**: 모바일이나 임베디드 환경에서 64~128차원으로 가볍게 사용한다.

## 비MRL 모델과의 차이

일반 임베딩 모델을 임의로 잘라내면 성능이 급격히 떨어진다. 뒷부분 차원도 중요한 정보를 담고 있기 때문이다. MRL은 앞부분에 정보를 집중시키도록 학습해 잘라내도 성능이 유지된다.

`all-MiniLM-L6-v2`처럼 MRL이 아닌 모델의 384차원 임베딩을 절반으로 자르면 성능이 크게 떨어진다.

## 트레이드오프

MRL 학습은 여러 차원에서 동시에 최적화하므로 단일 차원 최적화보다 학습이 복잡하다. 그러나 OpenAI text-embedding-3 계열처럼 사전학습된 MRL 모델을 사용한다면 이 복잡성은 사용자에게 투명하다. 사용 측면에서는 유연성만 얻는다.
