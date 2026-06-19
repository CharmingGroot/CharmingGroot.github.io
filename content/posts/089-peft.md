---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "089. PEFT — 파라미터 효율적 파인튜닝 프레임워크"
date: 2026-06-14
tags: [ai, peft, lora, adapter, prompt-tuning, huggingface, parameter-efficient, fine-tuning, ia3]
summary: "PEFT(Parameter-Efficient Fine-Tuning)는 Hugging Face가 관리하는 파인튜닝 기법 모음 라이브러리다. LoRA, Prefix Tuning, Prompt Tuning, Adapter, IA3 등의 기법을 통일된 API로 제공한다. 모델 가중치의 1% 미만 파라미터만 학습해 전체 파인튜닝에 가까운 성능을 낸다."
slug: "089-peft"
categories: ["AI · ML"]
---

파라미터 효율적 파인튜닝 기법들(LoRA, Prefix Tuning, Prompt Tuning 등)은 각자 별도 코드베이스로 구현됐다. 모델마다, 태스크마다 통합 방법이 달랐다.

Hugging Face의 PEFT 라이브러리는 이 기법들을 하나의 통일된 API로 제공한다. `transformers` 생태계와 자연스럽게 통합된다.

## 지원 기법

**LoRA (Low-Rank Adaptation)**: 어텐션 레이어의 가중치 업데이트를 저랭크 행렬로 근사한다. 가장 널리 쓰인다. 다음 글(090)에서 Quantization과 함께 QLoRA로 다룬다.

**Prefix Tuning**: 각 레이어의 Key/Value에 학습 가능한 접두사를 추가한다. 088에서 설명했다.

**Prompt Tuning**: 입력 임베딩에 소프트 프롬프트를 추가한다. 088에서 설명했다.

**Adapter**: 트랜스포머 레이어 사이에 작은 보틀넥 레이어를 삽입한다. 원본 가중치는 고정하고 Adapter만 학습한다. Prefix보다 레이어 수준에서 더 유연한 조정이 가능하다.

**IA3 (Infused Adapter by Inhibiting and Amplifying Inner Activations)**: 가중치를 변경하지 않고 학습된 스케일 벡터를 곱해 활성화를 조정한다. LoRA보다 더 적은 파라미터(~10배)로 비슷한 성능을 낸다.

## 통일된 API

```python
from peft import (
    get_peft_model,
    LoraConfig,
    PrefixTuningConfig,
    PromptTuningConfig,
    TaskType,
)
from transformers import AutoModelForSeq2SeqLM

model = AutoModelForSeq2SeqLM.from_pretrained("t5-base")

# LoRA 설정
lora_config = LoraConfig(
    task_type=TaskType.SEQ_2_SEQ_LM,
    r=8,                    # 랭크
    lora_alpha=32,          # 스케일링 계수
    target_modules=["q", "v"],  # 어텐션 Q, V에 적용
    lora_dropout=0.1,
)
peft_model = get_peft_model(model, lora_config)
peft_model.print_trainable_parameters()
# trainable params: 294,912 || all params: 247,577,856 || trainable%: 0.12%

# 학습 (일반 Trainer와 동일)
trainer = Trainer(model=peft_model, ...)
trainer.train()

# 저장 (어댑터 가중치만)
peft_model.save_pretrained("./lora-t5")
# 파일 크기: ~1MB (전체 모델 900MB 대비)
```

## 로드와 추론

```python
from peft import PeftModel

base_model = AutoModelForSeq2SeqLM.from_pretrained("t5-base")
model = PeftModel.from_pretrained(base_model, "./lora-t5")

# 여러 어댑터를 전환
model.load_adapter("./lora-translation", adapter_name="translation")
model.load_adapter("./lora-summary", adapter_name="summary")

model.set_adapter("translation")
output = model.generate(...)

model.set_adapter("summary")
output = model.generate(...)
```

같은 베이스 모델에 태스크별 어댑터를 교체하며 사용한다.

## 어댑터 병합

LoRA는 추론 시 별도 어댑터 레이어가 필요해 약간의 오버헤드가 있다. 병합하면 오버헤드가 사라진다.

```python
# LoRA 가중치를 베이스 모델에 병합
merged_model = peft_model.merge_and_unload()
# 이제 일반 모델과 동일, LoRA 오버헤드 없음
merged_model.save_pretrained("./merged-model")
```

병합 후에는 어댑터를 교체할 수 없다.

## 멀티 어댑터 조합

여러 LoRA를 가중 합산으로 동시에 적용할 수 있다.

```python
# LoRA A (코딩 스타일)와 LoRA B (한국어) 동시 적용
model.add_weighted_adapter(
    adapters=["coding", "korean"],
    weights=[0.7, 0.3],
    adapter_name="combined"
)
```

LoRA 가중치를 선형 결합하는 방식이다. 두 특성을 동시에 부여하거나 강도를 조절할 수 있다.

## 트레이드오프

PEFT는 전체 파인튜닝보다 표현력이 제한된다. 태스크가 베이스 모델의 능력 범위 안에 있다면 PEFT로 충분하지만, 베이스 모델이 전혀 다루지 않은 도메인이나 완전히 새로운 형식의 출력이 필요하면 전체 파인튜닝이 필요할 수 있다.

또한 어댑터 개수가 늘어나면 관리가 복잡해진다. 베이스 모델 버전과 어댑터 버전의 호환성을 추적해야 한다. Hugging Face Hub에 어댑터를 공개하면 커뮤니티와 공유할 수 있어 이 문제를 일부 완화한다.
