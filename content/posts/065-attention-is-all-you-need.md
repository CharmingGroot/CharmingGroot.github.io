---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "065. Attention Is All You Need — 트랜스포머 논문 핵심 정리"
date: 2026-06-14
tags: [ai, transformer, attention, self-attention, nlp, deep-learning, vaswani, positional-encoding, multi-head-attention]
summary: "2017년 Google Brain의 Vaswani 등이 발표한 논문. RNN 없이 어텐션만으로 시퀀스를 처리하는 트랜스포머 아키텍처를 제안했다. 병렬 연산이 가능하고 장거리 의존성을 직접 포착한다는 두 가지 특성이 이후 모든 대형 언어 모델의 기반이 됐다."
slug: "065-attention-is-all-you-need"
categories: ["AI · ML"]
---

2017년 이전 자연어 처리의 주류는 RNN(순환 신경망)과 LSTM이었다. 이 구조는 시퀀스를 왼쪽에서 오른쪽으로 순서대로 처리한다. "나는 어제 서울에서 맛있는 밥을 먹었다"라는 문장을 처리할 때 "먹었다"에 도달하는 시점에는 "나는"의 정보가 여러 스텝을 거쳐 희석된다. 이것이 장거리 의존성 문제다. 또한 순서대로 처리해야 하므로 병렬화가 불가능해 학습이 느렸다.

Vaswani 등의 "Attention Is All You Need"는 순환 구조를 완전히 제거하고 어텐션 메커니즘만으로 시퀀스를 처리하는 트랜스포머(Transformer)를 제안했다.

## 핵심 아이디어: Self-Attention

어텐션(attention)은 문장 내 각 단어가 다른 단어들과 얼마나 관련 있는지를 가중치로 표현하는 메커니즘이다. "나는 사과를 먹었다"에서 "먹었다"는 "사과"와 강하게 관련되고 "나는"과는 약하게 관련된다. 이 관련도를 학습하는 것이 셀프 어텐션(self-attention)이다.

### Scaled Dot-Product Attention

입력 벡터에서 세 가지 행렬을 만든다.

- **Q (Query)** — "나는 어떤 정보를 찾고 있나"
- **K (Key)** — "나는 어떤 정보를 갖고 있나"
- **V (Value)** — "실제로 전달할 정보"

```
Attention(Q, K, V) = softmax(QK^T / √d_k) × V
```

1. Q와 K의 내적(dot product)으로 각 단어 쌍의 유사도 점수를 구한다
2. 차원 수의 제곱근 √d_k로 나눠 스케일링한다. d_k가 커질수록 내적 값이 커져 softmax가 극단적인 값으로 수렴하는 것을 방지한다
3. Softmax로 확률 분포로 변환한다 (어텐션 가중치)
4. V에 가중치를 곱해 최종 출력을 만든다

√d_k로 나누는 것이 "Scaled"의 의미다.

모든 단어 쌍의 관계를 한 번에 행렬 연산으로 계산하므로 병렬화가 가능하다.

### Multi-Head Attention

어텐션을 한 번만 하는 것보다 여러 번 병렬로 수행하면 더 풍부한 관계를 포착할 수 있다. h개의 헤드가 각자 다른 Q, K, V 투영 행렬을 학습한다.

```
MultiHead(Q, K, V) = Concat(head₁, ..., headₙ) × Wᴼ

headᵢ = Attention(Q×Wᵢᴼ, K×Wᵢᴷ, V×Wᵢᵛ)
```

한 헤드는 문법적 관계를, 다른 헤드는 의미적 관계를, 또 다른 헤드는 지시어 해소(대명사가 무엇을 가리키는지)를 포착하는 식으로 역할이 분화된다.

논문에서는 h = 8개 헤드, d_model = 512를 사용했다. 각 헤드의 차원은 512 / 8 = 64다.

## 위치 인코딩 (Positional Encoding)

RNN은 순서대로 처리하므로 위치 정보가 구조에 내재한다. 트랜스포머는 모든 위치를 동시에 처리하므로 위치 정보를 별도로 주입해야 한다.

논문은 사인/코사인 함수를 이용한 고정 위치 인코딩을 제안했다.

```
PE(pos, 2i)   = sin(pos / 10000^(2i/d_model))
PE(pos, 2i+1) = cos(pos / 10000^(2i/d_model))
```

pos는 문장 내 위치, i는 임베딩 차원 인덱스다. 각 차원이 서로 다른 주기의 사인/코사인 파형을 갖는다. 낮은 차원은 빠른 주기(세밀한 위치 구분), 높은 차원은 느린 주기(큰 단위 위치 구분)다.

이 방식의 장점은 학습 중에 보지 못한 더 긴 시퀀스에도 일반화된다는 것이다.

이후 BERT 등은 학습 가능한 위치 임베딩(learnable positional embedding)을 사용했다. RoPE(Rotary Position Embedding)와 ALiBi 같은 변형이 현재 LLM에서 더 많이 쓰인다.

## 트랜스포머 아키텍처

논문은 기계 번역 태스크를 위한 인코더-디코더 구조를 제안했다.

### 인코더

입력 시퀀스(예: 영어 문장)를 처리한다. N개(논문에서 6개)의 동일한 레이어로 구성된다.

각 레이어는 두 개의 서브레이어다.

1. **Multi-Head Self-Attention** — 입력 시퀀스 내 모든 위치 간의 관계를 계산
2. **Feed-Forward Network** — 각 위치별로 독립적인 2층 MLP

각 서브레이어는 잔차 연결(residual connection)과 레이어 정규화(layer normalization)를 거친다.

```
출력 = LayerNorm(x + SubLayer(x))
```

잔차 연결은 기울기 소실 문제를 완화하고 학습을 안정화한다.

### 디코더

출력 시퀀스(예: 한국어 번역)를 생성한다. 인코더와 다른 점이 두 가지다.

1. **Masked Self-Attention** — 생성 중인 위치 이후의 토큰을 보지 못하도록 마스킹. 미래 토큰을 참조해 "치팅"하는 것을 방지한다
2. **Cross-Attention** — Q는 디코더 상태, K와 V는 인코더 출력. 번역할 때 원문의 어떤 부분에 집중할지 학습한다

### Feed-Forward Network

각 위치별로 같은 FFN을 적용한다. 2층 선형 변환과 ReLU 활성화 함수다.

```
FFN(x) = max(0, xW₁ + b₁)W₂ + b₂
```

d_model = 512, 내부 차원 d_ff = 2048. 어텐션이 위치 간 관계를 포착하는 역할이라면, FFN은 각 위치에서 특징을 변환하는 역할이다.

## 왜 혁명적이었나

**병렬화**: 모든 위치를 동시에 처리하므로 GPU 활용도가 극적으로 높아졌다. 동일한 하드웨어로 훨씬 빠르게 학습할 수 있다.

**장거리 의존성**: 어떤 두 위치 사이의 거리와 관계없이 어텐션 한 번으로 직접 연결된다. RNN은 거리가 n이면 n번의 순환을 거쳐야 한다.

**확장성**: 모델 크기를 늘리면(파라미터, 레이어 수, 헤드 수) 성능이 예측 가능하게 향상된다. 이 스케일링 특성이 GPT, BERT, LLaMA 등 이후 모든 대형 모델의 기반이 됐다.

BERT는 트랜스포머 인코더만 사용해 양방향 언어 이해를 학습했고, GPT는 트랜스포머 디코더만 사용해 자기회귀 생성을 학습했다. 인코더-디코더 전체를 사용하는 T5, BART 등도 기계 번역과 요약에 쓰인다.

## 트레이드오프

Self-Attention의 연산량은 시퀀스 길이 n의 제곱에 비례한다(O(n²)). 모든 위치 쌍의 어텐션을 계산하기 때문이다. 문서 전체를 처리하거나 컨텍스트 길이가 수만 토큰에 달하면 연산량이 폭발한다. 이를 해결하기 위해 Sparse Attention, FlashAttention, Ring Attention, Sliding Window Attention 등 다양한 효율화 기법이 나왔다.

위치 인코딩 방식도 한계가 있다. 논문의 절대 위치 인코딩은 학습 시 본 최대 길이 이상의 시퀀스에서 성능이 떨어진다. 현재 LLM들은 RoPE에 YaRN, LongRoPE 등 외삽(extrapolation) 기법을 적용해 학습 시보다 긴 컨텍스트를 처리한다.
