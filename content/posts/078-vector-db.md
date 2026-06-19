---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "078. 벡터 DB — Qdrant, pgvector, Pinecone"
date: 2026-06-14
tags: [ai, vector-db, qdrant, pgvector, pinecone, hnsw, ann, semantic-search, rag, embedding]
summary: "벡터 DB는 고차원 임베딩 벡터를 저장하고 근사 최근접 이웃(ANN) 검색을 빠르게 수행하는 데이터베이스다. Qdrant, pgvector, Pinecone 세 가지 대표 선택지의 구조, 인덱싱 알고리즘, 트레이드오프를 다룬다."
slug: "078-vector-db"
categories: ["AI · ML"]
---

임베딩 모델이 만든 벡터는 수백~수천 차원의 실수 배열이다. 이 벡터들을 저장하고, 쿼리 벡터와 가장 유사한 것을 빠르게 찾는 것이 벡터 DB의 역할이다.

단순하게는 모든 벡터와 코사인 유사도를 계산해 정렬하면 된다(브루트 포스). 1,000개 문서에서는 충분하지만, 100만 개가 되면 쿼리마다 100만 번의 내적 계산이 필요하다. 벡터 DB는 **ANN(Approximate Nearest Neighbor)** 알고리즘으로 정확도를 약간 희생하고 속도를 수십~수백 배 높인다.

## HNSW — 주류 인덱싱 알고리즘

대부분의 벡터 DB가 HNSW(Hierarchical Navigable Small World)를 사용한다.

계층적 그래프 구조다. 상위 레이어는 적은 노드가 긴 거리를 연결하고, 하위 레이어로 갈수록 많은 노드가 세밀하게 연결된다.

```
레이어 3: ●────────────────●   (장거리 연결, 소수 노드)
레이어 2: ●──●──────●──●──●
레이어 1: ●─●─●────●─●─●─●
레이어 0: ●●●●●●●●●●●●●●●●●  (모든 노드, 근거리 연결)
```

검색 시 최상위 레이어에서 시작해 목표 벡터에 가까운 방향으로 내려오며 탐색한다. 전체를 보지 않고 관련 영역만 탐색한다.

파라미터 `M`(각 노드의 최대 연결 수)과 `ef_construction`(인덱스 구축 시 탐색 범위)으로 속도-정확도 트레이드오프를 조정한다.

## Qdrant

Rust로 작성된 오픈소스 벡터 DB다. 자체 호스팅과 클라우드 서비스 모두 제공한다.

**특징**

- 필터링 + 벡터 검색을 동시에 효율적으로 처리한다. 메타데이터 필터를 벡터 검색과 결합할 때 성능이 좋다
- 페이로드(payload)로 임의의 JSON 메타데이터를 벡터와 함께 저장한다
- 스파스 벡터와 덴스 벡터를 동시에 저장해 하이브리드 검색을 지원한다

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

client = QdrantClient(url="http://localhost:6333")

# 컬렉션 생성
client.create_collection(
    collection_name="documents",
    vectors_config=VectorParams(size=768, distance=Distance.COSINE),
)

# 벡터 삽입
client.upsert(
    collection_name="documents",
    points=[
        PointStruct(
            id=1,
            vector=[0.1, 0.2, ...],   # 768차원 임베딩
            payload={"text": "원문 텍스트", "source": "doc1.pdf"}
        )
    ]
)

# 검색
results = client.search(
    collection_name="documents",
    query_vector=query_embedding,
    query_filter={"must": [{"key": "source", "match": {"value": "doc1.pdf"}}]},
    limit=5,
)
```

## pgvector

PostgreSQL 확장이다. 기존 PostgreSQL에 벡터 타입과 인덱스를 추가한다.

**특징**

- 기존 PostgreSQL 인프라를 그대로 사용한다. 별도 벡터 DB를 운영하지 않아도 된다
- SQL로 벡터 검색과 관계형 쿼리를 함께 실행한다
- RDS, Supabase, Neon 등 매니지드 PostgreSQL에서 바로 사용 가능하다

```sql
-- 벡터 컬럼 추가
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    content TEXT,
    embedding VECTOR(768)
);

-- HNSW 인덱스 생성
CREATE INDEX ON documents USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- 유사도 검색
SELECT content, 1 - (embedding <=> '[0.1, 0.2, ...]'::vector) AS similarity
FROM documents
ORDER BY embedding <=> '[0.1, 0.2, ...]'::vector
LIMIT 5;

-- 필터와 결합
SELECT content FROM documents
WHERE metadata->>'category' = 'tech'
ORDER BY embedding <=> query_embedding
LIMIT 5;
```

`<=>` 연산자가 코사인 거리, `<->` 는 L2 거리, `<#>` 는 내적이다.

## Pinecone

완전 관리형 클라우드 벡터 DB 서비스다. 자체 호스팅이 필요 없다.

**특징**

- 인프라 관리가 없다. API만으로 사용한다
- 수십억 개 벡터까지 자동 스케일링한다
- Serverless 티어가 있어 소규모 프로젝트에서 무료로 시작할 수 있다

```python
from pinecone import Pinecone

pc = Pinecone(api_key="...")
index = pc.Index("documents")

# 삽입
index.upsert(vectors=[
    {"id": "doc1", "values": [0.1, 0.2, ...], "metadata": {"text": "..."}}
])

# 검색
results = index.query(
    vector=query_embedding,
    top_k=5,
    filter={"category": {"$eq": "tech"}},
    include_metadata=True,
)
```

## 선택 기준

| 기준 | Qdrant | pgvector | Pinecone |
|---|---|---|---|
| 자체 호스팅 | 가능 | 가능 | 불가 |
| 기존 PostgreSQL 통합 | X | O | X |
| 관리 부담 | 중간 | 낮음 (기존 인프라) | 없음 |
| 대규모 벡터 수 | 우수 | 수천만까지 | 수십억 |
| 비용 | 서버 비용 | PostgreSQL 비용 | API 과금 |
| 하이브리드 검색 | 내장 | 별도 구성 | 내장 |

규모가 작고 이미 PostgreSQL을 쓴다면 pgvector로 시작하는 것이 가장 단순하다. 벡터 검색 성능이 병목이 되거나 수천만 이상의 벡터를 다룬다면 Qdrant로 이전한다. 인프라 관리를 최소화하고 빠르게 프로토타입을 만들 때는 Pinecone이 적합하다.

## 트레이드오프

ANN은 근사 검색이다. 정확한 최근접 이웃을 보장하지 않는다. `ef_search`(검색 시 탐색 범위)를 높이면 정확도가 올라가지만 속도가 낮아진다. 의료, 법률 같이 검색 정확도가 중요한 도메인에서는 이 파라미터를 신중하게 설정해야 한다.

벡터 차원이 높을수록(1536, 3072) 인덱스 구축과 검색이 느리고 저장 공간이 커진다. 임베딩 모델을 선택할 때 차원과 성능의 트레이드오프를 고려해야 한다. Matryoshka 방식의 임베딩 모델(text-embedding-3 계열)은 차원을 동적으로 줄일 수 있어 이 문제를 완화한다.
