---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "077. 청킹 전략 — RAG를 위한 텍스트 분할"
date: 2026-06-14
tags: [ai, rag, chunking, text-splitting, semantic-chunking, sliding-window, langchain, llamaindex]
summary: "RAG 파이프라인에서 청킹은 긴 문서를 임베딩 가능한 크기의 조각으로 나누는 과정이다. 청킹 방식이 검색 품질을 직접 결정한다. 고정 크기, 재귀적 분할, 시맨틱 청킹까지 각 방식의 원리와 트레이드오프를 다룬다."
slug: "077-chunking"
categories: ["AI · ML"]
---

임베딩 모델은 입력 길이에 제한이 있다. BERT 계열은 512 토큰, 현대 임베딩 모델도 대부분 512~8192 토큰이다. 100페이지 PDF를 통째로 임베딩할 수 없다. 청킹(chunking)은 문서를 이 한계 안에 들어오는 조각으로 나누는 과정이다.

청킹이 RAG 품질을 결정한다. 관련 정보가 청크 경계에서 잘리거나, 청크가 너무 짧아 문맥이 없거나, 너무 길어 핵심이 희석되면 검색이 실패한다.

## 고정 크기 청킹

가장 단순한 방법이다. 토큰 수 기준으로 일정 크기로 자른다.

```python
from langchain.text_splitter import CharacterTextSplitter

splitter = CharacterTextSplitter(
    chunk_size=500,       # 청크당 토큰 수
    chunk_overlap=50,     # 인접 청크 간 겹치는 토큰 수
)
chunks = splitter.split_text(document)
```

**오버랩(overlap)**이 중요하다. 오버랩 없이 자르면 문장이 청크 경계에서 끊긴다. 50~100 토큰 오버랩으로 앞 청크의 끝 부분을 다음 청크 시작에 포함시켜 문맥 연속성을 유지한다.

단점: 문장 중간에서 자를 수 있다. 단락, 섹션 경계를 무시한다.

## 재귀적 문자 분할

LangChain의 `RecursiveCharacterTextSplitter`가 대표적이다. 구분자 우선순위를 설정해 최대한 의미 단위로 자른다.

```python
splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
    separators=["\n\n", "\n", ".", " ", ""]
)
```

`\n\n`(단락 경계)로 먼저 분리 시도 → 청크가 너무 크면 `\n`으로 분리 → 그래도 크면 `.`으로 → 마지막엔 공백이나 문자 단위로. 의미 단위를 최대한 보존하면서 크기 제한을 지킨다.

실무에서 가장 많이 쓰이는 방식이다.

## 마크다운 / HTML 구조 활용

문서에 구조가 있으면 그 구조를 청킹 기준으로 활용한다.

```python
from langchain.text_splitter import MarkdownHeaderTextSplitter

headers = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
]
splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers)
chunks = splitter.split_text(markdown_doc)
# 각 청크에 헤더 메타데이터가 붙어있음
```

섹션별로 나눠지므로 "3장 2절의 내용"을 검색할 때 관련 청크를 잘 찾는다. 각 청크에 `{"h1": "3장", "h2": "2절"}` 메타데이터가 붙어 필터링도 가능하다.

## 시맨틱 청킹

문장 임베딩을 활용해 의미적으로 연결된 문장들을 같은 청크로 묶는다. LlamaIndex의 SemanticSplitterNodeParser가 이 방식을 구현한다.

```
1. 문서를 문장 단위로 분리
2. 인접 문장들의 임베딩 유사도 계산
3. 유사도가 크게 떨어지는 지점에서 청크 경계 설정
```

```
문장1 → 임베딩
문장2 → 임베딩 → 문장1과 유사도 0.92 (같은 청크)
문장3 → 임베딩 → 문장2와 유사도 0.61 (유사도 급감 → 청크 경계)
문장4 → 임베딩 → 문장3과 유사도 0.89 (새 청크)
```

의미 단위로 잘리므로 검색 품질이 좋다. 단점은 청킹 단계에서 임베딩 계산이 필요해 오프라인 처리가 느리다.

## 문서 유형별 전략

| 문서 유형 | 권장 방식 |
|---|---|
| 일반 텍스트 / 블로그 | 재귀적 분할, 500~800 토큰 |
| 마크다운 문서 | 헤더 기반 분할 |
| 코드 | 함수/클래스 단위 분할 |
| PDF (스캔) | OCR 후 단락 감지 |
| 법률/계약서 | 조항 단위 분할 + 계층 메타데이터 |
| QA 쌍 | 질문+답변을 하나의 청크로 |

## 청크 크기 선택

**작은 청크 (128~256 토큰)**
- 검색 정밀도가 높다 (관련 없는 내용이 섞이지 않음)
- 문맥이 부족해 LLM이 답을 생성하기 어려울 수 있다

**큰 청크 (512~1024 토큰)**
- 문맥이 풍부하다
- 검색 시 관련 없는 내용이 섞일 수 있다

**Parent-Child 청킹**: 작은 청크(child)로 검색하고, 검색된 청크의 상위 청크(parent)를 LLM에 전달한다. 검색 정밀도와 문맥 풍부함을 동시에 얻는다.

```
문서 → 큰 청크(parent, 1024 토큰) → 작은 청크(child, 256 토큰)
검색: child 벡터로 찾기 → parent를 LLM에 전달
```

## 트레이드오프

청킹 전략 최적화는 도메인과 쿼리 유형에 따라 다르다. 일반적인 최고 전략은 없다. 실제 쿼리 샘플로 청크 크기별 검색 결과를 직접 평가하는 것이 가장 확실하다. LlamaIndex의 RAG 평가 프레임워크나 RAGAS 같은 도구로 청킹 전략의 Faithfulness, Relevancy를 측정할 수 있다.
