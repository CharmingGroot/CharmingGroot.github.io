---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "072. BERT — 양방향 트랜스포머 인코더"
date: 2026-06-14
tags: [ai, nlp, bert, transformer, pre-training, fine-tuning, mlm, nsp, contextual-embedding, google]
summary: "BERT(2018)는 트랜스포머 인코더를 양방향으로 사전학습한 모델이다. MLM과 NSP 두 가지 태스크로 대규모 텍스트에서 언어 표현을 학습하고, 다운스트림 태스크에 파인튜닝한다. 문맥 의존 임베딩으로 다의어를 처리하고, 이후 NLP 사전학습 모델의 기준이 됐다."
slug: "072-bert"
categories: ["AI · ML"]
---

Word2Vec은 단어 하나에 벡터 하나다. "배"는 과일이든 신체 부위든 교통수단이든 항상 같은 벡터다. 문맥이 없다.

2018년 Google의 Devlin 등이 발표한 BERT(Bidirectional Encoder Representations from Transformers)는 이 한계를 해결했다. 같은 단어라도 문맥에 따라 다른 벡터를 생성한다. "배가 고프다"의 배와 "배를 타다"의 배가 다른 임베딩을 갖는다.

## 핵심 아이디어: 양방향성

GPT(2018)도 트랜스포머 기반이었지만 왼쪽에서 오른쪽으로만 읽는 단방향(left-to-right) 모델이었다. "나는 [MASK]를 먹었다"에서 [MASK]를 예측할 때 "먹었다"를 보지 못한다.

BERT는 양방향으로 문맥을 본다. [MASK] 앞뒤 모든 단어를 참조한다. 트랜스포머 인코더의 셀프 어텐션이 모든 위치를 동시에 본다는 특성을 그대로 활용한다.

## 사전학습 태스크

대규모 텍스트(Wikipedia + BookCorpus, 33억 단어)에서 레이블 없이 두 가지 태스크로 학습한다.

### MLM (Masked Language Model)

입력 토큰의 15%를 랜덤하게 마스킹하고 원래 토큰을 예측한다.

```
원문:   나는 오늘 [MASK]를 먹었다
정답:   사과
```

마스킹 전략이 단순하지 않다. 15% 중에서:
- 80%는 `[MASK]`로 교체
- 10%는 랜덤 단어로 교체
- 10%는 원래 단어 유지

랜덤 교체와 원본 유지를 섞는 이유는 파인튜닝 시 `[MASK]` 토큰이 등장하지 않는 불일치를 완화하기 위해서다. 모델이 어떤 토큰이든 문맥을 보고 표현을 만들도록 강제한다.

### NSP (Next Sentence Prediction)

두 문장 A, B가 주어졌을 때 B가 A 다음 문장인지 예측한다.

```
[CLS] 나는 사과를 먹었다 [SEP] 맛있었다 [SEP]  → IsNext
[CLS] 나는 사과를 먹었다 [SEP] 하늘이 파랗다 [SEP] → NotNext
```

50%는 실제 연속 문장, 50%는 랜덤 문장 쌍으로 학습한다. 문장 간 관계를 이해하는 능력을 학습한다.

NSP는 이후 연구(RoBERTa)에서 실제 효과가 미미하거나 오히려 해롭다는 것이 밝혀졌다.

## 입력 표현

BERT의 입력은 세 가지 임베딩의 합이다.

```
입력 = Token Embedding + Segment Embedding + Position Embedding

Token:    각 토큰의 임베딩 벡터
Segment:  문장 A인지 B인지 (0 또는 1)
Position: 시퀀스 내 위치 (학습 가능한 임베딩)
```

시작에 `[CLS]`, 문장 경계마다 `[SEP]`를 추가한다.

```
[CLS] 토큰 A1 A2 [SEP] 토큰 B1 B2 [SEP]
```

`[CLS]` 토큰의 최종 출력 벡터가 문장 전체의 표현으로 사용된다. 분류 태스크에서 이 벡터 위에 선형 레이어를 얹어 파인튜닝한다.

## 모델 크기

| 모델 | 레이어 | 히든 크기 | 헤드 수 | 파라미터 |
|---|---|---|---|---|
| BERT-base | 12 | 768 | 12 | 110M |
| BERT-large | 24 | 1024 | 16 | 340M |

## 파인튜닝

사전학습된 BERT에 태스크별 레이어를 추가하고 전체를 함께 파인튜닝한다. 소량의 레이블 데이터로도 좋은 성능이 나온다.

```
문장 분류:    [CLS] 벡터 → 선형 레이어 → 클래스
개체명 인식:  각 토큰 벡터 → 선형 레이어 → BIO 태그
질의응답:     각 토큰 벡터 → 시작/끝 위치 예측
문장 유사도:  두 문장 → [CLS] 벡터 → 유사도 점수
```

```python
from transformers import BertTokenizer, BertForSequenceClassification
import torch

tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')
model = BertForSequenceClassification.from_pretrained('bert-base-uncased', num_labels=2)

inputs = tokenizer("I love this movie!", return_tensors="pt")
outputs = model(**inputs)
logits = outputs.logits
```

## 문맥 의존 임베딩

BERT의 각 레이어 출력이 임베딩이다. 같은 단어라도 문맥에 따라 다른 벡터를 갖는다.

```
"나는 배가 고프다" → "배" = 신체 부위 임베딩
"나는 배를 타다" → "배" = 교통수단 임베딩
"나는 배를 먹었다" → "배" = 과일 임베딩
```

레이어마다 다른 수준의 정보를 담는다. 초기 레이어는 품사나 구문 정보, 후반 레이어는 의미론적 정보에 특화된다. 태스크에 따라 특정 레이어의 출력을 사용하거나 여러 레이어를 가중합한다.

## BERT의 한계

최대 시퀀스 길이가 512 토큰이다. 긴 문서를 처리하려면 잘라야 한다.

`[MASK]` 토큰이 사전학습 시에만 등장하고 파인튜닝 시에는 없는 불일치(pretrain-finetune discrepancy)가 있다.

MLM은 전체 토큰의 15%만 예측하므로 GPT의 자기회귀 방식보다 학습 효율이 낮다. 각 스텝에서 전체 시퀀스를 처리하지만 손실은 15%에서만 발생한다.

텍스트 생성에 적합하지 않다. 인코더 구조라 다음 토큰을 예측하는 자기회귀 생성을 할 수 없다. 분류, 추출, 이해 태스크에 강점이 있다.

## 트레이드오프

BERT는 파인튜닝 비용이 작다. 사전학습된 가중치에서 출발하므로 수천~수만 개의 레이블 데이터로도 충분한 성능이 나온다. 그러나 추론이 느리다. 512 토큰 입력에서 BERT-base도 CPU에서 수백 밀리초가 걸린다. 실시간 서비스에서는 BERT의 경량화 버전인 DistilBERT, TinyBERT를 사용한다.
