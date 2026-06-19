---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "079. 하이브리드 검색 — BM25 + 벡터 검색"
date: 2026-06-14
tags: [ai, rag, hybrid-search, bm25, dense-retrieval, sparse-vector, rrf, reranking, elasticsearch]
summary: "벡터 검색은 의미 유사도를 잘 포착하지만 정확한 키워드 매칭에 약하다. BM25는 반대다. 두 방식을 결합한 하이브리드 검색이 실무 RAG에서 더 안정적인 성능을 낸다. RRF로 두 순위를 결합하고 Cross-Encoder로 재정렬하는 전체 파이프라인을 다룬다."
slug: "079-hybrid-search"
categories: ["AI · ML"]
---

벡터 검색이 만능이 아니다.

"GPT-4o 모델 ID가 뭐야?"라는 쿼리에 벡터 검색은 "GPT-4o"와 의미적으로 유사한 문서를 찾는다. 그러나 정확한 모델 ID 문자열이 포함된 문서를 찾는 것은 키워드 매칭이 더 확실하다.

반대로 "텍스트를 벡터로 변환하는 방법"이라는 쿼리에는 "임베딩 모델 사용법"이라는 문서가 관련 있다. 공통 키워드가 없어도 의미가 같다. 키워드 검색은 이런 쿼리를 놓친다.

하이브리드 검색은 두 방식을 결합한다.

## BM25 (Best Match 25)

TF-IDF의 개선판이다. 문서에서 단어의 빈도와 문서 간 역빈도를 조합해 관련도를 계산한다.

```
BM25(q, d) = Σ IDF(t) × (TF(t,d) × (k1+1)) / (TF(t,d) + k1×(1-b+b×|d|/avgdl))

TF(t,d):  문서 d에서 단어 t의 빈도
IDF(t):   단어 t가 희귀할수록 높음 (많은 문서에 등장하면 낮음)
|d|:      문서 길이
avgdl:    평균 문서 길이
k1, b:    조정 파라미터 (보통 k1=1.2~2.0, b=0.75)
```

단어 빈도가 증가해도 점수가 포화(saturation)되도록 설계해 TF-IDF보다 안정적이다.

Elasticsearch, OpenSearch가 기본 검색 알고리즘으로 BM25를 사용한다.

## 스파스 벡터 표현

BM25를 벡터 DB와 통합하는 방법이 스파스 벡터다. 어휘 크기만큼의 차원을 갖지만 대부분이 0이고, 등장한 단어의 차원에만 BM25 점수가 채워진다.

```
어휘: [사과, 배, k8s, HPA, Pod, ...]
문서: "HPA는 Pod을 스케일링한다"
스파스 벡터: {HPA: 2.3, Pod: 1.8, 스케일링: 1.5, 나머지: 0}
```

SPLADE 같은 모델은 BERT를 이용해 문서의 잠재 의미를 스파스 벡터로 표현한다. 단순 단어 빈도가 아니라 의미를 반영한 스파스 표현이라 BM25보다 성능이 좋다.

Qdrant와 Pinecone은 스파스+덴스 벡터를 함께 저장하는 네이티브 하이브리드 검색을 지원한다.

## RRF (Reciprocal Rank Fusion)

BM25 결과와 벡터 검색 결과를 하나로 합치는 방법이다. 점수의 절대값이 아니라 **순위**를 기반으로 결합한다.

```
RRF(d) = Σ 1 / (k + rank_i(d))
         검색 방식 i마다

k: 상수 (보통 60), 상위 순위의 영향을 완화
rank_i(d): i번째 검색 방식에서 문서 d의 순위
```

문서가 두 방식 모두에서 높은 순위이면 RRF 점수가 높다.

```python
def rrf(bm25_results, vector_results, k=60):
    scores = {}
    for rank, doc_id in enumerate(bm25_results):
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
    for rank, doc_id in enumerate(vector_results):
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: -x[1])
```

점수 스케일이 달라도 순위 기반이라 자연스럽게 통합된다. 가중치 튜닝 없이도 안정적인 결과를 낸다.

## 전체 파이프라인

실무 RAG의 전형적인 검색 파이프라인이다.

```
쿼리
  ├→ BM25 검색 → 상위 50개
  └→ 벡터 검색 → 상위 50개
        ↓ RRF 결합
      상위 20개 후보
        ↓ Cross-Encoder 리랭킹
      최종 상위 5개
        ↓ LLM 답변 생성
```

**1단계 검색(Retrieval)**: Bi-Encoder + BM25로 빠르게 후보를 넓게 모은다  
**2단계 리랭킹(Reranking)**: Cross-Encoder로 정확하게 재정렬한다

Cross-Encoder는 쿼리와 각 후보를 함께 처리해 정밀한 관련도를 계산한다. 20개에 대해서만 실행하므로 속도 부담이 없다.

## Elasticsearch 하이브리드 검색

```python
from elasticsearch import Elasticsearch

client = Elasticsearch()

# 하이브리드 쿼리
response = client.search(
    index="documents",
    body={
        "query": {
            "bool": {
                "should": [
                    # BM25
                    {"match": {"content": query_text}},
                    # 벡터 검색 (kNN)
                    {"knn": {
                        "field": "embedding",
                        "query_vector": query_embedding,
                        "num_candidates": 50,
                        "k": 10,
                    }}
                ]
            }
        }
    }
)
```

## 트레이드오프

하이브리드 검색은 운영 복잡도가 높아진다. BM25 인덱스와 벡터 인덱스를 둘 다 관리해야 하고, 인덱스 동기화가 필요하다. 단일 방식 대비 저장 공간도 더 필요하다.

그러나 실무에서 "정확한 제품명이나 코드가 들어간 쿼리"와 "개념적 질문"을 모두 잘 처리해야 하는 경우가 대부분이다. 단순 벡터 검색만으로는 전자가 취약하다. 처음부터 하이브리드로 구성하는 것이 나중에 마이그레이션하는 것보다 낫다.
