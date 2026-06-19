---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "067. AI 모델 로드맵 — 발전 순서 목록"
date: 2026-06-14
tags: [ai, roadmap, index, deep-learning, vision, embedding, multimodal, rag, inference]
summary: "딥러닝 모델들의 발표 연도 기준 학습 로드맵. CNN 발전사부터 멀티모달, 추론 최적화, 에이전트까지 순서대로 정리한다."
slug: "067-ai-model-roadmap"
categories: ["AI · ML"]
---

## 완료
- [[068-cnn-alexnet-resnet|068. AlexNet → ResNet — CNN 발전사]] ✓
- [[069-yolo|069. YOLO 계보 — 실시간 객체 탐지]] ✓
- [[065-attention-is-all-you-need|065. Attention Is All You Need]] ✓
- [[066-sentence-transformers|066. Sentence Transformers]] ✓

---

## 2013–2017 — 단어 임베딩과 기반 기술
- [[070-word2vec-glove|070. Word2Vec / GloVe — 단어 임베딩의 시작]]
- [[071-tokenizer|071. 토크나이저 — BPE, WordPiece, SentencePiece]]

## 2018–2019 — BERT와 사전학습 혁명
- [[072-bert|072. BERT — 양방향 트랜스포머 인코더]]
- [[073-roberta|073. RoBERTa — BERT 학습 방식 개선]]

## 2020 — 트랜스포머의 비전 확장
- [[074-detr|074. DETR — 트랜스포머 기반 객체 탐지]]
- [[075-vit|075. ViT — Vision Transformer]]

## 2020–2021 — 검색과 임베딩 심화
- [[076-colbert|076. ColBERT — Late Interaction 검색]]
- [[077-chunking|077. 청킹 전략 — RAG를 위한 텍스트 분할]]
- [[078-vector-db|078. 벡터 DB — Qdrant, pgvector, Pinecone]]
- [[079-hybrid-search|079. 하이브리드 검색 — BM25 + 벡터 검색]]
- [[080-rag|080. RAG — 검색 증강 생성 파이프라인]]
- [[081-mteb|081. MTEB — 임베딩 모델 벤치마크]]

## 2021 — 자기지도학습과 멀티모달
- [[082-dino|082. DINO — 자기지도학습 비전]]
- [[083-clip|083. CLIP — 텍스트-이미지 공동 임베딩]]

## 2022 — 멀티모달 확장과 학습 효율화
- [[084-blip|084. BLIP — 이미지 캡셔닝과 VQA]]
- [[085-flamingo|085. Flamingo — Few-shot 멀티모달]]
- [[086-flash-attention|086. FlashAttention — 어텐션 메모리 최적화]]
- [[087-matryoshka|087. Matryoshka Representation Learning]]
- [[088-prompt-prefix-tuning|088. Prompt Tuning / Prefix Tuning]]
- [[089-peft|089. PEFT — 파라미터 효율적 파인튜닝 프레임워크]]
- [[090-gptq|090. GPTQ — 사후 학습 양자화]]

## 2023 — 오픈소스 멀티모달과 추론 최적화
- [[091-dinov2|091. DINOv2 — 범용 비전 특징 추출]]
- [[092-sam|092. SAM — Segment Anything Model]]
- [[093-blip2|093. BLIP-2 — Q-Former 기반 멀티모달]]
- [[094-llava|094. LLaVA — 오픈소스 멀티모달 LLM]]
- [[095-qlora|095. QLoRA — 4bit 양자화 + LoRA]]

---

## 이후 (96~)
- 096. AWQ / GGUF — 추론 양자화
- 097. PagedAttention / vLLM — KV 캐시 서빙
- 098. Speculative Decoding
- 099. Function Calling / Tool Use
- 100. BGE / E5 — 현세대 임베딩 모델
- 101. BGE-M3 — 다국어 다기능 임베딩
- 102. ReAct — 추론과 행동의 교차
- 103. MCP — 모델 컨텍스트 프로토콜
