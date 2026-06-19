---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "018. Kubernetes HPA — 트래픽에 따라 파드 수를 자동으로 조절하기"
date: 2026-06-12
tags: [kubernetes, k8s, hpa, horizontal-pod-autoscaler, autoscaling, metrics-server, prometheus, scale-out, scale-in]
summary: "HPA(Horizontal Pod Autoscaler)는 CPU·메모리 사용률이나 커스텀 메트릭을 보고 Deployment의 파드 수를 자동으로 늘리고 줄인다. 스케일 계산이 어떻게 이뤄지는지, 실무에서 자주 만나는 함정(requests 미설정, 스케일 다운 지연, 파드 준비 시간)이 무엇인지, 커스텀 메트릭으로 어떻게 확장하는지를 설명한다."
slug: "018-k8s-hpa"
categories: ["쿠버네티스"]
---

트래픽은 일정하지 않다. 평소에는 파드 3개로 충분하지만 점심 시간에는 10배가 몰릴 수 있다. 미리 10개를 띄워두면 낭비고, 3개만 두면 피크를 못 버틴다. HPA(Horizontal Pod Autoscaler)는 이 문제를 자동으로 푼다. 정의한 목표 수준(예: CPU 60%)을 넘으면 파드를 늘리고, 여유가 생기면 줄인다.

## HPA가 동작하려면

HPA는 메트릭을 보고 결정한다. 이 메트릭을 제공하는 `metrics-server`가 클러스터에 설치돼 있어야 한다. metrics-server는 각 노드의 kubelet에서 CPU·메모리 사용량을 주기적으로 긁어 집계한다.

파드에 `resources.requests`가 설정돼 있어야 한다. HPA의 CPU 사용률은 `limits` 대비가 아니라 **`requests` 대비**로 계산된다. requests가 없으면 HPA는 사용률을 계산할 수 없어 동작하지 않는다.

## 기본 구조

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: my-app-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: my-app
  minReplicas: 2        # 최소 파드 수 (0으로 설정 시 KEDA 필요)
  maxReplicas: 20       # 최대 파드 수
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60    # 평균 CPU 사용률 60% 목표
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 70
```

## 스케일 계산 원리

HPA는 주기적으로(기본 15초) 메트릭을 확인하고 다음 공식으로 필요한 파드 수를 계산한다.

```
필요한 파드 수 = ceil(현재 파드 수 × (현재 평균 사용률 / 목표 사용률))
```

예를 들어 현재 파드 3개, 평균 CPU 90%, 목표 60%라면:

```
ceil(3 × (90 / 60)) = ceil(4.5) = 5
```

5개로 스케일 아웃한다. 5개가 됐을 때 평균이 60%가 되면 안정 상태다.

여러 메트릭을 정의하면 각 메트릭에 대해 계산한 값 중 **가장 큰 값**을 쓴다. 어떤 메트릭 하나라도 목표를 넘으면 스케일 아웃이 일어난다.

## 스케일 아웃과 스케일 인의 비대칭

HPA는 스케일 아웃과 스케일 인의 속도가 다르게 설계돼 있다.

스케일 아웃은 빠르게 반응한다. 목표를 넘으면 즉시 파드를 늘린다.

스케일 인은 천천히 일어난다. 기본적으로 사용률이 낮아져도 **5분간 안정적인 상태가 유지돼야** 스케일 인을 시작한다. 트래픽이 잠깐 내려갔다가 다시 올라올 수 있는데, 그 사이에 파드를 너무 빨리 줄이면 다시 올라온 트래픽을 처리하지 못하기 때문이다.

이 동작은 `behavior`로 조정할 수 있다.

```yaml
spec:
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300   # 스케일 인 전 안정화 대기 (기본 300초)
      policies:
      - type: Percent
        value: 10                        # 한 번에 최대 10%씩 줄임
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0     # 스케일 아웃은 즉시 (기본 0초)
      policies:
      - type: Pods
        value: 4                         # 한 번에 최대 4개씩 늘림
        periodSeconds: 60
```

## 실무에서 자주 만나는 함정

**스케일 아웃 후 새 파드가 준비되는 시간**: 스케일 아웃이 결정됐다고 바로 트래픽을 받는 게 아니다. 이미지 풀 시간 + 앱 시작 시간 + Readiness probe 통과 시간이 필요하다. 이 시간 동안 기존 파드들이 과부하를 감당해야 한다. 이미지 풀을 빠르게 하려면 이미지를 노드에 미리 캐시하거나 이미지 크기를 줄이고, 앱 시작 시간을 최소화하는 것이 중요하다. 피크가 예측 가능하다면(점심 시간, 마케팅 이벤트) 미리 `minReplicas`를 올려두는 것도 방법이다.

**requests를 너무 낮게 잡는 실수**: requests를 낮게 잡으면 실제 CPU 사용량이 같아도 "사용률"이 더 높게 계산된다. `requests: 100m`인 파드가 실제로 150m을 쓰면 사용률이 150%다. 스케줄러는 100m만 예약했으므로 노드 자원은 충분해 보이지만 HPA는 계속 스케일 아웃을 시도한다. requests는 실제 평균 사용량을 반영해야 한다.

**maxReplicas 한계 설정**: maxReplicas를 너무 높게 잡으면 장애 상황에서 파드가 무한정 늘어나 노드가 과부하된다. 클러스터 용량을 고려해 현실적인 상한을 설정해야 한다. 반대로 너무 낮게 잡으면 진짜 피크 트래픽을 처리 못 한다.

## 커스텀 메트릭

CPU·메모리 외에 Prometheus 같은 모니터링 시스템에서 가져오는 지표로도 HPA를 구성할 수 있다. `custom.metrics.k8s.io` API를 통해 메트릭을 제공하는 **Prometheus Adapter**를 설치하면 된다.

```yaml
metrics:
- type: Pods
  pods:
    metric:
      name: http_requests_per_second    # Prometheus 메트릭 이름
    target:
      type: AverageValue
      averageValue: "100"               # 파드당 평균 100 RPS 목표
- type: External
  external:
    metric:
      name: sqs_queue_depth             # 외부 시스템 메트릭
      selector:
        matchLabels:
          queue: my-queue
    target:
      type: Value
      value: "500"                      # 큐 깊이 500 미만 유지
```

커스텀 메트릭이 CPU보다 유용한 경우가 많다. CPU 사용률이 낮아도 응답 시간이 느려지는 경우가 있고, 반대로 CPU가 높아도 파드가 더 필요하지 않은 경우도 있다. 실제 처리 부하를 더 직접적으로 나타내는 RPS, 큐 깊이, 응답 시간 같은 메트릭이 더 정확한 스케일링 신호가 되기도 한다.

## VPA — 파드 수 대신 파드 크기를 조절

HPA가 파드 수를 수평으로 늘린다면, VPA(Vertical Pod Autoscaler)는 파드의 CPU·메모리 requests/limits 값을 자동으로 조정한다. 파드를 재시작해야 값이 적용되므로 상태가 있는 애플리케이션이나 재시작 비용이 큰 경우에 유용하다. HPA와 VPA를 CPU 기준으로 동시에 쓰면 서로 충돌할 수 있어, 보통 하나를 선택해 쓴다.

## 트레이드오프

HPA는 반응적(reactive)이다. 트래픽이 이미 몰린 뒤에 반응한다. 새 파드가 준비되기까지 시간이 걸리므로, 트래픽 급증의 처음 수 분은 기존 파드들이 과부하를 버텨야 한다. 이를 완화하려면 `minReplicas`를 충분히 잡아두고, 이미지 시작 시간을 최소화하며, 파드 중단 예산(PodDisruptionBudget)으로 스케일 인 중 가용성을 보장하는 것이 필요하다.
