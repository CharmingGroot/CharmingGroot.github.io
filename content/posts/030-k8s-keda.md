---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "030. KEDA — 이벤트 드리븐 오토스케일러"
date: 2026-06-12
tags: [kubernetes, k8s, keda, autoscaling, hpa, event-driven, kafka, sqs, redis, scaledobject, scaledJob]
summary: "HPA는 CPU와 메모리 사용률을 기준으로 파드를 스케일한다. 하지만 Kafka 큐에 메시지가 쌓이거나 SQS 대기열이 늘어나는 경우처럼 외부 이벤트 소스를 기준으로 스케일하고 싶을 때 HPA만으로는 한계가 있다. KEDA는 70개 이상의 외부 스케일러를 지원하는 이벤트 드리븐 오토스케일러로, 0개에서 N개까지 스케일하는 것도 지원한다."
slug: "030-k8s-keda"
categories: ["쿠버네티스"]
---

HPA는 CPU 또는 메모리 사용률을 보고 파드 수를 조절한다. 이 방식이 대부분의 HTTP 서버에는 잘 맞지만, 메시지 처리 서비스에는 잘 맞지 않는다. Kafka 토픽에 메시지가 100만 개 쌓여 있어도 아무 파드도 처리를 시작하기 전이라면 CPU 사용률은 0%다. HPA는 아무것도 스케일하지 않는다.

**KEDA(Kubernetes Event-Driven Autoscaling)** 는 이 문제를 위해 만들어진 오토스케일러다. Kafka 컨슈머 랙, SQS 대기열 길이, Redis 큐 크기, Prometheus 메트릭 등 외부 이벤트 소스를 직접 보고 스케일한다. 70개 이상의 내장 스케일러를 제공하고, 파드를 **0개에서 N개**로 스케일하는 것도 지원한다.

## 구조

KEDA는 k8s에 CRD로 설치한다. 두 가지 핵심 컴포넌트로 동작한다.

**KEDA Operator**: ScaledObject와 ScaledJob을 감시하고, 조건에 따라 HPA를 생성·수정한다. KEDA는 HPA를 대체하는 게 아니라 HPA 위에서 동작한다. 외부 메트릭을 k8s External Metrics API로 노출하고, HPA가 그 값을 읽어 파드 수를 결정한다.

**Metrics Adapter**: 외부 소스에서 메트릭을 가져와 k8s Metrics API로 변환한다.

## ScaledObject — Deployment 스케일

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: kafka-consumer-scaler
  namespace: production
spec:
  scaleTargetRef:
    name: order-processor           # 스케일할 Deployment 이름
  minReplicaCount: 0                # 0으로 스케일 다운 허용
  maxReplicaCount: 50
  pollingInterval: 15               # 외부 소스 폴링 간격 (초)
  cooldownPeriod: 60                # 0으로 스케일 다운 전 대기 시간 (초)
  triggers:
  - type: kafka
    metadata:
      bootstrapServers: kafka:9092
      consumerGroup: order-processor-group
      topic: orders
      lagThreshold: "100"           # 컨슈머 랙이 파드당 100 이상이면 스케일 업
      offsetResetPolicy: latest
```

`lagThreshold: "100"`은 "파드 하나당 처리해야 할 메시지 100개"를 기준으로 삼는다는 의미다. 랙이 1000이면 파드 10개, 5000이면 50개(maxReplicaCount 제한)로 스케일한다.

`minReplicaCount: 0`을 설정하면 큐가 비어있을 때 파드를 0개로 줄인다. 비용을 극단적으로 절감할 수 있지만, 다음 메시지가 올 때 파드가 0에서 올라오는 **콜드 스타트** 지연이 생긴다. 실시간성이 중요하지 않은 배치 작업에 적합하다.

## 다양한 트리거 예시

### AWS SQS

```yaml
triggers:
- type: aws-sqs-queue
  metadata:
    queueURL: https://sqs.ap-northeast-2.amazonaws.com/123456/my-queue
    queueLength: "10"             # 파드당 메시지 10개 기준
    awsRegion: ap-northeast-2
  authenticationRef:
    name: keda-aws-credentials    # TriggerAuthentication으로 자격증명 관리
```

### Redis 리스트

```yaml
triggers:
- type: redis
  metadata:
    address: redis:6379
    listName: job-queue
    listLength: "20"              # 파드당 아이템 20개 기준
  authenticationRef:
    name: keda-redis-credentials
```

### Prometheus 메트릭

```yaml
triggers:
- type: prometheus
  metadata:
    serverAddress: http://prometheus:9090
    metricName: http_requests_pending
    query: sum(http_requests_pending{service="api"})
    threshold: "100"              # 대기 요청이 파드당 100 이상이면 스케일 업
```

Prometheus 스케일러를 쓰면 HPA의 Custom Metrics Adapter 없이도 Prometheus 메트릭으로 스케일할 수 있다.

## TriggerAuthentication — 자격증명 분리

외부 소스(AWS, Redis, Kafka 등)에 접근할 자격증명은 트리거에 직접 넣지 않고 `TriggerAuthentication` 오브젝트로 분리한다.

```yaml
apiVersion: keda.sh/v1alpha1
kind: TriggerAuthentication
metadata:
  name: keda-aws-credentials
  namespace: production
spec:
  secretTargetRef:
  - parameter: awsAccessKeyID
    name: aws-secret
    key: access-key-id
  - parameter: awsSecretAccessKey
    name: aws-secret
    key: secret-access-key
```

`ClusterTriggerAuthentication`을 쓰면 클러스터 전체에서 자격증명을 공유할 수 있다. AWS IRSA(IAM Roles for Service Accounts)와 함께 쓰면 자격증명 없이 IAM 역할로 인증할 수도 있다.

## ScaledJob — Job 스케일

Deployment가 아닌 Job을 이벤트에 따라 생성하고 싶을 때 `ScaledJob`을 쓴다. 큐의 각 아이템을 별도 Job 파드가 처리하는 패턴이다.

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledJob
metadata:
  name: image-processing-job
spec:
  jobTargetRef:
    template:
      spec:
        restartPolicy: Never
        containers:
        - name: processor
          image: image-processor:1.0.0
  maxReplicaCount: 20
  triggers:
  - type: redis
    metadata:
      address: redis:6379
      listName: image-jobs
      listLength: "1"             # 아이템 하나당 Job 하나
```

큐에 아이템이 15개 있으면 Job 파드 15개가 생겨 동시에 처리한다. 각 파드가 하나씩 가져가 처리하고 종료된다. `ScaledObject`(Deployment)는 파드들이 계속 살아 큐에서 메시지를 소비하는 반면, `ScaledJob`은 각 아이템을 독립적인 Job으로 처리한다.

## KEDA vs HPA

| | HPA | KEDA |
|---|---|---|
| 스케일 기준 | CPU, 메모리, Custom Metrics | 외부 이벤트 소스 (Kafka, SQS, Redis 등) |
| 0으로 스케일 다운 | 불가 (최소 1개) | 가능 |
| 외부 스케일러 수 | 별도 Adapter 필요 | 70개+ 내장 |
| 설치 | 기본 내장 | CRD 추가 설치 |
| HPA와의 관계 | — | 내부적으로 HPA를 생성 |

KEDA가 설치되면 기존 HPA와 공존한다. 같은 Deployment에 HPA와 ScaledObject를 동시에 쓰면 충돌하므로, 하나만 써야 한다.

## 트레이드오프

`minReplicaCount: 0`으로 파드를 완전히 내리면 첫 메시지 처리까지 파드가 올라오는 시간이 걸린다. 이미지 크기가 크면 풀 시간도 더해진다. 실시간 응답이 필요한 서비스에서는 `minReplicaCount: 1` 이상을 유지하는 것이 낫다.

KEDA는 외부 소스를 `pollingInterval`마다 폴링한다. Kafka 랙 같은 값이 폴링 간격 안에 급격히 변하면 스케일 결정이 늦을 수 있다. 폴링 간격을 줄이면 반응이 빨라지지만 외부 소스에 부하가 늘어난다.

여러 스케일러를 같은 ScaledObject에 설정하면 OR 조건으로 동작한다. 어느 하나라도 임계값을 넘으면 스케일 업된다.
