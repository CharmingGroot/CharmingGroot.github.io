---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "068. AlexNet → ResNet — CNN과 딥러닝 르네상스"
date: 2026-06-14
tags: [ai, deep-learning, cnn, alexnet, vgg, resnet, computer-vision, convolution, residual-connection]
summary: "2012년 AlexNet이 ImageNet 대회에서 압도적인 성능을 보이며 딥러닝 시대를 열었다. 이후 VGGNet, GoogLeNet, ResNet으로 이어지는 CNN 발전사를 다룬다. 각 모델이 해결하려 했던 문제와 핵심 기여를 중심으로 설명한다."
slug: "068-cnn-alexnet-resnet"
categories: ["AI · ML"]
---

2012년 이전 컴퓨터 비전은 사람이 설계한 특징(feature)을 사용했다. SIFT, HOG 같은 알고리즘이 픽셀에서 엣지, 방향, 텍스처를 추출하고, SVM 같은 분류기가 그 특징으로 판단했다. ImageNet 같은 대규모 분류 대회에서 오류율은 25% 수준에서 수년째 답보 상태였다.

2012년 AlexNet이 오류율을 15.3%로 낮추며 2위(26.2%)를 압도했다. 단순히 1등이 아니라 격차가 기존 기술의 한계를 넘어선 것이었다.

## CNN의 기본 원리

합성곱 신경망(Convolutional Neural Network, CNN)은 이미지의 공간적 구조를 활용한다.

**합성곱 레이어 (Convolutional Layer)**

작은 필터(커널)를 이미지 전체에 슬라이딩하며 적용한다. 3×3 필터는 입력의 3×3 영역을 보고 하나의 값을 출력한다. 같은 필터를 이미지 전체에 적용하므로 위치와 무관하게 같은 패턴을 인식한다(평행 이동 불변성, translation invariance).

```
입력 이미지 (32×32×3)
    ↓ 합성곱 (3×3 필터 × 64개)
특징 맵 (30×30×64)
    ↓ ReLU 활성화
    ↓ Max Pooling (2×2)
특징 맵 (15×15×64)
```

얕은 레이어는 엣지와 색상 같은 저수준 특징을 학습하고, 깊은 레이어로 갈수록 눈, 코, 바퀴 같은 고수준 패턴을 학습한다.

**풀링 레이어 (Pooling Layer)**

특징 맵의 크기를 줄여 파라미터 수와 연산량을 줄인다. Max Pooling은 영역 내 최댓값을 취해 가장 두드러진 특징을 유지한다.

## AlexNet (2012)

Alex Krizhevsky, Ilya Sutskever, Geoffrey Hinton이 발표했다. 8개 레이어(5개 합성곱 + 3개 완전 연결)로 구성됐다.

**세 가지 핵심 기여**

**ReLU 활성화 함수**: 기존 sigmoid와 tanh는 입력이 크거나 작으면 기울기가 0에 가까워지는 기울기 소실(vanishing gradient) 문제가 있었다. ReLU(Rectified Linear Unit)는 양수 구간에서 기울기가 항상 1이라 학습이 훨씬 빠르다.

```
sigmoid: f(x) = 1 / (1 + e^(-x))  → 기울기 최대 0.25
ReLU:    f(x) = max(0, x)          → 양수 구간 기울기 = 1
```

**드롭아웃 (Dropout)**: 학습 시 랜덤하게 50%의 뉴런을 비활성화한다. 특정 뉴런에 의존하지 않도록 강제해 과적합을 방지한다. 추론 시에는 모든 뉴런을 사용하고 출력에 0.5를 곱한다.

**GPU 병렬 학습**: 두 개의 GTX 580 GPU를 사용해 모델을 나눠 학습했다. 당시로서는 대규모였던 6,000만 파라미터를 현실적인 시간 안에 학습할 수 있었다.

## VGGNet (2014)

Oxford의 Simonyan과 Zisserman이 발표했다. AlexNet의 11×11, 5×5 큰 필터 대신 **3×3 필터만 사용**한다는 단순한 원칙을 따른다.

3×3 필터 두 개를 쌓으면 5×5 필터와 같은 수용 영역(receptive field)을 갖지만 파라미터 수는 더 적다. 3×3 세 개를 쌓으면 7×7과 동일한 수용 영역에 파라미터는 3×(3×3) = 27 vs 7×7 = 49로 절반이다.

네트워크를 16~19개 레이어로 깊게 만들어 성능을 높였다. 구조가 단순하고 이해하기 쉬워 이후 연구의 기준선으로 오래 사용됐다.

단점은 1억 3,800만 개 파라미터로 메모리 사용량이 많다는 것이다.

## GoogLeNet / Inception (2014)

Google이 발표했다. VGGNet과 같은 해에 ImageNet에서 더 좋은 성능을 냈지만 파라미터는 1/12 수준(500만 개)이었다.

핵심 아이디어는 **Inception 모듈**이다. 1×1, 3×3, 5×5 합성곱을 병렬로 적용해 다양한 스케일의 특징을 동시에 포착한다.

```
입력
├→ 1×1 conv
├→ 1×1 conv → 3×3 conv
├→ 1×1 conv → 5×5 conv
└→ 3×3 max pool → 1×1 conv
         ↓
      Concat
```

1×1 합성곱은 채널 수를 줄이는 역할(bottleneck)을 한다. 3×3이나 5×5 합성곱 전에 채널을 먼저 줄여 연산량을 크게 절약한다.

## ResNet (2015)

Microsoft Research의 He 등이 발표했다. 152개 레이어로 당시 인간 수준(5%)을 넘어선 3.57% 오류율을 달성했다.

**문제: 깊을수록 오히려 나빠진다**

네트워크를 단순히 더 깊게 쌓으면 성능이 오히려 떨어진다. 기울기 소실 문제뿐 아니라 **최적화 문제**도 있었다. 20층 네트워크보다 56층 네트워크의 학습 오류가 더 높게 나타났다.

**해결: 잔차 연결 (Residual Connection)**

레이어가 입력을 그대로 출력에 더하는 지름길(shortcut)을 추가한다.

```
일반 레이어:   H(x) = F(x)
잔차 레이어:   H(x) = F(x) + x
```

레이어가 학습해야 하는 것이 `H(x)`에서 `F(x) = H(x) - x`로 바뀐다. 즉 입력 대비 얼마나 **변화**해야 하는지(잔차, residual)만 학습하면 된다. 아무것도 학습하지 않아도 F(x) = 0이면 입력이 그대로 통과한다.

```python
# ResNet 블록 개념
class ResidualBlock(nn.Module):
    def forward(self, x):
        residual = x
        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)
        out = self.conv2(out)
        out = self.bn2(out)
        out += residual  # 잔차 연결
        out = self.relu(out)
        return out
```

기울기가 역전파될 때 잔차 연결을 통해 직접 흐를 수 있어 깊은 네트워크에서도 초기 레이어까지 기울기가 전달된다.

잔차 연결은 이후 트랜스포머의 Add & Norm 레이어에도 그대로 사용됐다. "Attention Is All You Need"에서 각 서브레이어 후에 `LayerNorm(x + SubLayer(x))`를 쓰는 것이 같은 개념이다.

## 발전 흐름 요약

| 모델 | 연도 | 레이어 | 핵심 기여 | ImageNet 오류율 |
|---|---|---|---|---|
| 기존 방식 | ~2011 | — | 수작업 특징 | ~26% |
| AlexNet | 2012 | 8 | ReLU, Dropout, GPU | 15.3% |
| VGGNet | 2014 | 16~19 | 3×3 필터만, 깊게 | 7.3% |
| GoogLeNet | 2014 | 22 | Inception 모듈, 1×1 병목 | 6.7% |
| ResNet | 2015 | 152 | 잔차 연결 | 3.6% |

## 이후 영향

ResNet의 잔차 연결은 현대 딥러닝의 표준 구성 요소가 됐다. EfficientNet(2019)은 네트워크의 깊이, 너비, 해상도를 균형있게 스케일링하는 방법을 제안해 더 적은 파라미터로 더 높은 성능을 냈다.

CNN은 2020년 ViT(Vision Transformer)가 등장하기 전까지 컴퓨터 비전의 주류였다. 현재도 모바일 환경이나 실시간 처리가 필요한 태스크에서는 CNN 계열이 더 효율적인 경우가 많다.

## 트레이드오프

깊을수록 일반적으로 성능이 좋지만 추론 속도가 느려진다. ResNet-50과 ResNet-152의 정확도 차이는 1~2% 수준이지만 추론 시간은 3배 차이 난다. 엣지 디바이스나 실시간 애플리케이션에서는 MobileNet, ShuffleNet 같은 경량화 모델을 선택한다.

합성곱 연산은 공간 구조를 가정한다. 이미지에서는 강력하지만 순서 관계나 그래프 구조에는 적합하지 않다. 이 한계가 이후 ViT가 등장한 배경이기도 하다.
