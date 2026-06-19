---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "076. ColBERT — Late Interaction 검색"
date: 2026-06-14
tags: [ai, nlp, colbert, retrieval, late-interaction, semantic-search, dense-retrieval, maxsim, stanford]
summary: "ColBERT(2020)는 쿼리와 문서를 각각 토큰 단위 벡터로 인코딩하고, 검색 시 MaxSim 연산으로 유사도를 계산하는 Late Interaction 방식을 제안했다. Bi-Encoder의 속도와 Cross-Encoder의 정확도 사이 균형을 잡는다."
slug: "076-colbert"
categories: ["AI · ML"]
---

Sentence Transformers의 Bi-Encoder와 Cross-Encoder는 명확한 트레이드오프가 있다.

Bi-Encoder는 쿼리와 문서를 각각 단일 벡터로 압축해 코사인 유사도를 계산한다. 빠르지만 두 텍스트 간의 세밀한 어휘 매칭이 손실된다.

Cross-Encoder는 쿼리와 문서를 함께 처리해 정밀한 점수를 낸다. 정확하지만 문서마다 추론을 실행해야 해 대규모 검색에 사용할 수 없다.

Stanford의 Khattab과 Zaharia가 2020년 발표한 ColBERT는 두 방식 사이에 새로운 선택지를 제시했다.

## Late Interaction

ColBERT의 핵심 아이디어는 **늦은 상호작용(Late Interaction)**이다.

Bi-Encoder(Early Compression): 쿼리/문서 → 단일 벡터 → 유사도  
Cross-Encoder(Early Interaction): 쿼리+문서 → 함께 처리 → 점수  
ColBERT(Late Interaction): 쿼리/문서 → 토큰 벡터들 → 매칭

쿼리와 문서를 각각 인코딩하되, 단일 벡터가 아니라 **토큰별 벡터 시퀀스**를 유지한다.

```
쿼리 "k8s Pod 스케일링" → [v_k8s, v_Pod, v_스케일링] (3개 벡터)
문서 "HPA는 CPU 기반으로..." → [v_HPA, v_는, v_CPU, ...] (N개 벡터)
```

## MaxSim 연산

유사도 계산은 **MaxSim(Maximum Similarity)**으로 한다.

```
score(쿼리, 문서) = Σ max(쿼리_토큰 · 문서_토큰)
                  쿼리 토큰마다

각 쿼리 토큰이 문서의 모든 토큰과 내적을 계산하고,
그 중 가장 높은 값을 선택(max)한 뒤,
모든 쿼리 토큰의 최댓값을 합산(sum)한다.
```

"k8s" 쿼리 토큰은 문서에서 "쿠버네티스"와 높은 유사도를 갖는다. "스케일링" 쿼리 토큰은 "HPA", "자동", "확장"과 높은 유사도를 갖는다. 각 쿼리 토큰이 문서에서 자신과 가장 관련된 부분을 찾는다.

단일 벡터로 압축했을 때 사라지는 어휘 수준의 매칭 정보를 보존한다.

## 효율적인 인덱싱

Cross-Encoder와 달리 문서 벡터를 **미리 계산해 저장**할 수 있다.

```
오프라인: 문서들 → BERT → 토큰 벡터들 → 인덱스 저장
온라인:   쿼리 → BERT → 토큰 벡터들 → MaxSim → 점수
```

검색 시 쿼리만 새로 인코딩하고, 저장된 문서 벡터로 MaxSim을 계산한다. 문서당 추론이 없다.

## ColBERT v2

2021년 발표된 ColBERT v2는 벡터 압축으로 저장 공간을 줄였다. 토큰 벡터를 잔차 압축(residual compression)으로 양자화해 원본 대비 6~10배 작은 인덱스를 만든다. 속도 손실 없이 저장 공간 문제를 해결했다.

## 성능 위치

| 방식 | 속도 | 정확도 | 저장 공간 |
|---|---|---|---|
| Bi-Encoder | 빠름 | 낮음 | 작음 |
| ColBERT | 중간 | 높음 | 큼 |
| Cross-Encoder | 느림 | 최고 | — |

## 트레이드오프

ColBERT의 단점은 저장 공간이다. 문서당 단일 벡터가 아니라 토큰 수만큼의 벡터를 저장한다. 문서가 100 토큰이면 Bi-Encoder 대비 100배 더 많은 벡터를 저장한다. 수백만 문서 규모에서는 ColBERT v2의 압축이 필수다.

RAGatouille 같은 라이브러리가 ColBERT를 쉽게 사용할 수 있게 래핑해 제공한다. 검색 정확도가 중요하고 저장 공간 여유가 있다면 Bi-Encoder 대신 ColBERT를 고려할 만하다.
