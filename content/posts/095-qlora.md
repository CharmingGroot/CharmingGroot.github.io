---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "095. QLoRA — 소비자 GPU에서 65B 모델 파인튜닝"
date: 2026-06-14
tags: [ai, qlora, quantization, lora, fine-tuning, peft, nf4, 4bit, consumer-gpu, memory-efficient]
summary: "QLoRA(2023)는 4비트 양자화된 기반 모델에 LoRA를 적용해 65B 모델을 단일 48GB GPU에서 파인튜닝하는 방법이다. NF4(Normal Float 4) 양자화, 이중 양자화, 페이지드 옵티마이저 세 가지 기술을 결합해 메모리를 획기적으로 줄인다."
slug: "095-qlora"
categories: ["AI · ML"]
---

LoRA(089)는 가중치를 고정하고 저차원 행렬만 학습해 파인튜닝 비용을 낮췄다. 그러나 기반 모델 가중치는 FP16으로 메모리에 올려야 한다. LLaMA-65B는 130GB VRAM이 필요하다. LoRA를 써도 옵티마이저 상태와 활성화 메모리가 추가된다.

UW의 Dettmers 등이 2023년 발표한 QLoRA는 한 단계 더 나아갔다. 기반 모델을 4비트로 양자화한 상태에서 LoRA를 적용한다.

## 세 가지 핵심 기술

### NF4 (Normal Float 4)

LLM 가중치는 정규 분포(가우시안 분포)를 따른다. 대부분의 값이 0 근처에 밀집하고 극단값이 드물다.

기존 INT4는 -8~7의 균등 간격으로 표현한다. 가중치가 많이 몰려 있는 0 근처는 정밀도가 낮고 실제로 거의 없는 극단값에 비트를 낭비한다.

NF4는 정규 분포에 맞춰 양자화 경계를 설계한다. 0 근처는 경계를 촘촘하게, 극단 쪽은 듬성듬성하게 배치해 동일한 4비트로 더 많은 정보를 보존한다.

```
INT4: -8, -7, -6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7 (균등)
NF4:  -1.0, -0.69, -0.49, -0.33, -0.18, -0.06, 0.06, 0.18, ...  (정규 분포 분위수 기반)
```

### 이중 양자화 (Double Quantization)

NF4로 가중치를 양자화하려면 각 블록마다 스케일 상수가 필요하다. 이 스케일 상수 자체도 메모리를 차지한다.

이중 양자화는 스케일 상수를 다시 양자화한다. FP32 스케일 상수를 FP8로 줄여 추가로 메모리를 절약한다. 효과는 파라미터당 약 0.37비트 절약으로 작지만 대형 모델에서는 수 GB가 된다.

### 페이지드 옵티마이저 (Paged Optimizer)

GPU 메모리가 부족한 순간이 있다. 긴 시퀀스를 처리하는 배치는 순간적으로 메모리를 많이 사용한다. 이때 일반적으로 OOM(Out-of-Memory) 오류가 발생한다.

페이지드 옵티마이저는 NVIDIA의 통합 메모리를 활용한다. 옵티마이저 상태(Adam의 모멘텀, 분산 추정값)를 CPU RAM에도 저장해 GPU 메모리가 부족할 때 자동으로 CPU로 페이지 아웃한다. 메모리 spike를 흡수해 OOM 없이 학습을 안정화한다.

## 결합하면

```
기반 모델 가중치: FP16 → NF4 (4× 감소)
스케일 상수: FP32 → FP8 (이중 양자화)
옵티마이저 상태: GPU 부족 시 CPU로 페이지 아웃

+ LoRA: NF4 가중치를 고정하고 저차원 행렬만 FP16으로 학습
```

LLaMA-65B(FP16: 130GB) → QLoRA(NF4 + LoRA: ~48GB). 단일 A40 또는 A6000에서 학습 가능하다.

## 코드

```python
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
import torch

# 4비트 양자화 설정
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,   # 이중 양자화
    bnb_4bit_quant_type="nf4",        # NF4 사용
    bnb_4bit_compute_dtype=torch.bfloat16  # 계산은 BF16
)

model = AutoModelForCausalLM.from_pretrained(
    "meta-llama/Llama-2-13b-hf",
    quantization_config=bnb_config,
    device_map="auto",
)

# 양자화 모델에 LoRA 적용 준비
model = prepare_model_for_kbit_training(model)

lora_config = LoraConfig(
    r=16,
    lora_alpha=32,
    target_modules=["q_proj", "v_proj"],
    lora_dropout=0.05,
    task_type="CAUSAL_LM",
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()
# trainable params: 6,553,600 || all params: 6,744,444,928 || trainable%: 0.0972
```

## Guanaco 모델

QLoRA 논문은 LLaMA를 OASST1(오픈소스 인간 피드백 데이터)으로 파인튜닝한 Guanaco 시리즈를 공개했다. 65B Guanaco는 ChatGPT와 비교했을 때 사람 평가자의 30% 이상이 동등하거나 더 낫다고 평가했다.

단일 48GB GPU에서 24시간 이내에 학습한 결과다. 이것이 QLoRA가 주목받은 이유다.

## trl 라이브러리

Hugging Face의 TRL(Transformer Reinforcement Learning)은 QLoRA 파인튜닝을 더 간단하게 만드는 `SFTTrainer`를 제공한다.

```python
from trl import SFTTrainer
from transformers import TrainingArguments

training_args = TrainingArguments(
    output_dir="./output",
    num_train_epochs=3,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    learning_rate=2e-4,
    fp16=True,
    optim="paged_adamw_32bit",  # 페이지드 옵티마이저
)

trainer = SFTTrainer(
    model=model,
    train_dataset=dataset,
    peft_config=lora_config,
    dataset_text_field="text",
    max_seq_length=2048,
    args=training_args,
)
trainer.train()
```

## GPTQ와의 차이

GPTQ(090)는 추론 최적화다. 이미 학습된 모델을 압축한다. QLoRA는 학습 최적화다. 4비트 상태에서 새 지식을 주입한다.

학습이 끝나면 LoRA 가중치를 기반 모델에 병합할 수 있다. 병합된 모델을 다시 GPTQ나 GGUF로 압축하면 배포도 효율적이다.

## 트레이드오프

4비트 양자화 상태에서 학습하면 full fine-tuning이나 LoRA(FP16 기반)보다 성능이 약간 낮을 수 있다. 특히 오랜 지시 학습이나 수학 추론처럼 세밀한 지식 주입이 필요한 경우다. 그러나 리소스 제약이 있는 환경에서 받아들일 수 있는 트레이드오프다.

학습 속도도 느리다. 양자화/역양자화 과정이 계산 오버헤드를 만든다. FP16 LoRA보다 20-30% 느린 것이 일반적이다.

실용적으로는 가장 폭넓게 쓰이는 파인튜닝 방법이다. 7B~13B 모델 기준 소비자 GPU(RTX 3090, 4090 24GB)에서도 QLoRA 파인튜닝이 가능하다.
