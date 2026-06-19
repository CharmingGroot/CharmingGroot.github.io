---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "097. zvec — SQLite처럼 임베드되는 in-process 벡터 데이터베이스"
date: 2026-06-19
tags: [zvec, vector-database, ann, hnsw, embedded, simd, quantization, rag, alibaba, oss-analysis]
summary: "zvec은 애플리케이션 프로세스 안에 박혀 동작하는 임베디드 벡터 DB다. 서버 없이 라이브러리로 dense/sparse 벡터 검색, 전문 검색, 스칼라 필터를 하나의 쿼리로 결합한다. Faiss의 임베디드성과 Milvus의 DB 기능성 사이를 메운다. in-process가 무슨 뜻인지, 6종 인덱스와 HNSW 검색 코드 흐름, VNNI int8 커널 같은 성능 설계, 그리고 RaBitQ·DiskANN이 리눅스 전용이라는 함정까지 분해한다."
source: "https://github.com/alibaba/zvec"
slug: "097-zvec"
categories: ["OSS 분석"]
---

RAG, 추천, 시맨틱 검색은 임베딩 벡터의 근사 최근접 이웃(ANN) 검색을 필요로 한다. 선택지는 보통 둘로 갈렸다. Faiss나 hnswlib 같은 순수 인덱스 라이브러리는 빠르지만 영속성·필터·CRUD가 없다. Milvus나 Qdrant 같은 서버형 벡터 DB는 기능이 풍부하지만 별도 프로세스를 띄우고 운영해야 한다. zvec은 그 사이를 메운다. 스키마·CRUD·WAL 영속성·필터·전문 검색·하이브리드 같은 DB 기능을 갖추되, 별도 서버 없이 애플리케이션 프로세스에 박혀 라이브러리로 동작한다.

비유하면 SQLite의 벡터 DB 버전이다. 알리바바 그룹 내부 프로덕션에서 검증된 엔진을 오픈소스화한 것으로(Apache-2.0), 분석 시점 기준 v0.5.0이다.

## in-process가 무슨 뜻인가

코드로 확인되는 임베디드 모델의 근거는 명확하다. 진입점이 네트워크 클라이언트가 아니라 정적 팩토리 메서드 `Collection::CreateAndOpen(path, schema, option)`이고, `Collection::Ptr`(shared_ptr) 객체를 직접 반환한다. 데이터는 로컬 파일시스템 경로에 저장되고, 동시성은 RPC가 아니라 `{path}/LOCK` 파일락으로 조정된다. 다중 프로세스 읽기는 공유락, 쓰기는 단일 프로세스 배타락이다. 코드베이스 전체에 gRPC나 소켓, 서버 데몬이 없다. SQLite와 정확히 같은 배포 모델이다.

## 핵심 개념

코드의 1급 개념은 `type.h`에 직접 정의돼 있다.

- **IndexType**: `HNSW`, `IVF`, `FLAT`, `HNSW_RABITQ`, `DISKANN`, `VAMANA`, `INVERT`(스칼라 역색인), `FTS`(전문 검색). 벡터 인덱스 6종에 스칼라·전문 검색을 더했다.
- **MetricType**: `L2`(유클리드), `IP`(내적), `COSINE`, `MIPSL2`(Maximum Inner Product를 L2로 환원). metric별 구현 파일이 따로 있다.
- **QuantizeType**: `FP16`, `INT8`, `INT4`, `RABITQ`. 메모리와 속도를 위한 벡터 압축.
- **DataType**: dense 벡터(FP16/FP32/FP64/INT4/INT8/BINARY 등)와 sparse 벡터(SPARSE_VECTOR_FP16/FP32)를 모두 지원한다.

ANN(근사 최근접 이웃)은 정확한 최근접 탐색이 대규모에서 비싸므로 정확도를 약간 희생해 속도를 얻는 그래프·클러스터 기반 근사 검색이다. zvec은 FLAT(완전탐색, 정확)부터 HNSW·Vamana(그래프), IVF(클러스터), DiskANN(디스크 기반)까지 정확도·속도·메모리 트레이드오프의 전 스펙트럼을 제공한다.

## 아키텍처

`src/` 아래가 세 레이어 이상으로 나뉜다.

```
ailego/   — 저수준 토대 (math/SIMD, threadpool, mmap, container, hash)
core/     — 벡터 인식 엔진: ANN 알고리즘 + metric + quantizer
  algorithm/  flat, hnsw, hnsw_rabitq, hnsw_sparse, ivf, vamana, diskann
  metric/     L2, IP, cosine, mips, quantized int8
  quantizer/  fp16, int8, int4, binary, rabitq
turbo/    — AVX-512 VNNI int8 거리 커널 (성능 핫패스)
db/       — DB 레이어: collection, segment, storage(WAL), sqlengine, reranker
binding/  — c (C API), python (pybind11)
```

빌드는 CMake(≥3.13, C++17)다. 산출물은 올인원 `libzvec`와 분리된 `libzvec_ailego`/`libzvec_core` 공유 라이브러리다. C++가 1급 시민이고 C API(`c_api.cc`, 약 243KB)가 Go·Rust·Dart FFI 바인딩의 기반이 된다. 공식 SDK는 Python, Node.js, Go, Rust, Dart/Flutter로 제공된다.

**중요한 함정**: 빌드 옵션이 플랫폼을 게이팅한다. RaBitQ는 Linux x86_64 + AVX2/AVX-512에서만, DiskANN은 Linux x86_64 + libaio에서만 컴파일된다. macOS와 ARM에서는 둘 다 비활성이다. 즉 README의 "Runs Anywhere"는 기본 인덱스(FLAT/HNSW/IVF/Vamana) 기준이고, RaBitQ와 DiskANN은 리눅스 x86_64 전용이다.

## HNSW 검색은 코드에서 어떻게 도는가

주력 인덱스 HNSW를 코드로 따라가면 구조가 드러난다.

레벨 생성은 Faiss 알고리즘을 명시적으로 차용한다. `1 / log(scaling_factor)`로 level multiplier를 구하고 노드별 레벨을 지수 분포로 뽑는다(주석에 "refers faiss get_random_level alg"). 표준 HNSW 방식이다.

삽입(`add_node`)은 SpinLock으로 진입점과 최대 레벨을 읽고, 최상위 레벨부터 노드 레벨까지 greedy descent로 진입점을 좁힌 뒤, 각 레벨에서 이웃 후보를 탐색해 역방향 링크까지 연결한다. 동시성은 전역 SpinMutex에 노드별 락풀 256개(`kLockCnt = 1U<<8`)를 더해 병렬 삽입을 지원한다.

검색(`search`)은 진입점에서 상위 레벨을 greedy하게 내려오며 진입점을 좁히고, 레벨 0에서 beam search를 수행한다. 핫패스는 두 경로로 갈린다. `fast_search_neighbors`는 mmap/연속 메모리 저장에 직접 포인터로 접근하는 무필터 경로이고, `dual_heap_search_neighbors`는 후보 힙·top-k 힙·방문 필터를 쓰는 필터 검색 경로다. 디스패치는 저장 모드와 필터 유무로 결정된다. 무필터 mmap 경로에는 64바이트 캐시라인 단위 소프트웨어 프리페치가 들어간다.

검색 후보 풀 자료구조(LinearPool, BlockHeap)는 NOTICE 파일에 따르면 pyglass(zilliztech, MIT)에서 차용·수정한 것이다. 완전한 from-scratch 구현은 아니고, 검증된 자료구조를 가져다 썼다.

저장 모드는 세 가지다. `mmap`, `buffer_pool`, `contiguous`. `use_contiguous_memory`를 켜면 그래프 노드를 단일 연속 메모리 아레나에 할당해 캐시 지역성과 검색 처리량을 올리는 대신 피크 메모리가 늘어난다. 영속 데이터는 메모리맵 파일이 1차 저장 전략이다.

## SQL 엔진이 DB로 만든다

zvec을 단순 인덱스 라이브러리가 아닌 "DB"로 만드는 핵심 컴포넌트가 `src/db/sqlengine/`에 있다. ANTLR 기반 파서, analyzer, planner를 갖춘 본격 쿼리 엔진이다. `SQLEngine::execute(schema, SearchQuery, segments)`가 진입점이다. 벡터 검색·스칼라 필터·전문 검색을 SQL 유사 쿼리로 표현해 세그먼트들에 걸쳐 실행하고 최적화한다.

## "lightning-fast"의 근거

코드로 확인되는 성능 최적화는 다음과 같다.

- **VNNI int8 커널**(`src/turbo/`): AVX-512 VNNI `_mm512_dpbusd_epi32` 단일 명령으로 곱-누산을 처리하고, 4-way 독립 누산기로 의존성 체인을 분리한다. 단 이 가속은 uniform-quantized int8 경로가 핵심이고, record-quantized는 AVX2 `_mm256_maddubs_epi16` 경로다. "VNNI로 다 빠르다"는 부정확하다.
- **소프트웨어 프리페치**: HNSW 검색에서 이웃 벡터를 캐시라인 단위로 선반입한다.
- **연속 메모리 아레나**: 그래프 노드 단일 할당으로 캐시 지역성을 올린다.
- **mmap 1차 저장** + huge-page 지원.
- **멀티스레딩**: OpenMP가 아니라 자체 ThreadPool(std::thread 기반)을 쓰고, 리눅스에서 `pthread_setaffinity_np`로 CPU 코어를 바인딩해 NUMA 트래픽을 줄인다. Python 바인딩은 쿼리·삽입 시 GIL을 해제해 스레드별 동시 쿼리를 허용한다.
- **양자화**: INT8/INT4/RaBitQ로 메모리 풋프린트와 거리 계산 비용을 동시에 절감한다.

다만 README의 "billions of vectors in milliseconds"나 QPS 그래프는 외부 벤치 문서 기반이며 코드만으로 검증할 수 없다. 인용한다면 어떤 양자화와 플랫폼인지 명시해야 한다.

## 사용법

Python이 가장 간단하다. 스키마 정의 → `create_and_open` → `insert(Doc 리스트)` → `query(VectorQuery, topk)` 흐름이다.

```python
import zvec
schema = zvec.CollectionSchema(
    name="example",
    vectors=zvec.VectorSchema("embedding", zvec.DataType.VECTOR_FP32, 4),
)
collection = zvec.create_and_open(path="./zvec_example", schema=schema)
collection.insert([
    zvec.Doc(id="doc_1", vectors={"embedding": [0.1, 0.2, 0.3, 0.4]}),
])
results = collection.query(
    zvec.VectorQuery("embedding", vector=[0.4, 0.3, 0.3, 0.1]), topk=10)
```

하이브리드 검색은 문자열 필드에 FTS 인덱스를 붙이고 `MultiQuery`에 전문 검색 서브쿼리와 벡터 서브쿼리를 함께 넣어 reranker(기본 RRF, k=60)로 융합한다. 리랭커는 RRF/Weighted/Callback 세 종이다.

## 강점과 한계

**강점**은 임베디드(서버 0개)이면서 풀 DB 기능을 갖춘 SQLite식 배포 단순함, WAL 기반 내구성, 6종 인덱스로 메모리↔디스크와 정확↔속도 전 스펙트럼 커버, dense+sparse+전문 검색을 단일 `MultiQuery`로 융합, 광범위한 SIMD/양자화/멀티스레딩 최적화, 다언어 SDK다.

**한계**는 단일 프로세스 쓰기(다중 읽기는 되지만 쓰기는 단일 writer, 분산·고가용성 없음), 플랫폼 종속(RaBitQ·DiskANN은 리눅스 x86_64 전용), 분산 샤딩·복제 없음(임베디드라 당연하나 초대규모 수평 확장엔 부적합)이다. 코드에 "FtsClause currently bypasses validation (FTS not yet implemented)" 같은 잔재가 있어 영역별 성숙도가 다를 수 있다.

## 차별점

| 항목 | zvec | Faiss / hnswlib | Qdrant / Milvus | pgvector |
|---|---|---|---|---|
| 배포 모델 | in-process 라이브러리 | in-process 라이브러리 | 서버 | Postgres 확장 |
| DB 기능 | 있음 | 없음(순수 인덱스) | 있음 | 있음 |
| 영속성/WAL | 있음 | 거의 없음 | 있음 | Postgres 의존 |
| FTS·하이브리드 | 내장 | 없음 | 있음 | 확장 필요 |
| 운영 부담 | 없음 | 없음 | 높음 | Postgres 운영 |

포지셔닝은 명확하다. Faiss/hnswlib의 임베디드성과 Qdrant/Milvus의 DB 기능성을 합치고 서버 운영 부담을 없앤 것이다. 가장 가까운 경쟁자는 같은 임베디드 벡터 DB인 LanceDB나 Chroma다. zvec의 차별점은 알리바바 프로덕션 검증, 본격 SQL 쿼리 플래너, 다양한 인덱스·양자화, 다언어 SDK다.

## 정리

zvec은 "서버 없는 풀 기능 벡터 DB"라는 빈자리를 채운다. 본질은 검증된 ANN 알고리즘(HNSW는 Faiss 참조 + pyglass 자료구조)과 광범위한 SIMD·양자화 최적화 위에, ANTLR 기반 SQL 쿼리 플래너를 얹어 인덱스 라이브러리를 DB로 끌어올린 구조다. 도입할 때 두 가지를 기억하면 된다. RaBitQ·DiskANN은 리눅스 x86_64 전용이고, 쓰기는 단일 프로세스다. 단일 노드 임베디드 워크로드에는 강하지만 분산 확장은 설계 범위 밖이다.
