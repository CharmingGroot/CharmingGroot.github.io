---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "069. YOLO 계보 — 실시간 객체 탐지의 발전"
date: 2026-06-14
tags: [ai, yolo, object-detection, computer-vision, real-time, bounding-box, anchor, fpn, ultralytics]
summary: "YOLO(You Only Look Once)는 2015년 Joseph Redmon이 제안한 단일 패스 객체 탐지 모델이다. 이미지를 한 번만 보고 모든 객체의 위치와 클래스를 동시에 예측한다. 이전 방식 대비 수십 배 빠른 추론 속도로 실시간 탐지를 가능하게 했다. v1부터 현재 v11까지의 발전 흐름을 다룬다."
slug: "069-yolo"
categories: ["AI · ML"]
---

객체 탐지(Object Detection)는 이미지에서 물체의 위치(bounding box)와 종류(class)를 동시에 찾는 태스크다. 분류(Classification)가 "이 이미지는 고양이다"라면, 탐지는 "이 이미지의 이 위치에 고양이가 있고, 저 위치에 개가 있다"다.

## YOLO 이전: 2단계 탐지기

YOLO 이전의 주류는 R-CNN 계열이었다. 두 단계로 나뉜다.

1. **Region Proposal**: 객체가 있을 것 같은 후보 영역을 수백~수천 개 추출한다
2. **Classification**: 각 후보 영역을 CNN에 통과시켜 분류한다

Faster R-CNN은 당시 최고 성능이었지만 초당 7프레임(fps) 수준이었다. 실시간 처리(30fps 이상)에는 쓸 수 없었다.

## YOLO v1 (2015)

Joseph Redmon, Santosh Divvala, Ross Girshick, Ali Farhadi가 발표했다. 제목 그대로 "한 번만 본다(You Only Look Once)".

**핵심 아이디어: 그리드 기반 단일 패스**

이미지를 S×S 그리드로 나눈다(v1에서 S=7). 각 그리드 셀이 자신의 영역에 있는 객체를 책임진다.

각 셀은 B개의 바운딩 박스(bounding box)를 예측한다. 각 바운딩 박스는 5개 값을 출력한다.

```
(x, y, w, h, confidence)

x, y:        그리드 셀 내 박스 중심 좌표 (0~1 상대값)
w, h:        전체 이미지 대비 박스 너비/높이
confidence:  박스에 객체가 있을 확률 × IoU
```

각 셀은 C개 클래스 확률도 출력한다. 최종 출력 텐서는 S×S×(B×5 + C)다. 7×7×(2×5 + 20) = 7×7×30.

이 전체 예측이 CNN 한 번의 포워드 패스로 나온다. Faster R-CNN이 후보 영역마다 CNN을 실행하는 것과 근본적으로 다르다.

**IoU (Intersection over Union)**

예측 박스와 정답 박스가 얼마나 겹치는지 측정하는 지표다.

```
IoU = 교집합 넓이 / 합집합 넓이
```

IoU = 1이면 완벽하게 일치, 0이면 전혀 겹치지 않는다. 일반적으로 IoU > 0.5이면 올바른 탐지로 본다.

**NMS (Non-Maximum Suppression)**

같은 객체에 여러 박스가 겹쳐 예측될 때 가장 신뢰도 높은 것만 남기는 후처리다.

```
1. 신뢰도 순으로 정렬
2. 가장 높은 박스 선택
3. 선택된 박스와 IoU > 임계값인 박스 제거
4. 남은 박스 중 다음 최고 신뢰도 선택
5. 반복
```

**성능**: 45fps, mAP(mean Average Precision) 63.4%. Faster R-CNN(mAP 73.2%, 7fps)과 비교하면 속도는 압도적이고 정확도는 낮았다. 작은 객체 탐지가 약했다.

## YOLO v2 / YOLO9000 (2016)

**Anchor Box 도입**: v1은 박스 크기를 처음부터 예측했다. v2는 사전에 정의한 앵커 박스(anchor box) 크기를 기준으로 오프셋만 예측한다. 학습 데이터에서 k-means 클러스터링으로 자주 등장하는 박스 크기를 앵커로 설정한다.

```
앵커 박스 예시 (COCO 데이터셋):
- 가로로 긴 형태 (자동차, 버스)
- 세로로 긴 형태 (사람, 기둥)
- 정사각형에 가까운 형태 (얼굴, 공)
```

**Batch Normalization**: 각 레이어 출력을 정규화해 학습을 안정화하고 드롭아웃 없이도 과적합을 방지한다.

**YOLO9000**: ImageNet의 9,000개 클래스와 COCO 탐지 데이터를 동시에 학습해 탐지 데이터가 없는 클래스도 탐지할 수 있었다. WordNet 계층 구조로 클래스 간 관계를 활용했다.

## YOLO v3 (2018)

**다중 스케일 예측 (Multi-Scale Prediction)**: 세 가지 해상도에서 동시에 예측한다. 큰 해상도는 작은 객체를, 작은 해상도는 큰 객체를 잘 탐지한다.

```
13×13  — 큰 객체 (3개 앵커)
26×26  — 중간 객체 (3개 앵커)
52×52  — 작은 객체 (3개 앵커)
```

이 구조를 FPN(Feature Pyramid Network)이라고 한다. 깊은 레이어의 의미론적 특징과 얕은 레이어의 세밀한 공간 정보를 결합한다.

**Darknet-53 백본**: ResNet의 잔차 연결을 적용한 53개 레이어 CNN을 백본으로 사용한다.

**소프트맥스 대신 시그모이드**: 클래스 예측에 소프트맥스(합이 1) 대신 시그모이드(각 클래스 독립)를 사용해 멀티레이블 탐지가 가능해졌다. 한 객체가 "사람"이면서 "운동선수"일 수 있다.

mAP 33.0% (COCO), 51ms. Faster R-CNN과 비슷한 정확도에 3배 빠른 속도였다.

## YOLO v4 (2020)

Redmon이 군사 응용과 개인정보 침해 우려를 이유로 연구를 중단한 후, Alexey Bochkovskiy 등이 발표했다.

다양한 기법을 체계적으로 실험해 최적 조합을 찾는 접근이었다. "Bag of Freebies"(학습 시간만 늘리는 기법)와 "Bag of Specials"(추론 비용을 조금 늘리되 성능을 크게 높이는 기법)로 나눠 분류했다.

**주요 기법**

- **Mosaic Augmentation**: 4개 이미지를 하나로 합쳐 배경 다양성을 높이고 배치 사이즈를 줄여도 다양한 컨텍스트를 학습
- **CIoU Loss**: 단순 IoU 손실 대신 박스 중심 거리, 가로세로 비율까지 고려한 손실 함수
- **CSPNet 백본**: 기울기 흐름을 개선해 학습 효율을 높인 연결 구조

## YOLO v5 ~ v11

v4 이후 공식 계보가 없어지며 여러 팀이 독립적으로 발전시켰다.

**YOLOv5 (Ultralytics, 2020)**: 공식 논문 없이 GitHub 코드로만 발표됐다. PyTorch 기반, 사용하기 쉬운 API, 빠른 학습으로 폭발적인 인기를 얻었다. "공식" YOLO가 아니라는 논란이 있었지만 사실상 업계 표준이 됐다.

**YOLOv8 (Ultralytics, 2023)**: 앵커 프리(anchor-free) 방식을 도입했다. 앵커 박스를 사전 정의할 필요 없이 박스 중심점과 크기를 직접 예측한다. 탐지뿐 아니라 세그멘테이션, 포즈 추정, 분류를 모두 지원하는 통합 프레임워크가 됐다.

**YOLOv10 (Tsinghua, 2024)**: NMS를 제거한 End-to-End 탐지. 기존 YOLO는 NMS라는 후처리가 필수였는데, 이중 할당(dual assignment) 학습으로 NMS 없이도 중복 박스를 제거한다. 추론 지연이 줄어든다.

## 실용적인 사용

```python
from ultralytics import YOLO

model = YOLO('yolov8n.pt')  # n=nano, s=small, m=medium, l=large, x=xlarge
results = model('image.jpg')

for result in results:
    boxes = result.boxes      # 바운딩 박스
    masks = result.masks      # 세그멘테이션 마스크 (세그 모델일 때)
    keypoints = result.keypoints  # 포즈 키포인트 (포즈 모델일 때)
    result.show()             # 시각화
    result.save('output.jpg')
```

모델 크기별 트레이드오프:

| 모델 | 파라미터 | mAP | 추론(ms) |
|---|---|---|---|
| YOLOv8n | 3.2M | 37.3 | 0.8 |
| YOLOv8s | 11.2M | 44.9 | 1.1 |
| YOLOv8m | 25.9M | 50.2 | 1.8 |
| YOLOv8l | 43.7M | 52.9 | 2.3 |
| YOLOv8x | 68.2M | 53.9 | 3.5 |

## 트레이드오프

YOLO 계열은 속도를 위해 정확도를 일부 포기한다. 특히 **작고 밀집된 객체** 탐지가 약하다. 군중 속 사람 수 세기, 드론 영상의 작은 객체 탐지 같은 태스크에서는 2단계 탐지기나 전용 모델이 더 적합하다.

앵커 기반 모델은 데이터셋에 맞는 앵커 크기를 튜닝해야 한다. COCO로 학습된 앵커가 의료 영상이나 위성 영상에서는 맞지 않아 재학습이 필요하다. 앵커 프리 모델(v10 이후)이 이 문제를 일부 완화한다.
